import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ferramentas import RegistroFerramentas
from ferramentas.modelos import Ferramenta
from ia.planejador import ErroPlanejamento, PlanejadorASTRA, Plano, FORMATO_CONVERSA, INSTRUCAO_CONVERSA


class ClienteFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def gerar_resposta(self, sistema, usuario, **kwargs):
        self.chamadas.append((sistema, json.loads(usuario)))
        return self.respostas.pop(0)


class ExecutorFalso:
    def __init__(self, resultados=None):
        self.resultados = list(resultados or [])
        self.chamadas = []

    def executar(self, nome, argumentos, confirmado=False):
        self.chamadas.append((nome, argumentos, confirmado))
        if self.resultados:
            return self.resultados.pop(0)
        return {"status": "sucesso", "executado": True, "dados": "ok"}


class PlanejadorTests(unittest.TestCase):
    def setUp(self):
        self.registro = RegistroFerramentas()
        self.registro.registrar(Ferramenta(
            nome="pesquisar", descricao="Pesquisa na web", categoria="pesquisa",
            parametros={"type": "object", "properties": {
                "parametro": {"type": "string"}}, "additionalProperties": False}
        ))
        self.registro.registrar(Ferramenta(
            nome="excluir", descricao="Exclui arquivo", categoria="arquivos",
            requer_confirmacao=True
        ))

    def test_planeja_chamada_autorizada_sem_executar(self):
        cliente = ClienteFalso(['{"acao":"executar","ferramentas":[{"nome":"pesquisar","argumentos":{"parametro":"clima"}}],"resposta":"Vou pesquisar."}'])
        executor = ExecutorFalso()
        planejador = PlanejadorASTRA(cliente, self.registro, executor)
        plano = planejador.planejar("pesquise o clima")
        self.assertEqual(plano.ferramentas[0]["nome"], "pesquisar")
        self.assertEqual(executor.chamadas, [])

    def test_rejeita_ferramenta_inventada(self):
        cliente = ClienteFalso(['{"acao":"executar","ferramentas":[{"nome":"rodar_terminal","argumentos":{}}]}'])
        planejador = PlanejadorASTRA(cliente, self.registro, ExecutorFalso())
        with self.assertRaises(ErroPlanejamento):
            planejador.planejar("faça algo")

    def test_rejeita_parametro_desconhecido(self):
        cliente = ClienteFalso(['{"acao":"executar","ferramentas":[{"nome":"pesquisar","argumentos":{"parametro":"x","shell":"rm"}}]}'])
        planejador = PlanejadorASTRA(cliente, self.registro, ExecutorFalso())
        with self.assertRaises(ErroPlanejamento):
            planejador.planejar("pesquise x")

    def test_acao_sensivel_para_aguardando_confirmacao(self):
        cliente = ClienteFalso(['{"acao":"executar","ferramentas":[{"nome":"excluir","argumentos":{"parametro":"arquivo.txt"}}]}'])
        executor = ExecutorFalso([{"status": "confirmacao_necessaria", "executado": False}])
        resultado = PlanejadorASTRA(cliente, self.registro, executor).processar("exclua arquivo.txt")
        self.assertEqual(resultado["status"], "aguardando_confirmacao")
        self.assertFalse(executor.chamadas[0][2])

    def test_resposta_sem_ferramentas(self):
        cliente = ClienteFalso(['{"acao":"responder","ferramentas":[],"resposta":"Não tenho essa capacidade."}'])
        resultado = PlanejadorASTRA(cliente, self.registro, ExecutorFalso()).processar("toque música")
        self.assertEqual(resultado["status"], "resposta")
        self.assertEqual(resultado["mensagem"], "Não tenho essa capacidade.")

    def test_pergunta_usa_formato_exclusivo_de_resposta(self):
        cliente = Mock()
        cliente.gerar_resposta.return_value = '{"acao":"responder","ferramentas":[],"resposta":"Linux é um núcleo de sistema operacional."}'
        executor = ExecutorFalso()
        p = PlanejadorASTRA(cliente, self.registro, executor)
        resultado = p.processar('o que é Linux?')
        self.assertEqual(resultado['status'], 'resposta')
        args, kwargs = cliente.gerar_resposta.call_args
        self.assertEqual(args[0], INSTRUCAO_CONVERSA)
        self.assertEqual(kwargs['formato'], FORMATO_CONVERSA)
        self.assertEqual(kwargs['formato']['properties']['acao']['enum'], ['responder'])
        self.assertEqual(kwargs['formato']['properties']['ferramentas']['maxItems'], 0)
        self.assertEqual(json.loads(args[1])['catalogo_autorizado'], [])
        self.assertEqual(executor.chamadas, [])

    def test_modo_conversa_bloqueia_ferramenta_inventada(self):
        cliente = Mock()
        cliente.gerar_resposta.return_value = '{"acao":"executar","ferramentas":[{"nome":"inventada","argumentos":{"parametro":""}}],"resposta":""}'
        executor = ExecutorFalso()
        resultado = PlanejadorASTRA(cliente, self.registro, executor).processar('o que é Linux?')
        self.assertEqual(resultado['status'], 'plano_invalido')
        self.assertEqual(executor.chamadas, [])

    def test_limite_de_etapas_e_respeitado(self):
        for nome in ("abrir_navegador", "ver_hora"):
            self.registro.registrar(Ferramenta(nome=nome, descricao=nome, categoria="teste"))
        executor = ExecutorFalso()
        resultado = PlanejadorASTRA(ClienteFalso([]), self.registro, executor, max_etapas=1).processar("abra o navegador e diga as horas")
        self.assertEqual(resultado["status"], "limite_de_etapas")
        self.assertEqual(executor.chamadas, [])

    def test_mesma_ferramenta_com_parametros_distintos_bloqueada(self):
        cliente = ClienteFalso([json.dumps({"acao":"executar","ferramentas":[{"nome":"pesquisar","argumentos":{"parametro":x}} for x in ("a","b")]})])
        executor = ExecutorFalso()
        planejador = PlanejadorASTRA(cliente, self.registro, executor)
        self.assertEqual(planejador.processar("pesquise a e b")["status"], "ciclo_detectado")
        self.assertEqual(executor.chamadas, [])

    def test_conversa_mantem_contexto(self):
        cliente = ClienteFalso([
            '{"acao":"responder","ferramentas":[],"resposta":"Python é uma linguagem."}',
            '{"indices":[1]}',
            '{"acao":"responder","ferramentas":[],"resposta":"Continuação."}'
        ])
        executor = ExecutorFalso()
        planejador = PlanejadorASTRA(cliente, self.registro, executor)
        planejador.processar("o que é Python")
        planejador.processar("continue")
        self.assertEqual(cliente.chamadas[2][1]["historico_conversa"][0]["usuario"], "o que é Python")
        self.assertEqual(executor.chamadas, [])
        planejador.limpar_historico()
        self.assertEqual(planejador.historico, [])

    def test_ocr_como_dado(self):
        self.registro.registrar(Ferramenta(nome="ler_tela", descricao="OCR", categoria="tela"))
        cliente = ClienteFalso([
            '{"acao":"executar","ferramentas":[{"nome":"ler_tela","argumentos":{"parametro":""}}]}',
            '{"acao":"responder","ferramentas":[],"resposta":"Erro de sintaxe."}'
        ])
        executor = ExecutorFalso([{"status":"sucesso","dados":"SyntaxError"}])
        resultado = PlanejadorASTRA(cliente,self.registro,executor).processar("explique a tela")
        self.assertEqual(resultado["mensagem"], "Erro de sintaxe.")
        self.assertEqual(cliente.chamadas[1][1]["resultados_anteriores"][0]["dados"], "SyntaxError")


if __name__ == "__main__":
    unittest.main()
