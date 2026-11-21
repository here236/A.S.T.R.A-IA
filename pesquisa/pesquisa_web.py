import base64
import html
import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser

from configs import configuracoes_voz
from voz.utilitarios_voz import log, normalizar_texto

"""
Pesquisa na web (rede).

Responsabilidade:
    Buscar resultados, ler páginas e extrair texto e tabelas.
    Sem janela e SEM bibliotecas extras: usa só a biblioteca padrão
    do Python. O navegador invisível (Playwright) é um reserva
    opcional, usado só se os sites bloquearem o pedido direto.

Como a busca é feita:
    1) pedido HTTP direto ao DuckDuckGo e ao Bing (leve);
    2) se ambos falharem por bloqueio, o mesmo pedido pelo navegador
       invisível (se configuracoes_voz.MODO_BUSCA permitir);
    3) a Wikipédia (API oficial) serve de reserva e de fonte de resumos.

Segurança:
    - Tudo que vem da web é DADO, nunca instrução: este módulo só
      devolve texto, nunca executa nada.
    - Só abre endereços http/https de fora da sua rede. Links que
      apontem para o próprio computador ou a rede local são recusados,
      inclusive em redirecionamentos.

Este módulo NÃO fala nem salva arquivos: isso é do pesquisa_voz.
"""


# TIPOS

@dataclass
class Resultado:
    titulo: str
    link: str
    resumo: str = ""
    motor: str = ""


@dataclass
class Pagina:
    link: str
    titulo: str = ""
    paragrafos: list = field(default_factory=list)
    tabelas: list = field(default_factory=list)


class ErroBusca(Exception):
    """
    Falha ao buscar. `sem_internet` é True quando o motivo foi a
    falta de conexão (e não um bloqueio do site).
    """

    def __init__(self, motivo, sem_internet=False):

        super().__init__(motivo)

        self.sem_internet = sem_internet


AGENTE_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

AGENTE_ASTRA = "A.S.T.R.A./1.0 (assistente de voz pessoal)"

# Frases que aparecem quando o site desconfia de robô.
SINAIS_DE_BLOQUEIO = (
    "captcha",
    "unusual traffic",
    "trafego incomum",
    "anomaly",
    "are you a human",
    "verifique que voce",
    "verificar que voce",
)

LIMITE_PARAGRAFOS = 60
LIMITE_TABELAS = 5
LIMITE_LINHAS_TABELA = 200
LIMITE_COLUNAS_TABELA = 12
LIMITE_CELULA = 120

_cache = {}


# TEXTO

def _limpar(texto):
    """
    Espaços comuns, sem caracteres de controle nem marcas de nota
    de rodapé como [1] ou [nota 2].
    """

    texto = html.unescape(texto or "")

    texto = re.sub(r"\[(?:nota\s*)?\d+\]|\[[a-z]\]", "", texto)

    texto = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", texto)

    return re.sub(r"\s+", " ", texto.replace("\xa0", " ")).strip()


def _decodificar(corpo, tipo):

    codificacoes = []

    achou = re.search(r"charset=([\w-]+)", tipo or "", re.IGNORECASE)

    if achou:
        codificacoes.append(achou.group(1))

    meta = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', corpo[:4096], re.IGNORECASE)

    if meta:
        codificacoes.append(meta.group(1).decode("ascii", "ignore"))

    codificacoes += ["utf-8", "cp1252"]

    for codificacao in codificacoes:

        try:
            return corpo.decode(codificacao)
        except (LookupError, UnicodeDecodeError):
            continue

    return corpo.decode("utf-8", errors="replace")


# SEGURANÇA DE ENDEREÇOS

def url_segura(url):
    """
    True só para http/https que apontem para a internet de fora.
    Recusa o próprio computador, a rede local e endereços reservados.
    """

    try:
        partes = urllib.parse.urlsplit(url)
        porta = partes.port
    except ValueError:
        return False

    if partes.scheme not in ("http", "https") or not partes.hostname:
        return False

    try:
        enderecos = {
            info[4][0]
            for info in socket.getaddrinfo(
                partes.hostname,
                porta or (443 if partes.scheme == "https" else 80),
                proto=socket.IPPROTO_TCP
            )
        }
    except (socket.gaierror, UnicodeError):
        return False

    for endereco in enderecos:

        ip = ipaddress.ip_address(endereco.split("%")[0])

        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            return False

    return bool(enderecos)


class _RedirecionamentoSeguro(urllib.request.HTTPRedirectHandler):
    """
    Confere cada redirecionamento: um site não pode mandar a
    A.S.T.R.A. para dentro da sua rede.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):

        if not url_segura(newurl):
            raise urllib.error.URLError("redirecionamento para endereço não permitido")

        return super().redirect_request(req, fp, code, msg, headers, newurl)


# DOWNLOAD

def _baixar(url, agente=AGENTE_NAVEGADOR, verificar=True, aceitar="text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5"):
    """
    Devolve (corpo, tipo, url_final, status).
    verificar=False só para os endereços fixos dos buscadores.
    """

    if verificar and not url_segura(url):
        raise ErroBusca("endereço não permitido")

    requisicao = urllib.request.Request(
        url,
        headers={
            "User-Agent": agente,
            "Accept": aceitar,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.5",
        }
    )

    abridor = urllib.request.build_opener(_RedirecionamentoSeguro)

    limite = configuracoes_voz.LIMITE_PAGINA_BYTES

    try:

        with abridor.open(
            requisicao, timeout=configuracoes_voz.TEMPO_LIMITE_REDE
        ) as resposta:

            tipo = resposta.headers.get("Content-Type", "")

            corpo = resposta.read(limite + 1)[:limite]

            return corpo, tipo, resposta.geturl(), resposta.status

    except urllib.error.HTTPError as erro:
        raise ErroBusca(f"HTTP {erro.code}")

    except urllib.error.URLError as erro:

        motivo = erro.reason

        sem_conexao = (
            isinstance(motivo, (socket.gaierror, ConnectionError, OSError))
            and not isinstance(motivo, TimeoutError)
        )

        raise ErroBusca(f"falha de rede ({motivo})", sem_internet=sem_conexao)

    except (TimeoutError, socket.timeout):
        raise ErroBusca("tempo esgotado")

    except (ConnectionError, OSError) as erro:
        raise ErroBusca(f"falha de rede ({erro})", sem_internet=True)


# BUSCADORES: LEITURA DAS PÁGINAS DE RESULTADO

def _link_ddg(href):
    """
    O DuckDuckGo embrulha o link verdadeiro no parâmetro "uddg".
    Devolve "" para anúncios e links internos.
    """

    href = (href or "").strip()

    if href.startswith("//"):
        href = "https:" + href

    partes = urllib.parse.urlsplit(href)

    if "duckduckgo.com" in (partes.hostname or ""):

        alvo = urllib.parse.parse_qs(partes.query).get("uddg")

        return alvo[0] if alvo else ""

    return href


def _link_bing(href):
    """
    O Bing embrulha o link verdadeiro, em base64, no parâmetro "u"
    (começa com "a1").
    """

    href = (href or "").strip()

    partes = urllib.parse.urlsplit(href)

    if "bing.com" in (partes.hostname or "") and partes.path.startswith("/ck/"):

        valor = urllib.parse.parse_qs(partes.query).get("u", [""])[0]

        if valor.startswith("a1"):

            try:
                bruto = valor[2:]
                bruto += "=" * (-len(bruto) % 4)
                return base64.urlsafe_b64decode(bruto).decode("utf-8")
            except Exception:
                return href

    return href


class _ParserDDG(HTMLParser):

    def __init__(self):

        super().__init__(convert_charrefs=True)

        self.itens = []
        self._atual = None
        self._campo = None
        self._tag_campo = None

    def handle_starttag(self, tag, attrs):

        atributos = dict(attrs)

        classes = (atributos.get("class") or "").split()

        if tag == "a" and "result__a" in classes:

            self._atual = {"titulo": "", "link": atributos.get("href", ""), "resumo": ""}
            self.itens.append(self._atual)
            self._campo = "titulo"
            self._tag_campo = "a"

        elif "result__snippet" in classes and self._atual is not None:

            self._campo = "resumo"
            self._tag_campo = tag

    def handle_endtag(self, tag):

        if self._campo and tag == self._tag_campo:
            self._campo = None

    def handle_data(self, dados):

        if self._campo and self._atual is not None:
            self._atual[self._campo] += dados


class _ParserBing(HTMLParser):

    def __init__(self):

        super().__init__(convert_charrefs=True)

        self.itens = []
        self._atual = None
        self._profundidade = 0
        self._em_h2 = False
        self._em_titulo = False
        self._em_resumo = False
        self._resumo_pronto = False

    def handle_starttag(self, tag, attrs):

        atributos = dict(attrs)

        classes = (atributos.get("class") or "").split()

        if tag == "li" and "b_algo" in classes:

            self._atual = {"titulo": "", "link": "", "resumo": ""}
            self.itens.append(self._atual)
            self._profundidade = 1
            self._em_h2 = self._em_titulo = self._em_resumo = False
            self._resumo_pronto = False
            return

        if self._atual is None:
            return

        if tag == "li":
            self._profundidade += 1

        elif tag == "h2":
            self._em_h2 = True

        elif tag == "a" and self._em_h2 and not self._atual["link"]:
            self._atual["link"] = atributos.get("href", "")
            self._em_titulo = True

        elif tag == "p" and self._atual["link"] and not self._resumo_pronto:
            self._em_resumo = True

    def handle_endtag(self, tag):

        if self._atual is None:
            return

        if tag == "a":
            self._em_titulo = False

        elif tag == "h2":
            self._em_h2 = False

        elif tag == "p" and self._em_resumo:
            self._em_resumo = False
            self._resumo_pronto = bool(self._atual["resumo"].strip())

        elif tag == "li":

            self._profundidade -= 1

            if self._profundidade <= 0:
                self._atual = None

    def handle_data(self, dados):

        if self._atual is None:
            return

        if self._em_titulo:
            self._atual["titulo"] += dados

        elif self._em_resumo:
            self._atual["resumo"] += dados


def _parece_bloqueio(texto_html):

    texto = normalizar_texto(re.sub(r"<[^>]+>", " ", texto_html[:20000]))

    return any(sinal in texto for sinal in SINAIS_DE_BLOQUEIO)


def _extrair(motor, texto_html, status=200):
    """
    Lê a página de resultados de um buscador.
    Levanta ErroBusca se a página parecer um bloqueio.
    """

    if motor == "duckduckgo":
        parser, converter = _ParserDDG(), _link_ddg
    elif motor == "bing":
        parser, converter = _ParserBing(), _link_bing
    else:
        raise ErroBusca(f"buscador desconhecido: {motor}")

    try:
        parser.feed(texto_html)
        parser.close()
    except Exception as erro:
        raise ErroBusca(f"página ilegível ({erro})")

    resultados = []
    vistos = set()

    for item in parser.itens:

        link = converter(item["link"])

        partes = urllib.parse.urlsplit(link)

        if partes.scheme not in ("http", "https") or not partes.hostname:
            continue

        if any(h in partes.hostname for h in ("bing.com", "duckduckgo.com")):
            continue

        titulo = _limpar(item["titulo"])

        if not titulo or link in vistos:
            continue

        vistos.add(link)

        resultados.append(
            Resultado(titulo, link, _limpar(item["resumo"]), motor)
        )

    if not resultados and (status in (202, 403, 429) or _parece_bloqueio(texto_html)):
        raise ErroBusca("verificação anti-robô")

    return resultados


def _url_de_busca(motor, consulta):

    if motor == "duckduckgo":
        return "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
            {"q": consulta, "kl": "br-pt"}
        )

    if motor == "bing":
        return "https://www.bing.com/search?" + urllib.parse.urlencode(
            {"q": consulta, "setlang": "pt-BR", "cc": "BR", "count": 10}
        )

    raise ErroBusca(f"buscador desconhecido: {motor}")


def _buscar_http(motor, consulta):

    corpo, tipo, _, status = _baixar(_url_de_busca(motor, consulta), verificar=False)

    return _extrair(motor, _decodificar(corpo, tipo), status)


def _buscar_no_navegador(motor, consulta):
    """
    Reserva: o mesmo pedido, mas por um navegador invisível, que
    executa a página como uma pessoa faria. Mais pesado e mais lento.
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ErroBusca("Playwright não está instalado")

    url = _url_de_busca(motor, consulta)

    try:

        with sync_playwright() as p:

            navegador = None

            for canal in ("msedge", "chrome"):

                try:
                    navegador = p.chromium.launch(channel=canal, headless=True)
                    break
                except Exception:
                    continue

            if navegador is None:
                raise ErroBusca("Edge e Chrome não encontrados")

            try:

                pagina = navegador.new_page(locale="pt-BR")

                pagina.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=configuracoes_voz.TEMPO_LIMITE_REDE * 1000
                )

                pagina.wait_for_timeout(1000)

                texto_html = pagina.content()

            finally:
                navegador.close()

    except ErroBusca:
        raise

    except Exception as erro:
        raise ErroBusca(f"navegador: {erro}")

    return _extrair(motor, texto_html)


# BUSCA NA WEB

def buscar_web(consulta, quantidade=None):
    """
    Pesquisa na web e devolve uma lista de Resultado (pode ser vazia
    se a busca funcionou mas não achou nada).
    Levanta ErroBusca se NENHUM buscador respondeu.
    """

    quantidade = quantidade or configuracoes_voz.QUANTIDADE_RESULTADOS

    chave = normalizar_texto(consulta)

    guardado = _cache.get(chave)

    if guardado and time.time() - guardado[0] < configuracoes_voz.VALIDADE_CACHE_BUSCA:
        return list(guardado[1])[:quantidade]

    modo = configuracoes_voz.MODO_BUSCA

    motores = [
        m for m in configuracoes_voz.MOTORES_DE_BUSCA
        if m in ("duckduckgo", "bing")
    ]

    if not motores:
        raise ErroBusca("nenhum buscador válido em MOTORES_DE_BUSCA")

    falhas = []
    sem_internet = []
    respondeu = False

    if modo != "navegador":

        for motor in motores:

            try:
                resultados = _buscar_http(motor, consulta)
            except ErroBusca as erro:
                falhas.append(f"{motor}: {erro}")
                sem_internet.append(erro.sem_internet)
                log(f"Busca no {motor} falhou: {erro}", "AVISO")
                continue

            respondeu = True

            if resultados:
                _cache[chave] = (time.time(), resultados)
                return resultados[:quantidade]

            falhas.append(f"{motor}: nenhum resultado")

    # Sem internet, o navegador não ajudaria: só gastaria tempo.
    sem_conexao = bool(sem_internet) and all(sem_internet)

    if modo in ("automatico", "navegador") and not sem_conexao and not respondeu:

        for motor in motores:

            try:
                resultados = _buscar_no_navegador(motor, consulta)
            except ErroBusca as erro:
                falhas.append(f"{motor}+navegador: {erro}")
                sem_internet.append(erro.sem_internet)
                log(f"Busca no {motor} pelo navegador falhou: {erro}", "AVISO")
                continue

            respondeu = True

            if resultados:
                _cache[chave] = (time.time(), resultados)
                return resultados[:quantidade]

            falhas.append(f"{motor}+navegador: nenhum resultado")

    if respondeu:
        return []

    raise ErroBusca(
        "; ".join(falhas),
        sem_internet=bool(sem_internet) and all(sem_internet)
    )


# WIKIPÉDIA

_API_WIKIPEDIA = "https://pt.wikipedia.org/w/api.php?"


def _json_wikipedia(parametros):

    parametros = {**parametros, "format": "json", "utf8": 1}

    corpo, tipo, _, _ = _baixar(
        _API_WIKIPEDIA + urllib.parse.urlencode(parametros),
        agente=AGENTE_ASTRA,
        verificar=False,
        aceitar="application/json"
    )

    try:
        return json.loads(_decodificar(corpo, tipo))
    except ValueError:
        raise ErroBusca("resposta inválida da Wikipédia")


def _link_wikipedia(titulo):

    return "https://pt.wikipedia.org/wiki/" + urllib.parse.quote(titulo.replace(" ", "_"))


def buscar_wikipedia(consulta, quantidade=3):
    """
    Resultados da Wikipédia em português (API oficial).
    """

    dados = _json_wikipedia({
        "action": "query",
        "list": "search",
        "srsearch": consulta,
        "srlimit": quantidade,
    })

    itens = dados.get("query", {}).get("search", [])

    return [
        Resultado(
            titulo=item["title"],
            link=_link_wikipedia(item["title"]),
            resumo=_limpar(re.sub(r"<[^>]+>", "", item.get("snippet", ""))),
            motor="wikipedia"
        )
        for item in itens
        if item.get("title")
    ]


_PALAVRAS_VAZIAS = {
    "de", "da", "do", "das", "dos", "para", "como", "sobre", "que", "uma",
    "uns", "com", "por", "em", "na", "no", "os", "as", "um", "e", "o", "a",
}


def _radicais(texto):

    return {
        palavra[:5]
        for palavra in normalizar_texto(texto).split()
        if len(palavra) >= 4 and palavra not in _PALAVRAS_VAZIAS
    }


def _relevante(assunto, titulo):
    """
    O artigo da Wikipédia tem a ver com o assunto? Compara o começo
    das palavras, assim "buracos negros" bate com "Buraco negro".
    """

    return bool(_radicais(assunto) & _radicais(titulo))


def resumo_wikipedia(assunto):
    """
    Introdução do artigo mais próximo do assunto.
    Devolve (titulo, [parágrafos], link) ou None.
    """

    for resultado in buscar_wikipedia(assunto, 1):

        if not _relevante(assunto, resultado.titulo):
            return None

        dados = _json_wikipedia({
            "action": "query",
            "prop": "extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": resultado.titulo,
        })

        paginas = dados.get("query", {}).get("pages", {})

        if not paginas:
            return None

        extrato = next(iter(paginas.values())).get("extract", "")

        paragrafos = [
            _limpar(p) for p in extrato.split("\n") if len(_limpar(p)) >= 40
        ]

        if not paragrafos:
            return None

        return resultado.titulo, paragrafos, resultado.link

    return None


# LEITURA DE PÁGINAS

_IGNORAR = {
    "script", "style", "noscript", "svg", "template", "nav", "footer",
    "header", "aside", "form", "iframe", "button", "select", "dialog",
}

_CLASSES_DE_TABELA_IGNORADAS = {
    "navbox", "vertical-navbox", "sidebar", "ambox", "mbox", "infobox",
    "metadata", "navbar",
}


def _montar_grade(linhas):
    """
    Transforma as linhas lidas (texto, colspan, rowspan) numa grade
    retangular, repetindo as células mescladas.
    """

    grade = []
    pendentes = {}

    for linha in linhas:

        atual = []

        def preencher():

            while len(atual) in pendentes:

                coluna = len(atual)
                texto, resta = pendentes[coluna]
                atual.append(texto)

                if resta <= 1:
                    del pendentes[coluna]
                else:
                    pendentes[coluna][1] = resta - 1

        for texto, colspan, rowspan in linha:

            preencher()

            for _ in range(colspan):

                coluna = len(atual)
                atual.append(texto)

                if rowspan > 1:
                    pendentes[coluna] = [texto, rowspan - 1]

        preencher()

        grade.append(atual)

    return grade


def _tabela_util(grade):
    """
    Limpa a grade e devolve None se não parecer uma tabela de dados.
    """

    if len(grade) < 3:
        return None

    contagem = {}

    for linha in grade:
        contagem[len(linha)] = contagem.get(len(linha), 0) + 1

    largura = max(contagem, key=lambda n: (contagem[n], n))

    if largura < 2:
        return None

    largura = min(largura, LIMITE_COLUNAS_TABELA)

    linhas = [
        [_limpar(c)[:LIMITE_CELULA] for c in linha[:largura]]
        for linha in grade
        if len(linha) >= largura
    ][:LIMITE_LINHAS_TABELA]

    if len(linhas) < 3 or not any(linhas[0]):
        return None

    return linhas


class _ParserPagina(HTMLParser):

    def __init__(self):

        super().__init__(convert_charrefs=True)

        self.titulo = ""
        self.paragrafos = []
        self.tabelas = []

        self._ignorando = 0
        self._em_titulo = False
        self._em_p = False
        self._buffer_p = ""

        self._tabela_prof = 0
        self._tabela_ignorada = False
        self._linhas = []
        self._linha = None
        self._em_celula = False
        self._texto_celula = ""
        self._span = (1, 1)

    @staticmethod
    def _inteiro(valor):

        try:
            return max(1, min(int(valor), 20))
        except (TypeError, ValueError):
            return 1

    def handle_starttag(self, tag, attrs):

        atributos = dict(attrs)

        if tag == "title":
            self._em_titulo = True

        if tag in _IGNORAR:
            self._ignorando += 1
            return

        if self._ignorando:
            return

        if tag == "br":

            if self._em_celula:
                self._texto_celula += " "
            elif self._em_p:
                self._buffer_p += " "

        elif tag == "table":

            self._tabela_prof += 1

            if self._tabela_prof == 1:

                classes = set((atributos.get("class") or "").split())

                self._tabela_ignorada = bool(classes & _CLASSES_DE_TABELA_IGNORADAS)
                self._linhas = []
                self._linha = None

        elif self._tabela_prof == 1 and not self._tabela_ignorada:

            if tag == "tr":
                self._linha = []

            elif tag in ("td", "th") and self._linha is not None:

                self._em_celula = True
                self._texto_celula = ""
                self._span = (
                    self._inteiro(atributos.get("colspan")),
                    self._inteiro(atributos.get("rowspan")),
                )

        elif tag == "p" and self._tabela_prof == 0:

            self._em_p = True
            self._buffer_p = ""

    def handle_endtag(self, tag):

        if tag == "title":
            self._em_titulo = False

        if tag in _IGNORAR:
            self._ignorando = max(0, self._ignorando - 1)
            return

        if self._ignorando:
            return

        if tag == "table" and self._tabela_prof > 0:

            if self._tabela_prof == 1 and not self._tabela_ignorada:

                tabela = _tabela_util(_montar_grade(self._linhas))

                if tabela:
                    self.tabelas.append(tabela)

            self._tabela_prof -= 1

        elif self._tabela_prof == 1 and not self._tabela_ignorada:

            if tag in ("td", "th") and self._em_celula:

                self._em_celula = False

                if self._linha is not None:
                    self._linha.append((self._texto_celula, *self._span))

            elif tag == "tr" and self._linha is not None:

                if self._linha:
                    self._linhas.append(self._linha)

                self._linha = None

        elif tag == "p" and self._em_p:

            self._em_p = False

            texto = _limpar(self._buffer_p)

            if len(texto) >= 40:
                self.paragrafos.append(texto)

    def handle_data(self, dados):

        if self._em_titulo:
            self.titulo += dados

        if self._ignorando:
            return

        if self._em_celula:
            self._texto_celula += dados

        elif self._em_p and self._tabela_prof == 0:
            self._buffer_p += dados


def ler_pagina(url):
    """
    Baixa uma página e devolve o título, os parágrafos de texto e as
    tabelas de dados. Levanta ErroBusca se não conseguir.
    """

    corpo, tipo, url_final, _ = _baixar(url)

    if tipo and "html" not in tipo.lower():
        raise ErroBusca(f"tipo de arquivo não suportado: {tipo.split(';')[0]}")

    parser = _ParserPagina()

    try:
        parser.feed(_decodificar(corpo, tipo))
        parser.close()
    except Exception as erro:
        raise ErroBusca(f"página ilegível ({erro})")

    vistos = set()
    paragrafos = []

    for paragrafo in parser.paragrafos:

        if paragrafo not in vistos:
            vistos.add(paragrafo)
            paragrafos.append(paragrafo)

    return Pagina(
        link=url_final,
        titulo=_limpar(parser.titulo),
        paragrafos=paragrafos[:LIMITE_PARAGRAFOS],
        tabelas=parser.tabelas[:LIMITE_TABELAS],
    )


def limpar_cache():

    _cache.clear()
