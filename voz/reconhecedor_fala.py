import os
import time
from datetime import datetime

import speech_recognition as sr

from configs import configuracoes_voz
from .utilitarios_voz import log

'''
    Voz → Texto

    Responsabilidade:
    Captar áudio do microfone
    Converter fala em texto

    Captura: speech_recognition (microfone)
    Transcrição: Whisper via faster-whisper, 100% offline.
    O modelo é baixado uma única vez (python -m voz.baixar_modelo) e
    depois carregado da pasta local, sem nenhum acesso à rede.
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


class ModeloNaoEncontradoError(Exception):
    """
    O modelo de reconhecimento de fala ainda não foi baixado.
    É um problema de instalação (não de fala), por isso é uma exceção
    e não um texto vazio: assim não se confunde com "ninguém falou".
    """


# O modelo demora alguns segundos para carregar. Carregamos uma vez e
# reaproveitamos em todas as transcrições seguintes.
_modelo = None


def _caminho_modelo():

    return os.path.join(
        configuracoes_voz.PASTA_MODELOS,
        configuracoes_voz.MODELO_STT
    )


def carregar_modelo():
    """
    Carrega o modelo de reconhecimento de fala na memória.

    Pode ser chamada na inicialização do programa para que a primeira
    fala do usuário não espere o carregamento. Se não for, a primeira
    chamada de converter_fala_para_texto() carrega sozinha.
    """

    global _modelo

    if _modelo is not None:
        return _modelo

    caminho = _caminho_modelo()

    if not os.path.isfile(os.path.join(caminho, "model.bin")):

        raise ModeloNaoEncontradoError(
            f"Modelo '{configuracoes_voz.MODELO_STT}' não encontrado em:\n"
            f"    {caminho}\n"
            "Baixe uma vez (só nesse passo é preciso internet) com:\n"
            "    python -m voz.baixar_modelo"
        )

    # Importado aqui (e não no topo) porque a biblioteca é pesada para
    # importar, e quem só quer gravar áudio não deveria pagar esse custo.
    from faster_whisper import WhisperModel

    log(f"Carregando modelo de voz '{configuracoes_voz.MODELO_STT}'...")

    inicio = time.perf_counter()

    # Apontar para uma pasta local (em vez de um nome como "small")
    # garante que a biblioteca nunca tente baixar nada da internet.
    _modelo = WhisperModel(
        caminho,
        device=configuracoes_voz.DISPOSITIVO_STT,
        compute_type=configuracoes_voz.TIPO_COMPUTACAO_STT,
        local_files_only=True
    )

    log(f"Modelo carregado em {time.perf_counter() - inicio:.1f}s.")

    return _modelo


def converter_fala_para_texto(audio):
    """
    Transcreve um arquivo de áudio (o caminho devolvido por
    ouvir_microfone) para texto, sem usar internet.

    Devolve o texto reconhecido, ou "" se não houve fala reconhecível
    ou se ocorreu algum erro durante a transcrição.

    Levanta ModeloNaoEncontradoError se o modelo ainda não foi baixado.
    """

    if not audio or not os.path.isfile(audio):

        log(f"Arquivo de áudio não encontrado: {audio}", "ERRO")
        return ""

    modelo = carregar_modelo()

    inicio = time.perf_counter()

    try:

        segmentos, _ = modelo.transcribe(
            audio,
            language=configuracoes_voz.IDIOMA_STT,
            beam_size=configuracoes_voz.BEAM_SIZE_STT,
            # Ignora os trechos de silêncio antes de transcrever. É o
            # que mais evita o Whisper inventar texto em cima de ruído.
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            # Cada gravação é um comando curto e independente: usar o
            # que foi dito antes só aumentaria o risco de repetições.
            condition_on_previous_text=False
        )

        # "segmentos" é um gerador: a transcrição de verdade acontece
        # enquanto ele é percorrido, por isso isto fica dentro do try.
        partes = [
            segmento.text.strip()
            for segmento in segmentos
            if segmento.no_speech_prob < configuracoes_voz.LIMIAR_SEM_FALA
        ]

    except Exception as erro:

        log(f"Erro ao transcrever o áudio: {erro}", "ERRO")
        return ""

    texto = " ".join(parte for parte in partes if parte).strip()

    duracao = time.perf_counter() - inicio

    if texto:
        log(f"Transcrito em {duracao:.1f}s: {texto}")
    else:
        log("Nenhuma fala reconhecida no áudio.", "AVISO")

    return texto


def ouvir_e_transcrever():
    """
    Atalho: grava do microfone e já devolve o texto falado.
    Devolve "" se ninguém falou, ou se não houve microfone.
    """

    audio = ouvir_microfone()

    if audio is None:
        return ""

    return converter_fala_para_texto(audio)


# TESTES

if __name__ == "__main__":

    print("Fale alguma coisa depois do aviso 'Ouvindo...'")

    caminho = ouvir_microfone()

    if not caminho:
        print("Não foi possível capturar áudio (veja o motivo no log acima).")

    else:
        print(f"Áudio salvo em: {caminho}")

        try:
            texto = converter_fala_para_texto(caminho)

        except ModeloNaoEncontradoError as erro:
            print(f"\n{erro}")

        else:
            if texto:
                print(f"\nVocê disse: {texto!r}")
            else:
                print("\nNão reconheci nenhuma fala.")
