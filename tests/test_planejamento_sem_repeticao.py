"""Composição explícita e proteção de ferramentas concluídas."""
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from ferramentas import RegistroFerramentas
from ferramentas.modelos import Ferramenta
from ia.escopo_ferramentas import ferramentas_do_pedido, sequencia_explicita
from ia.planejador import PlanejadorASTRA
from voz.comandos_voz import GerenciadorComandos
from voz.processador_linguagem import ProcessadorConversa
from voz.voz_principal import AssistenteVoz


class PlanejamentoSemRepeticao(unittest.TestCase):
    def setUp(self):
        self.registro = RegistroFerramentas()
        for nome in ('abrir_navegador', 'abrir_bloco_notas', 'ver_hora', 'listar_arquivos', 'ler_tela', 'pesquisar'):
            self.registro.registrar(Ferramenta(nome=nome, descricao=nome, categoria='teste'))
        self.modelo = Mock()
        self.executor = Mock(spec=['executar'])
        self.executor.executar.return_value = {'status':'sucesso','executado':True,'resposta':'OK'}
        self.p = PlanejadorASTRA(self.modelo, self.registro, self.executor)

    def test_sequencia_tres_acoes_ordenadas(self):
        pedido = 'abra o navegador e depois abra o bloco de notas e diga as horas'
        r = self.p.processar(pedido)
        self.assertEqual(r['status'], 'etapas_executadas')
        self.assertEqual([c.args[0] for c in self.executor.executar.call_args_list], ['abrir_navegador','abrir_bloco_notas','ver_hora'])
        self.assertTrue(all(c.kwargs['confirmado'] is False for c in self.executor.executar.call_args_list))
        self.modelo.gerar_resposta.assert_not_called()

    def test_falha_interrompe_sequencia(self):
        self.executor.executar.side_effect = [{'status':'erro','mensagem':'Falhou'}]
        r = self.p.processar('abra o navegador e diga as horas')
        self.assertEqual(r['status'], 'erro_na_etapa')
        self.assertFalse(r['concluido'])
        self.executor.executar.assert_called_once()

    def test_preflight_ferramenta_desabilitada_ou_sensivel(self):
        original = self.registro.obter('ver_hora')
        for f in (replace(original, disponivel_para_ia=False), replace(original, requer_confirmacao=True)):
            self.registro._ferramentas['ver_hora'] = f
            self.assertEqual(self.p.processar('abra o navegador e diga as horas')['status'], 'ferramenta_bloqueada')
            self.executor.executar.assert_not_called()

    def test_repeticao_explicita_bloqueada(self):
        self.assertEqual(self.p.processar('abra o navegador e abra o navegador')['status'], 'ciclo_detectado')
        self.executor.executar.assert_not_called()

    def test_perguntas_e_conteudo_literal_nao_ampliam_escopo(self):
        for pedido in ('como abrir o navegador e diga as horas', 'não abra o navegador e diga as horas', 'pesquise sobre abrir o navegador e diga as horas', 'crie uma pasta chamada abra o navegador e diga as horas'):
            self.assertIsNone(sequencia_explicita(pedido))
            self.assertNotIn('ver_hora', ferramentas_do_pedido(pedido))

    def test_ocr_nao_pode_repetir_com_outro_argumento(self):
        self.modelo.gerar_resposta.side_effect = [json.dumps({'acao':'executar','ferramentas':[{'nome':'ler_tela','argumentos':{'parametro':v}}]}) for v in ('','outra captura')]
        r = self.p.processar('explique a tela')
        self.assertFalse(r['concluido'])
        self.executor.executar.assert_called_once()
        contexto = json.loads(self.modelo.gerar_resposta.call_args.args[1])
        self.assertEqual(contexto['catalogo_autorizado'], [])
        self.assertEqual(contexto['ferramentas_concluidas'], ['ler_tela'])

    def test_busca_generica_nao_volta_ao_modelo(self):
        self.modelo.gerar_resposta.return_value = '{"acao":"executar","ferramentas":[{"nome":"pesquisar","argumentos":{"parametro":"clima"}}]}'
        r = self.p.processar('pesquise o clima')
        self.assertEqual(r['status'], 'etapas_executadas')
        self.executor.executar.assert_called_once()
        self.modelo.gerar_resposta.assert_called_once()

    def test_fluxo_voz_confirma_todas_acoes_fechadas(self):
        g = GerenciadorComandos()
        p = PlanejadorASTRA(Mock(), g.registro_ferramentas, g.executor_ferramentas)
        c = ProcessadorConversa(planejador=p, ia_habilitada=True)
        for resposta in ('sim','não'):
            a = AssistenteVoz(lambda:'', lambda _:None, executar=g.executar, aguardando_confirmacao=g.confirmacao.aguardando, conversar=c.responder, interpretar_intencao=lambda _:None, entrada_por_voz=True)
            with patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'1'}), patch('webbrowser.open', return_value=True) as abrir:
                saida = a.processar('astra abra o navegador e diga as horas')
                self.assertIn('sim ou não', saida.fala)
                abrir.assert_not_called()
                resultado = a.processar(resposta)
                if resposta == 'sim':
                    abrir.assert_called_once()
                    self.assertIn('Agora são', resultado.fala)
                else:
                    abrir.assert_not_called()

    def test_sequencia_clara_rejeitada_pelo_qwen_pede_confirmacao(self):
        from voz.intencao_voz import Esclarecimento
        pedido = 'abra o navegador e depois abra o bloco de notas e diga as horas'
        for voz in (False, True):
            for resposta in ('sim', 'não'):
                with self.subTest(voz=voz, resposta=resposta):
                    self.executor.reset_mock()
                    self.executor.executar.side_effect = [
                        {'status':'sucesso','resposta':'Abrindo navegador.'},
                        {'status':'sucesso','resposta':'Abrindo bloco de notas.'},
                        {'status':'sucesso','resposta':'Agora são 10 horas.'},
                    ]
                    conversa = ProcessadorConversa(planejador=self.p, ia_habilitada=True)
                    g = GerenciadorComandos()
                    a = AssistenteVoz(lambda:'', lambda _:None, executar=g.executar,
                        aguardando_confirmacao=g.confirmacao.aguardando, conversar=conversa.responder,
                        interpretar_intencao=lambda _:Esclarecimento('Repita.'), entrada_por_voz=voz)
                    with patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'1'}):
                        self.assertIn('sim ou não', a.processar('astra ' + pedido).fala)
                        self.executor.executar.assert_not_called()
                        saida = a.processar(resposta)
                        if resposta == 'sim':
                            self.assertEqual([c.args[0] for c in self.executor.executar.call_args_list],
                                ['abrir_navegador','abrir_bloco_notas','ver_hora'])
                            self.assertIn('Agora são 10 horas', saida.fala)
                        else:
                            self.executor.executar.assert_not_called()
        self.modelo.gerar_resposta.assert_not_called()

    def test_fallback_nao_confirma_pedido_incompleto_ou_negado(self):
        from voz.intencao_voz import Esclarecimento
        g = GerenciadorComandos()
        c = Mock()
        for pedido in ('abra o navegador e exclua o arquivo teste', 'não abra o navegador e diga as horas', 'abra o navegador e abra o navegador'):
            a = AssistenteVoz(lambda:'', lambda _:None, executar=g.executar,
                aguardando_confirmacao=g.confirmacao.aguardando, conversar=c,
                interpretar_intencao=lambda _:Esclarecimento('Repita.'))
            with patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'1'}):
                self.assertEqual(a.processar('astra ' + pedido).fala, 'Repita.')
                self.assertIsNone(a._intencao_pendente)
        c.assert_not_called()

    def test_listagem_e_horario_preservam_as_duas_respostas(self):
        self.executor.executar.side_effect = [
            {'status':'sucesso','resposta':'Tenho 13 itens. ' + 'Arquivo. '*30},
            {'status':'sucesso','resposta':'Agora são 10 horas.'},
        ]
        conversa = ProcessadorConversa(planejador=self.p, ia_habilitada=True)
        fala = conversa.responder('liste os arquivos e diga as horas')
        self.assertIn('Tenho 13 itens', fala)
        self.assertTrue(fala.endswith('Agora são 10 horas.'))
        self.assertEqual([c.args[0] for c in self.executor.executar.call_args_list], ['listar_arquivos','ver_hora'])

if __name__ == '__main__':
    unittest.main()
