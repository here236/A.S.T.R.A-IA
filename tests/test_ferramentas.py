import unittest
from types import SimpleNamespace

from ferramentas import ExecutorFerramentas, RegistroFerramentas
from ferramentas.politicas import validar_argumentos


class RegistroFerramentasTests(unittest.TestCase):
    def test_registra_comando_legado_e_cria_schema(self):
        registro = RegistroFerramentas()
        comando = SimpleNamespace(
            nome="ler_tela", descricao="Lê a tela", critico=False
        )
        ferramenta = registro.registrar_comando(comando)

        self.assertEqual(ferramenta.nome, "ler_tela")
        self.assertEqual(ferramenta.categoria, "tela")
        self.assertIn("parametro", ferramenta.parametros["properties"])
        self.assertIn("ler_tela", registro.nomes(apenas_ia=True))
        schema = registro.schemas_ia()[0]
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)

    def test_nao_disponibiliza_comando_conversacional_para_ia(self):
        registro = RegistroFerramentas()
        registro.registrar_comando(SimpleNamespace(
            nome="encerrar", descricao="Encerrar", critico=False
        ))
        self.assertNotIn("encerrar", registro.nomes(apenas_ia=True))

    def test_rejeita_nome_duplicado(self):
        registro = RegistroFerramentas()
        comando = SimpleNamespace(nome="ler_tela", descricao="Ler", critico=False)
        registro.registrar_comando(comando)
        with self.assertRaises(ValueError):
            registro.registrar_comando(comando)


class PoliticasTests(unittest.TestCase):
    def test_argumentos_validos(self):
        self.assertEqual(validar_argumentos({"parametro": "relatório"}), (True, ""))

    def test_rejeita_argumento_desconhecido(self):
        valido, mensagem = validar_argumentos({"comando_shell": "del *"})
        self.assertFalse(valido)
        self.assertIn("não reconhecidos", mensagem)

    def test_rejeita_parametro_nao_textual(self):
        valido, _ = validar_argumentos({"parametro": ["x"]})
        self.assertFalse(valido)


class ExecutorFerramentasTests(unittest.TestCase):
    def setUp(self):
        self.registro = RegistroFerramentas()
        self.registro.registrar_comando(SimpleNamespace(
            nome="excluir", descricao="Excluir arquivo", critico=True
        ))
        self.manager = SimpleNamespace()
        self.manager.executar_ferramenta = lambda nome, parametro, confirmado=False: SimpleNamespace(
            status=SimpleNamespace(value="sucesso"), comando=nome,
            mensagem="ok", resposta_falada="feito", dados=None
        )
        self.executor = ExecutorFerramentas(self.manager, self.registro)

    def test_exclusao_pede_confirmacao_antes_de_executar(self):
        resultado = self.executor.executar("excluir", {"parametro": "teste.txt"})
        self.assertEqual(resultado["status"], "confirmacao_necessaria")
        self.assertFalse(resultado["executado"])


    def test_executor_registra_confirmacao_no_fluxo_de_voz(self):
        from voz.comandos_voz import GerenciadorComandos, RespostaAcao, StatusComando

        gerenciador = GerenciadorComandos()
        executado = []
        comando = next(c for c in gerenciador.comandos if c.nome == "escrever_texto")
        comando.funcao = lambda parametro: (
            executado.append(parametro) or RespostaAcao(fala="Ação concluída.")
        )

        resultado = gerenciador.executor_ferramentas.executar(
            "escrever_texto", {"parametro": "alvo"}
        )
        self.assertEqual(resultado["status"], "confirmacao_necessaria")
        self.assertTrue(gerenciador.confirmacao.aguardando())
        self.assertEqual(executado, [])

        resposta = gerenciador.executar("sim")
        self.assertEqual(resposta.status, StatusComando.SUCESSO)
        self.assertEqual(executado, ["alvo"])

    def test_exclusao_executa_apos_confirmacao(self):
        resultado = self.executor.executar(
            "excluir", {"parametro": "teste.txt"}, confirmado=True
        )
        self.assertTrue(resultado["executado"])
        self.assertEqual(resultado["status"], "sucesso")

    def test_nao_executa_ferramenta_nao_cadastrada(self):
        resultado = self.executor.executar("executar_codigo", {})
        self.assertEqual(resultado["status"], "nao_encontrada")

    def test_retorno_de_data_e_convertido_para_texto_iso(self):
        from datetime import datetime
        valor = datetime(2026, 11, 23, 12, 30)
        self.assertEqual(
            self.executor._normalizar_dados(valor),
            "2026-11-23T12:30:00",
        )


class IntegracaoGerenciadorComandosTests(unittest.TestCase):
    def test_comandos_legados_alimentam_o_catalogo_unificado(self):
        from voz.comandos_voz import GerenciadorComandos, StatusComando

        gerenciador = GerenciadorComandos()
        nomes_comandos = {c.nome for c in gerenciador.comandos}
        nomes_catalogo = set(gerenciador.registro_ferramentas.nomes())

        self.assertEqual(nomes_comandos, nomes_catalogo)
        self.assertIn("ler_tela", nomes_catalogo)
        self.assertIn("pesquisar_documento", nomes_catalogo)
        self.assertNotIn("encerrar", gerenciador.registro_ferramentas.nomes(apenas_ia=True))

        # O caminho tradicional continua independente do executor de IA.
        resultado = gerenciador.executar("que horas sao")
        self.assertEqual(resultado.status, StatusComando.SUCESSO)

    def test_catalogo_informa_confirmacao_para_acoes_sensiveis(self):
        from voz.comandos_voz import GerenciadorComandos

        gerenciador = GerenciadorComandos()
        catalogo = {item["name"]: item for item in gerenciador.catalogo_ferramentas_ia()}
        self.assertTrue(catalogo["excluir"]["requires_confirmation"])
        self.assertTrue(catalogo["escrever_texto"]["requires_confirmation"])
        self.assertFalse(catalogo["ler_tela"]["requires_confirmation"])
        regras = gerenciador.instrucoes_seguranca_ferramentas_ia()
        self.assertIn("não confiáveis", regras)


if __name__ == "__main__":
    unittest.main()
