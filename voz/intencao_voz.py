"""Adaptador do interpretador semântico para a interface de voz.

Não contém dicionário de correções nem acessa ferramentas. A sugestão só
pode ser encaminhada depois da confirmação gerenciada por AssistenteVoz.
"""
import os
from dataclasses import dataclass

from .utilitarios_voz import log


@dataclass(frozen=True)
class Esclarecimento:
    pergunta: str
    sugestao: str | None = None
    indisponivel: bool = False


def ia_habilitada():
    return os.getenv("ASTRA_IA_HABILITADA", "1").strip().lower() not in {
        "0", "false", "nao", "não", "off"
    }


def esclarecer_intencao(texto, interpretador=None):
    """None significa pedido claro; falhas nunca autorizam execução."""
    if not ia_habilitada():
        return None
    try:
        if interpretador is None:
            from ia.cliente_ollama import ClienteOllama
            from ia.interpretador_intencao import InterpretadorIntencao
            interpretador = InterpretadorIntencao(ClienteOllama(
                url=os.getenv("ASTRA_OLLAMA_URL", "http://localhost:11434"),
                modelo=os.getenv("ASTRA_OLLAMA_MODELO", "qwen2.5:1.5b"),
                timeout=float(os.getenv("ASTRA_OLLAMA_TIMEOUT", "45")),
                temperatura=0.1, max_tokens=128,
            ))
        log("Analisando intenção da solicitação com a IA local.", "IA")
        resultado = interpretador.interpretar(texto)
        if resultado.decisao == "clara":
            return None
        if resultado.decisao == "corrigir":
            sugestao = resultado.interpretacao
            return Esclarecimento(f"Você quis dizer: {sugestao.rstrip('?!.')}? Diga sim ou não.", sugestao)
        return Esclarecimento("Não consegui compreender o pedido com segurança. Pode repetir a frase ou explicar melhor?")
    except Exception as erro:
        log(f"Não foi possível interpretar a intenção ({type(erro).__name__}): {erro}", "AVISO")
        return Esclarecimento("Não consegui interpretar o pedido. Pode repetir ou usar um comando conhecido?", indisponivel=True)
