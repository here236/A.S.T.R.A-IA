from capturador_tela import (
    capturar_tela,
    capturar_regiao
)

from detector_elementos import (
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

        # Captura região específica
        capturar_regiao(
            elemento["x"],
            elemento["y"],
            elemento["largura"],
            elemento["altura"]
        )

    else:

        print("\n[ERRO] Elemento não encontrado.")


# EXECUÇÃO PRINCIPAL

if __name__ == "__main__":

    executar_captura()