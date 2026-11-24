import functools
import re
from pathlib import Path
from typing import Optional
import difflib

from configs import configuracoes_voz
from voz.utilitarios_voz import log, normalizar_texto

"""
Manipulação de arquivos da A.S.T.R.A.

Responsabilidade:
    Criar pastas, documentos Word, planilhas Excel, apresentações
    PowerPoint e arquivos de texto; escrever e ler neles; listar e
    excluir.

Regras de segurança:
    - Só mexe nos locais de configuracoes_voz.LOCAIS_ARQUIVOS.
    - Nunca sobrescreve: se o nome já existe, avisa.
    - Excluir manda para a LIXEIRA (dá para recuperar).

Este módulo NÃO reconhece comandos (isso é do comandos_voz) e NÃO
fala nada. Cada operação devolve a frase que deve ser FALADA.
"""


# Palavras que sobram no começo do que foi falado ("a pasta fotos",
# "o documento chamado relatorio") e não fazem parte do nome.
PALAVRAS_IGNORADAS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da",
    "arquivo", "pasta", "documento", "planilha",
    "chamado", "chamada", "nome", "com"
}

# Palavras que anunciam o nome: "chamado joel", "com o nome joel".
# Tudo que vem DEPOIS delas é o nome. Aceita erro de digitação
# ("chamdo" também vale).
MARCADORES_DE_NOME = ("chamado", "chamada", "nome", "intitulado", "intitulada")

# Marcadores do título de um slide: "slide chamado X", "com o título X".
MARCADORES_DE_TITULO = ("titulo", "chamado", "chamada", "intitulado", "intitulada")

# Só procura o marcador nas primeiras palavras, para não confundir
# com uma palavra do próprio nome.
PALAVRAS_ANTES_DO_NOME = 4

# Como cada extensão é dita em voz.
TIPOS_DE_ARQUIVO = {
    ".docx": "documento",
    ".xlsx": "planilha",
    ".pptx": "apresentação",
    ".txt": "arquivo de texto",
}

LIMITE_ITENS_FALADOS = 15
LIMITE_LINHAS_LIDAS = 20


class ErroArquivo(Exception):
    """
    Erro previsto. A mensagem já é a frase a ser falada.
    """


# FUNÇÕES AUXILIARES

def _chave(texto):
    """
    Forma comparável de um nome: sem acento, minúsculo, com "_".
    "Relatório Final" e "relatorio final" viram "relatorio_final".
    """

    return "_".join(normalizar_texto(texto).split())


def _eh_marcador(palavra):
    """
    "chamado", "chamada", "nome"... mesmo com erro de digitação.
    """

    return bool(
        difflib.get_close_matches(
            palavra, MARCADORES_DE_NOME, n=1, cutoff=0.8
        )
    )


def _limpar_nome(parametro):
    """
    Devolve só o nome, em forma de chave.

    1) Se houver um marcador ("chamado", "com o nome"...) nas primeiras
       palavras, o nome é tudo que vem depois dele.
    2) Senão, tira as palavras soltas do começo ("a pasta fotos").

    "a pasta chamada fotos de viagem" -> "fotos_de_viagem"
    "documento chamdo joel"           -> "joel"
    """

    palavras = normalizar_texto(parametro).split()

    for i, palavra in enumerate(palavras[:PALAVRAS_ANTES_DO_NOME]):

        if _eh_marcador(palavra) and palavras[i + 1:]:
            palavras = palavras[i + 1:]
            break

    while palavras and palavras[0] in PALAVRAS_IGNORADAS:
        palavras.pop(0)

    return "_".join(palavras)


def _texto_apos_marcador(texto, marcadores):
    """
    Como _limpar_nome, mas mantém o texto COMO FOI FALADO (acento e
    maiúscula) e usa a lista de marcadores que você passar.
    "com o título Introdução" -> "Introdução"
    """

    palavras = texto.split()

    for i, palavra in enumerate(palavras[:PALAVRAS_ANTES_DO_NOME]):

        parecida = difflib.get_close_matches(
            normalizar_texto(palavra), marcadores, n=1, cutoff=0.8
        )

        if parecida and palavras[i + 1:]:
            return " ".join(palavras[i + 1:])

    return texto.strip()


def _separar_colunas(parametro):
    """
    "vendas com as colunas nome, idade e cidade"
        -> ("vendas", "nome, idade e cidade")
    """

    partes = re.split(
        r"\bcom\s+(?:as\s+)?colunas?\b",
        parametro,
        maxsplit=1,
        flags=re.IGNORECASE
    )

    if len(partes) == 2:
        return partes[0], partes[1]

    return parametro, ""


def _lista_de_valores(texto, misto=False):
    """
    Separa o que foi dito em itens. Aceita vírgula, a palavra "e",
    ou só espaços.

    misto=True (colunas): "nome, idade e cidade" -> 3 itens.
    misto=False (linhas): se tiver vírgula, só ela separa, assim
    "Ana e Paulo, 30" -> ["Ana e Paulo", "30"].
    """

    texto = texto.strip().rstrip(".")

    if not texto:
        return []

    tem_virgula = "," in texto
    tem_e = re.search(r"\s+e\s+", texto) is not None

    if misto and (tem_virgula or tem_e):
        partes = re.split(r"\s*,\s*|\s+e\s+", texto)
    elif tem_virgula:
        partes = texto.split(",")
    elif tem_e:
        partes = re.split(r"\s+e\s+", texto)
    else:
        partes = texto.split()

    return [parte.strip() for parte in partes if parte.strip()]


def _separar_local(parametro):
    """
    Separa o lugar falado do resto.
    "teste na area de trabalho" -> ("teste", "area de trabalho")
    "teste"                     -> ("teste", None)
    """

    texto = normalizar_texto(parametro)

    for chave in sorted(configuracoes_voz.LOCAIS_ARQUIVOS, key=len, reverse=True):

        padrao = (
            r"\b(?:em|na|no|nos|nas|de|da|do)\s+"
            r"(?:(?:a|o|os|as)\s+)?" + re.escape(chave) + r"\b"
        )

        achou = re.search(padrao, texto)

        if achou:
            resto = texto[:achou.start()] + " " + texto[achou.end():]
            return resto.strip(), chave

    return texto, None


def _onde(chave):
    """
    Como o lugar é dito em voz. Vazio para o local padrão.
    """

    if chave == configuracoes_voz.LOCAL_PADRAO:
        return ""

    preposicao = "na" if chave.startswith("area") else "em"

    return f" {preposicao} {chave}"


def _descrever(caminho):
    """
    Como o item é dito em voz: "documento relatorio", "pasta fotos".
    """

    if caminho.is_dir():
        tipo = "pasta"
    else:
        tipo = TIPOS_DE_ARQUIVO.get(caminho.suffix, "arquivo")

    return f"{tipo} {caminho.stem.replace('_', ' ')}"


def _converter_valor(texto):
    """
    "100" -> 100, "12,5" -> 12.5; o resto continua texto.
    Assim o Excel consegue somar o que foi ditado.
    """

    limpo = texto.strip().replace(",", ".")

    try:
        numero = float(limpo)
    except ValueError:
        return texto.strip()

    return int(numero) if numero.is_integer() else numero


def _valor_da_celula(valores, formulas, linha, coluna):
    """
    Valor de uma célula para ser lido em voz.

    Fórmulas escritas pela A.S.T.R.A. ainda não têm resultado guardado
    (o Excel só calcula ao abrir o arquivo). Para o total de
    "=SUM(C2:C5)" ser falado, a soma é refeita aqui.
    """

    valor = valores.cell(linha, coluna).value

    if valor is not None:
        return valor

    formula = formulas.cell(linha, coluna).value

    if not isinstance(formula, str):
        return None

    achou = re.fullmatch(r"=SUM\(([A-Z]{1,3}[0-9]+):([A-Z]{1,3}[0-9]+)\)", formula)

    if not achou:
        return None

    total = sum(
        celula.value
        for faixa in valores[achou.group(1):achou.group(2)]
        for celula in faixa
        if isinstance(celula.value, (int, float))
        and not isinstance(celula.value, bool)
    )

    return round(total, 2)


def _falar_numero(numero):
    """
    12.0 -> "12"; 12.5 -> "12,50"
    """

    if float(numero).is_integer():
        return str(int(numero))

    return f"{numero:.2f}".replace(".", ",")


def _seguro(funcao):
    """
    Transforma os erros comuns em frases faladas, em vez de deixar
    a A.S.T.R.A. responder só "não consegui executar".
    """

    @functools.wraps(funcao)
    def interna(*args, **kwargs):

        try:
            return funcao(*args, **kwargs)

        except ErroArquivo as erro:
            return str(erro)

        except PermissionError:
            return (
                "Não consegui mexer nesse arquivo. Ele pode estar "
                "aberto em outro programa. Feche e tente de novo."
            )

        except ImportError as erro:
            log(
                f"Biblioteca ausente: {erro.name}. Rode: "
                "pip install python-docx openpyxl python-pptx send2trash",
                "ERRO"
            )
            return "Falta instalar uma biblioteca do Python. Veja o terminal."

    return interna


# GERENCIADOR

class GerenciadorArquivos:

    def __init__(self):

        # Arquivo em uso: é nele que "escreva" e "leia" trabalham.
        self.atual: Optional[Path] = None

    @staticmethod
    def _pasta_local(chave):
        """
        Pasta (já criada) de um dos locais permitidos.
        """

        pasta = Path(configuracoes_voz.LOCAIS_ARQUIVOS[chave]).resolve()

        if not pasta.exists():

            # Só cria sozinha as pastas que são da própria A.S.T.R.A.
            # Área de trabalho, Downloads etc. já têm que existir: se
            # não existem, o caminho está errado, e criar uma pasta
            # nova em silêncio esconderia o problema.
            if pasta.name.lower() != "astra":

                log(
                    f"A pasta do local '{chave}' não existe: {pasta}",
                    "ERRO"
                )

                raise ErroArquivo(
                    f"Não achei a pasta {chave} neste computador. "
                    "Confira o caminho nas configurações."
                )

            pasta.mkdir(parents=True, exist_ok=True)

        return pasta

    def _novo_caminho(self, parametro, extensao=""):
        """
        Caminho de algo NOVO. Devolve (local, caminho).
        """

        texto, chave = _separar_local(parametro)

        chave = chave or configuracoes_voz.LOCAL_PADRAO

        nome = _limpar_nome(texto)

        if not nome:
            raise ErroArquivo("Qual nome você quer usar?")

        base = self._pasta_local(chave)

        caminho = (base / f"{nome}{extensao}").resolve()

        if not caminho.is_relative_to(base):
            raise ErroArquivo("Esse nome não é permitido.")

        if caminho.exists():
            raise ErroArquivo(f"Já existe {_descrever(caminho)}{_onde(chave)}.")

        return chave, caminho

    @staticmethod
    def _procurar(nome, chaves):
        """
        Procura um nome nos locais indicados. Devolve [(local, caminho)].
        """

        achados = {}

        for chave in chaves:

            pasta = Path(configuracoes_voz.LOCAIS_ARQUIVOS[chave])

            if not pasta.is_dir():
                continue

            for item in pasta.iterdir():

                if _chave(item.stem) == nome:
                    achados[item.resolve()] = (chave, item)

        return list(achados.values())

    def _localizar(self, parametro, estrito=False):
        """
        Acha um item que JÁ existe, pelo nome (sem a extensão).
        Devolve (local, caminho).

        Sem o lugar na frase, procura em todos os locais.
        estrito=True (usado para excluir): sem o lugar na frase,
        só olha o local padrão.
        """

        texto, chave_local = _separar_local(parametro)

        nome = _limpar_nome(texto)

        if not nome:
            raise ErroArquivo("Qual arquivo você quer?")

        falado = nome.replace("_", " ")

        locais = configuracoes_voz.LOCAIS_ARQUIVOS

        if chave_local:
            chaves = [chave_local]
        elif estrito:
            chaves = [configuracoes_voz.LOCAL_PADRAO]
        else:
            chaves = list(locais)

        achados = self._procurar(nome, chaves)

        if not achados and estrito and not chave_local:

            outros = self._procurar(
                nome,
                [c for c in locais if c != configuracoes_voz.LOCAL_PADRAO]
            )

            if outros:

                onde = " e ".join(
                    f"{_descrever(item)}{_onde(chave)}"
                    for chave, item in outros
                )

                raise ErroArquivo(
                    f"Encontrei {onde}. Para excluir, diga também o lugar."
                )

        if not achados:
            raise ErroArquivo(f"Não encontrei {falado}.")

        if len(achados) > 1:

            if len({chave for chave, _ in achados}) == 1:
                raise ErroArquivo(
                    "Existe mais de um item com esse nome na mesma pasta. "
                    "Renomeie um deles."
                )

            onde = " e ".join(
                f"{_descrever(item)}{_onde(chave)}"
                for chave, item in achados
            )

            raise ErroArquivo(f"Encontrei {onde}. Diga também o lugar.")

        return achados[0]

    def _em_uso(self):
        """
        Devolve o arquivo em uso, conferindo se ainda existe.
        """

        if self.atual is None:
            raise ErroArquivo(
                "Nenhum arquivo está em uso. Crie um, ou diga: "
                "abra o arquivo, e o nome."
            )

        if not self.atual.exists():
            self.atual = None
            raise ErroArquivo("O arquivo em uso não existe mais.")

        return self.atual

    def _planilha_editavel(self):
        """
        Arquivo em uso, garantido como planilha que pode ser editada.

        O openpyxl não guarda gráficos nem imagens ao salvar. Em vez
        de apagá-los em silêncio, a A.S.T.R.A. se recusa a editar.
        """

        caminho = self._atual_como(".xlsx", "uma planilha")

        with zipfile.ZipFile(caminho) as pacote:

            if any(
                nome.startswith(("xl/charts/", "xl/drawings/", "xl/media/"))
                for nome in pacote.namelist()
            ):
                raise ErroArquivo(
                    "Essa planilha tem gráficos ou imagens, e eu os "
                    "apagaria ao editar. Edite essa planilha pelo Excel."
                )

        return caminho

    def _atual_como(self, extensao, nome_tipo):
        """
        Devolve o arquivo em uso, conferindo se é do tipo esperado.
        """

        caminho = self._em_uso()

        if caminho.suffix != extensao:
            raise ErroArquivo(f"O arquivo em uso não é {nome_tipo}.")

        return caminho


    # CRIAR

    @_seguro
    def criar_pasta(self, parametro):

        chave, caminho = self._novo_caminho(parametro)

        caminho.mkdir()

        return f"{_descrever(caminho).capitalize()} criada{_onde(chave)}."

    @_seguro
    def criar_documento(self, parametro):

        from docx import Document

        chave, caminho = self._novo_caminho(parametro, ".docx")

        Document().save(caminho)

        self.atual = caminho

        return (
            f"{_descrever(caminho).capitalize()} criado{_onde(chave)}. "
            "Diga escreva, e o texto, para adicionar conteúdo."
        )

    @_seguro
    def criar_planilha(self, parametro):
        """
        "vendas" ou "vendas com as colunas nome, idade e cidade".
        """

        from openpyxl import Workbook
        from openpyxl.styles import Font

        nome, texto_colunas = _separar_colunas(parametro)

        chave, caminho = self._novo_caminho(nome, ".xlsx")

        colunas = _lista_de_valores(texto_colunas, misto=True)

        planilha = Workbook()

        if colunas:

            planilha.active.append(colunas)

            for celula in planilha.active[1]:
                celula.font = Font(bold=True)

        planilha.save(caminho)

        self.atual = caminho

        frase = f"{_descrever(caminho).capitalize()} criada{_onde(chave)}"

        if colunas:
            plural = "coluna" if len(colunas) == 1 else "colunas"

            frase += f" com {len(colunas)} {plural}: " + ", ".join(colunas)

        return frase + ". Diga adicione a linha, e os valores."

    @_seguro
    def criar_texto(self, parametro):

        chave, caminho = self._novo_caminho(parametro, ".txt")

        caminho.write_text("", encoding="utf-8")

        self.atual = caminho

        return (
            f"{_descrever(caminho).capitalize()} criado{_onde(chave)}. "
            "Diga escreva, e o texto, para adicionar conteúdo."
        )

    @_seguro
    def criar_apresentacao(self, parametro):

        from pptx import Presentation

        chave, caminho = self._novo_caminho(parametro, ".pptx")

        Presentation().save(caminho)

        self.atual = caminho

        return (
            f"{_descrever(caminho).capitalize()} criada{_onde(chave)}. "
            "Diga adicione um slide, e o título."
        )


    # ESCREVER

    @_seguro
    def escrever_texto(self, texto):
        """
        Escreve no arquivo em uso: parágrafo no Word, linha no arquivo
        de texto, tópico no último slide do PowerPoint.
        """

        caminho = self._em_uso()

        texto = texto.strip()

        if not texto:
            return "O que devo escrever?"

        if caminho.suffix == ".docx":

            from docx import Document

            documento = Document(caminho)

            documento.add_paragraph(texto)

            documento.save(caminho)

            return "Escrito."

        if caminho.suffix == ".txt":

            with open(caminho, "a", encoding="utf-8") as arquivo:
                arquivo.write(texto + "\n")

            return "Escrito."

        if caminho.suffix == ".pptx":

            from pptx import Presentation

            apresentacao = Presentation(caminho)

            slides = list(apresentacao.slides)

            if not slides:
                raise ErroArquivo(
                    "A apresentação não tem slides. "
                    "Diga: adicione um slide, e o título."
                )

            corpo = next(
                (
                    forma for forma in slides[-1].placeholders
                    if forma.placeholder_format.idx == 1
                ),
                None
            )

            if corpo is None:
                raise ErroArquivo("O último slide não tem espaço para texto.")

            quadro = corpo.text_frame

            if quadro.text.strip():
                quadro.add_paragraph().text = texto
            else:
                quadro.text = texto

            apresentacao.save(caminho)

            return f"Escrito no slide {len(slides)}."

        if caminho.suffix == ".xlsx":
            raise ErroArquivo(
                "O arquivo em uso é uma planilha. "
                "Use: escreva na célula, ou: adicione a linha."
            )

        raise ErroArquivo("Não sei escrever nesse tipo de arquivo.")

    @_seguro
    def adicionar_linha(self, parametro):
        """
        Acrescenta uma linha no fim da planilha em uso.
        "Joel, 30, São Paulo" ou "joel e 30 e sao paulo".
        """

        from openpyxl import load_workbook

        caminho = self._planilha_editavel()

        texto = _texto_apos_marcador(parametro, ("valores", "valor"))

        palavras = texto.split()

        if palavras and normalizar_texto(palavras[0]) == "com":
            texto = " ".join(palavras[1:])

        valores = [
            _converter_valor(v)
            for v in _lista_de_valores(texto)
        ]

        if not valores:
            return "Diga os valores. Por exemplo: Joel, 30, São Paulo."

        planilha = load_workbook(caminho)

        planilha.active.append(valores)

        linha = planilha.active.max_row

        planilha.save(caminho)

        return f"Linha {linha} adicionada com {len(valores)} valores."

    @_seguro
    def embelezar_planilha(self, parametro=""):
        """
        Deixa a planilha em uso bonita. Aceita o nome do tema
        ("verde", "roxo"...); sem tema, usa o azul.
        """

        from openpyxl import load_workbook

        from ..manipulacao_arquivos import estilo_planilha

        caminho = self._planilha_editavel()

        tema = next(
            (
                palavra
                for palavra in normalizar_texto(parametro).split()
                if palavra in estilo_planilha.TEMAS
            ),
            estilo_planilha.TEMA_PADRAO
        )

        planilha = load_workbook(caminho)

        try:
            estilo_planilha.embelezar(planilha.active, tema)
        except estilo_planilha.ErroPlanilha as erro:
            raise ErroArquivo(str(erro))

        planilha.save(caminho)

        return f"Planilha formatada no tema {tema}."

    @_seguro
    def somar_coluna(self, parametro):
        """
        Soma uma coluna da planilha em uso e põe o total no fim.
        """

        from openpyxl import load_workbook

        from ..manipulacao_arquivos import estilo_planilha

        caminho = self._planilha_editavel()

        planilha = load_workbook(caminho)

        try:
            soma, titulo = estilo_planilha.adicionar_total(
                planilha.active, parametro
            )
        except estilo_planilha.ErroPlanilha as erro:
            raise ErroArquivo(str(erro))

        planilha.save(caminho)

        return f"Total de {titulo}: {_falar_numero(soma)}."

    @_seguro
    def adicionar_slide(self, parametro):

        from pptx import Presentation

        caminho = self._atual_como(".pptx", "uma apresentação")

        titulo = _texto_apos_marcador(parametro, MARCADORES_DE_TITULO)

        if not titulo:
            return "Qual o título do slide?"

        apresentacao = Presentation(caminho)

        slide = apresentacao.slides.add_slide(apresentacao.slide_layouts[1])

        slide.shapes.title.text = titulo

        apresentacao.save(caminho)

        return (
            f"Slide {len(apresentacao.slides)} criado. "
            "Diga escreva, e o texto, para adicionar tópicos."
        )

    @_seguro
    def escrever_celula(self, parametro):
        """
        Espera algo como "b2 total geral": primeiro a célula,
        depois o valor.
        """

        from openpyxl import load_workbook

        caminho = self._planilha_editavel()

        partes = parametro.strip().split(maxsplit=1)

        if len(partes) < 2 or not re.fullmatch(
            r"[A-Za-z]{1,3}[0-9]{1,7}", partes[0]
        ):
            return "Diga a célula e o valor. Por exemplo: b2 cem."

        celula = partes[0].upper()

        planilha = load_workbook(caminho)

        planilha.active[celula] = _converter_valor(partes[1])

        planilha.save(caminho)

        return f"Escrito na célula {celula}."


    # LER

    @_seguro
    def ler_atual(self, parametro=""):

        if self.atual is None or not self.atual.exists():
            raise ErroArquivo("Nenhum arquivo está em uso.")

        if self.atual.suffix == ".docx":

            from docx import Document

            paragrafos = [
                p.text.strip()
                for p in Document(self.atual).paragraphs
                if p.text.strip()
            ]

            if not paragrafos:
                return "O documento está vazio."

            return " ".join(paragrafos)

        if self.atual.suffix == ".xlsx":

            from openpyxl import load_workbook

            valores = load_workbook(self.atual, data_only=True).active

            formulas = load_workbook(self.atual).active

            linhas = []

            for linha in range(1, min(valores.max_row, LIMITE_LINHAS_LIDAS) + 1):

                celulas = [
                    _valor_da_celula(valores, formulas, linha, coluna)
                    for coluna in range(1, valores.max_column + 1)
                ]

                falados = [str(v) for v in celulas if v is not None]

                if falados:
                    linhas.append(", ".join(falados))

            if not linhas:
                return "A planilha está vazia."

            return ". ".join(linhas)

        if self.atual.suffix == ".txt":

            conteudo = self.atual.read_text(encoding="utf-8").strip()

            return conteudo.replace("\n", ". ") or "O arquivo está vazio."

        if self.atual.suffix == ".pptx":

            from pptx import Presentation

            falas = []

            for numero, slide in enumerate(Presentation(self.atual).slides, 1):

                partes = [
                    forma.text_frame.text.strip().replace("\n", ". ")
                    for forma in slide.shapes
                    if forma.has_text_frame and forma.text_frame.text.strip()
                ]

                falas.append(f"Slide {numero}: " + ". ".join(partes))

            return " ".join(falas) or "A apresentação está vazia."

        raise ErroArquivo("Não sei ler esse tipo de arquivo.")


    # USAR / LISTAR / EXCLUIR

    @_seguro
    def usar_arquivo(self, parametro):

        chave, caminho = self._localizar(parametro)

        if caminho.is_dir():
            raise ErroArquivo("Esse item é uma pasta, não um arquivo.")

        self.atual = caminho

        return f"Em uso: {_descrever(caminho)}{_onde(chave)}."

    @_seguro
    def listar(self, parametro=""):

        _, chave = _separar_local(parametro)

        chave = chave or configuracoes_voz.LOCAL_PADRAO

        itens = sorted(
            (
                i for i in self._pasta_local(chave).iterdir()
                if not i.name.startswith(".")
                and i.name.lower() != "desktop.ini"
            ),
            key=lambda i: i.name.lower()
        )

        if not itens:
            return f"Não há nada{_onde(chave)}."

        falados = [_descrever(i) for i in itens[:LIMITE_ITENS_FALADOS]]

        frase = (
            f"Tenho {len(itens)} itens{_onde(chave)}: "
            + ", ".join(falados) + "."
        )

        if len(itens) > LIMITE_ITENS_FALADOS:
            frase += " Há mais itens além desses."

        return frase

    @_seguro
    def excluir(self, parametro):
        """
        Ação crítica (RN03): só chega aqui depois da confirmação.
        """

        from send2trash import send2trash

        chave, caminho = self._localizar(parametro, estrito=True)

        descricao = _descrever(caminho)

        send2trash(str(caminho))

        if self.atual == caminho:
            self.atual = None

        return f"{descricao.capitalize()}{_onde(chave)} foi para a lixeira."


# INSTÂNCIA PRINCIPAL

gerenciador_arquivos = GerenciadorArquivos()
