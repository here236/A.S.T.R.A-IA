from .leitor_ocr import detectar_elementos_texto

'''
DETECTOR DE ELEMENTOS

Responsável por:
- Detectar elementos de texto na tela (via OCR, ver leitor_ocr.py)
- Buscar um elemento específico pelo texto

Decisão de projeto: o detector usa só Tesseract OCR como fonte de
elementos (sem UI Automation/pywinauto). Isso simplifica o formato de
dado em um único padrão para o resto do projeto (RF03, RF04), ao custo
de não detectar botões/ícones sem nenhum texto — ver ASTRA_Roadmap.md.
'''


def detectar_elementos(imagem):
    """
    Detecta todos os elementos de texto presentes na imagem,
    cada um com sua posição na tela.
    """

    return detectar_elementos_texto(imagem)


def encontrar_elemento_por_texto(texto_busca, imagem):
    """
    Procura, entre os elementos detectados na imagem, o primeiro
    cujo texto contenha 'texto_busca' (case-insensitive).
    """

    elementos = detectar_elementos(imagem)

    texto_busca = texto_busca.lower()

    for elemento in elementos:

        texto_elemento = elemento["texto"].lower()

        if texto_busca in texto_elemento:

            return elemento

    return None
