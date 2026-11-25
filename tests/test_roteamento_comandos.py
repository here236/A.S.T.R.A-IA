import unittest
import json
from unittest.mock import Mock, patch

from ia.escopo_ferramentas import ferramentas_do_pedido
from voz.comandos_voz import GerenciadorComandos, ResultadoComando, StatusComando
from voz.intencao_voz import Esclarecimento
from voz.roteamento_comandos import avaliar_rota
from voz.voz_principal import AssistenteVoz


class TestRoteamento(unittest.TestCase):
    def setUp(self):
        self.gerenciador = GerenciadorComandos()
        self.executar = Mock(return_value=ResultadoComando(StatusComando.SUCESSO, resposta_falada='Direto.'))
        self.conversar = Mock(return_value='Planejador.')
        self.interpretar = Mock(return_value=None)
        self.assistente = AssistenteVoz(lambda: '', lambda _: None,
            executar=self.executar, aguardando_confirmacao=lambda: False,
            conversar=self.conversar, interpretar_intencao=self.interpretar)
        env = patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})
        env.start()
        self.addCleanup(env.stop)

    def test_composto_sem_palavra_especial(self):
        pedido = 'abrir o navegador e pesquisar sobre godot'
        self.assistente.processar('astra ' + pedido)
        self.executar.assert_not_called()
        self.interpretar.assert_called_once_with(pedido)
        self.conversar.assert_not_called()
        self.assistente.processar('sim')
        self.conversar.assert_called_once_with(pedido)
        self.assertIn('pesquisar', ferramentas_do_pedido(pedido))

    def test_composto_com_depois(self):
        pedido = 'abra o navegador e depois pesquise sobre godot'
        self.assistente.processar('astra ' + pedido)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()
        self.assistente.processar('sim')
        self.conversar.assert_called_once_with(pedido)
        self.assertIn('pesquisar', ferramentas_do_pedido(pedido))

    def test_composto_com_criacao_aguarda_nome(self):
        saida = self.assistente.processar('astra abra o navegador e crie uma pasta')
        self.assertIn('Qual nome', saida.fala)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()

    def test_cortesia_nao_oculta_segunda_acao(self):
        saida = self.assistente.processar('astra por favor abra o navegador e crie uma pasta')
        self.assertIn('Qual nome', saida.fala)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()

    def test_composto_sem_ia_nao_executa_parte(self):
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '0'}):
            saida = self.assistente.processar('astra abra o navegador e pesquise sobre godot')
        self.assertIn('desabilitada', saida.fala)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()

    def test_comando_simples_independente_da_ia(self):
        for estado in ('0', '1'):
            with patch.dict('os.environ', {'ASTRA_IA_HABILITADA': estado}):
                self.assistente.processar('astra abra o navegador')
        self.assertEqual(self.executar.call_count, 2)
        self.interpretar.assert_not_called()
        self.conversar.assert_not_called()

    def test_pergunta_nao_abre_navegador(self):
        self.assistente.processar('astra como abrir o navegador')
        self.executar.assert_not_called()
        self.conversar.assert_called_once_with('como abrir o navegador')

    def test_texto_livre_e_assunto_nao_viram_ordens(self):
        for pedido in ('escreva abra o navegador e pesquise', 'pesquise gatos e cachorros', 'crie uma pasta chamada projetos e estudos'):
            with self.subTest(pedido=pedido):
                self.assertTrue(avaliar_rota(pedido, self.gerenciador).direta)

    def test_criacao_direta_ainda_exige_confirmacao(self):
        assistente = AssistenteVoz(lambda: '', lambda _: None, executar=self.gerenciador.executar,
            aguardando_confirmacao=self.gerenciador.confirmacao.aguardando, interpretar_intencao=self.interpretar,
            conversar=self.conversar)
        saida = assistente.processar('astra crie uma pasta chamada teste rota')
        self.assertIn('sim ou não', saida.fala)
        self.assertTrue(self.gerenciador.confirmacao.aguardando())
        self.assertIn('cancelei', assistente.processar('não').fala.lower())
        self.interpretar.assert_not_called()

    def test_correcao_confirmada_mantem_fluxo_ia(self):
        self.interpretar.return_value = Esclarecimento('Confirma?', 'pesquise sobre árvores')
        self.assistente.processar('astra pesquize sobre arvores')
        self.conversar.assert_not_called()
        self.assistente.processar('sim')
        self.conversar.assert_called_once_with('pesquise sobre árvores')
        self.executar.assert_not_called()

    def test_sufixo_nao_e_ignorado(self):
        self.assistente.processar('astra abra o navegador no modo anonimo')
        self.executar.assert_not_called()
        self.conversar.assert_called_once_with('abra o navegador no modo anonimo')

    def test_integracao_composto_com_executor_real_e_navegador_simulado(self):
        from ia.planejador import PlanejadorASTRA
        from voz.processador_linguagem import ProcessadorConversa
        cliente = Mock()
        planejador = PlanejadorASTRA(cliente, self.gerenciador.registro_ferramentas,
                                     self.gerenciador.executor_ferramentas)
        conversa = ProcessadorConversa(planejador=planejador, ia_habilitada=True)
        assistente = AssistenteVoz(lambda: '', lambda _: None,
            executar=self.gerenciador.executar,
            aguardando_confirmacao=self.gerenciador.confirmacao.aguardando,
            conversar=conversa.responder, interpretar_intencao=self.interpretar)
        with patch('webbrowser.open', return_value=True) as abrir:
            saida = assistente.processar('astra abra o navegador e pesquise sobre godot')
            self.assertIn('sim ou não', saida.fala)
            abrir.assert_not_called()
            saida = assistente.processar('sim')
            abrir.assert_called_once_with('https://www.google.com/search?q=godot')
            self.assertIn('Pesquisando godot', saida.fala)
        cliente.gerar_resposta.assert_not_called()

    def test_composto_transcrito_com_erro_passa_por_interpretacao(self):
        self.interpretar.return_value = Esclarecimento('Confirma?', 'abrir o navegador e pesquisar sobre Godot')
        pedido = 'abrir ou navegador e pesquisar sobe go dutch'
        saida = self.assistente.processar('astra ' + pedido)
        self.assertIn('Confirma?', saida.fala)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()
        self.assistente.processar('sim')
        self.conversar.assert_called_once_with('abrir o navegador e pesquisar sobre Godot')

    def test_correcao_para_composto_com_criacao_aguarda_nome(self):
        self.interpretar.return_value = Esclarecimento('Confirma?', 'abra o navegador e crie uma pasta')
        self.assistente.processar('astra abrir ou navegador e pesquisar sobe go dutch')
        saida = self.assistente.processar('sim')
        self.assertIn('Qual nome', saida.fala)
        self.conversar.assert_not_called()
        self.executar.assert_not_called()

    def test_planeje_continua_opcional(self):
        self.assistente.processar('astra planeje abrir o navegador')
        self.executar.assert_not_called()
        self.conversar.assert_called_once_with('planeje abrir o navegador')

if __name__ == '__main__':
    unittest.main()
