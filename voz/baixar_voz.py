import argparse
import os

from configs import configuracoes_voz
from .utilitarios_voz import log

'''
    Baixa a voz da assistente (Piper) para o computador.

    Rode UMA vez por máquina, com internet:

        python -m voz.baixar_voz

    Depois disso a voz funciona 100% offline: o programa carrega os
    arquivos da pasta "modelos/voz/" e nunca mais acessa a rede.
    A voz usada é definida em configs/configuracoes_voz.py (VOZ_TTS).
'''


def baixar_voz(nome=None):

    nome = nome or configuracoes_voz.VOZ_TTS

    info = configuracoes_voz.VOZES_PIPER.get(nome)

    if info is None:

        log(
            f"Voz '{nome}' desconhecida. "
            f"Opções: {', '.join(configuracoes_voz.VOZES_PIPER)}",
            "ERRO"
        )
        return False

    destino = os.path.join(configuracoes_voz.PASTA_VOZES, nome)

    modelo = os.path.join(destino, info["modelo"])
    configuracao = os.path.join(destino, info["config"])

    if os.path.isfile(modelo) and os.path.isfile(configuracao):

        log(f"A voz '{nome}' já está baixada em: {destino}")
        return _verificar(nome)

    # Importado aqui para o erro, se o pacote não estiver instalado,
    # aparecer com uma mensagem clara em vez de quebrar o import.
    try:
        from huggingface_hub import snapshot_download

    except ImportError:

        log(
            "Pacote 'huggingface_hub' não encontrado. "
            "Rode: python -m pip install -r requirements.txt",
            "ERRO"
        )
        return False

    os.makedirs(destino, exist_ok=True)

    log(
        f"Baixando a voz '{nome}' ({info['repositorio']}) para: {destino}\n"
        "São cerca de 65 MB e não aparece barra de progresso. "
        "Aguarde até aparecer a mensagem final."
    )

    try:

        snapshot_download(
            info["repositorio"],
            revision=info["revisao"],
            local_dir=destino,
            allow_patterns=[info["modelo"], info["config"]]
        )

    except Exception as erro:

        log(f"Falha no download: {erro}", "ERRO")
        log("Verifique sua conexão com a internet e tente de novo.", "ERRO")
        return False

    if not (os.path.isfile(modelo) and os.path.isfile(configuracao)):

        log("O download terminou, mas os arquivos da voz não apareceram.", "ERRO")
        return False

    log("Voz baixada.")

    return _verificar(nome)


def _verificar(nome):
    """
    Carrega a voz e sintetiza uma frase (sem tocar nada), para confirmar
    já agora que ela funciona neste computador.
    """

    from . import sintetizador_voz

    try:

        voz = sintetizador_voz.carregar_voz(nome)

        amostras = sum(
            len(trecho.audio_int16_bytes) // 2
            for trecho in voz.synthesize("Olá, eu sou a Astra.")
        )

        segundos = amostras / voz.config.sample_rate

    except Exception as erro:

        log(f"A voz foi baixada, mas não funcionou: {erro}", "ERRO")
        return False

    if segundos <= 0:

        log("A voz carregou, mas não gerou nenhum áudio.", "ERRO")
        return False

    log(f"Voz verificada: gerou {segundos:.1f}s de áudio. Pronta para usar.")

    return True


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Baixa a voz da A.S.T.R.A.")
    parser.add_argument("--voz", help="nome da voz (padrão: VOZ_TTS da configuração)")

    baixar_voz(parser.parse_args().voz)
