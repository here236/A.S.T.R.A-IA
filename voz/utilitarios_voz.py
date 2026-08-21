from datetime import datetime

'''
    Funções auxiliares

    Responsabilidade:
    Logs
    Tratamento de erro
    Ajuste de áudio
'''

def log(mensagem, tipo="INFO"):
    """
    Exibe uma mensagem de log com data e hora.
    Mesmo padrão usado em captura_tela/utilitarios.py.
    """

    horario = datetime.now().strftime("%H:%M:%S")
    print(f"[{horario}] [{tipo}] {mensagem}")
