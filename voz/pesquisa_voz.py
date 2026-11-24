import re
import webbrowser
from urllib.parse import urlparse

from configs import configuracoes_voz
from pesquisa import pesquisa_web
from arquivos.gerenciador_arquivos import (
    ConteudoPesquisado,
    Fonte,
    TrechoPesquisado,
    _padrao_local,
    gerenciador_arquivos,
)
from pesquisa.pesquisa_web import ErroBusca
from .utilitarios_voz import log, normalizar_texto

"""
Pesquisa por voz.

Responsabilidade:
    Pesquisar, falar os resultados, ler páginas aos poucos e
    transformar uma pesquisa em documento, planilha, apresentação
    ou arquivo de texto (sempre com as fontes).

Cada operação devolve a frase que deve ser FALADA. A rede fica no
pesquisa_web e a gravação dos arquivos no arquivos_voz.

O que a A.S.T.R.A. faz com o que acha na web:
    SÓ LÊ e MOSTRA. Nunca executa passos, comandos ou arquivos
    encontrados na internet. Quem decide o que fazer é você.

Como o conteúdo é montado (sem IA):
    - resumo da Wikipédia, quando há um artigo sobre o assunto;
    - os primeiros parágrafos de cada página (trechos curtos,
      sempre com o nome e o link da fonte);
    - a maior tabela de dados encontrada, para planilhas.
    Confira sempre as fontes: a A.S.T.R.A. reúne, não confirma.
"""


MSG_SEM_INTERNET = (
    "Não consegui pesquisar. Parece que o computador está sem internet."
)

MSG_INDISPONIVEL = (
    "Não consegui pesquisar agora. Os sites de busca não responderam. "
    "Tente de novo em instantes."
)

_ORDINAIS = (
    "Primeiro", "Segundo", "Terceiro", "Quarto", "Quinto",
    "Sexto", "Sétimo", "Oitavo", "Nono", "Décimo",
)

_NUMEROS = {
    "um": 1, "uma": 1, "primeiro": 1, "primeira": 1,
    "dois": 2, "duas": 2, "segundo": 2, "segunda": 2,
    "tres": 3, "terceiro": 3, "terceira": 3,
    "quatro": 4, "quarto": 4, "quarta": 4,
    "cinco": 5, "quinto": 5, "quinta": 5,
    "seis": 6, "sexto": 6, "sexta": 6,
    "sete": 7, "setimo": 7, "oito": 8, "oitavo": 8,
    "nove": 9, "nono": 9, "dez": 10, "decimo": 10,
}

_FORMATOS = {
    "documento": "documento", "relatorio": "documento", "word": "documento",
    "planilha": "planilha", "excel": "planilha",
    "apresentacao": "apresentacao", "slides": "apresentacao",
    "powerpoint": "apresentacao",
    "texto": "texto",
}

# "buracos negros e faça um documento na área de trabalho"
_PEDIDO_ARQUIVO = re.compile(
    r"^(?:sobre\s+)?(?P<assunto>.+?)\s+e\s+"
    r"(?:fa[cç]a|crie|monte|gere|salve|escreva)\s+"
    r"(?:(?:em|num|numa)\s+)?(?:(?:um|uma)\s+)?"
    r"(?P<formato>documento|relat[oó]rio|word|planilha|excel|"
    r"apresenta[cç][aã]o|slides|powerpoint|texto)\b"
    r"(?P<resto>.*)$",
    re.IGNORECASE | re.DOTALL,
)

_SOBRE = re.compile(r"^(?:sobre|a respeito de|acerca de)(?:\s+|$)", re.IGNORECASE)


def _dominio(link):
    """Extrai o domínio legível de um endereço de resultado."""
    return urlparse(link).netloc.removeprefix("www.") or "site desconhecido"


# FUNÇÕES AUXILIARES

def _numero(parametro):
    """
    "dois", "2", "segundo" -> 2. Vazio -> 1. Não entendeu -> None.
    """

    palavras = normalizar_texto(parametro).split()

    if not palavras:
        return 1

    for palavra in palavras:

        if palavra.isdigit():
            return int(palavra)

        if palavra in _NUMEROS:
            return _NUMEROS[palavra]

    return None


def _encurtar(texto, limite):
    """
    Corta em uma palavra inteira, sem reticências (para falar em voz alta).
    """

    texto = (texto or "").strip()

    if len(texto) <= limite:
        return texto

    return texto[:limite].rsplit(" ", 1)[0].rstrip(",;:- ")


def _com_ponto(texto):

    texto = texto.strip()

    if not texto:
        return ""

    return texto if texto[-1] in ".!?" else texto + "."


def _dividir_em_trechos(texto, limite):
    """
    Divide um texto longo em trechos que cabem numa leitura, sempre
    terminando no fim de uma frase.
    """

    trechos = []
    atual = ""

    for frase in re.split(r"(?<=[.!?])\s+", texto):

        while len(frase) > limite:

            if atual:
                trechos.append(atual)
                atual = ""

            corte = frase[:limite].rsplit(" ", 1)[0] or frase[:limite]

            trechos.append(corte)

            frase = frase[len(corte):].strip()

        if atual and len(atual) + len(frase) + 1 > limite:
            trechos.append(atual)
            atual = ""

        atual = f"{atual} {frase}".strip()

    if atual:
        trechos.append(atual)

    return trechos


def _indice_do_extra(texto):
    """
    Onde, no texto original, começa o lugar falado ("na area de
    trabalho"). None se não houver.
    """

    palavras = texto.split()

    normais = []
    origem = []

    for indice, palavra in enumerate(palavras):

        for parte in normalizar_texto(palavra).split():
            normais.append(parte)
            origem.append(indice)

    juntas = " ".join(normais)

    menor = None

    for chave in configuracoes_voz.LOCAIS_ARQUIVOS:

        achou = re.search(_padrao_local(chave), juntas)

        if achou and (menor is None or achou.start() < menor):
            menor = achou.start()

    if not menor:
        return None

    return origem[juntas[:menor].count(" ")]


def _trecho_da_pagina(pagina, limite=600):
    """
    Os primeiros parágrafos da página, até o limite. Só um trecho
    curto de cada fonte: o resto fica no link.
    """

    paragrafos = [p for p in pagina.paragrafos if len(p) >= 80]

    paragrafos = paragrafos or [p for p in pagina.paragrafos if len(p) >= 40]

    texto = ""

    for paragrafo in paragrafos:

        if texto and len(texto) + len(paragrafo) > limite:
            break

        texto = f"{texto} {paragrafo}".strip()

    if len(texto) > limite:

        corte = texto[:limite]

        ponto = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))

        texto = corte[:ponto + 1] if ponto > limite // 2 else _encurtar(texto, limite)

    return texto


def _montar_conteudo(assunto, resultados, resumo, paginas):
    """
    Junta o que foi encontrado num ConteudoPesquisado.
    """

    conteudo = ConteudoPesquisado(assunto=assunto)

    fontes = {}

    def registrar_fonte(titulo, link):

        if link and link not in fontes:
            fontes[link] = Fonte(titulo[:120] or link, link)

    if resumo:

        titulo, paragrafos, link = resumo

        texto = ""
        escolhidos = []

        for paragrafo in paragrafos:

            if len(texto) + len(paragrafo) > 1500 and escolhidos:
                break

            escolhidos.append(paragrafo)
            texto += paragrafo

        conteudo.introducao = escolhidos
        conteudo.fonte_introducao = Fonte(f"Wikipédia: {titulo}", link)

        registrar_fonte(f"Wikipédia: {titulo}", link)

    usados = set()

    for resultado, pagina in paginas:

        texto = _trecho_da_pagina(pagina)

        chave = normalizar_texto(texto)[:80]

        if texto and chave not in usados:

            usados.add(chave)

            fonte = Fonte(
                (pagina.titulo or resultado.titulo)[:120],
                pagina.link or resultado.link
            )

            conteudo.trechos.append(TrechoPesquisado(fonte, texto))

            registrar_fonte(fonte.titulo, fonte.link)

    melhor = None

    for resultado, pagina in paginas:

        for tabela in pagina.tabelas:

            tamanho = len(tabela) * len(tabela[0])

            if melhor is None or tamanho > melhor[0]:
                melhor = (tamanho, tabela, Fonte(
                    (pagina.titulo or resultado.titulo)[:120],
                    pagina.link or resultado.link
                ))

    if melhor:

        _, conteudo.tabela, conteudo.fonte_tabela = melhor

        registrar_fonte(conteudo.fonte_tabela.titulo, conteudo.fonte_tabela.link)

    for resultado in resultados:
        registrar_fonte(resultado.titulo, resultado.link)

    conteudo.fontes = list(fontes.values())

    conteudo.resultados = [(r.titulo, r.resumo, r.link) for r in resultados]

    return conteudo


# GERENCIADOR

class GerenciadorPesquisa:

    def __init__(self):

        self.consulta = ""
        self.resultados = []

        self._trechos = []
        self._indice = 0

    # BUSCAR E FALAR

    def _wikipedia_de_reserva(self, consulta):

        try:
            return pesquisa_web.buscar_wikipedia(consulta, 3)
        except ErroBusca as erro:
            log(f"Wikipédia também falhou: {erro}", "AVISO")
            return []

    def _pesquisar_e_falar(self, consulta):

        try:
            resultados = pesquisa_web.buscar_web(consulta)

        except ErroBusca as erro:

            if erro.sem_internet:
                return MSG_SEM_INTERNET

            log(f"Nenhum buscador respondeu: {erro}", "ERRO")

            resultados = self._wikipedia_de_reserva(consulta)

            if not resultados:
                return MSG_INDISPONIVEL

        else:

            if not resultados:
                resultados = self._wikipedia_de_reserva(consulta)

            if not resultados:
                return f"Não encontrei resultados para {consulta}."

        self.consulta = consulta
        self.resultados = resultados
        self._trechos = []
        self._indice = 0

        return self._falar_resultados()

    def _falar_resultados(self):

        total = len(self.resultados)

        partes = [
            f"Encontrei {total} "
            f"{'resultado' if total == 1 else 'resultados'} "
            f"para {self.consulta}."
        ]

        falados = self.resultados[:configuracoes_voz.RESULTADOS_FALADOS]

        for indice, resultado in enumerate(falados):

            partes.append(
                f"{_ORDINAIS[indice]}, no site {_dominio(resultado.link)}: "
                f"{_com_ponto(resultado.titulo)} "
                f"{_com_ponto(_encurtar(resultado.resumo, 140))}".strip()
            )

        partes.append(
            "Diga leia o resultado, e o número, ou abra o resultado, "
            "e o número."
        )

        return " ".join(partes)

    def pesquisar(self, parametro):
        """
        "buracos negros" ou "sobre buracos negros e faça um documento".
        """

        texto = (parametro or "").strip().strip(".,;!?")

        pedido = _PEDIDO_ARQUIVO.match(texto)

        if pedido:

            formato = _FORMATOS[normalizar_texto(pedido.group("formato"))]

            return self._pesquisar_e_salvar(
                pedido.group("assunto").strip(),
                formato,
                pedido.group("resto").strip()
            )

        assunto = _SOBRE.sub("", texto).strip()

        if not assunto:
            return "O que você quer pesquisar?"

        return self._pesquisar_e_falar(assunto)

    def pesquisar_como(self, parametro, prefixo="como"):
        """
        "como fazer um gráfico no Excel": só pesquisa e explica.
        """

        assunto = (parametro or "").strip().strip(".,;!?")

        if not assunto:
            return (
                "Como fazer o quê? Diga, por exemplo: "
                "como fazer um gráfico no Excel."
            )

        return self._pesquisar_e_falar(f"{prefixo} {assunto}")

    # LER E ABRIR RESULTADOS

    def _resultado(self, parametro):
        """
        Devolve (número, Resultado) ou uma frase de erro.
        """

        if not self.resultados:
            return None, "Ainda não pesquisei nada. Diga pesquise, e o assunto."

        numero = _numero(parametro)

        if numero is None:
            return None, (
                "Qual resultado? Diga um número, por exemplo: "
                "leia o resultado dois."
            )

        if not 1 <= numero <= len(self.resultados):

            total = len(self.resultados)

            return None, (
                f"Só tenho {total} "
                f"{'resultado' if total == 1 else 'resultados'}."
            )

        return (numero, self.resultados[numero - 1]), ""

    def _proximo_trecho(self):

        trecho = self._trechos[self._indice]

        self._indice += 1

        if self._indice < len(self._trechos):
            return trecho + " Diga continue lendo para ouvir mais."

        return trecho + " Fim do texto."

    def ler_resultado(self, parametro=""):

        escolhido, erro = self._resultado(parametro)

        if escolhido is None:
            return erro

        numero, resultado = escolhido

        try:
            pagina = pesquisa_web.ler_pagina(resultado.link)

        except ErroBusca as falha:

            log(f"Não consegui ler {resultado.link}: {falha}", "AVISO")

            return (
                "Não consegui ler essa página. "
                f"Diga abra o resultado {numero} para vê-la no navegador."
            )

        texto = " ".join(pagina.paragrafos)

        if not texto:

            if resultado.resumo:
                return (
                    "Não achei texto nessa página. O resumo diz: "
                    + _com_ponto(resultado.resumo)
                )

            return "Não achei texto nessa página."

        self._trechos = _dividir_em_trechos(
            texto, configuracoes_voz.CARACTERES_POR_LEITURA
        )

        self._indice = 0

        titulo = _com_ponto(pagina.titulo or resultado.titulo)

        return f"{titulo} {self._proximo_trecho()}"

    def continuar_leitura(self):

        if self._indice >= len(self._trechos):
            return "Não há mais texto para ler."

        return self._proximo_trecho()

    def abrir_resultado(self, parametro=""):

        escolhido, erro = self._resultado(parametro)

        if escolhido is None:
            return erro

        numero, resultado = escolhido

        if not resultado.link.lower().startswith(("http://", "https://")):
            return "Esse endereço não é seguro para abrir."

        webbrowser.open(resultado.link)

        return f"Abrindo o resultado {numero} no navegador."

    def repetir_resultados(self):

        if not self.resultados:
            return "Ainda não pesquisei nada. Diga pesquise, e o assunto."

        return self._falar_resultados()

    # PESQUISAR E SALVAR

    def pesquisar_para_arquivo(self, parametro, formato):
        """
        "faça um documento sobre buracos negros na area de trabalho"
        """

        texto = _SOBRE.sub("", (parametro or "").strip().strip(".,;!?")).strip()

        corte = _indice_do_extra(texto)

        if corte is None:
            assunto, extra = texto, ""
        else:
            palavras = texto.split()
            assunto, extra = " ".join(palavras[:corte]), " ".join(palavras[corte:])

        if not assunto:
            return "Sobre qual assunto?"

        return self._pesquisar_e_salvar(assunto, formato, extra)

    def _pesquisar_e_salvar(self, assunto, formato, extra):

        falhou = False
        sem_internet = False

        try:
            resultados = pesquisa_web.buscar_web(
                assunto, configuracoes_voz.QUANTIDADE_RESULTADOS
            )
        except ErroBusca as erro:
            resultados = []
            falhou = True
            sem_internet = erro.sem_internet
            log(f"Busca para o arquivo falhou: {erro}", "AVISO")

        resumo = None

        try:
            resumo = pesquisa_web.resumo_wikipedia(assunto)
        except ErroBusca as erro:
            falhou = True
            sem_internet = sem_internet and erro.sem_internet
            log(f"Resumo da Wikipédia falhou: {erro}", "AVISO")

        if not resultados and not resumo:

            if sem_internet:
                return MSG_SEM_INTERNET

            if falhou:
                return MSG_INDISPONIVEL

            return f"Não encontrei informações sobre {assunto}."

        paginas = []

        for resultado in resultados[:configuracoes_voz.PAGINAS_PARA_LER]:

            try:
                paginas.append((resultado, pesquisa_web.ler_pagina(resultado.link)))
            except ErroBusca as erro:
                log(f"Não consegui ler {resultado.link}: {erro}", "AVISO")

        # Para planilhas, a página da Wikipédia também entra: é onde
        # costumam estar as tabelas de dados.
        if formato == "planilha" and resumo:

            try:
                paginas.append((
                    pesquisa_web.Resultado(f"Wikipédia: {resumo[0]}", resumo[2]),
                    pesquisa_web.ler_pagina(resumo[2])
                ))
            except ErroBusca as erro:
                log(f"Não consegui ler a página da Wikipédia: {erro}", "AVISO")

        conteudo = _montar_conteudo(assunto, resultados, resumo, paginas)

        return gerenciador_arquivos.salvar_conteudo(formato, extra, conteudo)


# INSTÂNCIA PRINCIPAL

gerenciador_pesquisa = GerenciadorPesquisa()
