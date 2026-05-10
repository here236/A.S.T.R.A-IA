
import cv2
import easyocr

'''
Parte “inteligente” da visão

Detectar elementos visuais:
- Botões
- Textos
- Caixas
- Campos
'''


# OCR
reader = easyocr.Reader(['pt'])


def detectar_elementos(imagem):

    # Carrega imagem
    img = cv2.imread(imagem)

    # OCR
    resultados = reader.readtext(imagem)

    elementos = []

    for resultado in resultados:

        coordenadas, texto, confianca = resultado

        x1, y1 = coordenadas[0]
        x2, y2 = coordenadas[2]

        largura = int(x2 - x1)
        altura = int(y2 - y1)

        elemento = {
            "tipo": "texto",
            "texto": texto,
            "x": int(x1),
            "y": int(y1),
            "largura": largura,
            "altura": altura,
            "confianca": round(confianca, 2)
        }

        elementos.append(elemento)

    return elementos