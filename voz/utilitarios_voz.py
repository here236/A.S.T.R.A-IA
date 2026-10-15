import re
import unicodedata
from datetime import datetime

'''
    Funções auxiliares

    Responsabilidade:
    Logs
    Tratamento de erro
    Ajuste de áudio
    Normalização de texto (compartilhada por ativacao_voz,
    comandos_voz e processador_linguagem)
'''

def log(mensagem, tipo="INFO"):
    """
    Exibe uma mensagem de log com data e hora.
    Mesmo padrão usado em captura_tela/utilitarios.py.
    """

    horario = datetime.now().strftime("%H:%M:%S")
    print(f"[{horario}] [{tipo}] {mensagem}")


def normalizar_texto(texto):
    """
    Normaliza um texto vindo do reconhecimento de voz.

    Remove:
        - letras maiúsculas
        - acentos
        - caracteres especiais
        - espaços duplicados

    Ponto único de normalização do módulo de voz: antes cada arquivo
    tinha a sua cópia, e qualquer ajuste precisava ser feito em três
    lugares.
    """

    if not texto:
        return ""

    texto = texto.lower().strip()

    texto = unicodedata.normalize("NFD", texto)

    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    texto = re.sub(r"[^a-z0-9\s]", " ", texto)

    texto = re.sub(r"\s+", " ", texto)

    return texto.strip()
