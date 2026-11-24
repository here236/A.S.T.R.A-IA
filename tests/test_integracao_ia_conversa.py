import unittest

from voz.processador_linguagem import ProcessadorConversa, RESPOSTA_PADRAO


class PlanejadorFalso:
    def __init__(self, resultado):
        self.resultado = resultado
        self.solicitacoes = []

    def processar(self, texto):
        self.solicitacoes.append(texto)
        return self.resultado


class IntegracaoIAConversaTests(unittest.TestCase):
    def test_ia_desabilitada_preserva_fallback_tradicional(self):
        processador = ProcessadorConversa(ia_habilitada=False)
        self.assertEqual(processador.responder("pedido que não existe"), RESPOSTA_PADRAO)

    def test_regras_de_conversa_tem_prioridade_sobre_ia(self):
        planejador = PlanejadorFalso({"status": "resposta", "mensagem": "resposta IA"})
        processador = ProcessadorConversa(planejador=planejador)
        self.assertEqual(processador.responder("bom dia"), "Bom dia! Como posso ajudar?")
        self.assertEqual(planejador.solicitacoes, [])

    def test_pedido_desconhecido_e_encaminhado_ao_planejador(self):
        planejador = PlanejadorFalso({"status": "resposta", "mensagem": "Posso ajudar com isso."})
        processador = ProcessadorConversa(planejador=planejador)
        self.assertEqual(processador.responder("explique computação quântica"), "Posso ajudar com isso.")
        self.assertEqual(planejador.solicitacoes, ["explique computação quântica"])

    def test_resultados_de_ferramentas_sao_convertidos_em_fala(self):
        planejador = PlanejadorFalso({
            "status": "etapas_executadas",
            "mensagem": "Finalizado",
            "resultados": [
                {"resposta": "Abri o navegador."},
                {"resposta": "Pesquisei o assunto."},
            ],
        })
        processador = ProcessadorConversa(planejador=planejador)
        self.assertEqual(
            processador.responder("faça uma pesquisa e abra o resultado"),
            "Abri o navegador. Pesquisei o assunto.",
        )

    def test_confirmacao_e_apresentada_ao_usuario(self):
        planejador = PlanejadorFalso({
            "status": "aguardando_confirmacao",
            "mensagem": "Confirma a exclusão? Diga sim ou não.",
        })
        processador = ProcessadorConversa(planejador=planejador)
        self.assertEqual(
            processador.responder("exclua o arquivo antigo"),
            "Confirma a exclusão? Diga sim ou não.",
        )

    def test_erro_da_ia_nao_quebra_a_conversa(self):
        class PlanejadorComErro:
            def processar(self, texto):
                raise RuntimeError("Ollama desligado")
        processador = ProcessadorConversa(planejador=PlanejadorComErro())
        self.assertEqual(processador.responder("pedido desconhecido"), RESPOSTA_PADRAO)


if __name__ == "__main__":
    unittest.main()
