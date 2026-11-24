import argparse
import os
import time
from dataclasses import dataclass

from configs import configuracoes_voz
from . import comandos_voz
from .ativacao_voz import DetectorAtivacao
from .comandos_voz import StatusComando
from .processador_linguagem import RESPOSTA_PADRAO, responder_conversa
from .utilitarios_voz import log

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
        detector=None
    ):

        self._ouvir = ouvir
        self._falar = falar

        self._executar = executar or comandos_voz.executar_comando

        self._aguardando_confirmacao = (
            aguardando_confirmacao or comandos_voz.aguardando_confirmacao
        )

        self._conversar = conversar or responder_conversa

        self.detector = detector or DetectorAtivacao()

        self.pausa_apos_fala = PAUSA_APOS_FALA

        # True enquanto uma ação crítica espera o "sim/não". Serve para
        # notar quando a espera vence sozinha (ninguém respondeu).
        self._confirmacao_em_andamento = False

    # DECISÃO

    def processar(self, texto):
        """
        Decide o que fazer com UMA fala já transcrita.

        Devolve uma Saida, ou None se a fala não era com a assistente
        (nada a fazer).
        """

        texto = (texto or "").strip()

        # RN03: com uma ação crítica esperando, a próxima fala é a resposta,
        # mesmo sem "Ok Astra". Silêncio também conta (como "não entendi").
        if self._aguardando_confirmacao():
            return self._comando(texto)

        # A espera pelo "sim/não" venceu sem resposta: a ação foi descartada
        # e a assistente volta a exigir "Ok Astra" (senão um "sim" solto,
        # dito tarde, seria tratado como comando).
        if self._confirmacao_em_andamento:

            self._confirmacao_em_andamento = False
            self.detector.desativar()

        if not texto:
            return None

        ativacao = self.detector.processar(texto)

        if ativacao.ativada:

            log(
                f"Chamada detectada ({ativacao.palavra_detectada!r}, "
                f"confiança {ativacao.confianca:.2f})."
            )

            if ativacao.comando:
                return self._comando(ativacao.comando, da_chamada=True)

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

    def _comando(self, texto, da_chamada=False):
        """
        Executa o comando e monta o que dizer.
        """

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

        resumo = fala if len(fala) <= 160 else fala[:160] + "..."

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

                        if saida.aguardar_comando:
                            # A janela de 10 s conta a partir de agora, e
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

    return AssistenteVoz(ouvir, falar)


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
