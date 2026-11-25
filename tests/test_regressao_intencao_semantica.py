import json
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

from ia.interpretador_intencao import InterpretadorIntencao
from ia.planejador import PlanejadorASTRA
from voz.comandos_voz import GerenciadorComandos
from voz.intencao_voz import esclarecer_intencao
from voz.processador_linguagem import ProcessadorConversa
from voz.voz_principal import AssistenteVoz


class RegressaoIntencaoTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.gerenciador = GerenciadorComandos()
        self.modelo = Mock()
        self.planejador = PlanejadorASTRA(self.modelo, self.gerenciador.registro_ferramentas,
                                          self.gerenciador.executor_ferramentas)
        self.conversa = ProcessadorConversa(planejador=self.planejador, ia_habilitada=True)
        self.modelo_intencao = Mock()
        self.interpretador = InterpretadorIntencao(self.modelo_intencao)
        self.assistente = AssistenteVoz(lambda: '', lambda _: None,
            executar=self.gerenciador.executar,
            aguardando_confirmacao=self.gerenciador.confirmacao.aguardando,
            conversar=self.conversa.responder,
            interpretar_intencao=lambda texto: esclarecer_intencao(texto, self.interpretador))

    def test_pesquisa_confirmada_uma_vez(self):
        self.modelo_intencao.gerar_resposta.return_value = '{"frase":"Pesquise sobre árvores"}'
        with patch('webbrowser.open', return_value=True) as abrir:
            pergunta = self.assistente.processar('astra pesquize sobre árvores')
            self.assertIn('Você quis dizer', pergunta.fala)
            abrir.assert_not_called()
            resposta = self.assistente.processar('sim')
            abrir.assert_called_once_with('https://www.google.com/search?q=%C3%A1rvores')
            self.assertIn('Pesquisando árvores', resposta.fala)
        self.modelo.gerar_resposta.assert_not_called()

    def test_pesquisa_negada_nao_abre(self):
        self.modelo_intencao.gerar_resposta.return_value = '{"frase":"Pesquise sobre árvores"}'
        with patch('webbrowser.open') as abrir:
            self.assistente.processar('astra pesquize sobre árvores')
            self.assistente.processar('não')
            abrir.assert_not_called()
        self.modelo.gerar_resposta.assert_not_called()

    def test_falha_navegador_nao_e_sucesso(self):
        with patch('webbrowser.open', return_value=False) as abrir:
            r = self.planejador.processar('Pesquise sobre árvores')
            self.assertEqual(r['status'], 'erro_na_etapa')
            self.assertFalse(r['concluido'])
            abrir.assert_called_once()
        self.modelo.gerar_resposta.assert_not_called()

    def test_fragmento_copiado_nao_chega_ao_planejador(self):
        self.modelo_intencao.gerar_resposta.return_value = '{"frase":"destruir"}'
        with patch('webbrowser.open') as abrir:
            saida = self.assistente.processar('astra destruir')
            self.assertTrue(saida.aguardar_comando)
            abrir.assert_not_called()
        self.modelo.gerar_resposta.assert_not_called()

    def test_pergunta_independente_sem_historico(self):
        self.planejador.historico = [{'usuario':'O que é Linux?', 'astra':'Linux é um núcleo.'}]
        self.modelo.gerar_resposta.side_effect = ['{"indices":[]}', '{"acao":"responder","ferramentas":[],"resposta":"Água é H2O."}']
        self.planejador.processar('O que é água?')
        contexto = json.loads(self.modelo.gerar_resposta.call_args.args[1])
        self.assertEqual(contexto['historico_conversa'], [])
        self.assertEqual(contexto['catalogo_autorizado'], [])

    def test_referencia_explicita_preserva_historico(self):
        self.planejador.historico = [{'usuario':'O que é Python?', 'astra':'Uma linguagem.'}]
        self.modelo.gerar_resposta.side_effect = ['{"indices":[1]}', '{"acao":"responder","ferramentas":[],"resposta":"É versátil."}']
        self.planejador.processar('Quais as vantagens dele?')
        contexto = json.loads(self.modelo.gerar_resposta.call_args.args[1])
        self.assertEqual(contexto['historico_conversa'][0]['usuario'], 'O que é Python?')

    def test_negacao_nao_despacha_pesquisa(self):
        self.modelo.gerar_resposta.return_value = '{"acao":"responder","ferramentas":[],"resposta":"Certo."}'
        with patch('webbrowser.open') as abrir:
            self.planejador.processar('não pesquise sobre árvores')
            abrir.assert_not_called()

    def test_ferramenta_desabilitada_nao_despacha(self):
        registro = self.gerenciador.registro_ferramentas
        registro._ferramentas['pesquisar'] = replace(registro.obter('pesquisar'), disponivel_para_ia=False)
        self.modelo.gerar_resposta.return_value = '{"acao":"responder","ferramentas":[],"resposta":"Não posso pesquisar."}'
        with patch('webbrowser.open') as abrir:
            self.planejador.processar('pesquise sobre árvores')
            abrir.assert_not_called()

if __name__ == '__main__':
    unittest.main()
