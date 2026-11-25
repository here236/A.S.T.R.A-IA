import argparse
import os
import time
from dataclasses import dataclass

from configs import configuracoes_voz
from . import comandos_voz
from .ativacao_voz import DetectorAtivacao, PALAVRAS_ATIVACAO
from .comandos_voz import StatusComando
from .processador_linguagem import RESPOSTA_PADRAO, responder_conversa, processador_conversa
from .utilitarios_voz import log, normalizar_texto
from .intencao_voz import esclarecer_intencao, ia_habilitada
from .roteamento_comandos import avaliar_rota
from ia.escopo_ferramentas import ferramentas_do_pedido, sequencia_explicita
from ia.plano_composto import plano_criacao_explicito, pedido_escrita_dependente
from .plano_pendente import PlanoPendente

'''
    Cérebro do sistema de voz

    Responsabilidade:
    Controlar todo o fluxo da conversa
    Integrar os módulos

    Fluxo:

        microfone → reconhecedor_fala → texto
            ↓
        há uma ação crítica esperando "sim/não"?
            sim → a fala é a resposta (RN03), sem precisar de "Ok Astra"
            não ↓
        ativacao_voz: ouviu "Ok Astra"?  (ou a assistente ainda está
        ativa, depois de um chamado sozinho)
            não → ignora (não era com ela)
            sim ↓
        comandos_voz → executa a ação
            não reconheceu → processador_linguagem (conversa)
            ↓
        sintetizador_voz → fala a resposta

    Enquanto a assistente fala, o microfone fica desligado (senão ela
    transcreveria a própria voz). Por isso a fala é sequencial.

    Para usar:
        python -m voz.voz_principal                (microfone e voz)
        python -m voz.voz_principal --teclado      (digita em vez de falar)
        python -m voz.voz_principal --sem-voz      (respostas só no texto)
'''


SAUDACAO_INICIAL = "Olá, eu sou a Astra. Diga Ok Astra para me chamar."

# O que ela diz ao ser chamada sem nenhum comando ("Ok Astra").
FALA_CHAMADO = "Pois não?"

# Pausa depois de falar, antes de voltar a ouvir: o eco da sala ainda
# pode estar chegando ao microfone.
PAUSA_APOS_FALA = 0.3

# Tempo para responder à sugestão de intenção (não é confirmação de segurança).
TEMPO_INTENCAO = 60.0

# Se ouvir_microfone() volta com nada em menos tempo que isto, não foi
# "ninguém falou" (isso leva o TIMEOUT_ESPERA_FALA inteiro): foi falha
# do microfone.
TEMPO_MINIMO_ESCUTA = 0.5
FALHAS_RAPIDAS_ATE_DESISTIR = 3

# Erros inesperados seguidos antes de desistir (para não ficar presa num
# erro que se repete sem parar).
ERROS_SEGUIDOS_ATE_DESISTIR = 5


class MicrofoneIndisponivelError(Exception):
    """
    O microfone não respondeu várias vezes seguidas.
    """


@dataclass
class Saida:
    """
    O que a assistente vai fazer depois de processar uma fala.

    fala:             o que dizer em voz alta.
    encerrar:         True para terminar a conversa depois de falar.
    aguardar_comando: True quando ela só foi chamada ("Ok Astra") e agora
                      espera o comando numa próxima fala.
    """

    fala: str
    encerrar: bool = False
    aguardar_comando: bool = False


# MICROFONE

def _apagar_audio(caminho):
    """
    Apaga o áudio já transcrito (RN08: áudio não fica guardado).
    """

    if getattr(configuracoes_voz, "MANTER_AUDIOS", False):
        return

    try:
        os.remove(caminho)

    except OSError as erro:
        log(f"Não consegui apagar o áudio {caminho}: {erro}", "AVISO")


class Microfone:
    """
    Escuta pelo microfone e devolve o texto falado, para ser usado num
    laço que escuta o tempo todo.
    """

    def __init__(self):

        self._calibrado = False
        self._falhas_rapidas = 0

    def ouvir(self):
        """
        Espera uma fala e devolve o texto. Devolve "" se ninguém falou.
        Levanta MicrofoneIndisponivelError se o microfone falhar.
        """

        # Importado aqui para este módulo poder ser carregado (e testado)
        # sem o microfone e o modelo de fala.
        from . import reconhecedor_fala

        inicio = time.monotonic()

        # O ruído ambiente é medido só na primeira vez: medir a cada
        # fala gastaria 1 s e perderia o começo do que a pessoa diz.
        audio = reconhecedor_fala.ouvir_microfone(
            calibrar=not self._calibrado,
            silencioso=True
        )

        duracao = time.monotonic() - inicio

        if audio is None:

            if duracao < TEMPO_MINIMO_ESCUTA:

                self._falhas_rapidas += 1

                if self._falhas_rapidas >= FALHAS_RAPIDAS_ATE_DESISTIR:

                    raise MicrofoneIndisponivelError(
                        "O microfone não respondeu. Verifique se ele está "
                        "conectado e liberado para o Python nas configurações "
                        "de privacidade do Windows."
                    )

            else:

                self._calibrado = True
                self._falhas_rapidas = 0

            return ""

        self._calibrado = True
        self._falhas_rapidas = 0

        try:
            return reconhecedor_fala.converter_fala_para_texto(audio)

        finally:
            _apagar_audio(audio)


# ASSISTENTE

class AssistenteVoz:
    """
    Decide o que fazer com cada fala e controla o laço principal.

    O microfone ('ouvir') e a voz ('falar') entram como funções, para a
    lógica poder ser testada sem hardware.

    ouvir: função sem argumentos que devolve o texto ouvido ("" = silêncio).
    falar: função que recebe o texto a ser falado.
    """

    def __init__(
        self,
        ouvir,
        falar,
        executar=None,
        aguardando_confirmacao=None,
        conversar=None,
        detector=None,
        interpretar_intencao=None,
        entrada_por_voz=False
    ):

        self._ouvir = ouvir
        self._falar = falar

        self._executar = executar or comandos_voz.executar_comando
        # O gerenciador injetado nos testes pode ter sua própria sessão.
        gerenciador = getattr(self._executar, "__self__", None)
        if gerenciador is None and executar is None:
            gerenciador = comandos_voz.gerenciador_comandos
        self._gerenciador = gerenciador
        self._dialogo = getattr(gerenciador, "dialogo", None)

        self._aguardando_confirmacao = (
            aguardando_confirmacao or comandos_voz.aguardando_confirmacao
        )

        self._conversar = conversar or responder_conversa
        self._processador_conversa = (getattr(conversar, "__self__", None)
                                       if conversar is not None else processador_conversa)
        self._interpretar_intencao = interpretar_intencao or esclarecer_intencao
        self._entrada_por_voz = entrada_por_voz

        self.detector = detector or DetectorAtivacao()

        self.pausa_apos_fala = PAUSA_APOS_FALA

        # True enquanto uma ação crítica espera o "sim/não". Serve para
        # notar quando a espera vence sozinha (ninguém respondeu).
        self._confirmacao_em_andamento = False
        self._intencao_pendente = None
        self._prazo_intencao = 0.0
        self._tentativas_intencao = 0
        self._plano_pendente = None

    # DECISÃO

    def processar(self, texto):
        """
        Decide o que fazer com UMA fala já transcrita.

        Devolve uma Saida, ou None se a fala não era com a assistente
        (nada a fazer).
        """

        texto = (texto or "").strip()

        # A sessão composta é exclusiva. Uma nova chamada explícita cancela
        # o plano antigo; respostas soltas nunca confirmam um plano vencido.
        if self._plano_pendente is not None:
            plano = self._plano_pendente
            normalizado = normalizar_texto(texto)
            nova_chamada = any(normalizado == p or normalizado.startswith(p + " ")
                               for p in map(normalizar_texto, PALAVRAS_ATIVACAO))
            if nova_chamada:
                plano.cancelar()
                self._plano_pendente = None
                self.detector.desativar()
            else:
                if not ia_habilitada():
                    fala = plano.cancelar("A IA está desabilitada. Cancelei o plano.")
                else:
                    fala = plano.responder(texto)
                if not plano.ativo:
                    self._plano_pendente = None
                    self.detector.desativar()
                return Saida(fala) if fala else None

        # RN03: com uma ação crítica esperando, a próxima fala é a resposta,
        # mesmo sem "Ok Astra". Silêncio também conta (como "não entendi").
        if self._aguardando_confirmacao():
            self._intencao_pendente = None
            return self._comando(texto)

        if self._dialogo is not None and self._dialogo.aguardando():
            # Uma nova chamada explícita abandona o parâmetro anterior.
            normalizado = normalizar_texto(texto)
            if any(normalizado == p or normalizado.startswith(p + " ")
                   for p in map(normalizar_texto, PALAVRAS_ATIVACAO)):
                self._dialogo.cancelar()
                self.detector.desativar()
            else:
                return self._comando(texto)

        if self._intencao_pendente is not None:
            if time.monotonic() >= self._prazo_intencao:
                self._intencao_pendente = None
                self.detector.desativar()
                if normalizar_texto(texto) in {"sim", "nao", "cancelar"}:
                    return Saida("O prazo de confirmação terminou. Pode me chamar novamente.")
                if not texto:
                    return None
            else:
                # Uma chamada explícita inicia outro pedido, sem confirmar o antigo.
                normalizado = normalizar_texto(texto)
                if any(normalizado == p or normalizado.startswith(p + " ")
                       for p in map(normalizar_texto, PALAVRAS_ATIVACAO)):
                    self._intencao_pendente = None
                    self.detector.desativar()
                else:
                    return self._responder_intencao(texto)

        # A espera pelo "sim/não" venceu sem resposta: a ação foi descartada
        # e a assistente volta a exigir "Ok Astra" (senão um "sim" solto,
        # dito tarde, seria tratado como comando).
        if self._confirmacao_em_andamento:

            self._confirmacao_em_andamento = False
            self.detector.desativar()
            if not texto or normalizar_texto(texto) in {"sim", "nao", "cancelar"}:
                return Saida("O prazo de confirmação terminou. Peça a ação novamente.")

        if not texto:
            return None

        ativacao = self.detector.processar(texto)

        if ativacao.ativada:

            log(
                f"Chamada detectada ({ativacao.palavra_detectada!r}, "
                f"confiança {ativacao.confianca:.2f})."
            )

            comando_ouvido = ativacao.comando
            # O detector antigo remove apenas a grafia canônica. Quando a
            # chamada "ok ..." foi reconhecida por similaridade no início,
            # retire também a forma realmente ouvida (não o resto do pedido).
            original_normalizado = normalizar_texto(texto)
            if (ativacao.confianca < 1.0 and comando_ouvido == original_normalizado
                    and original_normalizado.startswith("ok ")
                    and (ativacao.palavra_detectada or "").startswith("ok ")):
                _, _, posicao = self.detector.encontrar_palavra_ativacao(texto)
                if posicao == 0:
                    quantidade = len(ativacao.palavra_detectada.split())
                    comando_ouvido = " ".join(original_normalizado.split()[quantidade:])
            if comando_ouvido:
                return self._comando(comando_ouvido, da_chamada=True)

            return self._chamado()

        # Depois de um "Ok Astra" sozinho, a assistente fica ativa por um
        # tempo: a fala inteira é o comando.
        if self.detector.verificar_estado():
            return self._comando(texto)

        log(f"Ignorado (sem 'Ok Astra'): {texto!r}")

        return None

    def _chamado(self):
        """
        Ela foi chamada, mas ainda não ouviu o comando.
        """

        return Saida(FALA_CHAMADO, aguardar_comando=True)

    def _responder_intencao(self, texto):
        """Aceita somente sim/não; não confirma operações sensíveis."""
        resposta = normalizar_texto(texto)
        sugestao = self._intencao_pendente
        if resposta in {"nao", "cancelar", "cancela", "cancele"}:
            self._intencao_pendente = None
            self.detector.desativar()
            return Saida("Tudo bem. Pode me dizer novamente o que deseja?", aguardar_comando=True)
        if resposta == "sim":
            self._intencao_pendente = None
            if not ia_habilitada():
                self.detector.desativar()
                return Saida("A IA local está desabilitada. Cancelei a sugestão.")
            # Passa pelo planejador: ainda pode exigir confirmação de segurança.
            return self._comando(sugestao, intencao_confirmada=True)
        if not resposta:
            return None
        self._tentativas_intencao -= 1
        if self._tentativas_intencao <= 0:
            self._intencao_pendente = None
            self.detector.desativar()
            return Saida("Não consegui confirmar o pedido. Pode me chamar novamente.")
        return Saida("Diga sim para confirmar o que você quis dizer, ou não para corrigir.")

    def _pedir_confirmacao_intencao(self, texto, pergunta):
        """Guarda exatamente o pedido que o usuário poderá confirmar."""
        self._intencao_pendente = texto
        self._prazo_intencao = time.monotonic() + TEMPO_INTENCAO
        self._tentativas_intencao = 2
        self.detector.desativar()
        return Saida(pergunta)

    def _comando(self, texto, da_chamada=False, intencao_confirmada=False):
        """
        Executa o comando e monta o que dizer.
        """

        # Confirmações de segurança existentes têm prioridade absoluta.
        # O modo tradicional permanece independente do Ollama. No modo IA,
        # somente comandos reconhecidos no início da frase seguem diretamente;
        # uma palavra-chave encontrada no meio de uma pergunta não é uma ordem.
        normalizado = normalizar_texto(texto)
        aguardando_parametro = self._dialogo is not None and self._dialogo.aguardando()
        # Consultas ao histórico verificado são locais e não precisam do Ollama.
        # Respeitam as pendências anteriores e nunca acionam ferramentas.
        if not aguardando_parametro and not self._aguardando_confirmacao():
            memoria = getattr(self._gerenciador, "memoria_operacional", None)
            if memoria is not None:
                if normalizado == "limpar contexto":
                    memoria.limpar()
                resposta_memoria = memoria.responder(texto)
                if resposta_memoria is not None:
                    self.detector.desativar()
                    return Saida(resposta_memoria)
        if not aguardando_parametro and not self._aguardando_confirmacao() and ia_habilitada():
            if da_chamada and normalizado in {"ok", "okay", "oca", "o"}:
                return self._chamado()
            gerenciador = self._gerenciador or comandos_voz.gerenciador_comandos
            texto_rota = texto.split(maxsplit=1)[1] if normalizado.startswith("planeje ") else texto
            rota = avaliar_rota(texto_rota, gerenciador)
            plano_criacao = plano_criacao_explicito(texto_rota)
            escrita_dependente = pedido_escrita_dependente(texto_rota)
            direto = not plano_criacao and not escrita_dependente and rota.direta and not normalizado.startswith("planeje ")
            conversa_local = normalizado in {"limpar contexto", "limpar conversa", "limpar memoria conversacional"} or any(
                normalizado in frases for frases, _ in processador_conversa.conversas
            )
            if intencao_confirmada or conversa_local or not direto:
                if not intencao_confirmada and not conversa_local:
                    esclarecimento = self._interpretar_intencao(texto)
                    if esclarecimento is not None:
                        if esclarecimento.indisponivel:
                            self.detector.desativar()
                            return Saida("Não consegui consultar a IA local. Verifique se o Ollama está em execução e tente novamente.")
                        if esclarecimento.sugestao is not None:
                            return self._pedir_confirmacao_intencao(
                                esclarecimento.sugestao, esclarecimento.pergunta)
                        # Uma sequência fechada, integralmente reconhecida, não
                        # depende de o modelo saber reescrever a frase. Só
                        # encaminhe o pedido literal após confirmação humana.
                        sequencia = sequencia_explicita(texto_rota)
                        if (sequencia and len(set(sequencia)) == len(sequencia)) or plano_criacao:
                            return self._pedir_confirmacao_intencao(
                                texto, f"Entendi: {texto_rota.rstrip('?.!')}. Está correto? Diga sim ou não.")
                        # Frases curtas (ex.: resposta a uma pergunta da IA)
                        # podem ser compreendidas somente com contexto. Esta
                        # tentativa é exclusivamente conversacional, sem executor.
                        if (not rota.composta and not escrita_dependente
                                and not ferramentas_do_pedido(texto_rota)
                                and not normalizado.startswith("planeje ")):
                            recuperar = getattr(self._processador_conversa, "responder_continuacao", None)
                            if callable(recuperar):
                                fala = recuperar(texto)
                                if fala:
                                    self.detector.desativar()
                                    return Saida(fala)
                        self.detector.ativar()
                        return Saida(esclarecimento.pergunta, aguardar_comando=True)
                if plano_criacao:
                    if self._entrada_por_voz and not intencao_confirmada:
                        return self._pedir_confirmacao_intencao(
                            texto, f"Entendi: {texto_rota.rstrip('?.!')}. Está correto? Diga sim ou não.")
                    plano = PlanoPendente(gerenciador, plano_criacao)
                    fala = plano.avancar()
                    self._plano_pendente = plano if plano.ativo else None
                    self.detector.desativar()
                    return Saida(fala)

                # Uma transcrição imperfeita pode parecer um composto não
                # suportado. Primeiro ofereça revisão semântica, depois
                # mantenha o bloqueio se o pedido (inclusive corrigido) não
                # estiver no escopo. Nunca execute só a primeira ação.
                if escrita_dependente or (rota.composta and not rota.suportada):
                    self.detector.desativar()
                    return Saida("Identifiquei mais de uma ação. Ainda não consigo combinar essas ferramentas com segurança. Pode pedir uma de cada vez?")
                # Pesquisas compostas exigem confirmação em qualquer modo.
                # Outras sequências fechadas exigem confirmação por voz.
                # Uma correção já confirmada não exige um segundo sim.
                busca_composta = {"abrir_navegador", "pesquisar"} <= ferramentas_do_pedido(texto_rota)
                if (not intencao_confirmada
                        and (busca_composta or (self._entrada_por_voz
                                                and sequencia_explicita(texto_rota)))):
                    return self._pedir_confirmacao_intencao(
                        texto, f"Entendi: {texto_rota.rstrip('?.!')}. Está correto? Diga sim ou não.")
                # Uma interpretação feita pelo modelo nunca entra no executor
                # legado por correspondência parcial. O planejador da etapa 1
                # valida o escopo; confirmações sensíveis continuam separadas.
                fala = self._conversar(texto)
                self._confirmacao_em_andamento = self._aguardando_confirmacao()
                if not self._confirmacao_em_andamento:
                    self.detector.desativar()
                return Saida(fala)

        # Planejamento explícito continua disponível (inclusive aviso de IA desligada).
        if not aguardando_parametro and not self._aguardando_confirmacao() and normalizado.startswith("planeje "):
            fala = self._conversar(texto)
            self._confirmacao_em_andamento = self._aguardando_confirmacao()
            if not self._confirmacao_em_andamento:
                self.detector.desativar()
            return Saida(fala)

        if not aguardando_parametro and not self._aguardando_confirmacao() and not ia_habilitada():
            rota = avaliar_rota(texto, self._gerenciador or comandos_voz.gerenciador_comandos)
            if rota.composta or plano_criacao_explicito(texto) or pedido_escrita_dependente(texto):
                self.detector.desativar()
                return Saida("A IA local está desabilitada. Para executar essas ações, peça uma de cada vez.")

        resultado = self._executar(texto)

        if resultado.status == StatusComando.NAO_ENCONTRADO:

            fala = self._conversar(texto)

            # O detector devolve como "comando" o que veio ANTES do nome
            # quando o nome está no fim da frase, e um "Ok" mal transcrito
            # ("okay", "oca", "ó") vira esse resto. Sem isto, ela
            # responderia "Não entendi" a um simples chamado.
            if (
                da_chamada
                and fala == RESPOSTA_PADRAO
                and len(texto.split()) <= 2
            ):
                return self._chamado()

            saida = Saida(fala)

        else:

            saida = Saida(
                resultado.resposta_falada,
                encerrar=resultado.encerrar
            )

        # Comando concluído: para a próxima, é preciso chamar de novo. Se
        # ela ficou esperando um "sim/não", segue ativa.
        self._confirmacao_em_andamento = self._aguardando_confirmacao()

        if not self._confirmacao_em_andamento:
            self.detector.desativar()

        return saida

    # LAÇO PRINCIPAL

    def _dizer(self, fala):

        if not fala:
            return

        # A aprovação precisa apresentar o conteúdo integral também no teclado.
        # Os demais logs mantêm o limite anterior.
        plano = self._plano_pendente
        mostrando_resumo = (plano is not None and plano.tipo == 'confirmacao'
                             and plano.pendente is not None
                             and plano.etapas[plano.pendente].nome == 'escrever_texto')
        resumo = fala if mostrando_resumo or len(fala) <= 160 else fala[:160] + "..."

        log(f"Astra: {resumo}")

        self._falar(fala)

        time.sleep(self.pausa_apos_fala)

    def rodar(self):
        """
        Escuta e responde até o usuário pedir para encerrar (ou Ctrl+C).
        """

        self._dizer(SAUDACAO_INICIAL)

        log("Pronta. Diga 'Ok Astra' para me chamar. (Ctrl+C para sair)")

        erros_seguidos = 0

        try:

            while True:

                try:

                    texto = self._ouvir()

                    if texto:
                        log(f"Ouvi: {texto!r}")

                    saida = self.processar(texto)

                    if saida is not None:

                        self._dizer(saida.fala)

                        if saida.encerrar:
                            return

                        if self._dialogo is not None and self._dialogo.pendente is not None and saida.fala:
                            self._dialogo.renovar_prazo()
                        if self._gerenciador is not None and self._confirmacao_em_andamento and saida.fala:
                            self._gerenciador.confirmacao.renovar_prazo()

                        if self._plano_pendente is not None and saida.fala:
                            self._plano_pendente.renovar_prazo()

                        if self._intencao_pendente is not None:
                            # A janela começa depois que a pergunta foi falada.
                            self._prazo_intencao = time.monotonic() + TEMPO_INTENCAO

                        if saida.aguardar_comando:
                            # A janela de ativação conta a partir de agora, e
                            # não de antes de ela falar.
                            self.detector.ativar()

                    erros_seguidos = 0

                except (KeyboardInterrupt, MicrofoneIndisponivelError):
                    raise

                except Exception as erro:

                    erros_seguidos += 1

                    log(f"Erro inesperado: {erro}", "ERRO")

                    if erros_seguidos >= ERROS_SEGUIDOS_ATE_DESISTIR:
                        raise

        except KeyboardInterrupt:

            log("Encerrado pelo usuário.")


# EXECUÇÃO

def _ouvir_do_teclado():

    try:
        return input("Você: ")

    except EOFError:
        raise KeyboardInterrupt


def _montar(argumentos):
    """
    Carrega o que for preciso e devolve o assistente pronto.
    Levanta ModeloNaoEncontradoError ou VozNaoEncontradaError se faltar
    baixar o modelo de fala ou a voz.
    """

    if argumentos.teclado:

        ouvir = _ouvir_do_teclado

    else:

        from . import reconhecedor_fala

        print("Carregando o reconhecimento de fala...")

        reconhecedor_fala.carregar_modelo()

        ouvir = Microfone().ouvir

    if argumentos.sem_voz:

        falar = lambda texto: True

    else:

        from . import sintetizador_voz

        print("Carregando a voz...")

        sintetizador_voz.carregar_voz()

        falar = sintetizador_voz.falar

    return AssistenteVoz(ouvir, falar, entrada_por_voz=not argumentos.teclado)


def iniciar_conversa(argv=None):
    """
    Ponto de entrada do assistente de voz. Devolve 0 se terminou bem e 1
    se não conseguiu começar.
    """

    parser = argparse.ArgumentParser(description="Assistente de voz A.S.T.R.A.")

    parser.add_argument("--teclado", action="store_true", help="digita as frases em vez de falar (para testar sem microfone)")
    parser.add_argument("--sem-voz", action="store_true", help="não fala as respostas, só as mostra no texto")

    argumentos = parser.parse_args(argv)

    from .reconhecedor_fala import ModeloNaoEncontradoError
    from .sintetizador_voz import VozNaoEncontradaError

    try:

        assistente = _montar(argumentos)

    except (ModeloNaoEncontradoError, VozNaoEncontradaError) as erro:

        print(f"\n{erro}")
        return 1

    try:

        assistente.rodar()

    except MicrofoneIndisponivelError as erro:

        print(f"\n{erro}")

        try:
            assistente._falar("Não consegui usar o microfone.")

        except Exception:
            pass

        return 1

    return 0


if __name__ == "__main__":

    raise SystemExit(iniciar_conversa())
