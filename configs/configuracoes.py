"""
Centraliza tudo
* Configurações do sistema
* Baixar o Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
"""

import os


# CONFIGURAÇÕES GERAIS DO SISTEMA DE IA ACESSÍVEL


# 1. CAMINHOS DO SISTEMA


# Lista de lugares onde o Tesseract costuma ser instalado
POSSIVEIS_CAMINHOS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]

# Função que procura automaticamente
def encontrar_tesseract():
    for caminho in POSSIVEIS_CAMINHOS:
        if os.path.exists(caminho):
            return caminho
    return None

# Tenta achar automaticamente
TESSERACT_PATH = encontrar_tesseract()

# Se não achou, avisa o usuário e para o programa
if TESSERACT_PATH is None:
    print("=" * 50)
    print("⚠️  ATENÇÃO: Tesseract não encontrado!")
    print("Instale em: https://github.com/UB-Mannheim/tesseract/wiki")
    print("Ou defina o caminho manualmente em config.py")
    print("=" * 50)
    raise FileNotFoundError("Tesseract não encontrado. Instale antes de continuar.")

# Pasta raiz do projeto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pasta onde os logs serão salvos
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Pasta para salvar screenshots (útil pra debug)
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")

# Cria as pastas automaticamente se não existirem
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(SCREENSHOT_DIR, exist_ok=True)



# 2. CONFIGURAÇÕES DE OCR(reconhecimento optico de caracteres)


# Idioma do OCR
IDIOMA_OCR = "por"  # "por" = português, "eng" = inglês

# Modo de segmentação de página do Tesseract
# 3 = automático (recomendado pra telas)
PSM_MODE = 3

# Configuração extra do Tesseract
TESSERACT_CONFIG = f"--psm {PSM_MODE}"



# 3. CONFIGURAÇÕES DE CAPTURA DE TELA


# Qual monitor capturar (1 = principal)
MONITOR_ALVO = 1

# Intervalo entre capturas em segundos
INTERVALO_CAPTURA = 2.0

# Salvar screenshot automaticamente? (True/False)
SALVAR_SCREENSHOT = False

# Converter imagem pra escala de cinza antes do OCR?
# Melhora a precisão do OCR
USAR_CINZA = True



# 4. CONFIGURAÇÕES DE LOG


# Nível de log: "DEBUG", "INFO", "WARNING", "ERROR"
NIVEL_LOG = "INFO"

# Salvar logs em arquivo?
SALVAR_LOG = True

# Nome do arquivo de log
NOME_LOG = "sistema.log"

# Caminho completo do log
CAMINHO_LOG = os.path.join(LOG_DIR, NOME_LOG)



# 5. CONFIGURAÇÕES DE VOZ (pra quando implementar STT/TTS)


# Idioma da voz
IDIOMA_VOZ = "pt-BR"

# Velocidade da fala (palavras por minuto)
VELOCIDADE_VOZ = 150

# Volume (0.0 a 1.0)
VOLUME_VOZ = 1.0



# 6. CONFIGURAÇÕES DA IA / NLP (pra quando integrar)


# Modelo de IA a usar futuramente
MODELO_IA = "aleTaVendoIssoAi"

# Temperatura da resposta (0 = preciso, 1 = criativo)
TEMPERATURA_IA = 0.3

# Máximo de tokens por resposta
MAX_TOKENS = 1000



# 7. MODO DE EXECUÇÃO


# Modo debug: mostra mais informações no terminal
MODO_DEBUG = False

# Rodar em loop contínuo ou uma vez só?
MODO_CONTINUO = True