import json
import unittest
from types import SimpleNamespace

from ferramentas import RegistroFerramentas
from ferramentas.modelos import Ferramenta
from ia.planejador import ErroPlanejamento, PlanejadorASTRA, Plano


class ClienteFalso:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def gerar_resposta(self, sistema, usuario):
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

    def test_limite_de_etapas_e_respeitado(self):
        resposta = '{"acao":"executar","ferramentas":[{"nome":"pesquisar","argumentos":{"parametro":"x"}}]}'
        cliente = ClienteFalso([resposta, resposta])
        resultado = PlanejadorASTRA(cliente, self.registro, ExecutorFalso(), max_etapas=1).processar("pesquise x")
        self.assertEqual(resultado["status"], "limite_de_etapas")

    def test_multiplas_ferramentas_e_contexto(self):
        cliente = ClienteFalso([
            json.dumps({"acao":"executar","ferramentas":[{"nome":"pesquisar","argumentos":{"parametro":x}} for x in ("a","b")]}),
            '{"acao":"responder","ferramentas":[],"resposta":"Resultado combinado."}',
            '{"acao":"responder","ferramentas":[],"resposta":"Continuação."}'
        ])
        executor = ExecutorFalso()
        planejador = PlanejadorASTRA(cliente, self.registro, executor)
        self.assertEqual(planejador.processar("compare a e b")["status"], "resposta")
        self.assertEqual(len(executor.chamadas), 2)
        self.assertEqual(len(cliente.chamadas[1][1]["resultados_anteriores"]), 2)
        planejador.processar("continue")
        self.assertEqual(cliente.chamadas[2][1]["historico_conversa"][0]["usuario"], "compare a e b")
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
