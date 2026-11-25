import subprocess
import webbrowser

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional
from urllib.parse import quote_plus

from .utilitarios_voz import normalizar_texto

from .confirmacao_voz import Decisao, GerenciadorConfirmacao
from .memoria_operacional import MemoriaOperacional
from .gerenciador_dialogo import GerenciadorDialogo, parametro_faltante, CANCELAMENTOS, CRIACOES

from arquivos.gerenciador_arquivos import gerenciador_arquivos, ResultadoArquivo
from .utilitarios_voz import log

"""
Ações específicas da A.S.T.R.A.

Responsabilidade:
    Único reconhecedor de comandos do projeto: interpretar comandos
    conhecidos e executar as ações correspondentes.

Exemplos:
    "leia a tela"
    "abra o navegador"
    "pesquise receita de bolo"
    "que horas são"

Este módulo NÃO é responsável por:
    - Reconhecimento de voz
    - OCR
    - Inteligência artificial / conversa livre
    - Captura de áudio

Ele recebe um texto já reconhecido e decide qual ação executar.
Quando nenhum comando é reconhecido, o resultado vem com status
NAO_ENCONTRADO e quem orquestra (voz_principal) pode encaminhar o
texto para processador_linguagem, que cuida da conversa.
"""


# TIPOS DE RESULTADO

class StatusComando(Enum):
    SUCESSO = "sucesso"
    NAO_ENCONTRADO = "nao_encontrado"
    ERRO = "erro"
    AGUARDANDO_CONFIRMACAO = "aguardando_confirmacao"
    AGUARDANDO_PARAMETRO = "aguardando_parametro"
    CANCELADO = "cancelado"

@dataclass
class RespostaAcao:
    """
    O que uma ação devolve depois de executada.

    fala:     frase pensada para ser FALADA ao usuário (TTS).
    dados:    informação extra para quem chamou (ex: texto lido da tela).
    encerrar: True quando a ação pede o fim da sessão (ex: "tchau").
    """

    fala: str = ""
    dados: Optional[object] = None
    encerrar: bool = False


@dataclass
class ResultadoComando:
    """
    Resultado da execução de um comando.

    mensagem:        texto de log/depuração (NÃO é para falar em voz alta).
    resposta_falada: o que o sintetizador de voz deve dizer ao usuário.
    encerrar:        True quando a sessão deve terminar.
    """

    status: StatusComando
    comando: str = ""
    mensagem: str = ""
    dados: Optional[object] = None
    resposta_falada: str = ""
    encerrar: bool = False


# DEFINIÇÃO DE UM COMANDO

@dataclass
class Comando:
    """
    Representa um comando que a A.S.T.R.A. sabe executar.

    A função recebe o parâmetro falado depois da expressão que ativou
    o comando. Ex: em "pesquise receita de bolo", o parâmetro é
    "receita de bolo". Comandos sem parâmetro apenas ignoram o valor.
    """

    nome: str
    palavras_chave: list[str]
    funcao: Callable[[str], RespostaAcao]
    descricao: str = ""

    # RN03: ação crítica só executa depois de confirmação por voz.
    # pergunta_confirmacao é a frase falada para pedir isso.
    critico: bool = False
    pergunta_confirmacao: str = ""

    # True: o parâmetro chega COMO FOI FALADO (com acento e maiúscula),
    # em vez de normalizado. Usado quando o texto vai para um arquivo.
    texto_livre: bool = False

# VARIANTES DE VERBO

# Pelo mesmo motivo, o verbo chega em formas diferentes: "abra o site" foi
# escrito "abre o site" e "abro o site". Cada grupo reúne as formas de um
# verbo, e uma frase que começa por uma delas vale para todas.
GRUPOS_DE_VERBOS = [
    ["abra", "abre", "abro", "abrir"],
    ["feche", "fecha", "fecho", "fechar"],
    ["pesquise", "pesquisa", "pesquiso", "pesquisar"],
    ["busque", "busca", "busco", "buscar"],
    ["procure", "procura", "procuro", "procurar"],
    ["leia", "le", "leio", "ler"],
    ["inicie", "inicia", "inicio", "iniciar"],
    ["descreva", "descreve", "descrevo", "descrever"],
]


def variantes_de_verbo(frase: str) -> list[str]:
    """
    Devolve a frase (já normalizada) com cada forma do verbo inicial:
    "abra o site" -> "abra o site", "abre o site", "abro o site",
    "abrir o site". Se não começa por um verbo conhecido, devolve só ela.
    """

    palavras = frase.split()

    if not palavras:
        return [frase]

    for grupo in GRUPOS_DE_VERBOS:

        if palavras[0] in grupo:

            resto = " ".join(palavras[1:])

            variantes = []

            for forma in [palavras[0]] + [g for g in grupo if g != palavras[0]]:

                variantes.append(f"{forma} {resto}".strip())

            return variantes

    return [frase]


# VARIANTES DE ARTIGO

# O reconhecimento de fala troca "o" por "um" (e "a" por "uma") com
# facilidade: em teste, "abra o navegador" foi escrito "abra um navegador".
# Para cada frase cadastrada, aceita-se também a troca e a versão sem artigo.
ARTIGOS = {"o": "um", "a": "uma"}


def variantes_de_artigo(frase: str) -> list[str]:
    """
    Devolve a frase (já normalizada) e suas variantes de artigo:
    "abra o navegador" -> "abra o navegador", "abra um navegador",
    "abra navegador". Sem artigo, devolve só a própria frase.
    """

    palavras = frase.split()

    if not any(p in ARTIGOS for p in palavras):
        return [frase]

    trocada = " ".join(ARTIGOS.get(p, p) for p in palavras)
    sem_artigo = " ".join(p for p in palavras if p not in ARTIGOS)

    variantes = [frase]

    for v in (trocada, sem_artigo):
        if v and v not in variantes:
            variantes.append(v)

    return variantes


# GERENCIADOR DE COMANDOS

class GerenciadorComandos:

    def __init__(self):

        self.comandos: list[Comando] = []

        # RN03: controle das confirmações (voz/confirmacao_voz.py)
        self.confirmacao = GerenciadorConfirmacao()
        self.dialogo = GerenciadorDialogo()
        self.memoria_operacional = MemoriaOperacional()

        self._registrar_comandos()
        self._registrar_comandos_extras()

        # Catálogo unificado: os comandos tradicionais continuam sendo
        # reconhecidos pelo fluxo antigo, mas também passam a ser
        # descritos em um registro independente para futuras chamadas da IA.
        from ferramentas import RegistroFerramentas, ExecutorFerramentas

        self.registro_ferramentas = RegistroFerramentas()
        for comando in self.comandos:
            self.registro_ferramentas.registrar_comando(comando)

        self.executor_ferramentas = ExecutorFerramentas(
            self, self.registro_ferramentas
        )


    # REGISTRO

    def registrar(
        self,
        nome: str,
        palavras_chave: list[str],
        funcao: Callable[[str], RespostaAcao],
        descricao: str = "",
        critico: bool = False,
        pergunta_confirmacao: str = "",
        texto_livre: bool = False
    ):
        """
        Registra um novo comando.
           critico=True faz o comando exigir confirmação por voz (RN03).
        """
        

        expandidas = []

        for frase in palavras_chave:

            for com_verbo in variantes_de_verbo(normalizar_texto(frase)):

                for variante in variantes_de_artigo(com_verbo):

                    if variante and variante not in expandidas:
                        expandidas.append(variante)

        comando = Comando(
            nome=nome,
            palavras_chave=expandidas,
            funcao=funcao,
            descricao=descricao,
            critico=critico or nome in CRIACOES,
            pergunta_confirmacao=pergunta_confirmacao,
            texto_livre=texto_livre
        )

        self.comandos.append(comando)


    # COMANDOS DISPONÍVEIS

    def _registrar_comandos(self):

        # Frases sem acento: o texto falado e as palavras-chave passam
        # pela mesma normalização, então não é preciso cadastrar a
        # versão com e sem acento.

        self.registrar(
            nome="ler_tela",
            palavras_chave=[
                "leia a tela",
                "ler a tela",
                "leia minha tela",
                "ler minha tela",
                "o que tem na tela",
                "o que esta na tela",
                "descreva a tela",
                "le a tela",
                "le minha tela",
                "leia tela",
                "ler tela",
                "descreve a tela"
            ],
            funcao=self.ler_tela,
            descricao="Ler o conteúdo visível da tela."
        )

        self.registrar(
            nome="abrir_navegador",
            palavras_chave=[
                "abra o navegador",
                "abrir o navegador",
                "abra navegador",
                "abrir navegador",
                "inicie o navegador",
                "abre o navegador",
                "abre navegador",
                "inicia o navegador",
                "iniciar o navegador",
                "abrir ou navegador"
            ],
            funcao=self.abrir_navegador,
            descricao="Abrir o navegador."
        )
        
        self.registrar(
            nome="fechar_navegador",
            palavras_chave=[
                "feche o navegador",
                "fechar o navegador",
                "feche navegador",
                "fechar navegador",
                "fecha o navegador",
                "fecha navegador"
            ],
            funcao=self.fechar_navegador,
            descricao="Fechar o navegador.",
            critico=True,
            pergunta_confirmacao=(
                "Tem certeza que quer fechar o navegador? "
                "Diga sim ou não."
            )
        )

        self.registrar(
            nome="criar_pasta",
            palavras_chave=[
                "crie a pasta",
                "criar pasta",
                "crie pasta",
                "crie uma pasta",
                "nova pasta"
            ],
            funcao=self.criar_pasta,
            descricao="Criar uma pasta. Diga, por exemplo: crie a pasta fotos."
        )

        self.registrar(
            nome="criar_documento",
            palavras_chave=[
                "crie um documento",
                "crie um arquivo word",
                "crie um word",
                "novo arquivo word",
                "criar documento",
                "crie documento",
                "novo documento",
                "cria um documento",
                "criam um documento",
                "queria um documento"
            ],
            funcao=self.criar_documento,
            descricao="Criar um documento do Word."
        )

        self.registrar(
            nome="criar_planilha",
            palavras_chave=[
                "crie uma planilha",
                "crie um arquivo excel",
                "crie um excel",
                "novo arquivo excel",
                "criar planilha",
                "crie planilha",
                "nova planilha"
            ],
            funcao=self.criar_planilha,
            descricao=(
                "Criar uma planilha do Excel. Pode dizer: crie uma "
                "planilha vendas com as colunas nome, idade e cidade."
            ),
            texto_livre=True
        )

        self.registrar(
            nome="embelezar_planilha",
            palavras_chave=[
                "deixe a planilha bonita",
                "deixar a planilha bonita",
                "deixe a planilha mais bonita",
                "embeleze a planilha",
                "formate a planilha",
                "aplique o tema",
                "mude o tema"
            ],
            funcao=self.embelezar_planilha,
            descricao=(
                "Deixar a planilha bonita. Pode dizer o tema: azul, "
                "verde, vermelho, laranja, roxo ou cinza."
            )
        )

        self.registrar(
            nome="somar_coluna",
            palavras_chave=[
                "some a coluna",
                "somar a coluna",
                "total da coluna"
            ],
            funcao=self.somar_coluna,
            descricao="Somar uma coluna da planilha. Diga: some a coluna quantidade."
        )

        self.registrar(
            nome="criar_texto",
            palavras_chave=[
                "crie um arquivo de texto",
                "criar arquivo de texto",
                "novo arquivo de texto",
                "crie um texto"
            ],
            funcao=self.criar_texto,
            descricao="Criar um arquivo de texto simples."
        )

        self.registrar(
            nome="criar_apresentacao",
            palavras_chave=[
                "crie uma apresentacao",
                "criar apresentacao",
                "nova apresentacao",
                "crie um powerpoint",
                "crie um power point"
            ],
            funcao=self.criar_apresentacao,
            descricao="Criar uma apresentação do PowerPoint."
        )

        self.registrar(
            nome="adicionar_slide",
            palavras_chave=[
                "adicione um slide",
                "adicionar slide",
                "novo slide",
                "crie um slide"
            ],
            funcao=self.adicionar_slide,
            descricao="Adicionar um slide. Diga: adicione um slide, e o título.",
            texto_livre=True
        )

        self.registrar(
            nome="adicionar_linha",
            palavras_chave=[
                "adicione a linha",
                "adicione uma linha",
                "adicionar linha",
                "nova linha"
            ],
            funcao=self.adicionar_linha,
            descricao="Adicionar uma linha na planilha. Diga: adicione a linha, e os valores separados por vírgula.",
            texto_livre=True
        )

        self.registrar(
            nome="escrever_texto",
            palavras_chave=[
                "escreva",
                "escrever"
            ],
            funcao=self.escrever_texto,
            descricao="Escrever no arquivo em uso. Diga: escreva, e o texto.",
            texto_livre=True
        )

        self.registrar(
            nome="escrever_celula",
            palavras_chave=[
                "escreva na celula",
                "escrever na celula"
            ],
            funcao=self.escrever_celula,
            descricao="Escrever numa célula da planilha. Diga: escreva na célula b2 e o valor.",
            texto_livre=True
        )

        self.registrar(
            nome="ler_arquivo",
            palavras_chave=[
                "leia o documento",
                "ler o documento",
                "leia a planilha",
                "ler a planilha",
                "leia o arquivo"
            ],
            funcao=self.ler_arquivo,
            descricao="Ler o arquivo em uso."
        )

        self.registrar(
            nome="usar_arquivo",
            palavras_chave=[
                "abra o arquivo",
                "use o arquivo",
                "edite o arquivo",
                "abra o documento",
                "abra a planilha"
            ],
            funcao=self.usar_arquivo,
            descricao="Escolher o arquivo em uso. Diga: abra o arquivo, e o nome."
        )

        self.registrar(
            nome="listar_arquivos",
            palavras_chave=[
                "liste os arquivos",
                "listar arquivos",
                "listar os arquivos",
                "quais arquivos eu tenho"
            ],
            funcao=self.listar_arquivos,
            descricao="Listar os arquivos. Diga, por exemplo: liste os arquivos em documentos."
        )

        self.registrar(
            nome="excluir",
            palavras_chave=[
                "exclua",
                "excluir",
                "apague",
                "apagar",
                "delete"
            ],
            funcao=self.excluir,
            descricao="Excluir um arquivo ou pasta, mandando para a lixeira.",
            critico=True,
            pergunta_confirmacao=(
                "Tem certeza que quer excluir {parametro}? "
                "Diga sim ou não."
            )
        )

        self.registrar(
            nome="abrir_bloco_notas",
            palavras_chave=[
                "abra o bloco de notas",
                "abrir bloco de notas",
                "abra o bloco notas",
                "inicie o bloco de notas",
                "abre o bloco de notas",
                "abra bloco de notas",
                "abre bloco de notas",
                "abrir o bloco de notas",
                "inicia o bloco de notas"
            ],
            funcao=self.abrir_bloco_notas,
            descricao="Abrir o Bloco de Notas."
        )

        self.registrar(
            nome="abrir_site",
            palavras_chave=[
                "abra o site",
                "abrir o site",
                "abre o site",
                "abra site",
                "abre site",
                "abrir site"
            ],
            funcao=self.abrir_site,
            descricao="Abrir um site. Diga, por exemplo: abra o site youtube."
        )

        self.registrar(
            nome="pesquisar",
            palavras_chave=[
                "pesquise",
                "pesquisar",
                "busque",
                "buscar",
                "pesquisa",
                "busca",
                "procure",
                "procura"
            ],
            funcao=self.pesquisar,
            descricao="Pesquisar na internet. Diga, por exemplo: pesquise receita de bolo."
        )

        self.registrar(
            nome="ver_hora",
            palavras_chave=[
                "que horas sao",
                "qual a hora",
                "qual e a hora",
                "me diga as horas"
            ],
            funcao=self.ver_hora,
            descricao="Dizer as horas."
        )

        self.registrar(
            nome="identidade",
            palavras_chave=[
                "quem e voce",
                "qual seu nome",
                "qual o seu nome",
                "o que voce e"
            ],
            funcao=self.dizer_identidade,
            descricao="Dizer quem eu sou."
        )

        self.registrar(
            nome="agradecimento",
            palavras_chave=[
                "obrigado",
                "obrigada",
                "valeu",
                "agradeco"
            ],
            funcao=self.responder_agradecimento,
            descricao="Responder a um agradecimento."
        )

        self.registrar(
            nome="encerrar",
            palavras_chave=[
                "pode desligar",
                "desligue",
                "encerrar",
                "encerre",
                "ate mais",
                "tchau"
            ],
            funcao=self.encerrar,
            descricao="Encerrar a conversa."
        )

        self.registrar(
            nome="ajuda",
            palavras_chave=[
                "ajuda",
                "o que voce pode fazer",
                "quais comandos voce conhece"
            ],
            funcao=self.mostrar_ajuda,
            descricao="Listar o que eu sei fazer."
        )


    def _registrar_comandos_extras(self):
        """Registra capacidades de pesquisa que estavam declaradas à parte.

        Entradas duplicadas são ignoradas. Comandos extras que apontam para
        métodos inexistentes no gerenciador de arquivos não são ativados.
        """
        from pesquisa.comandos_arquivos_pesquisa import COMANDOS as EXTRAS

        nomes_existentes = {comando.nome for comando in self.comandos}

        for item in EXTRAS:
            nome = item["nome"]
            if nome in nomes_existentes:
                continue

            # Esses dois itens estavam declarados no módulo de extras, mas
            # as funções correspondentes não existem no gerenciador atual.
            if nome == "renomear_arquivo" and not hasattr(gerenciador_arquivos, "renomear"):
                continue
            if nome == "mostrar_arquivo" and not hasattr(gerenciador_arquivos, "mostrar"):
                continue

            acao = item["acao"]
            self.registrar(
                nome=nome,
                palavras_chave=item["frases"],
                funcao=lambda p, fn=acao: RespostaAcao(fala=fn(p)),
                descricao=item.get("descricao", ""),
                critico=item.get("critico", False),
                pergunta_confirmacao=item.get("pergunta", ""),
                texto_livre=item.get("texto_livre", False),
            )
            nomes_existentes.add(nome)


    # LOCALIZAR COMANDO

    def encontrar_comando(
        self,
        texto: str
    ) -> tuple[Optional[Comando], str]:
        """
        Procura qual comando o texto pede.

        Retorna (comando, expressão encontrada). Sem correspondência,
        retorna (None, "").

        A expressão encontrada é devolvida para que o parâmetro do
        comando possa ser extraído do que veio depois dela.
        """

        texto = normalizar_texto(texto)

        if not texto:
            return None, ""

        # As palavras só casam inteiras: assim "ajuda" não dispara
        # dentro de "ajudante", nem "valeu" dentro de outra palavra.
        texto_delimitado = f" {texto} "

        melhor_comando = None
        melhor_expressao = ""
        melhor_posicao = None

        for comando in self.comandos:

            for palavra in comando.palavras_chave:

                palavra = normalizar_texto(palavra)

                posicao = texto_delimitado.find(f" {palavra} ")

                if posicao == -1:
                    continue

                # O comando que aparece PRIMEIRO na frase vence. Assim,
                # em "escreva obrigado" quem manda é o "escreva", e não
                # o "obrigado" que faz parte do texto ditado. Se dois
                # começam no mesmo ponto, vence a expressão maior
                # ("escreva na celula" ganha de "escreva").
                if (
                    melhor_posicao is None
                    or posicao < melhor_posicao
                    or (
                        posicao == melhor_posicao
                        and len(palavra) > len(melhor_expressao)
                    )
                ):

                    melhor_posicao = posicao
                    melhor_expressao = palavra
                    melhor_comando = comando

        return melhor_comando, melhor_expressao


    # PARÂMETRO

    @staticmethod
    def _extrair_parametro(texto: str, expressao: str) -> str:
        """
        Devolve o que foi falado depois da expressão do comando.

        Usa a mesma regra de "palavra inteira" do encontrar_comando,
        para não cortar o texto no lugar errado quando a expressão
        também aparece dentro de outra palavra.
        """

        texto_delimitado = f" {normalizar_texto(texto)} "

        inicio = texto_delimitado.index(f" {expressao} ") + 1

        return texto_delimitado[inicio + len(expressao):].strip()


    @staticmethod
    def _extrair_parametro_livre(texto: str, expressao: str) -> str:
        """
        Como _extrair_parametro, mas devolve o que veio depois da
        expressão no texto ORIGINAL (com acento, maiúscula e pontuação).
        """

        palavras = texto.split()
        alvo = expressao.split()

        for i in range(len(palavras) - len(alvo) + 1):

            trecho = [
                normalizar_texto(p)
                for p in palavras[i:i + len(alvo)]
            ]

            if trecho == alvo:
                return " ".join(palavras[i + len(alvo):]).strip()

        return GerenciadorComandos._extrair_parametro(texto, expressao)


    # EXECUTAR

    def executar(self, texto: str) -> ResultadoComando:
        
        # RN03: se há ação crítica esperando, este texto é a resposta dela (inclusive texto vazio = não entendi).
        if self.confirmacao.aguardando():

            return self._tratar_confirmacao(texto)

        if self.dialogo.aguardando():
            return self._responder_parametro(texto)

        if not texto:

            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                mensagem="Nenhum comando foi recebido."
            )

        comando, expressao = self.encontrar_comando(texto)

        if comando is None:

            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                mensagem=f"Não reconheci o comando: {texto}"
            )

        # Tudo que foi falado depois da expressão do comando
        # ("pesquise receita de bolo" -> "receita de bolo").
        if comando.texto_livre:
            parametro = self._extrair_parametro_livre(texto, expressao)
        else:
            parametro = self._extrair_parametro(texto, expressao)

        return self._iniciar_comando(comando, parametro)

    def _iniciar_comando(self, comando, parametro):
        pendencia = self.solicitar_parametro_faltante(comando.nome, parametro, origem_ia=False)
        if pendencia:
            return pendencia
        # Toda criação exige confirmação explícita, mesmo com nome já informado.
        if comando.nome in CRIACOES:
            self.confirmacao.pedir(comando, parametro, exata=True)
            return ResultadoComando(StatusComando.AGUARDANDO_CONFIRMACAO, comando=comando.nome,
                                    resposta_falada=f"Confirma a ação {comando.nome.replace('_', ' ')} com nome {parametro}? Diga sim ou não.")
        # RN03: demais ações críticas mantêm o fluxo original.
        if comando.critico:

            self.confirmacao.pedir(comando, parametro)

            return ResultadoComando(
                status=StatusComando.AGUARDANDO_CONFIRMACAO,
                comando=comando.nome,
                mensagem=f"Aguardando confirmação de '{comando.nome}'.",
                resposta_falada=(
                    comando.pergunta_confirmacao
                    or "Tem certeza? Diga sim ou não."
                ).format(parametro=parametro)
            )

        return self._executar_comando(comando, parametro)

    def parametro_explicito_faltante(self, solicitacao, permitidas):
        """Reconhece somente o argumento ausente de uma ação já autorizada."""
        if len(permitidas) != 1:
            return None
        comando, expressao = self.encontrar_comando(solicitacao)
        if comando is None or comando.nome not in permitidas:
            return None
        parametro = (self._extrair_parametro_livre(solicitacao, expressao)
                     if comando.texto_livre else self._extrair_parametro(solicitacao, expressao))
        if parametro_faltante(comando.nome, parametro):
            return comando.nome, parametro
        return None

    def solicitar_parametro_faltante(self, nome, parametro, *, origem_ia):
        pergunta = parametro_faltante(nome, parametro)
        if not pergunta:
            return None
        if self.confirmacao.aguardando() or self.dialogo.aguardando():
            return ResultadoComando(StatusComando.ERRO, comando=nome,
                                    resposta_falada="Já existe uma tarefa pendente.")
        self.dialogo.pedir(nome, parametro, origem_ia, pergunta)
        return ResultadoComando(StatusComando.AGUARDANDO_PARAMETRO, comando=nome,
                                resposta_falada=pergunta)

    def _responder_parametro(self, texto):
        pendente = self.dialogo.pendente
        normalizado = normalizar_texto(texto)
        if normalizado in CANCELAMENTOS:
            self.dialogo.cancelar()
            return ResultadoComando(StatusComando.CANCELADO, comando=pendente.nome,
                                    resposta_falada="Tudo bem, cancelei a tarefa.")
        parametro = self.dialogo.completar(pendente, texto) if normalizado else None
        if (not parametro or normalizado == "sim" or len(parametro) > 4000
                or parametro_faltante(pendente.nome, parametro)):
            return ResultadoComando(StatusComando.AGUARDANDO_PARAMETRO, comando=pendente.nome,
                                    resposta_falada=pendente.pergunta if normalizado else "")
        self.dialogo.cancelar()
        if pendente.origem_ia:
            # Revalida registro, permissões e confirmação; nunca herda um sim.
            import os
            if os.getenv("ASTRA_IA_HABILITADA", "1").strip().lower() in {"0", "false", "nao", "não", "off"}:
                return ResultadoComando(StatusComando.CANCELADO, comando=pendente.nome,
                                        resposta_falada="A IA está desabilitada. Cancelei a tarefa.")
            resultado = self.executor_ferramentas.executar(pendente.nome, {"parametro": parametro})
            status = resultado.get("status")
            status = {"confirmacao_necessaria": StatusComando.AGUARDANDO_CONFIRMACAO,
                      "aguardando_parametro": StatusComando.AGUARDANDO_PARAMETRO,
                      "sucesso": StatusComando.SUCESSO}.get(status, StatusComando.ERRO)
            return ResultadoComando(status, comando=pendente.nome, dados=resultado.get("dados"),
                                    resposta_falada=resultado.get("resposta") or resultado.get("mensagem") or "Não consegui continuar a tarefa.")
        comando = next((c for c in self.comandos if c.nome == pendente.nome), None)
        if comando is None:
            return ResultadoComando(StatusComando.ERRO, resposta_falada="Comando não disponível.")
        return self._iniciar_comando(comando, parametro)

    def listar_ferramentas_ia(self) -> list[dict]:
        """Devolve schemas de ferramentas autorizadas para tool calling."""
        return self.registro_ferramentas.schemas_ia()


    def catalogo_ferramentas_ia(self) -> list[dict]:
        """Devolve descrição, categoria, risco e confirmação de cada ferramenta."""
        return self.registro_ferramentas.catalogo_ia()


    def instrucoes_seguranca_ferramentas_ia(self) -> str:
        """Devolve as regras de segurança que devem acompanhar o catálogo."""
        return self.registro_ferramentas.instrucoes_seguranca_ia()


    def solicitar_confirmacao_ferramenta(self, nome: str, parametro: str = "") -> dict:
        """Coloca uma chamada da IA na fila de confirmação por voz.

        A execução continua passando por _tratar_confirmacao; a IA não pode
        marcar a própria ação como confirmada.
        """
        comando = next((c for c in self.comandos if c.nome == nome), None)
        if comando is None:
            return {
                "status": "nao_encontrada",
                "mensagem": "Ferramenta não encontrada.",
                "executado": False,
            }

        if self.confirmacao.aguardando():
            return {"status": "erro", "mensagem": "Já existe uma ação pendente.", "executado": False}
        self.confirmacao.pedir(comando, parametro, origem_ia=True)
        pergunta = f"Confirma a ação {nome.replace('_', ' ')} com parâmetro {parametro or '(vazio)'}? Diga sim ou não."
        return {
            "status": "confirmacao_necessaria",
            "ferramenta": nome,
            "mensagem": pergunta,
            "resposta": pergunta,
            "executado": False,
            "aguardando_confirmacao": True,
        }


    def executar_ferramenta(
        self,
        nome: str,
        parametro: str = "",
        *,
        confirmado: bool = False
    ) -> ResultadoComando:
        """Executa uma ferramenta pelo identificador, sem passar pelo parser de voz.

        Este caminho é usado pelo executor unificado. A autorização e a
        confirmação da origem IA são verificadas antes de chegar aqui.
        O comando legado continua sendo a implementação real da operação.
        """
        comando = next((c for c in self.comandos if c.nome == nome), None)

        if comando is None:
            return ResultadoComando(
                status=StatusComando.NAO_ENCONTRADO,
                comando=nome,
                mensagem=f"Ferramenta não encontrada: {nome}",
            )

        if comando.critico and not confirmado:
            return ResultadoComando(
                status=StatusComando.AGUARDANDO_CONFIRMACAO,
                comando=nome,
                mensagem="A ferramenta exige confirmação.",
                resposta_falada="Preciso da sua confirmação antes de executar essa ação.",
            )

        return self._executar_comando(comando, parametro)


    def _tratar_confirmacao(self, texto: str) -> ResultadoComando:

        resposta = self.confirmacao.responder(texto)

        comando = resposta.acao.comando

        if resposta.decisao == Decisao.CONFIRMADA:

            return self._executar_comando(
                comando,
                resposta.acao.parametro
            )

        if resposta.decisao == Decisao.REPETIR:
            status = StatusComando.AGUARDANDO_CONFIRMACAO
        else:
            status = StatusComando.CANCELADO

        return ResultadoComando(
            status=status,
            comando=comando.nome,
            mensagem=resposta.mensagem,
            resposta_falada=resposta.fala
        )

    def _executar_comando(
        self,
        comando: Comando,
        parametro: str
    ) -> ResultadoComando:

        try:

            resposta = comando.funcao(parametro)

            fala = resposta.fala
            dados = resposta.dados
            if isinstance(fala, ResultadoArquivo):
                if not fala.sucesso:
                    return ResultadoComando(StatusComando.ERRO, comando=comando.nome,
                                            mensagem=str(fala), resposta_falada=str(fala))
                dados = fala.dados if fala.dados is not None else dados
                if dados and isinstance(dados, dict) and dados.get("caminho"):
                    log(f"Resultado de {comando.nome}: {dados['caminho']}")
                    if comando.nome in CRIACOES or comando.nome in {"pesquisar_documento", "pesquisar_planilha", "pesquisar_apresentacao"}:
                        fala = f"{fala} Caminho: {dados['caminho']}."
            self.memoria_operacional.registrar(comando.nome, dados)
            return ResultadoComando(
                status=StatusComando.SUCESSO,
                comando=comando.nome,
                mensagem=f"Comando '{comando.nome}' executado.",
                dados=dados,
                resposta_falada=str(fala),
                encerrar=resposta.encerrar
            )

        except Exception as erro:

            return ResultadoComando(
                status=StatusComando.ERRO,
                comando=comando.nome,
                mensagem=f"Erro ao executar '{comando.nome}': {erro}",
                resposta_falada="Não consegui executar esse comando."
            )


    # AÇÕES

    def ler_tela(self, parametro: str = "") -> RespostaAcao:
        """
        Captura a tela e envia para o OCR.
        """

        # Importados aqui dentro (e não no topo) porque carregar o
        # módulo de captura exige tela e Tesseract instalados, e o
        # reconhecimento de comandos não deveria depender disso para
        # funcionar nem para ser testado.
        from captura_tela.capturador_tela import capturar_tela
        from captura_tela.leitor_ocr import extrair_texto

        imagem = capturar_tela()

        if imagem is None:

            raise RuntimeError(
                "Não foi possível capturar a tela."
            )

        texto = extrair_texto(imagem)

        if not texto:

            return RespostaAcao(
                fala="Não encontrei nenhum texto na tela.",
                dados=""
            )

        return RespostaAcao(fala=texto, dados=texto)


    def abrir_navegador(self, parametro: str = "") -> RespostaAcao:

        if not webbrowser.open("https://www.google.com"):
            raise RuntimeError("O navegador não aceitou a solicitação.")

        return RespostaAcao(fala="Abrindo o navegador.")
    
    def fechar_navegador(self, parametro: str = "") -> RespostaAcao:
        """
        Ação crítica (RN03): só chega aqui depois da confirmação.

        Sem /F, o taskkill pede o fechamento em vez de matar o
        processo, dando ao navegador a chance de avisar sobre dados
        não salvos.
        """

        fechou_algum = False

        for processo in ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"):

            resultado = subprocess.run(
                ["taskkill", "/IM", processo],
                capture_output=True
            )

            if resultado.returncode == 0:
                fechou_algum = True

        if not fechou_algum:

            return RespostaAcao(
                fala="Não encontrei nenhum navegador aberto."
            )

        return RespostaAcao(fala="Navegador fechado.")


    def criar_pasta(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.criar_pasta(parametro))


    def criar_documento(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.criar_documento(parametro))


    def criar_planilha(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.criar_planilha(parametro))


    def embelezar_planilha(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.embelezar_planilha(parametro))


    def somar_coluna(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.somar_coluna(parametro))


    def criar_texto(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.criar_texto(parametro))


    def criar_apresentacao(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.criar_apresentacao(parametro))


    def adicionar_slide(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.adicionar_slide(parametro))


    def adicionar_linha(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.adicionar_linha(parametro))


    def escrever_texto(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.escrever_texto(parametro))


    def escrever_celula(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.escrever_celula(parametro))


    def ler_arquivo(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.ler_atual())


    def usar_arquivo(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.usar_arquivo(parametro))


    def listar_arquivos(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala=gerenciador_arquivos.listar(parametro))


    def excluir(self, parametro: str = "") -> RespostaAcao:
        """
        Ação crítica (RN03): só chega aqui depois da confirmação.
        """

        return RespostaAcao(fala=gerenciador_arquivos.excluir(parametro))


    def abrir_bloco_notas(self, parametro: str = "") -> RespostaAcao:

        subprocess.Popen(
            ["notepad.exe"]
        )

        return RespostaAcao(fala="Abrindo o Bloco de Notas.")


    def abrir_site(self, parametro: str = "") -> RespostaAcao:

        # Aceita "youtube" ou "youtube.com" (a fala já vem sem pontuação,
        # então quem diz o domínio completo costuma ficar com ele
        # separado por espaço; juntamos tudo).
        site = parametro.replace(" ", "")

        if not site:

            return RespostaAcao(fala="Qual site você quer abrir?")

        if "." not in site:

            site = f"{site}.com"

        if not webbrowser.open(f"https://www.{site}"):
            raise RuntimeError("O navegador não aceitou a solicitação.")

        return RespostaAcao(
            fala=f"Abrindo o site {parametro}.",
            dados=site
        )


    def pesquisar(self, parametro: str = "") -> RespostaAcao:

        if not parametro:

            return RespostaAcao(fala="O que você quer pesquisar?")

        abriu = webbrowser.open(
            f"https://www.google.com/search?q={quote_plus(parametro)}"
        )
        if abriu is False:
            raise RuntimeError("O navegador não aceitou a solicitação de pesquisa.")

        return RespostaAcao(
            fala=f"Pesquisando {parametro}.",
            dados=parametro
        )


    def ver_hora(self, parametro: str = "") -> RespostaAcao:

        agora = datetime.now()

        hora = agora.hour
        minuto = agora.minute

        palavra_hora = "hora" if hora == 1 else "horas"

        if minuto == 0:

            fala = f"Agora são {hora} {palavra_hora} em ponto."

        else:

            palavra_minuto = "minuto" if minuto == 1 else "minutos"

            fala = (
                f"Agora são {hora} {palavra_hora} "
                f"e {minuto} {palavra_minuto}."
            )

        return RespostaAcao(fala=fala, dados=agora)


    def dizer_identidade(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(
            fala="Eu sou a A.S.T.R.A., sua assistente virtual."
        )


    def responder_agradecimento(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(fala="Por nada.")


    def encerrar(self, parametro: str = "") -> RespostaAcao:

        return RespostaAcao(
            fala="Tudo bem. Até mais.",
            encerrar=True
        )


    def mostrar_ajuda(self, parametro: str = "") -> RespostaAcao:

        descricoes = [
            comando.descricao
            for comando in self.comandos
        ]

        return RespostaAcao(
            fala="Eu posso: " + " ".join(descricoes),
            dados=descricoes
        )


# INSTÂNCIA PRINCIPAL

gerenciador_comandos = GerenciadorComandos()


# FUNÇÃO PÚBLICA

def executar_comando(texto: str) -> ResultadoComando:
    """
    Função utilizada pelos outros módulos da A.S.T.R.A.
    """

    return gerenciador_comandos.executar(texto)

def aguardando_confirmacao() -> bool:
    """
    RN03: True se a A.S.T.R.A. espera um "sim"/"não" do usuário.
    """

    return gerenciador_comandos.confirmacao.aguardando()