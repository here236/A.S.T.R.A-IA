import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from configs import configuracoes_voz
from .utilitarios_voz import normalizar_texto

"""
RN03 - Confirmação por voz de ações críticas.

Responsabilidade:
    Guardar a ação crítica que está esperando o "sim" do usuário e
    interpretar a resposta (confirmou, cancelou, não entendeu,
    tempo esgotado).

Este módulo NÃO executa a ação e NÃO fala nada: ele só decide.
Quem executa é o comandos_voz; quem fala é o voz_principal.

Palavras aceitas e tempos ficam em configs/configuracoes_voz.py.
"""


# TIPOS

class Decisao(Enum):
    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"
    REPETIR = "repetir"


@dataclass
class AcaoPendente:
    """
    Ação crítica já entendida, mas ainda esperando o "sim".
    """

    comando: Any
    parametro: str
    momento: float
    tentativas_restantes: int


@dataclass
class RespostaConfirmacao:
    """
    O que o usuário decidiu.

    fala:     frase para ser FALADA (TTS).
    mensagem: texto de log/depuração.
    """

    decisao: Decisao
    acao: AcaoPendente
    fala: str = ""
    mensagem: str = ""


# INTERPRETAÇÃO DA RESPOSTA

def interpretar_confirmacao(texto: str) -> Optional[bool]:
    """
    True  -> usuário confirmou
    False -> usuário cancelou
    None  -> não deu para entender

    O cancelamento tem prioridade: na dúvida ("sim, não"),
    não executa.
    """

    texto = f" {normalizar_texto(texto)} "

    for palavra in configuracoes_voz.PALAVRAS_CANCELAR:
        if f" {normalizar_texto(palavra)} " in texto:
            return False

    for palavra in configuracoes_voz.PALAVRAS_CONFIRMAR:
        if f" {normalizar_texto(palavra)} " in texto:
            return True

    return None


# GERENCIADOR

class GerenciadorConfirmacao:

    def __init__(self):

        self._pendente: Optional[AcaoPendente] = None

    def pedir(self, comando: Any, parametro: str = ""):
        """
        Guarda a ação crítica e começa a esperar a confirmação.
        """

        self._pendente = AcaoPendente(
            comando = comando,
            parametro = parametro,
            momento = time.monotonic(),
            tentativas_restantes = configuracoes_voz.TENTATIVAS_CONFIRMACAO
        )

    def aguardando(self) -> bool:
        """
        True se há ação esperando o "sim"/"não". Se o tempo limite
        já passou, descarta a ação e devolve False.
        """

        if self._pendente is None:
            return False

        decorrido = time.monotonic() - self._pendente.momento

        if decorrido >= configuracoes_voz.TEMPO_LIMITE_CONFIRMACAO:
            self._pendente = None
            return False

        return True

    def cancelar(self):
        """
        Descarta a ação pendente, se houver.
        """

        self._pendente = None

    def responder(self, texto: str) -> RespostaConfirmacao:
        """
        Interpreta a resposta falada. Só chamar quando aguardando()
        for True.
        """

        pendente = self._pendente

        resposta = interpretar_confirmacao(texto)

        if resposta is True:

            self._pendente = None

            return RespostaConfirmacao(
                decisao = Decisao.CONFIRMADA,
                acao = pendente,
                mensagem = f"'{pendente.comando.nome}' confirmado."
            )

        if resposta is False:

            self._pendente = None

            return RespostaConfirmacao(
                decisao = Decisao.CANCELADA,
                acao = pendente,
                fala = "Ok, cancelei.",
                mensagem = f"'{pendente.comando.nome}' cancelado pelo usuário."
            )

        # Não entendeu: repete a pergunta e, se continuar sem
        # entender, cancela por segurança.
        if pendente.tentativas_restantes > 0:

            pendente.tentativas_restantes -= 1
            pendente.momento = time.monotonic()

            return RespostaConfirmacao(
                decisao = Decisao.REPETIR,
                acao = pendente,
                fala = "Não entendi. Diga sim para confirmar ou não para cancelar.",
                mensagem = "Resposta de confirmação não entendida."
            )

        self._pendente = None

        return RespostaConfirmacao(
            decisao = Decisao.CANCELADA,
            acao = pendente,
            fala = "Não consegui entender, então cancelei por segurança.",
            mensagem = f"'{pendente.comando.nome}' cancelado: sem confirmação."
        )
