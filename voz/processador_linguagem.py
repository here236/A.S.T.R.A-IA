from .utilitarios_voz import normalizar_texto

'''
    Conversa (fallback)

    Responsabilidade:
    Responder ao que NÃO é um comando conhecido.

    Fluxo: voz_principal primeiro tenta comandos_voz.executar_comando().
    Só se o resultado vier com status NAO_ENCONTRADO o texto chega aqui.

    Este módulo NÃO reconhece nem executa comandos (isso é do
    comandos_voz) e NÃO converte áudio em texto (isso é do
    reconhecedor_fala).

    Hoje responde por regras simples. É o ponto previsto para plugar
    uma IA de conversa (LLM) depois: basta implementar _responder_com_ia.
'''


RESPOSTA_PADRAO = (
    "Não entendi. Diga ajuda para ouvir o que eu sei fazer."
)

RESPOSTA_VAZIA = "Não consegui entender o que você disse."


class ProcessadorConversa:

    def __init__(self):

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

        texto = normalizar_texto(texto)

        if not texto:
            return RESPOSTA_VAZIA

        resposta = self._responder_por_regras(texto)

        if resposta:
            return resposta

        resposta = self._responder_com_ia(texto)

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

    def _responder_com_ia(self, texto):
        """
        Ponto de integração com uma IA de conversa (LLM).

        Deve devolver a resposta como texto, ou None quando não
        souber responder. Hoje não há IA conectada.
        """

        return None


# INSTÂNCIA PRINCIPAL

processador_conversa = ProcessadorConversa()


# FUNÇÃO PÚBLICA

def responder_conversa(texto):
    """
    Função utilizada pelos outros módulos da A.S.T.R.A.
    """

    return processador_conversa.responder(texto)
