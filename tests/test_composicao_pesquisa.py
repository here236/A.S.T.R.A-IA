import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from ia.planejador import PlanejadorASTRA
from voz.comandos_voz import GerenciadorComandos


class ComposicaoPesquisaTests(unittest.TestCase):
    def setUp(self):
        self.g = GerenciadorComandos()
        self.modelo = Mock()
        self.p = PlanejadorASTRA(self.modelo, self.g.registro_ferramentas,
                                self.g.executor_ferramentas)

    def test_busca_composta_abre_uma_unica_url(self):
        casos = [
            ('abrir o navegador e pesquisar sobre Godot', 'Godot'),
            ('abra o navegador e depois pesquise sobre Python', 'Python'),
            ('abra o navegador e pesquisar no navegador sobre Python', 'Python'),
            ('abra o navegador para buscar sobre árvores', '%C3%A1rvores'),
            ('por favor, abra o navegador e pesquise sobre Python e Java', 'Python+e+Java'),
        ]
        for pedido, query in casos:
            with self.subTest(pedido=pedido), patch('webbrowser.open', return_value=True) as abrir:
                resultado = self.p.processar(pedido)
                self.assertEqual(resultado['status'], 'etapas_executadas')
                self.assertTrue(resultado['concluido'])
                abrir.assert_called_once_with('https://www.google.com/search?q=' + query)
        self.modelo.gerar_resposta.assert_not_called()

    def test_falha_nao_repete(self):
        with patch('webbrowser.open', return_value=False) as abrir:
            resultado = self.p.processar('abra o navegador e pesquise sobre Python')
            self.assertEqual(resultado['status'], 'erro_na_etapa')
            self.assertFalse(resultado['concluido'])
            abrir.assert_called_once()
        self.modelo.gerar_resposta.assert_not_called()

    def test_pedido_incompleto_ou_terceira_acao_nao_abre(self):
        for pedido in ('abra o navegador e pesquise', 'abra o navegador e pesquise sobre',
                       'abra o navegador e pesquise no navegador sobre',
                       'abra o navegador e pesquise sobre Python e crie uma pasta'):
            with self.subTest(pedido=pedido), patch('webbrowser.open') as abrir:
                resultado = self.p.processar(pedido)
                self.assertFalse(resultado['concluido'])
                abrir.assert_not_called()
        self.modelo.gerar_resposta.assert_not_called()

    def test_desabilitada_nao_abre(self):
        for nome in ('pesquisar', 'abrir_navegador'):
            reg = self.g.registro_ferramentas
            original = reg.obter(nome)
            try:
                reg._ferramentas[nome] = replace(original, disponivel_para_ia=False)
                with patch('webbrowser.open') as abrir:
                    r = self.p.processar('abra o navegador e pesquise sobre Python')
                    self.assertEqual(r['status'], 'ferramenta_bloqueada')
                    abrir.assert_not_called()
            finally:
                reg._ferramentas[nome] = original
        self.modelo.gerar_resposta.assert_not_called()

    def test_pergunta_e_negacao_nao_abrem(self):
        self.modelo.gerar_resposta.return_value = '{"acao":"responder","ferramentas":[],"resposta":"Certo."}'
        for pedido in ('como abrir o navegador e pesquisar sobre Godot',
                       'não abra o navegador e pesquise sobre Godot'):
            with self.subTest(pedido=pedido), patch('webbrowser.open') as abrir:
                self.p.processar(pedido)
                abrir.assert_not_called()

if __name__ == '__main__':
    unittest.main()
