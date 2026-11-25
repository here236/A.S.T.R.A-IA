"""Composições explícitas com criação. Não interpreta texto livre como código."""
from dataclasses import dataclass
import re
from .escopo_ferramentas import _normalizar, _REGRAS, _COMPOSIVEIS, _LER

CRIACOES = frozenset({'criar_pasta', 'criar_documento', 'criar_planilha',
                      'criar_texto', 'criar_apresentacao'})


@dataclass(frozen=True)
class EtapaComposta:
    nome: str
    parametro: str = ''
    assunto: str = ''



# Uma composição dependente restrita: criar um novo Word/TXT e escrever
# um resumo nele. Não resolve pronomes a partir de histórico nem de OCR.
_PREFIXO_CORTESIA = r'^(?:por favor[, ]+|(?:voce )?(?:pode|poderia) |(?:eu )?(?:quero|gostaria de)(?: que voce)? )+'
_ESCRITA = r'\s+(?:e (?:depois |em seguida |entao )?|depois |em seguida )(?:(?:escreva|escreve|escrever|adicione|adicionar|coloque|colocar)\b)'


def _texto_pedido(pedido):
    texto = _normalizar(pedido)
    texto = re.sub(r'^planeje ', '', texto)
    return re.sub(_PREFIXO_CORTESIA, '', texto)


def pedido_escrita_dependente(pedido):
    """Detecta escrita composta mesmo quando o formato não é suportado."""
    texto = _texto_pedido(pedido)
    return bool(any(nome in CRIACOES and re.match(padrao, texto)
                    for nome, padrao in _REGRAS) and re.search(_ESCRITA, texto))


def plano_resumo_explicito(pedido):
    texto = _texto_pedido(pedido)
    if re.search(r'\b(?:nao|nunca|sem|se|caso|talvez)\b', texto):
        return None
    # Exige alvo explícito ("nele") e assunto. O nome é um parâmetro da
    # criação, não uma ordem. Não há terceira etapa nesta versão.
    m = re.fullmatch(
        r'(?:crie|cria|criar|gere|gerar) (?:um )?(documento|arquivo word|word|arquivo de texto)'
        r'(?:\s+((?:chamado|com o nome|intitulado) .+?))?'
        r'\s+(?:e (?:depois |em seguida |entao )?|depois |em seguida )'
        r'(?:escreva|escreve|escrever|adicione|adicionar|coloque|colocar) (?:nele|nesse arquivo|nesse documento) '
        r'(?:um )?resumo sobre (.+)', texto)
    if not m:
        return None
    tipo, nome, assunto = m.groups()
    nome = nome or ''
    if len(nome) > 240 or len(assunto) > 300:
        return None
    # Não engole ações adicionais no nome/assunto como conteúdo livre.
    for trecho in (nome, assunto):
        if re.search(r'\b(?:e depois|em seguida|e entao|depois)\b', trecho):
            return None
        for sep in re.finditer(r'\be\s+', trecho):
            if any(re.match(p, trecho[sep.end():]) for _, p in _REGRAS) or re.match(r'(?:escreva|escrever|adicione|adicionar|coloque|colocar)\b', trecho[sep.end():]):
                return None
    ferramenta = 'criar_texto' if tipo == 'arquivo de texto' else 'criar_documento'
    return (EtapaComposta(ferramenta, nome), EtapaComposta('escrever_texto', assunto=assunto))

def plano_criacao_explicito(pedido):
    """Aceita 2–4 cláusulas fechadas, ao menos uma criação, sem ações implícitas.

    Depois de um nome livre, exige separador explícito 'e depois' para
    outra ação. Nomes com conjunções devem ser fornecidos em uma resposta separada. Não aceita
    edição genérica, exclusão ou pesquisa. A exceção fechada de resumo
    depende da criação de um novo Word/TXT e exige aprovação do conteúdo.
    """
    if pedido_escrita_dependente(pedido):
        return plano_resumo_explicito(pedido)
    texto = _normalizar(pedido)
    texto = re.sub(r'^(?:por favor[, ]+|(?:voce )?(?:pode|poderia) |(?:eu )?(?:quero|gostaria de)(?: que voce)? )+', '', texto)
    if re.search(r'\b(?:nao|nunca|sem|se|caso|talvez)\b', texto):
        return None
    # Só divide 'e' quando a próxima cláusula começa com ação reconhecida.
    # Separadores temporais sempre delimitam uma cláusula (inclusive inválida).
    separador = re.compile(r'\s+(e depois|e em seguida|e entao|depois|em seguida|e)\s+')
    partes = []
    inicio = 0
    for m in separador.finditer(texto):
        if m.group(1) == 'e' and not any(re.match(p, texto[m.end():]) for _, p in _REGRAS):
            continue
        partes.append((texto[inicio:m.start()].strip(), m.group(1)))
        inicio = m.end()
    partes.append((texto[inicio:].strip(), None))
    if not 2 <= len(partes) <= 4:
        return None
    etapas = []
    for parte, conector in partes:
        for nome, padrao in _REGRAS:
            if nome in _COMPOSIVEIS and re.fullmatch(padrao, parte):
                if nome == 'ler_tela' and not re.match(_LER, parte):
                    return None
                etapas.append(EtapaComposta(nome))
                break
            if nome in CRIACOES:
                match = re.match(padrao, parte)
                if match:
                    parametro = parte[match.end():].strip()
                    # Um nome seguido de 'e' + verbo pode ser conteúdo literal.
                    if parametro and conector == 'e':
                        return None
                    # Não transforme conteúdo/nome com separadores desconhecidos
                    # em uma autorização para outras ferramentas.
                    if len(parametro) > 4000 or re.search(r"\be\b", parametro):
                        return None
                    etapas.append(EtapaComposta(nome, parametro))
                    break
        else:
            return None
    if not any(e.nome in CRIACOES for e in etapas):
        return None
    return tuple(etapas)
