"""Memória de criações verificadas, somente em RAM e sem acesso ao modelo.

Consultas explícitas não executam ferramentas nem enviam caminhos ao Ollama.
Não registra conteúdo escrito, OCR, argumentos ou respostas do modelo.
"""
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import re
from .utilitarios_voz import normalizar_texto

TIPOS = {
    'criar_pasta': 'pasta', 'criar_documento': 'documento',
    'criar_planilha': 'planilha', 'criar_apresentacao': 'apresentacao',
    'criar_texto': 'arquivo de texto',
}
TIPOS_CONSULTA = r'arquivo de texto|documento|planilha|apresentacao|pasta|arquivo'
# A gramática é deliberadamente fechada. Não interpretar ordens de criação
# ou exclusão como perguntas de memória.
PERGUNTA = re.compile(r'^(?:onde (?:voce )?(?:criou|salvou|gravou)|(?:qual|qual e) (?:o )?caminho d[oa])(?: (.*))?$')

@dataclass(frozen=True)
class RegistroCriacao:
    ferramenta: str
    caminho: str


class MemoriaOperacional:
    def __init__(self, limite=50):
        self._criadas = deque(maxlen=limite)
        self._removidas = set()

    def limpar(self):
        self._criadas.clear()
        self._removidas.clear()

    def registrar(self, ferramenta, dados):
        """Chamado apenas no retorno de sucesso do gerenciador compartilhado."""
        if ferramenta not in TIPOS and ferramenta != 'excluir':
            return
        if not isinstance(dados, dict) or not isinstance(dados.get('caminho'), str):
            return
        caminho = Path(dados['caminho'])
        if not caminho.is_absolute():
            return
        if ferramenta == 'excluir':
            if dados.get('verificacao') == 'ausente_no_origem':
                # Marcar também criações conhecidas dentro da pasta removida.
                for registro in self._criadas:
                    p = Path(registro.caminho)
                    if p == caminho or caminho in p.parents:
                        self._removidas.add(registro.caminho)
            return
        if dados.get('verificacao') != 'existe':
            return
        # Verificação realizada pelo gerenciador de arquivos; aqui só se
        # registra evidência explícita, nunca uma frase de sucesso do modelo.
        self._criadas.append(RegistroCriacao(ferramenta, str(caminho)))
        self._removidas.discard(str(caminho))
        self._removidas.intersection_update(r.caminho for r in self._criadas)

    def responder(self, texto):
        frase = normalizar_texto(texto)
        if frase in {'limpar memoria operacional', 'limpe a memoria operacional'}:
            self.limpar()
            return 'Memória operacional limpa. Nenhum arquivo foi alterado.'
        m = PERGUNTA.fullmatch(frase)
        if not m:
            return None
        alvo = (m.group(1) or '').strip()
        alvo = re.sub(r'^(?:o|a|os|as) ', '', alvo)
        alvo = re.sub(r'^(?:ultimo|ultima) ', '', alvo)
        alvo = re.sub(r' (?:que (?:voce )?(?:acabou de criar|criou|salvou)|agora|por ultimo)$', '', alvo)
        tipo = re.match(rf'^({TIPOS_CONSULTA})(?: |$)', alvo)
        categoria = tipo.group(1) if tipo else None
        nome = alvo[tipo.end():].strip() if tipo else alvo
        nome = re.sub(r'^(?:chamado|chamada|com o nome) ', '', nome)
        if nome in {'ele', 'ela', 'isso', 'ultimo', 'ultima'}:
            nome = ''
        candidatos = []
        for r in reversed(self._criadas):
            if categoria == 'arquivo' and r.ferramenta == 'criar_pasta':
                continue
            if categoria and categoria != 'arquivo' and TIPOS[r.ferramenta] != categoria:
                continue
            p = Path(r.caminho)
            nomes = {normalizar_texto(p.name), normalizar_texto(p.stem if r.ferramenta != 'criar_pasta' else p.name)}
            if nome and nome not in nomes:
                continue
            if not any(x.caminho == r.caminho for x in candidatos):
                candidatos.append(r)
        if not candidatos:
            return 'Não tenho registro dessa criação nesta sessão.'
        if nome and len(candidatos) > 1:
            return 'Há mais de um item com esse nome no histórico: ' + '; '.join(r.caminho for r in candidatos[:5]) + '. Especifique o tipo ou consulte os caminhos exibidos.'
        r = candidatos[0]
        resposta = f'Registrei a criação de {Path(r.caminho).name} em {r.caminho}.'
        if r.caminho in self._removidas:
            return resposta + ' Esse item foi removido do local original.'
        try:
            p = Path(r.caminho)
            existe = p.is_dir() if r.ferramenta == 'criar_pasta' else p.is_file()
        except OSError:
            return resposta + ' Não consegui verificar se o item ainda existe.'
        if not existe:
            resposta += ' O item não está mais nesse local ou não está acessível.'
        return resposta
