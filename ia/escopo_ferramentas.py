"""Escopo conservador de ferramentas da IA, baseado somente no pedido atual.

Não é um interpretador semântico completo. Na dúvida, não concede acesso.
Não usa histórico, OCR, resultados externos ou a saída do modelo como autorização.
"""
import re
import unicodedata


def _normalizar(texto):
    texto = unicodedata.normalize('NFKD', texto.casefold())
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(texto.split()).strip(' .?!')


# Cada padrão começa no início de uma solicitação, não dentro de uma
# pergunta explicativa, nome de arquivo ou conteúdo a escrever/pesquisar.
_ARTIGO = r'(?:(?:o|a|os|as|um|uma|meu|minha) )?'
_CRIAR = r'(?:crie|cria|criar|gere|gerar) '
_ABRIR = r'(?:abra|abre|abrir|inicie|iniciar) '
_LER = r'(?:leia|le|ler) '
_PESQUISA = r'(?:pesquise|pesquisa|pesquisar|busque|busca|buscar|procure|procura|procurar)'
_TELA = r'(?:a |na |da |na minha |da minha |minha |nesta |desta |nesta minha )?(?:tela|monitor)(?: atual)?'
_REGRAS = (
    ('ler_tela', rf'(?:{_LER}|(?:descreva|descreve|descrever|interprete|interpretar|capture|capturar) ){_TELA}\b'),
    ('ler_tela', rf'(?:explique|explicar|resuma|resumir|analise|analisar) (?:o |a |esse |este )?(?:(?:conteudo|texto|erro) (?:que (?:esta|aparece) )?)?{_TELA}\b'),
    ('ler_tela', r'(?:o que (?:tem|esta|aparece|diz|ha|esta aparecendo)|qual (?:e o|o) (?:texto|erro|conteudo)) (?:na|da|nesta|desta) (?:minha )?tela\b'),
    ('abrir_navegador', rf'{_ABRIR}{_ARTIGO}navegador\b'),
    ('fechar_navegador', rf'(?:feche|fecha|fechar) {_ARTIGO}navegador\b'),
    ('criar_pasta', rf'{_CRIAR}{_ARTIGO}pasta\b|nova pasta\b'),
    ('criar_documento', rf'{_CRIAR}{_ARTIGO}(?:documento|arquivo word|word)\b|novo documento\b'),
    ('criar_planilha', rf'{_CRIAR}{_ARTIGO}(?:planilha|arquivo excel|excel)\b|nova planilha\b'),
    ('criar_texto', rf'{_CRIAR}{_ARTIGO}arquivo de texto\b|novo arquivo de texto\b'),
    ('criar_apresentacao', rf'{_CRIAR}{_ARTIGO}(?:apresentacao|powerpoint|power point)\b|nova apresentacao\b'),
    ('embelezar_planilha', rf'(?:formate|formatar|embeleze|embelezar) {_ARTIGO}planilha\b|(?:aplique|mude) o tema\b'),
    ('somar_coluna', rf'(?:some|somar) {_ARTIGO}coluna\b|total da coluna\b'),
    ('adicionar_slide', rf'(?:adicione|adicionar|crie|criar) {_ARTIGO}slide\b|novo slide\b'),
    ('adicionar_linha', rf'(?:adicione|adicionar) {_ARTIGO}linha\b|nova linha\b'),
    ('escrever_celula', r'(?:escreva|escrever|escreve) na celula\b'),
    ('escrever_texto', r'(?:escreva|escrever|escreve) (?:no|na) (?:arquivo|documento|planilha)\b'),
    ('ler_arquivo', rf'{_LER}{_ARTIGO}(?:arquivo|documento|planilha)\b'),
    ('usar_arquivo', rf'(?:{_ABRIR}|(?:use|usar|edite|editar) ){_ARTIGO}(?:arquivo|documento|planilha)\b'),
    ('listar_arquivos', rf'(?:liste|listar) {_ARTIGO}arquivos\b|quais arquivos eu tenho\b'),
    ('excluir', r'(?:exclua|excluir|apague|apagar|delete|deletar)\b'),
    ('abrir_bloco_notas', rf'{_ABRIR}{_ARTIGO}bloco (?:de )?notas\b'),
    ('abrir_site', rf'{_ABRIR}{_ARTIGO}site\b'),
    ('pesquisar_documento', rf'{_PESQUISA} {_ARTIGO}documento\b'),
    ('pesquisar_planilha', rf'{_PESQUISA} {_ARTIGO}planilha\b'),
    ('pesquisar_apresentacao', rf'{_PESQUISA} {_ARTIGO}apresentacao\b'),
    ('pesquisar_no_navegador', rf'{_PESQUISA} no navegador\b'),
    ('pesquisar_como_fazer', rf'{_PESQUISA} como fazer\b'),
    ('pesquisar_como_faco', rf'{_PESQUISA} como faco\b'),
    ('pesquisar', rf'{_PESQUISA}\b|(?:faca|fazer) uma pesquisa\b'),
    ('ler_resultado', rf'{_LER}{_ARTIGO}resultado\b'),
    ('abrir_resultado', rf'{_ABRIR}{_ARTIGO}resultado\b'),
    ('continuar_leitura', r'(?:continue|continuar) (?:a )?leitura\b'),
    ('repetir_resultados', r'(?:repita|repetir) (?:os )?resultados\b'),
    ('ver_hora', r'(?:que horas sao|qual (?:e )?a hora|(?:diga|informe) (?:as )?horas)\b'),
)


# Composições fechadas: ações sem argumentos, sem risco elevado e com
# limites de frase inequívocos. O executor ainda decide permissões reais.
_COMPOSIVEIS = frozenset({'abrir_navegador', 'abrir_bloco_notas', 'ver_hora', 'listar_arquivos', 'ler_tela'})


def sequencia_explicita(solicitacao):
    """Retorna ações fechadas em ordem, ou None. Nunca divide conteúdo livre."""
    texto = _normalizar(solicitacao)
    texto = re.sub(r'^(?:por favor[, ]+|(?:voce )?(?:pode|poderia) |(?:eu )?(?:quero|gostaria de)(?: que voce)? )+', '', texto)
    if re.search(r'\b(?:nao|nunca|sem|se|caso|talvez)\b', texto):
        return None
    partes = re.split(r'\s+(?:e (?:depois |em seguida |entao )?|depois |em seguida )', texto)
    if not 2 <= len(partes) <= 4:
        return None
    nomes = []
    for parte in partes:
        nome = next((n for n, padrao in _REGRAS if n in _COMPOSIVEIS and re.fullmatch(padrao, parte.strip())), None)
        if nome is None:
            return None
        if nome == 'ler_tela' and not re.match(_LER, parte.strip()):
            # Explicação/síntese de OCR não equivale a leitura literal.
            return None
        nomes.append(nome)
    return tuple(nomes)


def ferramentas_do_pedido(solicitacao):
    """Concede somente capacidades reconhecidas; não concede autorização de risco."""
    sequencia = sequencia_explicita(solicitacao)
    if sequencia:
        return frozenset(sequencia)
    texto = _normalizar(solicitacao)
    # Prefixos explícitos de cortesia/pedido, nunca perguntas do tipo "como criar".
    texto = re.sub(r'^(?:por favor[, ]+|(?:voce )?(?:pode|poderia) |(?:eu )?(?:quero|gostaria de)(?: que voce)? )+', '', texto)
    # Por ora, negação e condições bloqueiam toda execução pela IA.
    if re.search(r'\b(?:nao|nunca|sem|se|caso|talvez)\b', texto):
        return frozenset()
    # Primeiro reconhecemos uma ação no início. Não interpretamos parâmetros
    # livres como novos comandos, mesmo que incluam verbos de ação.
    for nome, padrao in _REGRAS:
        correspondencia = re.match(padrao, texto)
        if correspondencia:
            permitidas = {nome}
            # Exceção restrita: abrir navegador + pesquisa explícita.
            if nome == 'abrir_navegador' and re.match(
                rf'\s*(?:e (?:depois |em seguida |entao )?|depois |em seguida |para ){_PESQUISA}\b', texto[correspondencia.end():]
            ):
                permitidas.add('pesquisar')
                permitidas.add('pesquisar_no_navegador')
            return frozenset(permitidas)
    return frozenset()
