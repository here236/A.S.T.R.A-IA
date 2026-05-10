import pyautogui as auto
from datetime import datetime
import os
import time

'''
CAPTURADOR DE TELA

Responsável por:
- Capturar tela inteira
- Capturar regiões específicas
- Gerar nomes automáticos
- Retornar caminhos das imagens
'''

PASTA_PRINTS = "Prints"


def gerar_nome_arquivo(tipo):

    data = datetime.now().strftime("%Y%m%d-%H%M%S")

    nome = f"{tipo}-{data}.png"

    return os.path.join(PASTA_PRINTS, nome)


def obter_resolucao():

    largura, altura = auto.size()

    return largura, altura


def capturar_tela():

    nome_arquivo = gerar_nome_arquivo("tela")

    imagem = auto.screenshot()

    imagem.save(nome_arquivo)

    print(f"[CAPTURA] Tela salva: {nome_arquivo}")

    return nome_arquivo


def capturar_regiao(x, y, largura, altura):

    nome_arquivo = gerar_nome_arquivo("regiao")

    imagem = auto.screenshot(
        region=(x, y, largura, altura)
    )

    imagem.save(nome_arquivo)

    print(f"[CAPTURA] Região salva: {nome_arquivo}")

    return nome_arquivo


# TESTES

if __name__ == "__main__":

    largura, altura = obter_resolucao()

    print(f"Resolução: {largura}x{altura}")

    time.sleep(7)

    capturar_tela()

    capturar_regiao(x, y, largura, altura)