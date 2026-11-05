import os

from configs import configuracoes_voz
from .utilitarios_voz import log

'''
    Baixa o modelo de reconhecimento de fala (Whisper) para o computador.

    Rode UMA vez por máquina, com internet:

        python -m voz.baixar_modelo

    Depois disso o reconhecimento de fala funciona 100% offline: o
    programa carrega o modelo da pasta "modelos/" e nunca mais acessa
    a rede. O tamanho do modelo é definido em
    configs/configuracoes_voz.py (MODELO_STT).
'''

# Repositórios dos modelos já convertidos para o faster-whisper.
REPOSITORIOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

# Só estes arquivos são necessários para rodar o modelo.
ARQUIVOS_NECESSARIOS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]


def baixar_modelo():

    nome = configuracoes_voz.MODELO_STT

    if nome not in REPOSITORIOS:

        log(
            f"Modelo '{nome}' desconhecido. "
            f"Opções: {', '.join(REPOSITORIOS)}",
            "ERRO"
        )
        return False

    destino = os.path.join(configuracoes_voz.PASTA_MODELOS, nome)

    if os.path.isfile(os.path.join(destino, "model.bin")):

        log(f"O modelo '{nome}' já está baixado em: {destino}")
        return True

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
        f"Baixando o modelo '{nome}' para: {destino}\n"
        "Isso pode levar alguns minutos e não mostra barra de progresso. "
        "Aguarde até aparecer a mensagem final."
    )

    try:

        snapshot_download(
            REPOSITORIOS[nome],
            local_dir=destino,
            allow_patterns=ARQUIVOS_NECESSARIOS
        )

    except Exception as erro:

        log(f"Falha no download: {erro}", "ERRO")
        log("Verifique sua conexão com a internet e tente de novo.", "ERRO")
        return False

    if not os.path.isfile(os.path.join(destino, "model.bin")):

        log("O download terminou, mas o arquivo model.bin não apareceu.", "ERRO")
        return False

    log("Modelo baixado. Já pode usar o reconhecimento de fala offline.")

    return True


if __name__ == "__main__":

    baixar_modelo()
