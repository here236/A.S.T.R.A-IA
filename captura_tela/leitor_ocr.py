import cv2
import pytesseract

"""
Converte imagem em texto

* Fazer OCR da imagem
* Tecnologia: Baseado em Tesseract OCR
"""

from utilitarios import (
    converter_para_cinza,
    converter_para_binario,
    redimensionar,
    log
)

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def extrair_texto(imagem):
    """
    Extrai o texto de uma imagem utilizando o Tesseract OCR.
    """

    try:
        imagem = redimensionar(imagem, 2)
        imagem = converter_para_cinza(imagem)
        imagem = converter_para_binario(imagem)

        texto = pytesseract.image_to_string(
            imagem,
            lang="por+eng",
            config="--oem 3 --psm 6"
        )

        return texto.strip()

    except Exception as erro:
        log(f"Erro no OCR: {erro}", "ERRO")
        return ""

