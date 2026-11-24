import re
from datetime import date, datetime

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import column_index_from_string, get_column_letter

from voz.utilitarios_voz import normalizar_texto


"""
Aparência das planilhas (Excel).

Responsabilidade:
    Deixar uma planilha bonita e somar colunas, usando só uma LISTA
    FIXA de opções (temas, formatos de número...). Nada aqui executa
    texto vindo de fora: quem pede só escolhe entre as opções abaixo.

Este módulo trabalha numa planilha já aberta (worksheet do openpyxl).
Quem abre e salva o arquivo é arquivos.gerenciador_arquivos.
"""


class ErroPlanilha(Exception):
    """
    Erro previsto. A mensagem já é a frase a ser falada.
    """


# Cores em hexadecimal (sem #).
TEMAS = {
    "azul":     {"cabecalho": "1F4E78", "texto_cabecalho": "FFFFFF", "zebra": "DDEBF7", "borda": "9BC2E6"},
    "verde":    {"cabecalho": "2E7D32", "texto_cabecalho": "FFFFFF", "zebra": "E8F5E9", "borda": "A5D6A7"},
    "vermelho": {"cabecalho": "B71C1C", "texto_cabecalho": "FFFFFF", "zebra": "FDECEA", "borda": "EF9A9A"},
    "laranja":  {"cabecalho": "E65100", "texto_cabecalho": "FFFFFF", "zebra": "FFF3E0", "borda": "FFCC80"},
    "roxo":     {"cabecalho": "4A148C", "texto_cabecalho": "FFFFFF", "zebra": "F3E5F5", "borda": "CE93D8"},
    "cinza":    {"cabecalho": "37474F", "texto_cabecalho": "FFFFFF", "zebra": "ECEFF1", "borda": "B0BEC5"},
}

TEMA_PADRAO = "azul"

# Fonte fixa: sem o nome, cada programa escolhe a sua e o visual muda.
FONTE = "Calibri"

LARGURA_MINIMA = 10
LARGURA_MAXIMA = 50

# Colunas com estas palavras no título recebem formato de dinheiro.
PALAVRAS_MOEDA = {
    "preco", "valor", "custo", "salario", "receita",
    "gasto", "despesa", "faturamento"
}

# Colunas com estas palavras são códigos: nunca levam separador de milhar.
PALAVRAS_CODIGO = {"ano", "anos", "id", "codigo", "cep", "telefone", "numero"}


# FUNÇÕES AUXILIARES

def _e_numero(valor):

    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _ultima_linha_de_dados(planilha):
    """
    Última linha com dados, sem contar uma linha final de "Total".
    """

    ultima = planilha.max_row

    if ultima > 1:

        rotulo = normalizar_texto(str(planilha.cell(ultima, 1).value or ""))

        if rotulo == "total":
            return ultima - 1

    return ultima


def _formato_numero(cabecalho, valores):
    """
    Escolhe o formato de número de uma coluna.
    """

    palavras = set(normalizar_texto(str(cabecalho or "")).split())

    if palavras & PALAVRAS_CODIGO:
        return "0"

    if palavras & PALAVRAS_MOEDA:
        return '"R$" #,##0.00'

    if all(float(v).is_integer() for v in valores):
        return "#,##0" if max(abs(v) for v in valores) >= 10000 else "0"

    return "#,##0.00"


def achar_coluna(planilha, nome):
    """
    Número da coluna pelo título (sem acento) ou pela letra.
    Devolve None se não achar.
    """

    alvo = normalizar_texto(nome)

    if not alvo:
        return None

    titulos = {
        coluna: normalizar_texto(str(planilha.cell(1, coluna).value or ""))
        for coluna in range(1, planilha.max_column + 1)
    }

    for coluna, titulo in titulos.items():
        if titulo == alvo:
            return coluna

    if len(alvo) >= 3:

        for coluna, titulo in titulos.items():
            if titulo and (alvo in titulo or titulo in alvo):
                return coluna

    if re.fullmatch(r"[a-z]{1,2}", alvo):

        numero = column_index_from_string(alvo.upper())

        if numero <= planilha.max_column:
            return numero

    return None


# EMBELEZAR

def embelezar(planilha, tema=TEMA_PADRAO):
    """
    Cabeçalho colorido, linhas alternadas, bordas, larguras ajustadas,
    formato de número, cabeçalho congelado e filtro.
    Pode ser aplicado de novo sem estragar nada.
    """

    cores = TEMAS[tema]

    if planilha["A1"].value is None:
        raise ErroPlanilha("A planilha está vazia. Crie as colunas primeiro.")

    ultima_coluna = planilha.max_column
    ultima_linha = planilha.max_row
    ultima_dados = _ultima_linha_de_dados(planilha)
    linha_total = ultima_linha if ultima_linha > ultima_dados else None

    lado = Side(style="thin", color=cores["borda"])
    borda = Border(left=lado, right=lado, top=lado, bottom=lado)

    fundo_cabecalho = PatternFill("solid", start_color=cores["cabecalho"], end_color=cores["cabecalho"])
    fundo_zebra = PatternFill("solid", start_color=cores["zebra"], end_color=cores["zebra"])
    sem_fundo = PatternFill(fill_type=None)

    for coluna in range(1, ultima_coluna + 1):

        cabecalho = planilha.cell(1, coluna).value

        valores = [
            planilha.cell(linha, coluna).value
            for linha in range(2, ultima_dados + 1)
        ]

        presentes = [v for v in valores if v not in (None, "")]

        numerica = bool(presentes) and all(_e_numero(v) for v in presentes)

        formato = _formato_numero(cabecalho, presentes) if numerica else None

        maior = len(str(cabecalho or ""))

        for linha in range(1, ultima_linha + 1):

            celula = planilha.cell(linha, coluna)

            valor = celula.value

            celula.border = borda

            if linha == 1:

                celula.font = Font(name=FONTE, family=2, scheme="minor", size=11, bold=True, color=cores["texto_cabecalho"])
                celula.fill = fundo_cabecalho
                celula.alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True
                )

            else:

                celula.alignment = Alignment(
                    horizontal="right" if numerica else "left",
                    vertical="center"
                )

                if linha == linha_total:
                    celula.font = Font(name=FONTE, family=2, scheme="minor", size=11, bold=True)
                    celula.fill = fundo_zebra
                else:
                    celula.fill = fundo_zebra if linha % 2 == 1 else sem_fundo

                eh_formula = isinstance(valor, str) and valor.startswith("=")

                if formato and (_e_numero(valor) or eh_formula):
                    celula.number_format = formato

                if isinstance(valor, (datetime, date)):
                    celula.number_format = "dd/mm/yyyy"

            if valor is not None:
                maior = max(maior, len(str(valor)))

        largura = min(max(maior + 3, LARGURA_MINIMA), LARGURA_MAXIMA)

        planilha.column_dimensions[get_column_letter(coluna)].width = largura

    planilha.row_dimensions[1].height = 22

    planilha.freeze_panes = "A2"

    planilha.auto_filter.ref = (
        f"A1:{get_column_letter(ultima_coluna)}{ultima_dados}"
    )


# TOTAIS

def adicionar_total(planilha, nome_coluna):
    """
    Põe a soma de uma coluna numa linha "Total" no fim.
    Devolve (soma, título da coluna).
    """

    if not normalizar_texto(nome_coluna):
        raise ErroPlanilha(
            "Diga qual coluna. Por exemplo: some a coluna quantidade."
        )

    coluna = achar_coluna(planilha, nome_coluna)

    if coluna is None:
        raise ErroPlanilha(f"Não achei a coluna {nome_coluna}.")

    if coluna == 1:
        raise ErroPlanilha(
            "A primeira coluna guarda os nomes. Escolha outra coluna."
        )

    ultima_dados = _ultima_linha_de_dados(planilha)

    numeros = [
        planilha.cell(linha, coluna).value
        for linha in range(2, ultima_dados + 1)
        if _e_numero(planilha.cell(linha, coluna).value)
    ]

    if not numeros:
        raise ErroPlanilha("Essa coluna não tem números para somar.")

    linha_total = ultima_dados + 1

    letra = get_column_letter(coluna)

    planilha.cell(linha_total, 1).value = "Total"
    planilha.cell(linha_total, 1).font = Font(name=FONTE, family=2, scheme="minor", size=11, bold=True)

    planilha.cell(linha_total, coluna).value = f"=SUM({letra}2:{letra}{ultima_dados})"
    planilha.cell(linha_total, coluna).font = Font(name=FONTE, family=2, scheme="minor", size=11, bold=True)

    return sum(numeros), str(planilha.cell(1, coluna).value)