from dataclasses import dataclass
from datetime import datetime
import difflib
import re
import time
import unicodedata

"""
Módulo de ativação por voz da A.S.T.R.A.

Responsabilidade:
    Detectar a palavra/frase de ativação da A.S.T.R.A.

Funções:
    - Normalização do texto
    - Reconhecimento de variações da palavra-chave
    - Tolerância a pequenos erros do reconhecimento de voz
    - Controle de estado da ativação
    - Controle de tempo de ativação
    - Extração do comando após a palavra-chave
    - Registro de eventos
"""

# CONFIGURAÇÕES

PALAVRAS_ATIVACAO = [
    "ok astra",
    "ok ás tra",
    "oi astra",
    "hey astra",
    "ei astra",
    "astra",
]

# Tolerância para erros do reconhecimento de voz.
# Quanto maior, mais tolerante será.
LIMITE_SIMILARIDADE = 0.78

# Tempo que a A.S.T.R.A. permanece ativa após ser chamada.
TEMPO_ATIVA = 10.0



# RESULTADO DA DETECÇÃO

@dataclass
class ResultadoAtivacao:
    """
    Resultado produzido pelo detector de ativação.
    """

    ativada: bool
    palavra_detectada: str | None = None
    comando: str = ""
    confianca: float = 0.0
    horario: datetime | None = None



# DETECTOR DE ATIVAÇÃO
class DetectorAtivacao:
    """
    Responsável por detectar quando a A.S.T.R.A. foi chamada.
    """

    def __init__(
        self,
        palavras=None,
        limite_similaridade=LIMITE_SIMILARIDADE,
        tempo_ativa=TEMPO_ATIVA
    ):

        self.palavras = palavras or PALAVRAS_ATIVACAO

        self.limite_similaridade = limite_similaridade

        self.tempo_ativa = tempo_ativa

        self.ativa = False

        self.momento_ativacao = None


    # NORMALIZAÇÃO
    @staticmethod
    def normalizar_texto(texto):
        """
        Normaliza o texto recebido pelo reconhecimento de voz.

        Remove:
            - acentos
            - caracteres especiais
            - espaços duplicados

        Também converte tudo para minúsculo.
        """

        if not texto:
            return ""

        texto = texto.lower().strip()

        # Remove acentos.
        texto = unicodedata.normalize("NFD", texto)

        texto = "".join(
            caractere
            for caractere in texto
            if unicodedata.category(caractere) != "Mn"
        )

        # Remove caracteres especiais.
        texto = re.sub(r"[^a-z0-9\s]", " ", texto)

        # Remove espaços duplicados.
        texto = re.sub(r"\s+", " ", texto)

        return texto.strip()


    # SIMILARIDADE
    @staticmethod
    def calcular_similaridade(texto_a, texto_b):
        """
        Calcula o quanto dois textos são semelhantes.

        Retorna um valor entre 0 e 1.
        """

        return difflib.SequenceMatcher(
            None,
            texto_a,
            texto_b
        ).ratio()


    # PROCURAR PALAVRA-CHAVE
    def encontrar_palavra_ativacao(self, texto):
        """
        Procura uma palavra de ativação dentro do texto.

        Retorna:

            palavra_detectada
            confianca
            posicao

        ou:

            None, 0.0, -1
        """

        texto_normalizado = self.normalizar_texto(texto)

        if not texto_normalizado:
            return None, 0.0, -1

        melhor_palavra = None
        melhor_confianca = 0.0
        melhor_posicao = -1


        # Primeiro: procura exata
        for palavra in self.palavras:

            palavra_normalizada = self.normalizar_texto(
                palavra
            )

            posicao = texto_normalizado.find(
                palavra_normalizada
            )

            if posicao != -1:

                return (
                    palavra,
                    1.0,
                    posicao
                )


        # Segundo: procura aproximada
        palavras_texto = texto_normalizado.split()

        palavras_ativacao = [
            self.normalizar_texto(palavra)
            for palavra in self.palavras
        ]

        for palavra_ativacao in palavras_ativacao:

            quantidade_palavras = len(
                palavra_ativacao.split()
            )

            if quantidade_palavras == 0:
                continue

            for indice in range(
                len(palavras_texto) - quantidade_palavras + 1
            ):

                trecho = " ".join(
                    palavras_texto[
                        indice:
                        indice + quantidade_palavras
                    ]
                )

                confianca = self.calcular_similaridade(
                    trecho,
                    palavra_ativacao
                )

                if confianca > melhor_confianca:

                    melhor_confianca = confianca

                    melhor_palavra = palavra_ativacao

                    melhor_posicao = indice

        if melhor_confianca >= self.limite_similaridade:

            return (
                melhor_palavra,
                melhor_confianca,
                melhor_posicao
            )

        return None, 0.0, -1


    # EXTRAIR COMANDO

    def extrair_comando(self, texto, palavra_detectada):
        """
        Remove a palavra de ativação e retorna somente
        o comando que foi falado.

        Exemplo:

            "Ok Astra abra o Chrome"

        retorna:

            "abra o Chrome"
        """

        if not texto or not palavra_detectada:
            return ""

        texto_normalizado = self.normalizar_texto(texto)

        palavra_normalizada = self.normalizar_texto(
            palavra_detectada
        )

        comando = texto_normalizado.replace(
            palavra_normalizada,
            "",
            1
        )

        return comando.strip()


    # ATIVAR

    def ativar(self):
        """
        Ativa a A.S.T.R.A.
        """

        self.ativa = True

        self.momento_ativacao = time.monotonic()


    # VERIFICAR ESTADO

    def verificar_estado(self):
        """
        Verifica se a A.S.T.R.A. ainda está ativa.
        """

        if not self.ativa:
            return False

        if self.momento_ativacao is None:
            self.ativa = False
            return False

        tempo_decorrido = (
            time.monotonic()
            - self.momento_ativacao
        )

        if tempo_decorrido >= self.tempo_ativa:

            self.desativar()

            return False

        return True


    # DESATIVAR

    def desativar(self):
        """
        Desativa a A.S.T.R.A.
        """

        self.ativa = False

        self.momento_ativacao = None


    # PROCESSAR TEXTO

    def processar(self, texto):
        """
        Processa um texto recebido do reconhecimento de voz.

        Retorna um ResultadoAtivacao.
        """

        horario = datetime.now()

        palavra, confianca, _ = (
            self.encontrar_palavra_ativacao(texto)
        )

        # Palavra não encontrada

        if palavra is None:

            return ResultadoAtivacao(
                ativada=False,
                confianca=0.0,
                horario=horario
            )

        # Palavra encontrada

        self.ativar()

        comando = self.extrair_comando(
            texto,
            palavra
        )

        return ResultadoAtivacao(
            ativada=True,
            palavra_detectada=palavra,
            comando=comando,
            confianca=confianca,
            horario=horario
        )



# INSTÂNCIA PADRÃO

detector_ativacao = DetectorAtivacao()


# FUNÇÃO PÚBLICA

def detectar_palavra_ativacao(texto):
    """
    Função simples para outros módulos.

    Retorna True quando a palavra de ativação
    for detectada.
    """

    resultado = detector_ativacao.processar(texto)

    return resultado.ativada