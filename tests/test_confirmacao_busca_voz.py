import json
import unittest
from unittest.mock import Mock, patch

from ia.interpretador_intencao import InterpretadorIntencao
from ia.planejador import PlanejadorASTRA
from voz.comandos_voz import GerenciadorComandos
from voz.intencao_voz import esclarecer_intencao
from voz.processador_linguagem import ProcessadorConversa
from voz.voz_principal import AssistenteVoz


class ConfirmacaoBuscaVozTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.g = GerenciadorComandos()
        self.modelo = Mock()
        self.interpretador = InterpretadorIntencao(self.modelo)
        self.planejador = PlanejadorASTRA(Mock(), self.g.registro_ferramentas,
                                         self.g.executor_ferramentas)
        self.conversa = ProcessadorConversa(planejador=self.planejador, ia_habilitada=True)

    def assistente(self, voz=True):
        return AssistenteVoz(lambda: '', lambda _: None, executar=self.g.executar,
            aguardando_confirmacao=self.g.confirmacao.aguardando,
            conversar=self.conversa.responder, entrada_por_voz=voz,
            interpretar_intencao=lambda texto: esclarecer_intencao(texto, self.interpretador))

    def modelo_copia(self, frase):
        self.modelo.gerar_resposta.return_value = json.dumps({'frase': frase})

    def test_modelo_nao_corrige_e_usuario_recusa(self):
        frase = 'abra o navegador e pesquise sobre o paito'
        self.modelo_copia(frase)
        a = self.assistente()
        with patch('webbrowser.open', return_value=True) as abrir:
            saida = a.processar('astra ' + frase)
            self.assertIn('paito', saida.fala)
            self.assertIn('sim ou não', saida.fala)
            self.assertEqual(self.modelo.gerar_resposta.call_count, 2)
            abrir.assert_not_called()
            cancelada = a.processar('não')
            self.assertIn('Tudo bem', cancelada.fala)
            self.assertTrue(cancelada.aguardar_comando)
            a.detector.ativar()  # rodar() ativa a janela após a fala
            abrir.assert_not_called()
            frase = 'abra o navegador e pesquise sobre python'
            self.modelo_copia(frase)
            a.processar(frase)
            abrir.assert_not_called()
            a.processar('sim')
            abrir.assert_called_once_with('https://www.google.com/search?q=python')

    def test_frase_correta_por_voz_confirma_uma_vez(self):
        frase = 'abrir o navegador e pesquisar sobre godot'
        self.modelo_copia(frase)
        a = self.assistente()
        with patch('webbrowser.open', return_value=True) as abrir:
            self.assertIn('sim ou não', a.processar('astra ' + frase).fala)
            abrir.assert_not_called()
            self.assertIn('Pesquisando', a.processar('SIM').fala)
            abrir.assert_called_once_with('https://www.google.com/search?q=godot')
            self.assertEqual(self.modelo.gerar_resposta.call_count, 2)

    def test_teclado_tambem_confirma_pesquisa_composta(self):
        frase = 'abra o navegador e pesquise sobre python'
        self.modelo_copia(frase)
        with patch('webbrowser.open', return_value=True) as abrir:
            a = self.assistente(False)
            self.assertIn('sim ou não', a.processar('astra ' + frase).fala)
            abrir.assert_not_called()
            a.processar('sim')
            abrir.assert_called_once_with('https://www.google.com/search?q=python')

    def test_teclado_cancelamento_nao_abre_navegador(self):
        frase = 'abra o navegador e pesquise sobre godot'
        self.modelo_copia(frase)
        with patch('webbrowser.open', return_value=True) as abrir:
            a = self.assistente(False)
            self.assertIn('sim ou não', a.processar('astra ' + frase).fala)
            self.assertIn('Tudo bem', a.processar('não').fala)
            abrir.assert_not_called()

    def test_teclado_correcao_nao_pede_confirmacao_dupla(self):
        self.modelo_copia('abra o navegador e pesquise sobre Python')
        a = self.assistente(False)
        with patch('webbrowser.open', return_value=True) as abrir:
            self.assertIn('Python', a.processar('astra abra o navegador e pesquise sobre paito').fala)
            abrir.assert_not_called()
            self.assertIn('Pesquisando', a.processar('sim').fala)
            abrir.assert_called_once_with('https://www.google.com/search?q=Python')

    def test_correcao_semantica_nao_exige_confirmacao_dupla(self):
        self.modelo_copia('abra o navegador e pesquise sobre Python')
        a = self.assistente()
        with patch('webbrowser.open', return_value=True) as abrir:
            saida = a.processar('astra abra o navegador e pesquise sobre paito')
            self.assertIn('Python', saida.fala)
            abrir.assert_not_called()
            a.processar('sim')
            abrir.assert_called_once_with('https://www.google.com/search?q=Python')
            self.assertEqual(self.modelo.gerar_resposta.call_count, 1)

    def test_comando_tradicional_nao_consulta_ia(self):
        with patch('webbrowser.open', return_value=True) as abrir:
            self.assistente().processar('astra abra o navegador')
            abrir.assert_called_once()
        self.modelo.gerar_resposta.assert_not_called()

    def test_sem_ia_nao_executa_composto(self):
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '0'}), patch('webbrowser.open') as abrir:
            saida = self.assistente().processar('astra abra o navegador e pesquise sobre python')
            self.assertIn('desabilitada', saida.fala)
            abrir.assert_not_called()
        self.modelo.gerar_resposta.assert_not_called()

    def test_nova_chamada_nao_confirma_pedido_antigo(self):
        frase = 'abra o navegador e pesquise sobre paito'
        self.modelo_copia(frase)
        a = self.assistente()
        with patch('webbrowser.open', return_value=True) as abrir:
            a.processar('astra ' + frase)
            self.modelo_copia('abra o navegador e pesquise sobre godot')
            a.processar('astra abra o navegador e pesquise sobre godot')
            abrir.assert_not_called()
            a.processar('sim')
            abrir.assert_called_once_with('https://www.google.com/search?q=godot')

if __name__ == '__main__':
    unittest.main()
