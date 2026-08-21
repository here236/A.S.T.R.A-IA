import os
from datetime import datetime

import speech_recognition as sr

from configs import configuracoes_voz
from .utilitarios_voz import log

'''
    Voz → Texto

    Responsabilidade:
    Captar áudio do microfone
    Converter fala em texto

    Pode usar:
    Whisper
    ou speech_recognition (mais simples)
'''

# Um único Recognizer reaproveitado entre chamadas: ele guarda o
# "limiar de energia" calibrado (o que é silêncio vs. o que é fala),
# recriar ele toda hora faria recalibrar do zero sempre.
_recognizer = sr.Recognizer()


def _gerar_nome_arquivo():

    data = datetime.now().strftime("%Y%m%d-%H%M%S")

    nome = f"audio-{data}.wav"

    return os.path.join(configuracoes_voz.PASTA_AUDIOS, nome)


def ouvir_microfone():
    """
    Grava um trecho de fala do microfone padrão do sistema.

    Fica escutando até detectar silêncio (fim da fala) ou até bater
    o LIMITE_DURACAO_FALA. Salva o áudio capturado em disco (mesmo
    padrão do captura_tela: arquivo com nome baseado em timestamp)
    e devolve o caminho do arquivo.

    Devolve None se não detectar nenhuma fala a tempo, ou se não
    encontrar microfone.
    """

    try:
        with sr.Microphone() as fonte:

            log("Calibrando ruído ambiente...")

            _recognizer.adjust_for_ambient_noise(
                fonte,
                duration=configuracoes_voz.DURACAO_CALIBRACAO_RUIDO
            )

            log("Ouvindo... pode falar.")

            audio = _recognizer.listen(
                fonte,
                timeout=configuracoes_voz.TIMEOUT_ESPERA_FALA,
                phrase_time_limit=configuracoes_voz.LIMITE_DURACAO_FALA
            )

    except sr.WaitTimeoutError:
        log("Nenhuma fala detectada a tempo.", "AVISO")
        return None

    except OSError as erro:
        # Ocorre quando não há nenhum microfone disponível/conectado.
        log(f"Microfone não encontrado: {erro}", "ERRO")
        return None

    caminho_arquivo = _gerar_nome_arquivo()

    with open(caminho_arquivo, "wb") as arquivo:
        arquivo.write(audio.get_wav_data())

    log(f"Áudio capturado: {caminho_arquivo}")

    return caminho_arquivo


def converter_fala_para_texto(audio):
    pass
