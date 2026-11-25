"""Coleta de parâmetros de uma ferramenta já identificada, sem consultar a IA."""
from dataclasses import dataclass
import time

from .utilitarios_voz import normalizar_texto

TEMPO_PARAMETRO = 60.0
CRIACOES = frozenset({"criar_pasta", "criar_documento", "criar_planilha",
                       "criar_texto", "criar_apresentacao"})
CANCELAMENTOS = frozenset({"nao", "cancelar", "cancela", "cancele", "desistir"})


def parametro_faltante(nome, parametro):
    """Usa o mesmo parser de nomes e locais que o gerenciador de arquivos."""
    if nome in CRIACOES:
        from arquivos.gerenciador_arquivos import _limpar_nome, _separar_local, _separar_colunas
        base, _ = _separar_colunas(parametro) if nome == "criar_planilha" else (parametro, "")
        texto, _ = _separar_local(base)
        if not _limpar_nome(texto):
            return "Qual nome você quer usar? Diga o nome ou cancelar."
    if nome == "pesquisar" and normalizar_texto(parametro) in {"", "sobre"}:
        return "O que você quer pesquisar? Diga o assunto ou cancelar."
    return None


@dataclass
class ParametroPendente:
    nome: str
    parametro: str
    origem_ia: bool
    pergunta: str
    prazo: float


class GerenciadorDialogo:
    def __init__(self):
        self.pendente = None

    def pedir(self, nome, parametro, origem_ia, pergunta):
        self.pendente = ParametroPendente(nome, parametro, origem_ia, pergunta,
                                          time.monotonic() + TEMPO_PARAMETRO)

    def aguardando(self):
        if self.pendente is not None and time.monotonic() >= self.pendente.prazo:
            self.cancelar()
        return self.pendente is not None

    def renovar_prazo(self):
        if self.pendente is not None:
            self.pendente.prazo = time.monotonic() + TEMPO_PARAMETRO

    def cancelar(self):
        self.pendente = None

    @staticmethod
    def completar(pendente, texto):
        # O texto complementar é exclusivamente um argumento, nunca um comando.
        if pendente.nome in CRIACOES:
            from arquivos.gerenciador_arquivos import _separar_local, _separar_colunas
            base, colunas = (_separar_colunas(pendente.parametro)
                             if pendente.nome == "criar_planilha" else (pendente.parametro, ""))
            _, local = _separar_local(base)
            nome, local_resposta = _separar_local(texto)
            if local and local_resposta and local != local_resposta:
                return None
            local = local or local_resposta
            parametro = nome + (f" em {local}" if local else "")
            if colunas:
                parametro += f" com as colunas {colunas}"
            return parametro
        return texto
