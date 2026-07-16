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

def listar_janelas():

    janelas = []

    def callback(hwnd, extra):

        # Ignora janelas invisíveis
        if not win32gui.IsWindowVisible(hwnd):
            return

        # Obtém o título da janela
        titulo = win32gui.GetWindowText(hwnd)

        # Ignora janelas sem título
        if titulo == "":
            return

        # Salva as informações da janela
        janelas.append({
            "handle": hwnd,
            "titulo": titulo
        })

    # Percorre todas as janelas abertas
    win32gui.EnumWindows(callback, None)

    return janelas

print("\nJanelas abertas:\n")

for janela in listar_janelas():
    print(f'Handle: {janela["handle"]}')
    print(f'Título: {janela["titulo"]}')
    print("-" * 40)