import cv2
from datetime import datetime

"""
Funções auxiliares

* Conversões
* Logs
* Tratamento de erros
"""

def log(mensagem, tipo="INFO"):
    """
    Exibe uma mensagem de log com data e hora.
    """

    horario = datetime.now().strftime("%H:%M:%S")
    print(f"[{horario}] [{tipo}] {mensagem}")


def carregar_imagem(caminho_imagem):
    """
    Carrega uma imagem do disco (caminho) como array do OpenCV.
    Ponto único de entrada do pipeline de OCR — evita cada módulo
    ler a imagem de um jeito diferente (PIL vs OpenCV).
    """

    imagem = cv2.imread(caminho_imagem)

    if imagem is None:
        log(f"Não foi possível carregar a imagem: {caminho_imagem}", "ERRO")

    return imagem


def converter_para_cinza(imagem):
    """
    Converte uma imagem colorida para escala de cinza.
    """

    try:
        return cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)

    except Exception as erro:
        log(f"Erro ao converter imagem para cinza: {erro}", "ERRO")
        return None


def converter_para_binario(imagem):
    """
    Converte uma imagem em preto e branco utilizando Otsu.
    """

    try:
        _, binaria = cv2.threshold(
            imagem,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        return binaria

    except Exception as erro:
        log(f"Erro ao converter imagem para binário: {erro}", "ERRO")
        return None


def redimensionar(imagem, escala=2):
    """
    Aumenta a resolução da imagem.
    Ajuda bastante o OCR.
    """

    try:
        largura = int(imagem.shape[1] * escala)
        altura = int(imagem.shape[0] * escala)

        return cv2.resize(
            imagem,
            (largura, altura),
            interpolation=cv2.INTER_CUBIC
        )

    except Exception as erro:
        log(f"Erro ao redimensionar imagem: {erro}", "ERRO")
        return None