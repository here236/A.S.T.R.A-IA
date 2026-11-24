import sys
import time
import types
import wave
import tempfile
import os
from unittest import mock

from .utilitarios_voz import log

'''
    Autoteste do reconhecimento de voz, SEM microfone

    A voz da assistente (Razo) fala algumas frases, o Whisper as transcreve e
    o texto passa pela ativação e pelos comandos reais. Mostra, para cada
    frase, o que o Whisper escreveu e o que a assistente fez.

    Serve para conferir o "Ok Astra" e os comandos depois de mexer no
    detector, na dica de vocabulário (DICA_VOCABULARIO_STT) ou nas
    palavras-chave dos comandos.

        python -m voz.autoteste

    Precisa da voz e do modelo de fala baixados. Nada é executado de verdade:
    navegador, taskkill e captura de tela são simulados.

    Limite: a fala vem de uma voz sintética, limpa. É um bom alarme (se aqui
    falha, no microfone falha), mas não prova que funcione com a sua voz.
'''

# (o que a Razo fala, o que a assistente deve fazer)
#   "ignorar":  não é com ela        "chamado": só foi chamada
#   "conversa": respondeu conversando    outro nome: o comando executado
CASOS = [
    ("Ok Astra, que horas são?", "ver_hora"),
    ("Ok Astra.", "chamado"),
    ("Ok Astra, leia a tela.", "ler_tela"),
    ("Astra, abra o navegador.", "abrir_navegador"),
    ("Ok Astra, pesquise receita de bolo.", "pesquisar"),
    ("Ok Astra, abra o site youtube.", "abrir_site"),
    ("Ok Astra, quem é você?", "identidade"),
    ("Ok Astra, feche o navegador.", "fechar_navegador"),
    ("Sim.", "fechar_navegador"),
    ("Bom dia, Astra!", "conversa"),
    ("Hoje o dia está bonito.", "ignorar"),
    ("Ok Astra, tchau.", "encerrar"),
]


def _falar_para_arquivo(voz, texto, caminho):
    """
    Sintetiza 'texto' com a voz da assistente e grava em .wav, com uma
    pausa antes e depois (como numa gravação de microfone).
    """

    import numpy as np

    from . import sintetizador_voz

    configuracao = sintetizador_voz._montar_configuracao(voz, None)

    pcm = b"".join(
        trecho.audio_int16_bytes
        for trecho in voz.synthesize(texto, configuracao)
    )

    silencio = b"\x00\x00" * int(voz.config.sample_rate * 0.4)

    with wave.open(caminho, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(voz.config.sample_rate)
        arquivo.writeframes(silencio + pcm + silencio)


def _resultado(saida, ultimo):
    """
    Resume o que a assistente fez, no mesmo vocabulário de CASOS.
    """

    from .comandos_voz import StatusComando
    from .processador_linguagem import RESPOSTA_PADRAO

    if saida is None:
        return "ignorar"

    if saida.aguardar_comando:
        return "chamado"

    if ultimo and ultimo[0].status != StatusComando.NAO_ENCONTRADO:
        return ultimo[0].comando

    if saida.fala == RESPOSTA_PADRAO:
        return "não entendeu"

    return "conversa"


def executar_autoteste():

    from . import reconhecedor_fala, sintetizador_voz, voz_principal
    from .ativacao_voz import DetectorAtivacao
    from .comandos_voz import GerenciadorComandos

    print("Carregando a voz e o modelo de fala...")

    voz = sintetizador_voz.carregar_voz()
    reconhecedor_fala.carregar_modelo()

    gerenciador = GerenciadorComandos()
    ultimo = []

    def executar(texto):
        resultado = gerenciador.executar(texto)
        ultimo[:] = [resultado]
        return resultado

    capturador = types.ModuleType("captura_tela.capturador_tela")
    capturador.capturar_tela = lambda: "Prints/autoteste.png"
    leitor = types.ModuleType("captura_tela.leitor_ocr")
    leitor.extrair_texto = lambda caminho: "texto da tela"
    pacote = types.ModuleType("captura_tela")
    pacote.__path__ = []

    pasta = tempfile.mkdtemp()

    acertos = chamados = chamadas_esperadas = 0

    print(f"\n{'a Razo falou':36} | {'o Whisper escreveu':38} | resultado")
    print("-" * 110)

    with mock.patch("webbrowser.open"), \
            mock.patch("subprocess.run", lambda *a, **k: types.SimpleNamespace(returncode=0)), \
            mock.patch("subprocess.Popen"), \
            mock.patch.dict(sys.modules, {
                "captura_tela": pacote,
                "captura_tela.capturador_tela": capturador,
                "captura_tela.leitor_ocr": leitor}), \
            mock.patch.object(voz_principal, "log", lambda *a, **k: None):

        assistente = voz_principal.AssistenteVoz(
            ouvir=lambda: "",
            falar=lambda texto: True,
            executar=executar,
            aguardando_confirmacao=gerenciador.confirmacao.aguardando,
            detector=DetectorAtivacao()
        )

        for numero, (frase, esperado) in enumerate(CASOS):

            ultimo.clear()

            arquivo = os.path.join(pasta, f"{numero}.wav")
            _falar_para_arquivo(voz, frase, arquivo)

            texto = reconhecedor_fala.converter_fala_para_texto(arquivo)

            saida = assistente.processar(texto)

            if saida is not None and saida.aguardar_comando:
                assistente.detector.ativar()

            obtido = _resultado(saida, ultimo)

            ok = obtido == esperado
            acertos += ok

            if esperado not in ("ignorar", "conversa"):
                chamadas_esperadas += 1
                chamados += obtido != "ignorar"

            marca = "ok " if ok else "ERRO"

            print(f"{frase:36} | {texto!r:38} | {marca} {obtido} (esperado: {esperado})")

            os.remove(arquivo)

    print(f"\nChamado reconhecido em {chamados} de {chamadas_esperadas} frases com 'Ok Astra'.")
    print(f"Resultado esperado em {acertos} de {len(CASOS)} frases.")

    return 0 if acertos == len(CASOS) else 1


if __name__ == "__main__":

    try:
        raise SystemExit(executar_autoteste())

    except Exception as erro:

        # Mais comum: a voz ou o modelo de fala ainda não foram baixados.
        print(f"\n{erro}")
        raise SystemExit(1)
