import tkinter as tk
import mss
import mss.tools

'''
Responsável por tirar o “print”

* Capturar tela inteira
* Capturar regiões específicas
'''

def capturar_tela():
    with mss.mss() as sct:
        sct.shot(output="tela.png")


def capturar_regiao(x, y, largura, altura):
    root = tk.Tk()

    largura_tela = root.winfo_screenwidth()
    altura_tela = root.winfo_screenheight()

    print(f"{largura_tela}x{altura_tela}")

    root.destroy()

    return

capturar_regiao(0, 0, 100, 100)
