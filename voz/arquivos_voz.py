"""Compatibilidade com versões anteriores.

A implementação foi centralizada em :mod:`arquivos.gerenciador_arquivos`.
Novos módulos devem importar diretamente do pacote ``arquivos``.
"""
from arquivos.gerenciador_arquivos import *  # noqa: F401,F403
from arquivos.gerenciador_arquivos import gerenciador_arquivos
