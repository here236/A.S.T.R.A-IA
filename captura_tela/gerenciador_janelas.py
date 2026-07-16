import win32gui
'''
Controla qual parte da tela será capturada


Identificar janela ativa
Obter posição e tamanho
'''
# receber o id na janela do windows
def obter_janela_ativa():
     janela = win32gui.GetForegroundWindow()
     return janela

#localizar onde esta a janela ativa
def obter_dimensoes_janela():
    handle = obter_janela_ativa()

    left, top, right, bottom = win32gui.GetWindowRect(handle)

    largura = right - left
    altura = bottom - top

    return left, top, largura, altura

print("Handle:", obter_janela_ativa())
print("Dimensões:", obter_dimensoes_janela())