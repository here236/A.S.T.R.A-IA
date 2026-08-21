from .capturador_tela import (
    capturar_tela,
    capturar_regiao,
    obter_resolucao
)

from .detector_elementos import (
    encontrar_elemento_por_texto
)

from configs import configuracoes

import time
'''
ARQUIVO PRINCIPAL DO MÓDULO

Responsável por:
- Controlar o fluxo principal
- Integrar os módulos
- Executar captura inteligente
- Localizar elementos
'''

def executar_captura():

    print("[ASTRA] Você tem 5 segundos para abrir a tela...")

    time.sleep(5)

    # Captura tela inteira
    imagem = capturar_tela()

    # Usuário digita o elemento desejado
    busca = input("Digite o elemento: ")

    # Procura elemento na tela
    elemento = encontrar_elemento_por_texto(
        busca,
        imagem
    )

    # Elemento encontrado
    if elemento:

        print("\n[ENCONTRADO]")
        print(elemento)

    else:

        # Se não encontrado, capturar tela inteira
        largura_tela, altura_tela = obter_resolucao()
        elemento = {
            "x": 0,
            "y": 0,
            "largura": largura_tela,
            "altura": altura_tela
        }
        print("\n[INFO] Elemento não encontrado. Capturando tela inteira.")

    # Captura região específica
    capturar_regiao(
        elemento["x"],
        elemento["y"],
        elemento["largura"],
        elemento["altura"]
    )


# EXECUÇÃO PRINCIPAL

if __name__ == "__main__":

    executar_captura()