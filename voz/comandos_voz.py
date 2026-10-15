import subprocess
import webbrowser

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional
from urllib.parse import quote_plus

from .utilitarios_voz import normalizar_texto

"""
Ações específicas da A.S.T.R.A.

Responsabilidade:
    Único reconhecedor de comandos do projeto: interpretar comandos
    conhecidos e executar as ações correspondentes.

Exemplos:
    "leia a tela"
    "abra o navegador"
    "pesquise receita de bolo"
    "que horas são"

Este módulo NÃO é responsável por:
    - Reconhecimento de voz
    - OCR
    - Inteligência artificial / conversa livre
    - Captura de áudio

Ele recebe um texto já reconhecido e decide qual ação executar.
Quando nenhum comando é reconhecido, o resultado vem com status
NAO_ENCONTRADO e quem orquestra (voz_principal) pode encaminhar o
texto para processador_linguagem, que cuida da conversa.
"""


# TIPOS DE RESULTADO

class StatusComando(Enum):
    SUCESSO = "sucesso"
    NAO_ENCONTRADO = "nao_encontrado"
    ERRO = "erro"


@dataclass
class RespostaAcao:
    """
    O que uma ação devolve depois de executada.

    fala:     frase pensada para ser FALADA ao usuário (TTS).
    dados:    informação extra para quem chamou (ex: texto lido da tela).
    encerrar: True quando a ação pede o fim da sessão (ex: "tchau").
    """

    fala: str = ""
    dados: Optional[object] = None
    encerrar: bool = False


@dataclass
class ResultadoComando:
    """
    Resultado da execução de um comando.

    mensagem:        texto de log/depuração (NÃO é para falar em voz alta).
    resposta_falada: o que o sintetizador de voz deve dizer ao usuário.
    encerrar:        True quando a sessão deve terminar.
    """

    status: StatusComando
    comando: str = ""
    mensagem: str = ""
    dados: Optional[object] = None
    resposta_falada: str = ""
    encerrar: bool = False


# DEFINIÇÃO DE UM COMANDO

@dataclass
class Comando:
    """
    Representa um comando que a A.S.T.R.A. sabe executar.

    A função recebe o parâmetro falado depois da expressão que ativou
    o comando. Ex: em "pesquise receita de bolo", o parâmetro é
    "receita de bolo". Comandos sem parâmetro apenas ignoram o valor.
    """

    nome: str
    palavras_chave: list[str]
    funcao: Callable[[str], RespostaAcao]
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
        funcao: Callable[[str], RespostaAcao],
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

        # Frases sem acento: o texto falado e as palavras-chave passam
        # pela mesma normalização, então não é preciso cadastrar a
        # versão com e sem acento.

        self.registrar(
            nome="ler_tela",
            palavras_chave=[
                "leia a tela",
                "ler a tela",
                "leia minha tela",
                "ler minha tela",
                "o que tem na tela",
                "o que esta na tela",
                "descreva a tela"
            ],
            funcao=self.ler_tela,
            descricao="Ler o conteúdo visível da tela."
        )

        self.registrar(
            nome="abrir_navegador",
            palavras_chave=[
                "abra o navegador",
                "abrir o navegador",
                "abra navegador",
                "abrir navegador",
                "inicie o navegador"
            ],
            funcao=self.abrir_navegador,
            descricao="Abrir o navegador."
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
            descricao="Abrir o Bloco de Notas."
        )

        self.registrar(
            nome="abrir_site",
            palavras_chave=[
                "abra o site",
                "abrir o site"
            ],
            funcao=self.abrir_site,
            descricao="Abrir um site. Diga, por exemplo: abra o site youtube."
        )

        self.registrar(
            nome="pesquisar",
            palavras_chave=[
                "pesquise",
                "pesquisar",
                "busque",
                "buscar"
            ],
            funcao=self.pesquisar,
            descricao="Pesquisar na internet. Diga, por exemplo: pesquise receita de bolo."
        )

        self.registrar(
            nome="ver_hora",
            palavras_chave=[
                "que horas sao",
                "qual a hora",
                "qual e a hora",
                "me diga as horas"
            ],
            funcao=self.ver_hora,
            descricao="Dizer as horas."
        )

        self.registrar(
            nome="identidade",
            palavras_chave=[
                "quem e voce",
                "qual seu nome",
                "qual o seu nome",
                "o que voce e"
            ],
            funcao=self.dizer_identidade,
            descricao="Dizer quem eu sou."
        )

        self.registrar(
            nome="agradecimento",
            palavras_chave=[
                "obrigado",
                "obrigada",
                "valeu",
                "agradeco"
            ],
            funcao=self.responder_agradecimento,
            descricao="Responder a um agradecimento."
        )

        self.registrar(
            nome="encerrar",
            palavras_chave=[
                "pode desligar",
                "desligue",
                "encerrar",
                "encerre",
                "ate mais",
                "tchau"
            ],
            funcao=self.encerrar,
            descricao="Encerrar a conversa."
        )

        self.registrar(
            nome="ajuda",
            palavras_chave=[
                "ajuda",
                "o que voce pode fazer",
                "quais comandos voce conhece"
            ],
            funcao=self.mostrar_ajuda,
            descricao="Listar o que eu sei fazer."
        )


    # LOCALIZAR COMANDO

    def encontrar_comando(
        self,
        texto: str
    ) -> tuple[Optional[Comando], str]:
        """
        Procura qual comando o texto pede.

        Retorna (comando, expressão encontrada). Sem correspondência,
        retorna (None, "").

        A expressão encontrada é devolvida para que o parâmetro do
        comando possa ser extraído do que veio depois dela.
        """

        texto = normalizar_texto(texto)

        if not texto:
            return None, ""

        # As palavras só casam inteiras: assim "ajuda" não dispara
        # dentro de "ajudante", nem "valeu" dentro de outra palavra.
        texto_delimitado = f" {texto} "

        melhor_comando = None
        melhor_expressao = ""

        for comando in self.comandos:

            for palavra in comando.palavras_chave:

                palavra = normalizar_texto(palavra)

                if f" {palavra} " in texto_delimitado:

                    # Quanto maior a expressão encontrada,
                    # maior a prioridade.
                    if len(palavra) > len(melhor_expressao):

                        melhor_expressao = palavra
                        melhor_comando = comando

        return melhor_comando, melhor_expressao


    # PARÂMETRO

    @staticmethod
    def _extrair_parametro(texto: str, expressao: str) -> str:
        """
        Devolve o que foi falado depois da expressão do comando.

        Usa a mesma regra de "palavra inteira" do encontrar_comando,
        para não cortar o texto no lugar errado quando a expressão
        também aparece dentro de outra palavra.
        """

        texto_delimitado = f" {normalizar_texto(texto)} "

        inicio = texto_delimitado.index(f" {expressao} ") + 1

        return texto_delimitado[inicio + len(expressao):].strip()


    # EXECUTAR

    def executar(self, texto: str) -> ResultadoComando:

        if not texto:

            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                mensagem="Nenhum comando foi recebido."
            )

        comando, expressao = self.encontrar_comando(texto)

        if comando is None:

            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                mensagem=f"Não reconheci o comando: {texto}"
            )

        # Tudo que foi falado depois da expressão do comando
        # ("pesquise receita de bolo" -> "receita de bolo").
        parametro = self._extrair_parametro(texto, expressao)

        try:

            resposta = comando.funcao(parametro)

            return ResultadoComando(
                status=StatusComando.SUCESSO,
                comando=comando.nome,
                mensagem=f"Comando '{comando.nome}' executado.",
                dados=resposta.dados,
                resposta_falada=resposta.fala,
                encerrar=resposta.encerrar
            )

        except Exception as erro:

            return ResultadoComando(
                status=StatusComando.ERRO,
                comando=comando.nome,
                mensagem=f"Erro ao executar '{comando.nome}': {erro}",
                resposta_falada="Não consegui executar esse comando."
            )


    # AÇÕES

    def ler_tela(self, parametro: str = "") -> RespostaAcao:
        """
        Captura a tela e envia para o OCR.
        """

        # Importados aqui dentro (e não no topo) porque carregar o
        # módulo de captura exige tela e Tesseract instalados, e o
        # reconhecimento de comandos não deveria depender disso para
        # funcionar nem para ser testado.
        from captura_tela.capturador_tela import capturar_tela
        from captura_tela.leitor_ocr import extrair_texto

        imagem = capturar_tela()

        if imagem is None:

            raise RuntimeError(
                "Não foi possível capturar a tela."
            )

        texto = extrair_texto(imagem)

        if not texto:

            return RespostaAcao(
                fala="Não encontrei nenhum texto na tela.",
                dados=""
            )

        return RespostaAcao(fala=texto, dados=texto)


    def abrir_navegador(self, parametro: str = "") -> RespostaAcao:

        webbrowser.open(
            "https://www.google.com"
        )

        return RespostaAcao(fala="Abrindo o navegador.")


    def abrir_bloco_notas(self, parametro: str = "") -> RespostaAcao:

        subprocess.Popen(
            ["notepad.exe"]
        )

        return RespostaAcao(fala="Abrindo o Bloco de Notas.")


    def abrir_site(self, parametro: str = "") -> RespostaAcao:

        # Aceita "youtube" ou "youtube.com" (a fala já vem sem pontuação,
        # então quem diz o domínio completo costuma ficar com ele
        # separado por espaço; juntamos tudo).
        site = parametro.replace(" ", "")

        if not site:

            return RespostaAcao(fala="Qual site você quer abrir?")

        if "." not in site:

            site = f"{site}.com"

        webbrowser.open(f"https://www.{site}")

        return RespostaAcao(
            fala=f"Abrindo o site {parametro}.",
            dados=site
        )


    def pesquisar(self, parametro: str = "") -> RespostaAcao:

        if not parametro:

            return RespostaAcao(fala="O que você quer pesquisar?")

        webbrowser.open(
            f"https://www.google.com/search?q={quote_plus(parametro)}"
        )

        return RespostaAcao(
            fala=f"Pesquisando {parametro}.",
            dados=parametro
        )


    def ver_hora(self, parametro: str = "") -> RespostaAcao:

        agora = datetime.now()

        hora = agora.hour
        minuto = agora.minute

        palavra_hora = "hora" if hora == 1 else "horas"

        if minuto == 0:

            fala = f"Agora são {hora} {palavra_hora} em ponto."

        else:

            palavra_minuto = "minuto" if minuto == 1 else "minutos"

            fala = (
                f"Agora são {hora} {palavra_hora} "
                f"e {minuto} {palavra_minuto}."
            )

        return RespostaAcao(fala=fala, dados=agora)


    def dizer_identidade(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(
            fala="Eu sou a A.S.T.R.A., sua assistente virtual."
        )


    def responder_agradecimento(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala="Por nada.")


    def encerrar(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(
            fala="Tudo bem. Até mais.",
            encerrar=True
        )


    def mostrar_ajuda(self, parametro: str = "") -> RespostaAcao:

        descricoes = [
            comando.descricao
            for comando in self.comandos
        ]

        return RespostaAcao(
            fala="Eu posso: " + " ".join(descricoes),
            dados=descricoes
        )


# INSTÂNCIA PRINCIPAL

gerenciador_comandos = GerenciadorComandos()


# FUNÇÃO PÚBLICA

def executar_comando(texto: str) -> ResultadoComando:
    """
    Função utilizada pelos outros módulos da A.S.T.R.A.
    """

    return gerenciador_comandos.executar(texto)
