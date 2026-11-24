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
#   "Ok Astra." sozinho: reconhecido em 0 de 10 sem a dica e em 10 de 10 com ela;
#   frases variadas:     7 de 10 sem a dica e 10 de 10 com ela;
#   e nenhum "Astra" inventado em silêncio, ruído branco, zumbido ou fala alheia.
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


# SÍNTESE DE VOZ (texto -> voz, 100% offline, com o Piper)

# As vozes ficam em "modelos/voz/<nome>/", fora do Git.
PASTA_VOZES = os.path.join(PASTA_MODELOS, "voz")

# Vozes disponíveis. Para baixar a voz escolhida (uma vez, com internet):
#     python -m voz.baixar_voz
# "revisao" fixa a versão exata da voz, para ela não mudar sem você saber.
VOZES_PIPER = {
    "razo": {
        "repositorio": "Lucasllfs/Razo-piper-voice",
        "revisao": "0f95a8d49045ef58a2dc6745b4f5e15db908e4aa",
        "modelo": "pt-BR-razo-medium.onnx",
        "config": "config.json",
    },
}

# Voz usada pela assistente (uma das chaves de VOZES_PIPER).
VOZ_TTS = "razo"

# 1.0 = velocidade normal. 0.8 = mais devagar, 1.3 = mais rápido.
# O Piper aceita de 0.5 a 2.0.
VELOCIDADE_FALA = 1.0

# De 0.0 (mudo) a 1.0 (máximo).
VOLUME_FALA = 1.0

# Silêncio, em segundos, entre uma frase e a seguinte.
PAUSA_ENTRE_FRASES = 0.15

# Máximo de caracteres falados de uma vez. Um texto maior é cortado ao
# final de uma frase. None = sem limite.
LIMITE_CARACTERES_FALA = None


# CONFIRMAÇÃO DE AÇÕES CRÍTICAS (RN03)

# O texto falado e as palavras abaixo passam pela mesma normalização
# (sem acento, sem maiúsculas), então basta escrever de um jeito só.
# Na dúvida ("sim, não") a ação é cancelada: o cancelamento tem prioridade.
PALAVRAS_CONFIRMAR = [
    "sim",
    "pode",
    "pode sim",
    "confirmo",
    "confirmar",
    "isso",
    "claro",
    "positivo",
    "afirmativo",
]

PALAVRAS_CANCELAR = [
    "nao",
    "cancela",
    "cancele",
    "cancelar",
    "negativo",
    "esquece",
    "deixa pra la",
]

# Segundos que a assistente espera pelo "sim" ou "não". Cada nova
# tentativa recomeça a contagem, e o tempo precisa ser maior que a pergunta
# falada + a escuta + a transcrição.
TEMPO_LIMITE_CONFIRMACAO = 20

# Quantas vezes ela repete a pergunta ao não entender, antes de cancelar
# por segurança.
TENTATIVAS_CONFIRMACAO = 2


# PRIVACIDADE DO ÁUDIO (RN08)

# Cada trecho ouvido é gravado em "Audios/" só para ser transcrito. Com False
# (padrão) o arquivo é apagado logo depois de transcrito. Use True apenas
# para depurar o reconhecimento de fala.
MANTER_AUDIOS = False


os.makedirs(PASTA_AUDIOS, exist_ok=True)
os.makedirs(LOCAIS_ARQUIVOS[LOCAL_PADRAO], exist_ok=True)