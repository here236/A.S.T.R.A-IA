"""Memória semântica com Ollama simulado e executor sem efeitos externos."""
import json
import unittest
from unittest.mock import Mock, patch

from ia.memoria_conversacional import LIMITE_HISTORICO, FORMATO_SELECAO, selecionar_historico
from ia.planejador import PlanejadorASTRA, FORMATO_CONVERSA
from voz.comandos_voz import GerenciadorComandos
from voz.intencao_voz import Esclarecimento
from voz.processador_linguagem import ProcessadorConversa
from voz.voz_principal import AssistenteVoz


def resposta(texto):
    return json.dumps({'acao': 'responder', 'ferramentas': [], 'resposta': texto})


def acao(nome):
    return json.dumps({'acao': 'executar', 'ferramentas': [{'nome': nome, 'argumentos': {'parametro': 'teste'}}], 'resposta': ''})


class MemoriaConversacionalTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})
        env.start(); self.addCleanup(env.stop)
        self.g = GerenciadorComandos()
        self.modelo = Mock()
        self.executor = Mock(spec=['executar'])
        self.p = PlanejadorASTRA(self.modelo, self.g.registro_ferramentas, self.executor)
        self.c = ProcessadorConversa(self.p, ia_habilitada=True)
        self.intencao = Mock(return_value=None)
        self.a = AssistenteVoz(lambda: '', lambda _: None, executar=self.g.executar,
                aguardando_confirmacao=self.g.confirmacao.aguardando,
                conversar=self.c.responder, interpretar_intencao=self.intencao)
        self.p.historico = [{'usuario':'O que é Python?', 'astra':'Uma linguagem.'},
                            {'usuario':'O que é Godot?', 'astra':'Um motor de jogos.'}]

    def contexto(self):
        return json.loads(self.modelo.gerar_resposta.call_args.args[1])

    def test_selecao_semantica_de_assunto_mais_antigo(self):
        self.modelo.gerar_resposta.side_effect = ['{"indices":[1]}', resposta('Python serve para automação.')]
        self.assertEqual(self.c.responder('Quais bibliotecas de automação?'), 'Python serve para automação.')
        self.assertEqual(self.contexto()['historico_conversa'], [self.p.historico[0]])
        self.assertEqual(self.contexto()['solicitacao_original'], 'Quais bibliotecas de automação?')
        self.assertEqual(self.contexto()['catalogo_autorizado'], [])
        self.executor.executar.assert_not_called()

    def test_assunto_independente_isolado(self):
        self.modelo.gerar_resposta.side_effect = ['{"indices":[]}', resposta('Santiago.')]
        self.assertEqual(self.c.responder('Qual a capital do Chile?'), 'Santiago.')
        self.assertEqual(self.contexto()['historico_conversa'], [])

    def test_comparacao_dois_assuntos(self):
        self.modelo.gerar_resposta.side_effect = ['{"indices":[2,1]}', resposta('São categorias diferentes.')]
        self.c.responder('Compare os dois assuntos.')
        self.assertEqual(self.contexto()['historico_conversa'], self.p.historico[:2])

    def test_selecao_invalidada_por_inteiro(self):
        for bruto in ('[]', '{}', '{"indices":[0]}', '{"indices":[true]}', '{"indices":[1,1]}',
                      '{"indices":[1,9]}', '{"indices":[1],"acao":"executar"}', '{"indices":["1"]}'):
            with self.subTest(bruto=bruto):
                self.modelo.gerar_resposta.return_value = bruto
                self.assertEqual(selecionar_historico(self.modelo, 'pedido', self.p.historico), [])

    def test_falha_seletor_continua_sem_historico(self):
        self.modelo.gerar_resposta.side_effect = [RuntimeError('falha'), resposta('Resposta isolada.')]
        self.assertEqual(self.c.responder('Pergunta nova'), 'Resposta isolada.')
        self.assertEqual(self.contexto()['historico_conversa'], [])

    def test_continuacao_fragmento_apos_intencao_inconclusiva(self):
        self.p.historico = [{'usuario':'Quero criar um jogo', 'astra':'2D ou 3D?'}]
        self.intencao.return_value = Esclarecimento('Pode repetir?')
        self.modelo.gerar_resposta.side_effect = ['{"indices":[1]}', resposta('Para 2D, use uma cena Node2D.')]
        self.assertIn('Node2D', self.a.processar('astra 2d').fala)
        self.assertEqual(self.contexto()['solicitacao_original'], '2d')
        self.assertEqual(self.modelo.gerar_resposta.call_args.kwargs['formato'], FORMATO_CONVERSA)
        self.executor.executar.assert_not_called()

    def test_fragmento_sem_referencia_mantem_esclarecimento(self):
        self.intencao.return_value = Esclarecimento('Pode repetir?')
        self.modelo.gerar_resposta.return_value = '{"indices":[]}'
        self.assertEqual(self.a.processar('astra baiten').fala, 'Pode repetir?')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 1)
        self.executor.executar.assert_not_called()

    def test_fragmento_nao_pode_acionar_ferramenta(self):
        self.intencao.return_value = Esclarecimento('Pode repetir?')
        self.modelo.gerar_resposta.side_effect = ['{"indices":[1]}', acao('criar_pasta')]
        self.assertEqual(self.a.processar('astra faça aquilo').fala, 'Pode repetir?')
        self.executor.executar.assert_not_called()
        self.assertEqual(len(self.p.historico), 2)

    def test_historico_nao_enviado_para_pedido_de_acao(self):
        self.modelo.gerar_resposta.return_value = acao('excluir')
        self.executor.executar.return_value = {'status':'confirmacao_necessaria', 'executado':False}
        self.assertEqual(self.p.processar('exclua teste')['status'], 'aguardando_confirmacao')
        self.assertEqual(self.contexto()['historico_conversa'], [])
        self.assertEqual(self.modelo.gerar_resposta.call_count, 1)
        self.assertFalse(self.executor.executar.call_args.kwargs['confirmado'])

    def test_resultado_ocr_nao_registrado_na_memoria_conversacional(self):
        self.modelo.gerar_resposta.side_effect = [acao('ler_tela'), resposta('Texto da tela.')]
        self.executor.executar.return_value = {'status':'sucesso', 'dados':'dado externo'}
        self.assertEqual(self.p.processar('explique a tela')['status'], 'resposta')
        self.assertEqual(len(self.p.historico), 2)
        self.assertEqual(self.contexto()['historico_conversa'], [])
        self.assertEqual(self.contexto()['resultados_anteriores'][0]['dados'], 'dado externo')

    def test_limite_e_limpeza_conversacional(self):
        for i in range(12):
            self.p._registrar_conversa('Pergunta ' + str(i), 'x'*1000)
        self.assertEqual(len(self.p.historico), LIMITE_HISTORICO)
        self.assertEqual(self.p.historico[0]['usuario'], 'Pergunta 6')
        self.assertEqual(len(self.p.historico[-1]['astra']), 700)
        with patch.object(self.g.memoria_operacional, 'limpar') as limpar:
            self.assertEqual(self.a.processar('astra limpar conversa').fala, 'Contexto da conversa limpo.')
            limpar.assert_not_called()
        self.assertEqual(self.p.historico, [])
        self.intencao.assert_not_called()
        self.modelo.gerar_resposta.assert_not_called()

    def test_limpar_contexto_preserva_semantica_anterior_de_limpar_ambas(self):
        with patch.object(self.g.memoria_operacional, 'limpar') as limpar:
            self.a.processar('astra limpar contexto')
            limpar.assert_called_once()
        self.assertEqual(self.p.historico, [])

    def test_historico_acao_legada_excluido_da_selecao(self):
        self.p.historico.append({'usuario':'crie uma pasta', 'astra':'Caminho externo.'})
        self.modelo.gerar_resposta.return_value = '{"indices":[1]}'
        self.assertEqual(selecionar_historico(self.modelo, 'continue', self.p.historico), [self.p.historico[0]])
        self.assertEqual(len(self.contexto()['trocas']), 2)
        self.assertEqual(self.modelo.gerar_resposta.call_args.kwargs['formato'], FORMATO_SELECAO)

    def test_consulta_operacional_nao_consulta_modelo(self):
        self.assertIn('Não tenho registro', self.a.processar('astra onde você salvou o último documento').fala)
        self.modelo.gerar_resposta.assert_not_called()
        self.intencao.assert_not_called()

    def test_ia_desabilitada_nao_recupera_contexto(self):
        self.c.ia_habilitada = False
        self.assertIsNone(self.c.responder_continuacao('continue'))
        self.modelo.gerar_resposta.assert_not_called()


if __name__ == '__main__':
    unittest.main()
