from voz.comandos_voz import StatusComando, executar_comando
from voz.processador_linguagem import responder_conversa

"""
Teste por texto: digite o que falaria e veja o que a A.S.T.R.A. diria.
Digite "sair" para parar.
"""

while True:

    texto = input("você> ").strip()

    if texto.lower() == "sair":
        break

    resultado = executar_comando(texto)

    if resultado.status == StatusComando.NAO_ENCONTRADO:
        fala = responder_conversa(texto)
    else:
        fala = resultado.resposta_falada

    print(f"astra> {fala}   [{resultado.status.value}]")

    if resultado.encerrar:
        break
