'''
    Configuração central

    Responsabilidade:
    Idioma
    Sensibilidade do microfone
    Voz usada
'''

import ctypes
import json
import os
import uuid

IDIOMA = "pt-BR"
PALAVRA_ATIVACAO = "assistente"


# CAPTURA DE ÁUDIO (microfone)

# Pasta onde os áudios capturados são salvos (mesmo padrão do
# captura_tela, que salva prints em "Prints/")
PASTA_AUDIOS = "Audios"

# Tempo máximo (segundos) esperando o usuário COMEÇAR a falar,
# antes de desistir. None = espera pra sempre.
TIMEOUT_ESPERA_FALA = 5

# Tempo máximo (segundos) de uma frase, depois de começar a falar.
# Evita que uma frase muito longa (ou ruído contínuo) trave a escuta.
LIMITE_DURACAO_FALA = 15

# Quantos segundos de silêncio ambiente calibrar antes de escutar,
# pra distinguir ruído de fundo de fala de verdade.
DURACAO_CALIBRACAO_RUIDO = 1

# MANIPULAÇÃO DE ARQUIVOS
# Lógica em voz/arquivos_voz.py

# LOCAIS onde a A.S.T.R.A. pode criar, ler e excluir arquivos.
# O nome (à esquerda) é o que o usuário fala: "crie uma pasta fotos
# em downloads". Sempre minúsculo e sem acento.
# Para adicionar um lugar novo, basta uma linha no dicionário.

_HOME = os.path.expanduser("~")

# IDs que o Windows usa para saber onde ficam as pastas do usuário.
_IDS_PASTAS_WINDOWS = {
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
}

# Lugares extras que o usuário quer ensinar à A.S.T.R.A. (opcional).
# Formato: {"jogos": "D:\\Jogos"}. Se o nome já existir abaixo, este
# arquivo vence, então serve também para corrigir um caminho errado.
ARQUIVO_LOCAIS_EXTRAS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "locais_usuario.json"
)


def _perguntar_ao_windows(nome):
    """
    Pergunta ao próprio Windows onde fica a pasta (Desktop, Documents
    ou Downloads). Funciona com OneDrive, pasta em outro disco e
    Windows em qualquer idioma. Devolve None se não conseguir.
    """

    if os.name != "nt":
        return None

    try:
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        id_pasta = uuid.UUID(_IDS_PASTAS_WINDOWS[nome])

        guid = GUID(
            id_pasta.time_low,
            id_pasta.time_mid,
            id_pasta.time_hi_version,
            (ctypes.c_ubyte * 8)(*id_pasta.bytes[8:])
        )

        caminho = ctypes.c_wchar_p()

        resultado = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(caminho)
        )

        if resultado != 0:
            return None

        valor = caminho.value

        ctypes.windll.ole32.CoTaskMemFree(caminho)

        return valor

    except Exception:
        return None


def _pasta_do_usuario(nome, *outros_nomes):
    """
    Acha uma pasta padrão do Windows (Desktop, Documents, Downloads).

    1) Pergunta ao Windows, que sempre sabe o caminho certo.
    2) Se não der, tenta os lugares comuns (OneDrive e a pasta do usuário).
    """

    oficial = _perguntar_ao_windows(nome)

    if oficial and os.path.isdir(oficial):
        return oficial

    bases = []

    onedrive = os.environ.get("OneDrive")

    if onedrive:
        bases.append(onedrive)

    bases.append(_HOME)

    candidatos = [
        os.path.join(base, nome_pasta)
        for base in bases
        for nome_pasta in (nome, *outros_nomes)
    ]

    for caminho in candidatos:
        if os.path.isdir(caminho):
            return caminho

    return candidatos[-1]


def _ler_locais_extras():
    """
    Lê o locais_usuario.json, se existir. Arquivo ausente ou com
    erro é ignorado, e a A.S.T.R.A. usa só os lugares padrão.
    """

    try:
        with open(ARQUIVO_LOCAIS_EXTRAS, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (OSError, ValueError):
        return {}

    if not isinstance(dados, dict):
        return {}

    return {
        str(nome).strip().lower(): os.path.expandvars(str(caminho))
        for nome, caminho in dados.items()
    }


LOCAIS_ARQUIVOS = {
    "astra": os.path.join(_HOME, "ASTRA"),
    "area de trabalho": _pasta_do_usuario("Desktop", "Área de Trabalho"),
    "documentos": os.path.join(
        _pasta_do_usuario("Documents", "Documentos"), "ASTRA"
    ),
    "downloads": _pasta_do_usuario("Downloads"),
}

LOCAIS_ARQUIVOS.update(_ler_locais_extras())

# Onde salva quando o usuário não diz o lugar.
LOCAL_PADRAO = "astra"


# CONFIRMAÇÃO DE AÇÕES CRÍTICAS (RN03)
# Lógica em voz/confirmacao_voz.py

# Segundos que a A.S.T.R.A. espera pelo "sim" ou "não" antes de
# desistir e cancelar a ação sozinha.
TEMPO_LIMITE_CONFIRMACAO = 15

# Quantas vezes repete a pergunta quando não entende a resposta.
# Depois disso, cancela por segurança.
TENTATIVAS_CONFIRMACAO = 1

# Palavras já sem acento (o texto passa por normalizar_texto).
# Se aparecer palavra dos dois lados ("sim, não"), vale o CANCELAR.
PALAVRAS_CONFIRMAR = [
    "sim",
    "confirmo",
    "confirmar",
    "confirmado",
    "pode",
    "positivo"
]

PALAVRAS_CANCELAR = [
    "nao",
    "cancela",
    "cancele",
    "cancelar",
    "negativo",
    "deixa",
    "esquece"
]

os.makedirs(PASTA_AUDIOS, exist_ok=True)
os.makedirs(LOCAIS_ARQUIVOS[LOCAL_PADRAO], exist_ok=True)