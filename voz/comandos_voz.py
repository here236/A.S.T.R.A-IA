import subprocess
import webbrowser
import unicodedata
import re

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

"""
Ações específicas da A.S.T.R.A.

Responsabilidade:
    Interpretar comandos conhecidos e executar ações específicas.

Exemplos:
    "leia a tela"
    "abra o navegador"
    "abra o bloco de notas"
    "feche a janela"

Este módulo NÃO é responsável por:
    - Reconhecimento de voz
    - OCR
    - Inteligência artificial
    - Captura de áudio

Ele recebe um texto já reconhecido e decide qual ação executar.
"""


# TIPOS DE RESULTADO

class StatusComando(Enum):
    SUCESSO = "sucesso"
    NAO_ENCONTRADO = "nao_encontrado"
    ERRO = "erro"


@dataclass
class ResultadoComando:
    """
    Resultado da execução de um comando.
    """

    status: StatusComando
    comando: str = ""
    mensagem: str = ""
    dados: Optional[object] = None


# NORMALIZAÇÃO

def normalizar_texto(texto: str) -> str:
    """
    Normaliza o texto recebido.

    Remove:
        - letras maiúsculas
        - acentos
        - caracteres especiais
        - espaços duplicados
    """

    if not texto:
        return ""

    texto = texto.lower().strip()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9\s]", " ", texto)

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()


# DEFINIÇÃO DE UM COMANDO

@dataclass
class Comando:
    """
    Representa um comando que a A.S.T.R.A. sabe executar.
    """

    nome: str
    palavras_chave: list[str]
    funcao: Callable
    descricao: str = ""


# GERENCIADOR DE COMANDOS

class GerenciadorComandos:

    def __init__(self):

        self.comandos: list[Comando] = []

        self._registrar_comandos()


    # REGISTRO

    def registrar(
        self,
        nome: str,
        palavras_chave: list[str],
        funcao: Callable,
        descricao: str = ""
    ):
        """
        Registra um novo comando.
        """

        comando = Comando(
            nome=nome,
            palavras_chave=palavras_chave,
            funcao=funcao,
            descricao=descricao
        )

        self.comandos.append(comando)


    # COMANDOS DISPONÍVEIS

    def _registrar_comandos(self):

        self.registrar(
            nome="ler_tela",
            palavras_chave=[
                "leia a tela",
                "ler a tela",
                "leia minha tela",
                "o que tem na tela",
                "o que esta na tela",
                "descreva a tela"
            ],
            funcao=self.ler_tela,
            descricao="Lê o conteúdo visível da tela."
        )

        self.registrar(
            nome="abrir_navegador",
            palavras_chave=[
                "abra o navegador",
                "abrir o navegador",
                "abra navegador",
                "inicie o navegador"
            ],
            funcao=self.abrir_navegador,
            descricao="Abre o navegador padrão."
        )

        self.registrar(
            nome="abrir_bloco_notas",
            palavras_chave=[
                "abra o bloco de notas",
                "abrir bloco de notas",
                "abra o bloco notas",
                "inicie o bloco de notas"
            ],
            funcao=self.abrir_bloco_notas,
            descricao="Abre o Bloco de Notas."
        )

        self.registrar(
            nome="ajuda",
            palavras_chave=[
                "ajuda",
                "o que voce pode fazer",
                "o que você pode fazer",
                "quais comandos voce conhece",
                "quais comandos você conhece"
            ],
            funcao=self.mostrar_ajuda,
            descricao="Mostra os comandos disponíveis."
        )


    # LOCALIZAR COMANDO

    def encontrar_comando(self, texto: str) -> Optional[Comando]:

        texto = normalizar_texto(texto)

        if not texto:
            return None

        melhor_comando = None
        maior_pontuacao = 0

        for comando in self.comandos:

            for palavra in comando.palavras_chave:

                palavra = normalizar_texto(palavra)

                if palavra in texto:

                    # Quanto maior a expressão encontrada,
                    # maior a prioridade.
                    pontuacao = len(palavra)

                    if pontuacao > maior_pontuacao:

                        maior_pontuacao = pontuacao
                        melhor_comando = comando

        return melhor_comando


    # EXECUTAR

    def executar(self, texto: str) -> ResultadoComando:

        if not texto:

            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                mensagem="Nenhum comando foi recebido."
            )

        comando = self.encontrar_comando(texto)

        if comando is None:

            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                mensagem=f"Não reconheci o comando: {texto}"
            )

        try:

            dados = comando.funcao()

            return ResultadoComando(
                status=StatusComando.SUCESSO,
                comando=comando.nome,
                mensagem=f"Comando '{comando.nome}' executado.",
                dados=dados
            )

        except Exception as erro:

            return ResultadoComando(
                status=StatusComando.ERRO,
                comando=comando.nome,
                mensagem=f"Erro ao executar '{comando.nome}': {erro}"
            )


    # AÇÕES

    def ler_tela(self):
        """
        Captura a tela e envia para o OCR.
        """

        # IMPORTANTE:
        # Ajuste estes imports para os nomes que você
        # realmente está utilizando no projeto.

        from .capturador_tela import capturar_tela
        from .leitor_ocr import extrair_texto

        imagem = capturar_tela()

        if imagem is None:

            raise RuntimeError(
                "Não foi possível capturar a tela."
            )

        texto = extrair_texto(imagem)

        return texto


    def abrir_navegador(self):

        webbrowser.open(
            "https://www.google.com"
        )

        return True


    def abrir_bloco_notas(self):

        subprocess.Popen(
            ["notepad.exe"]
        )

        return True


    def mostrar_ajuda(self):

        return [
            comando.descricao
            for comando in self.comandos
        ]


# INSTÂNCIA PRINCIPAL

gerenciador_comandos = GerenciadorComandos()


# FUNÇÃO PÚBLICA

def executar_comando(texto: str) -> ResultadoComando:
    """
    Função utilizada pelos outros módulos da A.S.T.R.A.
    """

    return gerenciador_comandos.executar(texto)