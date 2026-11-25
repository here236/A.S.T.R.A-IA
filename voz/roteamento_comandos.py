"""Decisão de encaminhamento, sem efeitos externos nem interpretação por IA.

O registro legado continua a reconhecer seus comandos. Esta camada evita que
um prefixo reconhecido seja confundido com uma solicitação inteira.
"""
import re
from dataclasses import dataclass

from .utilitarios_voz import normalizar_texto
from ia.escopo_ferramentas import ferramentas_do_pedido, sequencia_explicita

# As funções abaixo não consomem argumentos. Não descartar texto adicional.
SEM_PARAMETRO = frozenset({
    'abrir_navegador', 'fechar_navegador', 'abrir_bloco_notas', 'ler_tela',
    'ver_hora', 'identidade', 'agradecimento', 'encerrar', 'ajuda',
    'continuar_leitura', 'repetir_resultados',
})
# Nesses comandos, o restante da fala é conteúdo literal (não novas ordens).
CONTEUDO_LITERAL = frozenset({'escrever_texto', 'escrever_celula',
    'adicionar_linha', 'adicionar_slide', 'pesquisar', 'pesquisar_no_navegador',
    'pesquisar_como_fazer', 'pesquisar_como_faco', 'pesquisar_documento',
    'pesquisar_planilha', 'pesquisar_apresentacao'})
SEPARADOR = re.compile(r'\b(?:e\s+(?:depois\s+|em seguida\s+|entao\s+)?|depois\s+|em seguida\s+|para\s+)')

@dataclass(frozen=True)
class Rota:
    direta: bool = False
    composta: bool = False
    suportada: bool = True


def avaliar_rota(texto, gerenciador):
    """Reconhece apenas limites sintáticos; o Qwen interpreta o pedido livre.

    Não amplia permissões: o filtro da etapa 1 continua sendo a autoridade.
    Para compostos ainda não cobertos, evita executar apenas a primeira parte.
    """
    if sequencia_explicita(texto):
        return Rota(composta=True, suportada=True)
    normalizado = normalizar_texto(texto)
    # Cortesia pode preceder um pedido composto; não transforma por si só
    # uma frase livre em comando direto.
    inicio = re.sub(r'^(?:por favor |(?:voce )?(?:pode|poderia) |(?:eu )?(?:quero|gostaria de)(?: que voce)? )+', '', normalizado)
    comando, expressao = gerenciador.encontrar_comando(inicio)
    if comando is None or not (inicio == expressao or inicio.startswith(expressao + ' ')):
        return Rota()
    resto = inicio[len(expressao):].strip()
    if not resto or resto in {'por favor', 'por gentileza'}:
        return Rota(direta=inicio == normalizado)
    if comando.nome not in CONTEUDO_LITERAL:
        for separador in SEPARADOR.finditer(resto):
            segundo = resto[separador.end():].strip()
            outro, chave = gerenciador.encontrar_comando(segundo)
            escopo_segundo = ferramentas_do_pedido(segundo)
            if not escopo_segundo and not (outro and (segundo == chave or segundo.startswith(chave + ' '))):
                continue
            escopo = ferramentas_do_pedido(normalizado)
            necessarias = {comando.nome} | (set(escopo_segundo) or {outro.nome})
            return Rota(composta=True, suportada=necessarias <= escopo)
    if comando.nome in SEM_PARAMETRO:
        return Rota()
    return Rota(direta=inicio == normalizado)
