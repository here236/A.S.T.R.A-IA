from pywinauto import Desktop
import pytesseract
from PIL import Image
import pyautogui as auto
from configs import configuracoes



'''
DETECTOR DE ELEMENTOS

Responsável por:
- Detectar elementos reais da interface
- Usar OCR como fallback
- Localizar regiões da tela
'''

pytesseract.pytesseract.tesseract_cmd = (
    configuracoes.TESSERACT_PATH
)

def detectar_elementos_ui():

    elementos = []

    try:

        desktop = Desktop(backend="uia")

        janela = Desktop(backend="uia").get_active()

        controles = janela.descendants()

        for controle in controles:

            try:

                rect = controle.rectangle()

                elemento = {
                    "tipo": controle.friendly_class_name(),
                    "texto": controle.window_text(),
                    "x": rect.left,
                    "y": rect.top,
                    "largura": rect.width(),
                    "altura": rect.height(),
                    "origem": "ui_automation"
                }

                elementos.append(elemento)

            except:
                pass

    except Exception as erro:

        print(f"[ERRO UI] {erro}")

    return elementos


def detectar_elementos_ocr(imagem):

    elementos = []

    texto = pytesseract.image_to_data(
        Image.open(imagem),
        lang="por",
        output_type=pytesseract.Output.DICT
    )

    total = len(texto["text"])

    for i in range(total):

        conteudo = texto["text"][i].strip()

        if conteudo:

            elemento = {
                "tipo": "texto",
                "texto": conteudo,
                "x": texto["left"][i],
                "y": texto["top"][i],
                "largura": texto["width"][i],
                "altura": texto["height"][i],
                "origem": "ocr"
            }

            elementos.append(elemento)

    return elementos


def detectar_elementos(imagem=None):

    # Primeiro tenta UI Automation
    elementos = detectar_elementos_ui()

    # Fallback OCR
    if not elementos and imagem:

        print("[INFO] UI Automation falhou. Executando OCR...")

        elementos = detectar_elementos_ocr(imagem)

    return elementos

def encontrar_elemento_por_texto(texto_busca, imagem=None):

    elementos = detectar_elementos(imagem)

    texto_busca = texto_busca.lower()

    for elemento in elementos:

        texto_elemento = elemento["texto"].lower()

        if texto_busca in texto_elemento:

            return elemento

    return {
    "status": False,
    "erro": "Elemento não encontrado"
    }