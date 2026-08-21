import os
import re


'''
    Entender o usuário

    Responsabilidade:
    Interpretar intenção
    Gerar resposta
    Pode ser:
    Regras simples
    IA (chatbot)
'''

class Interpretador:

    def __init__(self):
        self.ultimo_texto = ""
        self.ultima_intencao = "desconhecido"
        self.ultimos_dados = {}

        self.intencoes = {
            "ler_tela": [
                "leia a tela",
                "ler a tela",
                "leia minha tela",
                "ler minha tela",
                "o que está na tela",
                "o que tem na tela"
            ],

            "abrir_navegador": [
                "abra o navegador",
                "abrir navegador",
                "abra navegador",
                "inicie o navegador"
            ],

            "fechar_navegador": [
                "feche o navegador",
                "fechar navegador",
                "fecha o navegador"
            ],

            "ver_hora": [
                "que horas são",
                "que horas sao",
                "qual é a hora",
                "qual a hora",
                "me diga as horas"
            ],

            "identidade": [
                "quem é você",
                "quem e voce",
                "qual seu nome",
                "qual o seu nome",
                "o que você é",
                "o que voce e"
            ],

            "agradecimento": [
                "obrigado",
                "obrigada",
                "valeu",
                "agradeço"
            ],

            "encerrar": [
                "pode desligar",
                "desligue",
                "encerrar",
                "encerre",
                "até mais",
                "ate mais",
                "tchau"
            ]
        }

    # Entrada

    def processar(self, entrada):
        """
        Processa texto ou áudio e retorna a intenção,
        os dados identificados e a resposta.
        """

        if isinstance(entrada, str):

            if os.path.isfile(entrada):
                texto = self.converter_audio_para_texto(entrada)
            else:
                texto = entrada

        else:
            texto = self.converter_audio_para_texto(entrada)

        if not texto:
            return {
                "texto": "",
                "intencao": "vazio",
                "dados": {},
                "resposta": "Não consegui entender o que você disse."
            }

        texto = self.normalizar_texto(texto)

        self.ultimo_texto = texto

        intencao = self.interpretar_texto(texto)
        dados = self.extrair_dados(texto, intencao)
        resposta = self.gerar_resposta(intencao, dados)

        self.ultima_intencao = intencao
        self.ultimos_dados = dados

        return {
            "texto": texto,
            "intencao": intencao,
            "dados": dados,
            "resposta": resposta
        }

    # Áudio

    def converter_audio_para_texto(self, audio):
        """
        Converte o áudio recebido em texto.

        O reconhecimento de voz pode ser conectado aqui
        posteriormente usando Whisper ou outro modelo.
        """

        if audio is None:
            return ""

        return ""

    # Normalização

    def normalizar_texto(self, texto):
        """
        Padroniza o texto antes da interpretação.
        """

        texto = texto.lower()
        texto = re.sub(r"\s+", " ", texto)
        texto = texto.strip()

        return texto

    # Interpretação

    def interpretar_texto(self, texto):
        """
        Identifica a intenção presente no texto.
        """

        for intencao, frases in self.intencoes.items():

            for frase in frases:

                if frase in texto:
                    return intencao

        return "desconhecido"

    # Extração de dados

    def extrair_dados(self, texto, intencao):
        """
        Extrai informações adicionais presentes no comando.
        """

        dados = {}

        if "abra o site" in texto:

            site = texto.replace("abra o site", "").strip()

            if site:
                dados["site"] = site

        if "pesquise" in texto:

            pesquisa = texto.split("pesquise", 1)[1].strip()

            if pesquisa:
                dados["pesquisa"] = pesquisa

        numeros = re.findall(r"\d+", texto)

        if numeros:
            dados["numeros"] = [
                int(numero)
                for numero in numeros
            ]

        return dados

    # Resposta

    def gerar_resposta(self, intencao, dados=None):
        """
        Gera uma resposta baseada na intenção identificada.
        """

        if dados is None:
            dados = {}

        respostas = {
            "vazio": "Não consegui entender o que você disse.",
            "ler_tela": "Vou analisar o conteúdo da tela.",
            "abrir_navegador": "Abrindo o navegador.",
            "fechar_navegador": "Fechando o navegador.",
            "ver_hora": "Vou verificar o horário.",
            "identidade": "Eu sou a A.S.T.R.A., sua assistente virtual.",
            "agradecimento": "Por nada.",
            "encerrar": "Tudo bem. Até mais.",
            "desconhecido": "Não consegui entender esse comando."
        }

        return respostas.get(
            intencao,
            "Ainda não sei como responder a esse comando."
        )