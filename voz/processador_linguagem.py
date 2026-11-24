import os

from .utilitarios_voz import normalizar_texto, log

'''
    Conversa (fallback)

    Responsabilidade:
    Responder ao que NÃO é um comando conhecido.

    Fluxo: voz_principal primeiro tenta comandos_voz.executar_comando().
    Só se o resultado vier com status NAO_ENCONTRADO o texto chega aqui.

    Este módulo NÃO reconhece nem executa comandos (isso é do
    comandos_voz) e NÃO converte áudio em texto (isso é do
    reconhecedor_fala).

    Responde primeiro por regras simples e, quando habilitada, usa o
    planejador local para pedidos que não correspondem a comandos conhecidos.
    A indisponibilidade do Ollama nunca interrompe o fluxo tradicional.
'''


RESPOSTA_PADRAO = (
    "Não entendi. Diga ajuda para ouvir o que eu sei fazer."
)

RESPOSTA_VAZIA = "Não consegui entender o que você disse."


class ProcessadorConversa:

    def __init__(self, planejador=None, ia_habilitada=None):

        self._planejador = planejador
        if ia_habilitada is None:
            valor = os.getenv("ASTRA_IA_HABILITADA", "1").strip().lower()
            ia_habilitada = valor not in {"0", "false", "nao", "não", "off"}
        self.ia_habilitada = bool(ia_habilitada)

        # Frases já sem acento: o texto passa por normalizar_texto
        # antes da comparação.
        self.conversas = [
            (
                ["bom dia"],
                "Bom dia! Como posso ajudar?"
            ),
            (
                ["boa tarde"],
                "Boa tarde! Como posso ajudar?"
            ),
            (
                ["boa noite"],
                "Boa noite! Como posso ajudar?"
            ),
            (
                ["ola", "oi", "e ai"],
                "Olá! Como posso ajudar?"
            ),
            (
                ["tudo bem", "como voce esta", "como vai voce"],
                "Estou bem, obrigada por perguntar. Como posso ajudar?"
            ),
        ]

    def responder(self, texto):
        """
        Devolve a frase que a A.S.T.R.A. deve falar em resposta
        a um texto que não era um comando.
        """

        original = (texto or "").strip()
        texto = normalizar_texto(original)

        if not texto:
            return RESPOSTA_VAZIA

        if texto == "limpar contexto":
            if self._planejador is not None:
                self._planejador.limpar_historico()
            return "Contexto da conversa limpo."

        if texto.startswith("planeje "):
            if not self.ia_habilitada:
                return "A IA local está desabilitada."
            return self._responder_com_ia(original.split(maxsplit=1)[1]) or RESPOSTA_PADRAO

        resposta = self._responder_por_regras(texto)

        if resposta:
            return resposta

        resposta = self._responder_com_ia(original)

        if resposta:
            return resposta

        return RESPOSTA_PADRAO

    def _responder_por_regras(self, texto):
        """
        Respostas fixas para conversas simples (saudações etc.).
        """

        # Compara por palavra inteira, para "oi" não casar dentro
        # de "foi" ou "boi".
        texto_delimitado = f" {texto} "

        for frases, resposta in self.conversas:

            for frase in frases:

                if f" {frase} " in texto_delimitado:
                    return resposta

        return None

    def _obter_planejador(self):
        """Inicializa a IA sob demanda, sem exigir Ollama ao importar a ASTRA."""
        if self._planejador is not None:
            return self._planejador

        from ia.cliente_ollama import ClienteOllama
        from ia.planejador import PlanejadorASTRA
        from voz.comandos_voz import gerenciador_comandos

        cliente = ClienteOllama(
            url=os.getenv("ASTRA_OLLAMA_URL", "http://localhost:11434"),
            modelo=os.getenv("ASTRA_OLLAMA_MODELO", "qwen2.5:1.5b"),
            timeout=float(os.getenv("ASTRA_OLLAMA_TIMEOUT", "45")),
        )
        self._planejador = PlanejadorASTRA(
            cliente_ia=cliente,
            registro=gerenciador_comandos.registro_ferramentas,
            executor=gerenciador_comandos.executor_ferramentas,
        )
        return self._planejador

    def _responder_com_ia(self, texto):
        """Planeja e executa somente ferramentas autorizadas pelo registro."""
        if not self.ia_habilitada:
            return None

        log("Solicitação não reconhecida como comando. Encaminhando para a IA local.", "IA")

        try:
            planejador = self._obter_planejador()
            log("Planejador carregado. Consultando o Ollama...", "IA")
            resultado = planejador.processar(texto)
        except Exception as erro:
            # A camada de IA é opcional: falhas nunca quebram comandos/voz.
            # O erro é registrado para que problemas de configuração não
            # sejam mascarados como uma simples frase não reconhecida.
            log(f"Falha ao inicializar ou consultar a IA: {type(erro).__name__}: {erro}", "ERRO")
            return None

        status = resultado.get("status")
        mensagem = resultado.get("mensagem", "")

        if status == "resposta":
            return mensagem or RESPOSTA_PADRAO

        if status == "aguardando_confirmacao":
            return mensagem or "Preciso da sua confirmação antes de continuar."

        if status == "etapas_executadas":
            falas = []
            for etapa in resultado.get("resultados", []):
                fala = etapa.get("resposta") or etapa.get("mensagem")
                if fala and fala not in falas:
                    falas.append(fala)
            if falas:
                return " ".join(falas)
            return mensagem or "Concluí as etapas autorizadas."

        if status == "limite_de_etapas":
            return mensagem or "A tarefa ficou parcialmente concluída."

        # O planejador converte falhas do Ollama em status, portanto elas
        # também precisam aparecer no console (antes eram silenciosas).
        if status == "ia_indisponivel":
            log(f"O Ollama não conseguiu responder: {mensagem or 'erro não informado'}", "ERRO")
        elif status in {"plano_invalido", "erro_na_etapa", "ciclo_detectado"}:
            log(f"A IA não concluiu a solicitação ({status}): {mensagem or 'sem detalhes'}", "AVISO")
        else:
            log(f"A IA retornou um status não tratado ({status!r}). {mensagem}", "AVISO")

        # A IA continua opcional: uma falha não interrompe os comandos
        # tradicionais nem derruba o loop de voz.
        return None


# INSTÂNCIA PRINCIPAL

processador_conversa = ProcessadorConversa()


# FUNÇÃO PÚBLICA

def responder_conversa(texto):
    """
    Função utilizada pelos outros módulos da A.S.T.R.A.
    """

    return processador_conversa.responder(texto)
