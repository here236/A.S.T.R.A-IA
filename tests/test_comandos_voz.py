import unittest
from unittest import mock

from voz.comandos_voz import GerenciadorComandos, StatusComando, variantes_de_artigo, variantes_de_verbo


class TestVariantesDeArtigo(unittest.TestCase):

    def test_troca_e_remove_o_artigo(self):
        self.assertEqual(
            variantes_de_artigo("abra o navegador"),
            ["abra o navegador", "abra um navegador", "abra navegador"])

    def test_artigo_feminino(self):
        self.assertEqual(
            variantes_de_artigo("leia a tela"),
            ["leia a tela", "leia uma tela", "leia tela"])

    def test_frase_sem_artigo_fica_igual(self):
        self.assertEqual(variantes_de_artigo("que horas sao"), ["que horas sao"])

    def test_so_troca_palavras_inteiras(self):
        # o "o" de "abrir" e o "a" de "navegador" não são artigos
        self.assertEqual(variantes_de_artigo("abrir navegador"), ["abrir navegador"])

    def test_frase_so_de_artigos_nao_gera_variante_vazia(self):
        self.assertNotIn("", variantes_de_artigo("o"))


class TestVariantesDeVerbo(unittest.TestCase):

    def test_todas_as_formas_do_verbo(self):
        self.assertEqual(
            variantes_de_verbo("abra o site"),
            ["abra o site", "abre o site", "abro o site", "abrir o site"])

    def test_a_forma_original_vem_primeiro_qualquer_que_seja(self):
        self.assertEqual(variantes_de_verbo("fecha navegador")[0], "fecha navegador")
        self.assertEqual(len(variantes_de_verbo("fecha navegador")), 4)

    def test_verbo_so_vale_no_comeco_da_frase(self):
        self.assertEqual(variantes_de_verbo("quero abrir o site"), ["quero abrir o site"])

    def test_frase_sem_verbo_conhecido_fica_igual(self):
        self.assertEqual(variantes_de_verbo("que horas sao"), ["que horas sao"])
        self.assertEqual(variantes_de_verbo(""), [""])


class TestReconhecimentoComVariantes(unittest.TestCase):

    def setUp(self):
        self.g = GerenciadorComandos()

    def nome(self, texto):
        comando, _ = self.g.encontrar_comando(texto)
        return comando.nome if comando else None

    def test_formas_que_o_whisper_escreveu(self):
        casos = {
            "abra um navegador": "abrir_navegador",
            "abre o navegador": "abrir_navegador",
            "abre um site youtube": "abrir_site",
            "leia uma tela": "ler_tela",
            "fecha o navegador": "fechar_navegador",
            "pesquisa e receita de bolo": "pesquisar",
            "abra o bloco de notas": "abrir_bloco_notas",
            "abre um bloco de notas": "abrir_bloco_notas",
            "abro o site youtube": "abrir_site",
            "fecho o navegador": "fechar_navegador",
            "pesquiso receita de bolo": "pesquisar",
            "leio a tela": "ler_tela",
        }
        for texto, esperado in casos.items():
            self.assertEqual(self.nome(texto), esperado, texto)

    def test_frases_comuns_sem_comando_continuam_sem_acionar_nada(self):
        for texto in ("quero um navegador novo", "a casa de um amigo", "o dia está bonito", "ele abriu a porta"):
            self.assertIsNone(self.nome(texto), texto)

    def test_o_parametro_continua_certo_com_a_variante(self):
        with mock.patch("webbrowser.open") as abrir:
            resultado = self.g.executar("abre um site youtube")
        self.assertEqual(resultado.status, StatusComando.SUCESSO)
        abrir.assert_called_once_with("https://www.youtube.com")

    def test_o_critico_continua_pedindo_confirmacao_na_variante(self):
        resultado = self.g.executar("fecha um navegador")
        self.assertEqual(resultado.status, StatusComando.AGUARDANDO_CONFIRMACAO)


if __name__ == "__main__":
    unittest.main()
