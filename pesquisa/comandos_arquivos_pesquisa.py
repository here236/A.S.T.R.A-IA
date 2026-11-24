import webbrowser
from urllib.parse import quote_plus

from arquivos.gerenciador_arquivos import gerenciador_arquivos as arq
from voz.pesquisa_voz import gerenciador_pesquisa as pes

"""
Comandos de ARQUIVOS (pastas, Word, Excel, PowerPoint, texto) e de
PESQUISA NA WEB.

Responsabilidade:
    Registrar no GerenciadorComandos os comandos dessas duas áreas.
    Cada comando só liga uma frase falada a uma função de
    arquivos_voz.py ou de pesquisa_voz.py, que devolvem a frase a ser
    FALADA.

Para adicionar um comando novo, acrescente um item na lista COMANDOS:
    nome         identificador do comando
    frases       o que o usuário pode dizer (sem acento)
    acao         função que recebe o que foi dito depois da frase (p)
    descricao    (opcional) aparece no "ajuda"
    critico      (opcional) True pede confirmação por voz antes (RN03)
    pergunta     (opcional) frase falada na confirmação; {parametro}
                 vira o que o usuário disse
    texto_livre  (opcional) True entrega p com acento e maiúscula
"""


def _pesquisar_no_navegador(parametro):

    if not parametro:
        return "O que você quer pesquisar?"

    webbrowser.open(f"https://www.google.com/search?q={quote_plus(parametro)}")

    return f"Pesquisando {parametro} no navegador."


COMANDOS = [
    dict(
        nome="criar_pasta",
        frases=[
            "crie a pasta",
            "criar pasta",
            "crie pasta",
            "crie uma pasta",
            "nova pasta",
        ],
        acao=lambda p: arq.criar_pasta(p),
        descricao="Criar uma pasta. Diga: crie a pasta fotos.",
    ),
    dict(
        nome="criar_documento",
        frases=[
            "crie um documento",
            "crie um arquivo word",
            "crie um word",
            "novo arquivo word",
            "criar documento",
            "crie documento",
            "novo documento",
        ],
        acao=lambda p: arq.criar_documento(p),
        descricao="Criar um documento do Word.",
    ),
    dict(
        nome="criar_planilha",
        frases=[
            "crie uma planilha",
            "crie um arquivo excel",
            "crie um excel",
            "novo arquivo excel",
            "criar planilha",
            "crie planilha",
            "nova planilha",
        ],
        acao=lambda p: arq.criar_planilha(p),
        descricao="Criar uma planilha do Excel, com colunas se quiser.",
        texto_livre=True,
    ),
    dict(
        nome="embelezar_planilha",
        frases=[
            "deixe a planilha bonita",
            "deixar a planilha bonita",
            "deixe a planilha mais bonita",
            "embeleze a planilha",
            "formate a planilha",
            "aplique o tema",
            "mude o tema",
        ],
        acao=lambda p: arq.embelezar_planilha(p),
        descricao="Deixar a planilha bonita.",
    ),
    dict(
        nome="somar_coluna",
        frases=[
            "some a coluna",
            "somar a coluna",
            "total da coluna",
        ],
        acao=lambda p: arq.somar_coluna(p),
    ),
    dict(
        nome="criar_texto",
        frases=[
            "crie um arquivo de texto",
            "criar arquivo de texto",
            "novo arquivo de texto",
            "crie um texto",
        ],
        acao=lambda p: arq.criar_texto(p),
    ),
    dict(
        nome="criar_apresentacao",
        frases=[
            "crie uma apresentacao",
            "criar apresentacao",
            "nova apresentacao",
            "crie um powerpoint",
            "crie um power point",
        ],
        acao=lambda p: arq.criar_apresentacao(p),
        descricao="Criar uma apresentação do PowerPoint.",
    ),
    dict(
        nome="adicionar_slide",
        frases=[
            "adicione um slide",
            "adicionar slide",
            "novo slide",
            "crie um slide",
        ],
        acao=lambda p: arq.adicionar_slide(p),
        texto_livre=True,
    ),
    dict(
        nome="adicionar_linha",
        frases=[
            "adicione a linha",
            "adicione uma linha",
            "adicionar linha",
            "nova linha",
        ],
        acao=lambda p: arq.adicionar_linha(p),
        texto_livre=True,
    ),
    dict(
        nome="escrever_texto",
        frases=[
            "escreva",
            "escrever",
        ],
        acao=lambda p: arq.escrever_texto(p),
        descricao="Escrever no arquivo em uso. Diga: escreva, e o texto.",
        texto_livre=True,
    ),
    dict(
        nome="escrever_celula",
        frases=[
            "escreva na celula",
            "escrever na celula",
        ],
        acao=lambda p: arq.escrever_celula(p),
        texto_livre=True,
    ),
    dict(
        nome="ler_arquivo",
        frases=[
            "leia o documento",
            "ler o documento",
            "leia a planilha",
            "ler a planilha",
            "leia o arquivo",
        ],
        acao=lambda p: arq.ler_atual(),
    ),
    dict(
        nome="usar_arquivo",
        frases=[
            "abra o arquivo",
            "use o arquivo",
            "edite o arquivo",
            "abra o documento",
            "abra a planilha",
        ],
        acao=lambda p: arq.usar_arquivo(p),
    ),
    dict(
        nome="listar_arquivos",
        frases=[
            "liste os arquivos",
            "listar arquivos",
            "listar os arquivos",
            "quais arquivos eu tenho",
        ],
        acao=lambda p: arq.listar(p),
        descricao="Listar os arquivos.",
    ),
    dict(
        nome="renomear_arquivo",
        frases=[
            "renomeie",
            "renomear",
        ],
        acao=lambda p: arq.renomear(p),
    ),
    dict(
        nome="mostrar_arquivo",
        frases=[
            "mostre o arquivo",
            "mostre o documento",
            "mostre a planilha",
            "mostre a apresentacao",
            "mostre a pasta",
        ],
        acao=lambda p: arq.mostrar(p),
    ),
    dict(
        nome="excluir",
        frases=[
            "exclua",
            "excluir",
            "apague",
            "apagar",
            "delete",
        ],
        acao=lambda p: arq.excluir(p),
        descricao="Excluir um arquivo, com confirmação.",
        critico=True,
        pergunta="Tem certeza que quer excluir {parametro}? Diga sim ou não.",
    ),
    dict(
        nome="pesquisar_no_navegador",
        frases=[
            "pesquise no navegador",
            "pesquisar no navegador",
            "pesquise no google",
            "pesquisar no google",
        ],
        acao=lambda p: _pesquisar_no_navegador(p),
    ),
    dict(
        nome="pesquisar_como_fazer",
        frases=[
            "como fazer",
            "como se faz",
        ],
        acao=lambda p: pes.pesquisar_como(p, "como fazer"),
        descricao="Pesquisar como fazer algo. Eu só explico, não executo.",
        texto_livre=True,
    ),
    dict(
        nome="pesquisar_como_faco",
        frases=[
            "como faco para",
            "como eu faco para",
            "me ensine a",
            "me ensina a",
        ],
        acao=lambda p: pes.pesquisar_como(p, "como"),
        texto_livre=True,
    ),
    dict(
        nome="pesquisar_documento",
        frases=[
            "faca um documento sobre",
            "monte um documento sobre",
            "faca um relatorio sobre",
        ],
        acao=lambda p: pes.pesquisar_para_arquivo(p, "documento"),
        descricao="Pesquisar e criar um documento com as fontes.",
        texto_livre=True,
    ),
    dict(
        nome="pesquisar_planilha",
        frases=[
            "faca uma planilha sobre",
            "monte uma planilha sobre",
        ],
        acao=lambda p: pes.pesquisar_para_arquivo(p, "planilha"),
        texto_livre=True,
    ),
    dict(
        nome="pesquisar_apresentacao",
        frases=[
            "faca uma apresentacao sobre",
            "monte uma apresentacao sobre",
        ],
        acao=lambda p: pes.pesquisar_para_arquivo(p, "apresentacao"),
        texto_livre=True,
    ),
    dict(
        nome="ler_resultado",
        frases=[
            "leia o resultado",
            "ler o resultado",
            "leia a pagina",
        ],
        acao=lambda p: pes.ler_resultado(p),
    ),
    dict(
        nome="abrir_resultado",
        frases=[
            "abra o resultado",
            "abrir o resultado",
        ],
        acao=lambda p: pes.abrir_resultado(p),
    ),
    dict(
        nome="continuar_leitura",
        frases=[
            "continue lendo",
            "continuar lendo",
            "continue a leitura",
        ],
        acao=lambda p: pes.continuar_leitura(),
    ),
    dict(
        nome="repetir_resultados",
        frases=[
            "repita os resultados",
            "repetir os resultados",
            "quais foram os resultados",
        ],
        acao=lambda p: pes.repetir_resultados(),
    ),
]


def registrar_comandos_extras(gerenciador, RespostaAcao):
    """
    Chamado pelo GerenciadorComandos ao montar a lista de comandos.
    """

    for comando in COMANDOS:

        gerenciador.registrar(
            nome=comando["nome"],
            palavras_chave=comando["frases"],
            funcao=lambda p, acao=comando["acao"]: RespostaAcao(fala=acao(p)),
            descricao=comando.get("descricao", ""),
            critico=comando.get("critico", False),
            pergunta_confirmacao=comando.get("pergunta", ""),
            texto_livre=comando.get("texto_livre", False),
        )
