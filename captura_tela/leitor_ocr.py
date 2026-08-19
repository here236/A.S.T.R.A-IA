import pytesseract

"""
Converte imagem em texto

* Fazer OCR da imagem (leitura corrida e detecção de elementos c/ posição)
* Tecnologia: Baseado em Tesseract OCR
* Ponto único de OCR do projeto — todo o resto do módulo captura_tela
  passa por aqui, em vez de cada arquivo chamar o pytesseract sozinho.
"""

from .utilitarios import (
    carregar_imagem,
    converter_para_cinza,
    converter_para_binario,
    redimensionar,
    log
)
from configs import configuracoes

pytesseract.pytesseract.tesseract_cmd = configuracoes.TESSERACT_PATH

# Escala usada no pré-processamento (redimensionar aumenta a imagem,
# o que melhora bastante a precisão do OCR em textos pequenos).
ESCALA_OCR = 2


def _preprocessar(caminho_imagem, escala=ESCALA_OCR):
    """
    Carrega e prepara a imagem pro OCR: aumenta a resolução,
    converte pra cinza e binariza (preto e branco).
    Retorna a imagem processada, pronta pro Tesseract.
    """

    imagem = carregar_imagem(caminho_imagem)

    if imagem is None:
        return None

    imagem = redimensionar(imagem, escala)
    imagem = converter_para_cinza(imagem)
    imagem = converter_para_binario(imagem)

    return imagem


def extrair_texto(caminho_imagem):
    """
    Extrai todo o texto de uma imagem, como uma string única.
    Útil pra "ler a tela inteira" (RF05 / TTS).
    """

    try:
        imagem = _preprocessar(caminho_imagem)

        if imagem is None:
            return ""

        texto = pytesseract.image_to_string(
            imagem,
            lang="por+eng",
            config="--oem 3 --psm 6"
        )

        return texto.strip()

    except Exception as erro:
        log(f"Erro no OCR (extrair_texto): {erro}", "ERRO")
        return ""


def detectar_elementos_texto(caminho_imagem, escala=ESCALA_OCR):
    """
    Detecta cada palavra/bloco de texto na imagem junto com a
    posição (x, y, largura, altura) na tela original.

    Usa o mesmo pré-processamento de extrair_texto(), mas devolve
    posição em vez de só o texto corrido — é o que RF04 (navegação)
    precisa pra saber ONDE clicar, não só O QUE tem na tela.
    """

    elementos = []

    try:
        imagem = _preprocessar(caminho_imagem, escala)

        if imagem is None:
            return elementos

        dados = pytesseract.image_to_data(
            imagem,
            lang="por+eng",
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT
        )

        total = len(dados["text"])

        for i in range(total):

            conteudo = dados["text"][i].strip()

            if not conteudo:
                continue

            # A imagem foi redimensionada (escala) antes do OCR, então as
            # coordenadas voltam divididas pela escala pra baterem com a
            # posição real na tela (senão o clique sai do lugar).
            elemento = {
                "tipo": "texto",
                "texto": conteudo,
                "x": int(dados["left"][i] / escala),
                "y": int(dados["top"][i] / escala),
                "largura": int(dados["width"][i] / escala),
                "altura": int(dados["height"][i] / escala),
                "origem": "ocr"
            }

            elementos.append(elemento)

    except Exception as erro:
        log(f"Erro no OCR (detectar_elementos_texto): {erro}", "ERRO")

    return elementos
