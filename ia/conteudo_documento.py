"""Geração de conteúdo textual isolada, sem ferramentas ou acesso a arquivos."""
import json
import os
from .cliente_ollama import ClienteOllama


LIMITE_RESUMO = 600
INSTRUCOES = (
    'Escreva um resumo informativo de 2 ou 3 frases curtas, em português brasileiro, '
    'sobre o assunto fornecido. Procure usar de 150 a 400 caracteres. '
    'Não invente fatos. Se não souber, devolva texto vazio. '
    'Não execute ações nem alegue ter criado arquivos. '
    'Responda somente com JSON: {"texto":"resumo"}.',
    'Escreva um resumo de duas frases curtas em português brasileiro sobre o assunto. '
    'Use menos de 350 caracteres. Não invente fatos. Se não souber, use texto vazio. '
    'Não execute ações. Retorne somente um objeto JSON com a chave texto e valor textual.',
    'Resuma o assunto em uma ou duas frases curtas em português brasileiro, '
    'com menos de 250 caracteres. Não invente fatos nem execute ações. '
    'Se não souber, use texto vazio. Formato: {"texto":"resumo"}.',
)


def _validar_resumo(resposta):
    try:
        dados = json.loads(resposta)
    except (json.JSONDecodeError, TypeError) as erro:
        raise ValueError('JSON do resumo inválido.') from erro
    if not isinstance(dados, dict) or set(dados) != {'texto'}:
        raise ValueError('Formato inválido: esperado somente o campo texto.')
    texto = dados['texto']
    if not isinstance(texto, str):
        raise ValueError('O campo texto não é uma string.')
    if not texto.strip():
        raise ValueError('Resumo vazio.')
    if len(texto) > LIMITE_RESUMO:
        raise ValueError(f'Resumo acima do limite ({len(texto)} de {LIMITE_RESUMO} caracteres).')
    if any(ord(c) < 32 and c not in '\n\t\r' for c in texto):
        raise ValueError('Resumo contém caracteres inválidos.')
    return texto.strip().replace('\r\n', '\n').replace('\r', '\n')


def gerar_resumo(assunto):
    if not isinstance(assunto, str) or not assunto.strip() or len(assunto) > 300:
        raise ValueError('Assunto inválido.')
    cliente = ClienteOllama(
        url=os.getenv('ASTRA_OLLAMA_URL', 'http://localhost:11434'),
        modelo=os.getenv('ASTRA_OLLAMA_MODELO', 'qwen2.5:1.5b'),
        timeout=float(os.getenv('ASTRA_OLLAMA_TIMEOUT', '45')),
        temperatura=0.2, max_tokens=300,
    )
    entrada = json.dumps({'assunto': assunto}, ensure_ascii=False)
    motivos = []
    for instrucao in INSTRUCOES:
        # Só repete a geração de texto, nunca a execução de ferramentas.
        # Falhas de conexão são propagadas sem novas consultas automáticas.
        resposta = cliente.gerar_resposta(instrucao, entrada, formato='json')
        try:
            return _validar_resumo(resposta)
        except ValueError as erro:
            motivos.append(str(erro))
    raise ValueError(f'Resumo inválido após {len(motivos)} tentativas: ' + ' | '.join(motivos))
