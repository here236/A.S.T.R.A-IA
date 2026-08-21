'''
    Configuração central

    Responsabilidade:
    Idioma
    Sensibilidade do microfone
    Voz usada
'''

import os

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

os.makedirs(PASTA_AUDIOS, exist_ok=True)
