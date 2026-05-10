import tkinter as tk
import pyautogui as auto
from datetime import datetime

'''
Responsável por tirar o “print”

* Capturar tela inteira
* Capturar regiões específicas
'''

PASTA_PRINTS = "Prints"


def gerar_nome_arquivo(tipo):

    # Exemplo:
    # tela-20260509-154230.png

    data = datetime.now().strftime("%Y%m%d-%H%M%S")

    return f"{PASTA_PRINTS}/{tipo}-{data}.png"


def capturar_tela():

    nome_arquivo = gerar_nome_arquivo("tela")

    img = auto.screenshot()

    img.save(nome_arquivo)

    print(f"Tela salva em: {nome_arquivo}")


def capturar_regiao(x, y, largura, altura):
    root = tk.Tk()

    largura_tela = root.winfo_screenwidth()
    altura_tela = root.winfo_screenheight()

    print(f"{largura_tela}x{altura_tela}")

    root.destroy()

    return

capturar_tela()
capturar_regiao(0, 0, 100, 100)
