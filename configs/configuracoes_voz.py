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


# CONFIRMAÇÃO DE AÇÕES CRÍTICAS (RN03)
# Lógica em voz/confirmacao_voz.py

# Segundos que a A.S.T.R.A. espera pelo "sim" ou "não" antes de
# desistir e cancelar a ação sozinha.
TEMPO_LIMITE_CONFIRMACAO = 15

# Quantas vezes repete a pergunta quando não entende a resposta.
# Depois disso, cancela por segurança.
TENTATIVAS_CONFIRMACAO = 1

# Palavras sem acento (o texto passa por normalizar_texto).
# Se aparecer palavra dos dois lados ("sim, não"), vale o CANCELAR.
PALAVRAS_CONFIRMAR = ["sim", "confirmo", "confirmar", "confirmado", "pode", "positivo"]

PALAVRAS_CANCELAR = ["nao", "cancela", "cancele", "cancelar", "negativo", "deixa", "esquece"]


# RECONHECIMENTO DE FALA (voz -> texto, 100% offline)

# Os modelos ficam numa pasta "modelos/" na raiz do projeto (ancorada
# no arquivo, e não na pasta onde o programa é executado, para o modelo
# ser sempre encontrado de onde quer que o projeto seja iniciado).
_RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_MODELOS = os.path.join(_RAIZ_PROJETO, "modelos")

# Tamanho do modelo Whisper. Quanto maior, mais preciso e mais lento:
#   "base"   ~140 MB  - rápido, erra mais em português
#   "small"  ~460 MB  - bom equilíbrio (padrão)
#   "medium" ~1,5 GB  - mais preciso, bem mais lento em CPU
# Depois de trocar, rode de novo: python -m voz.baixar_modelo
MODELO_STT = "small"

# "cpu" funciona em qualquer máquina. "int8" é o modo mais leve e
# rápido em CPU, com perda de precisão desprezível.
DISPOSITIVO_STT = "cpu"
TIPO_COMPUTACAO_STT = "int8"

# Idioma que o Whisper deve esperar ("pt-BR" -> "pt").
IDIOMA_STT = IDIOMA.split("-")[0]

# Dica de vocabulário para o Whisper: texto de exemplo que ele usa como
# "contexto" e que o faz escrever "Astra" do jeito certo, em vez de "Aster",
# "Hasta" ou "já está". Medido com a voz da Razo (voz sintética, não humana):
#   "Ok Astra." sozinho: 0 de 10 sem a dica; 32 de 34 com ela (duas amostras);
#   frases variadas:     7 de 10 sem a dica e 10 de 10 com ela;
#   nenhum "Astra" inventado em silêncio, ruído branco ou zumbido.
# Custo: frases parecidas com o chamado podem ser escritas como "Ok Astra"
# ("Ok, já está." virou "Ok, Astra." em 1 de 8 vezes). Variações da dica foram
# comparadas (beam maior, dica repetida, "Assistente Astra. Ok Astra.") e
# nenhuma foi melhor de forma consistente.
# Mantenha curto. None desliga. Para conferir de novo depois de mexer aqui:
#     python -m voz.autoteste
DICA_VOCABULARIO_STT = "Ok Astra."

# 1 = mais rápido. Valores maiores (ex: 5) podem acertar um pouco mais,
# mas demoram mais para transcrever.
BEAM_SIZE_STT = 1

# Trechos em que o modelo acha que NÃO há fala (probabilidade acima
# deste valor) são descartados. Evita o Whisper "inventar" frases em
# cima de ruído ou silêncio.
LIMIAR_SEM_FALA = 0.6

# SÍNTESE DE VOZ (Kokoro-82M ONNX, CPU, offline após download)
PASTA_VOZES = os.path.join(PASTA_MODELOS, "voz")
VOZES_KOKORO = {
    "pf_dora": {
        "repositorio": "thewh1teagle/kokoro-onnx",
        "revisao": "model-files-v1.1",
        "modelo": "kokoro-v1.0.onnx",
        "vozes": "voices-v1.0.bin",
        "idioma": "pt-br",
    },
}
VOZ_TTS = "pf_dora"
VELOCIDADE_FALA = 1.0

# De 0.0 (mudo) a 1.0 (máximo).
VOLUME_FALA = 1.0

# Silêncio, em segundos, entre uma frase e a seguinte.
PAUSA_ENTRE_FRASES = 0.15

# Máximo de caracteres falados de uma vez. Um texto maior é cortado ao
# final de uma frase. None = sem limite.
LIMITE_CARACTERES_FALA = None

# CONVERSA CONTÍNUA

# True: depois de executar um comando a assistente continua ativa por alguns
# segundos (a janela do detector de ativação), e o próximo comando não
# precisa de "Ok Astra". Nessa janela, uma fala que não é comando é ignorada
# em silêncio (para não responder à conversa dos outros).
# False: é preciso chamar "Ok Astra" antes de cada comando.
MANTER_ATIVA_APOS_COMANDO = True


# PRIVACIDADE DO ÁUDIO (RN08)

# Cada trecho ouvido é gravado em "Audios/" só para ser transcrito. Com False
# (padrão) o arquivo é apagado logo depois de transcrito. Use True apenas
# para depurar o reconhecimento de fala.
MANTER_AUDIOS = False



# MANIPULAÇÃO DE ARQUIVOS
# Lógica em arquivos/gerenciador_arquivos.py

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


# PESQUISA NA WEB
# Lógica em pesquisa/pesquisa_web.py (rede) e voz/pesquisa_voz.py (voz)

# Como pesquisar:
#   "leve"       só pedidos HTTP diretos. Não abre navegador. Para PCs fracos.
#   "automatico" tenta o leve e, se os sites bloquearem, usa o
#                navegador invisível (precisa do Playwright e do Edge/Chrome).
#   "navegador"  usa sempre o navegador invisível.
MODO_BUSCA = "automatico"

# Ordem dos buscadores. Opções: "duckduckgo", "bing".
MOTORES_DE_BUSCA = ["duckduckgo", "bing"]

# Quantos resultados guardar e quantos falar em voz alta.
QUANTIDADE_RESULTADOS = 5
RESULTADOS_FALADOS = 3

# Segundos esperando cada site responder.
TEMPO_LIMITE_REDE = 12

# Tamanho máximo de uma página baixada (bytes).
LIMITE_PAGINA_BYTES = 2_000_000

# Quantas páginas ler quando o pedido é "pesquise ... e faça um documento".
PAGINAS_PARA_LER = 3

# Tamanho de cada trecho lido em voz ("leia o resultado 1").
CARACTERES_POR_LEITURA = 900

# Quanto tempo (segundos) uma busca repetida fica guardada.
VALIDADE_CACHE_BUSCA = 600

os.makedirs(PASTA_AUDIOS, exist_ok=True)
os.makedirs(LOCAIS_ARQUIVOS[LOCAL_PADRAO], exist_ok=True)