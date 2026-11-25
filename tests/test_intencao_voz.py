import json
import unittest
from unittest.mock import Mock, patch

from ia.interpretador_intencao import InterpretadorIntencao, FORMATO_INTENCAO, EXEMPLOS_INTENCAO
from ia.cliente_ollama import ClienteOllama
from voz.voz_principal import AssistenteVoz
from voz.comandos_voz import ResultadoComando, StatusComando
from voz.intencao_voz import esclarecer_intencao


class TestInterpretador(unittest.TestCase):
    def setUp(self):
        self.cliente = Mock()
        self.interpretador = InterpretadorIntencao(self.cliente)

    def retornar(self, frase):
        self.cliente.gerar_resposta.return_value = json.dumps(dict(frase=frase))

    def test_pedido_claro_preservado(self):
        self.retornar('o que e agua')
        self.assertEqual(self.interpretador.interpretar('O que é água?').interpretacao, 'O que é água?')
        args, kwargs = self.cliente.gerar_resposta.call_args
        self.assertEqual(args[1], 'O que é água?')
        self.assertEqual(kwargs['formato'], FORMATO_INTENCAO)

    def test_novo_termo_sem_dicionario(self):
        self.retornar('O que é Kubernetes?')
        self.assertEqual(self.interpretador.interpretar('O que é cubernetes?').interpretacao, 'O que é Kubernetes?')

    def test_reescrita_que_remove_negacao_rejeitada(self):
        self.retornar('Apague relatório')
        self.assertEqual(self.interpretador.interpretar('Não apague relatório').decisao, 'esclarecer')

    def test_perguntas_claras_novas(self):
        for frase in ('o que e Python', 'o que e agua', 'qual a altura do Everest'):
            with self.subTest(frase=frase):
                self.retornar(frase)
                self.assertEqual(self.interpretador.interpretar(frase).decisao, 'clara')

    def test_correcao_de_verbo_e_assunto(self):
        self.retornar('pesquise sobre árvores')
        resultado = self.interpretador.interpretar('pesquize sobre arvores')
        self.assertEqual(resultado.decisao, 'corrigir')
        self.assertEqual(resultado.interpretacao, 'pesquise sobre árvores')

    def test_incompleto(self):
        self.retornar('')
        self.assertEqual(self.interpretador.interpretar('Destruir').decisao, 'esclarecer')

    def test_variacao_apenas_ortografica_preserva_original(self):
        self.retornar('O que é água?')
        resultado = self.interpretador.interpretar('o que e agua')
        self.assertEqual(resultado.decisao, 'clara')
        self.assertEqual(resultado.interpretacao, 'o que e agua')

    def test_json_invalido(self):
        for bruto in ('texto', '[]', '{}', '{"decisao":"esclarecer","interpretacao":""}', '{"frase":42}', '{"frase":null}', '{"frase":"a","ferramentas":[]}'):
            with self.subTest(bruto=bruto):
                self.cliente.gerar_resposta.return_value = bruto
                self.assertEqual(self.interpretador.interpretar('pedido').decisao, 'esclarecer')

    def test_rejeita_metatexto_observado_no_qwen(self):
        for frase in ("O texto faz sentido e o objetivo é compreensível", "A frase 'o que é água' faz sentido e o objetivo é compreensível?"):
            self.retornar(frase)
            self.assertEqual(self.interpretador.interpretar('o que é água').decisao, 'esclarecer')

    def test_segunda_tentativa_recupera_pedido_claro(self):
        self.cliente.gerar_resposta.side_effect = [
            '{"frase":"O texto faz sentido"}',
            '{"frase":"o que é água"}']
        resultado = self.interpretador.interpretar('o que é água')
        self.assertEqual(resultado.interpretacao, 'o que é água')
        self.assertEqual(self.cliente.gerar_resposta.call_count, 2)

    def test_correcao_que_muda_negacao_bloqueada(self):
        self.retornar('apague relatório')
        self.assertEqual(self.interpretador.interpretar('não apague relatório').decisao, 'esclarecer')

    def test_segunda_revisao_corrige_termo_copiado(self):
        self.cliente.gerar_resposta.side_effect = [
            '{"frase":"o que é cubernetes"}',
            '{"frase":"o que é Kubernetes?"}',
        ]
        resultado = self.interpretador.interpretar('o que e cubernetes')
        self.assertEqual(resultado.decisao, 'corrigir')
        self.assertEqual(resultado.interpretacao, 'o que é Kubernetes?')

    def test_segunda_revisao_recupera_verbo(self):
        self.cliente.gerar_resposta.side_effect = [
            '{"frase":""}', '{"frase":"pesquise sobre árvores"}',
        ]
        resultado = self.interpretador.interpretar('pesquize sobre arvores')
        self.assertEqual(resultado.decisao, 'corrigir')
        self.assertEqual(resultado.interpretacao, 'pesquise sobre árvores')

    def test_decisoes_contraditorias_nao_autorizam_pedido(self):
        self.cliente.gerar_resposta.side_effect = [
            '{"frase":""}', '{"frase":"destruir"}',
        ]
        self.assertEqual(self.interpretador.interpretar('destruir').decisao, 'esclarecer')

    def test_cliente_envia_formatos_distintos(self):
        resposta = Mock()
        resposta.read.return_value = b'{"message":{"content":"{}"}}'
        with patch('ia.cliente_ollama.urlopen') as abrir:
            abrir.return_value.__enter__.return_value = resposta
            cliente = ClienteOllama()
            cliente.gerar_resposta('sistema', 'pedido', formato=FORMATO_INTENCAO, exemplos=EXEMPLOS_INTENCAO)
            payload = json.loads(abrir.call_args.args[0].data)
            self.assertEqual(payload['format'], 'json')
            self.assertEqual(payload['messages'][-1], {'role': 'user', 'content': 'pedido'})
            self.assertEqual(payload['messages'][1:-1], [
                {'role': papel, 'content': texto}
                for entrada, saida in EXEMPLOS_INTENCAO
                for papel, texto in [('user', entrada), ('assistant', saida)]
            ])
            cliente.gerar_resposta('sistema', 'pedido')
            payload = json.loads(abrir.call_args.args[0].data)
            self.assertIn('acao', payload['format']['properties'])
            self.assertEqual(len(payload['messages']), 2)


class TestIntencaoVoz(unittest.TestCase):
    def setUp(self):
        env = patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})
        env.start()
        self.addCleanup(env.stop)
        self.cliente = Mock()
        self.interpretador = InterpretadorIntencao(self.cliente)
        self.executar = Mock(return_value=ResultadoComando(StatusComando.NAO_ENCONTRADO))
        self.conversar = Mock(return_value='Resposta simulada.')
        self.analisar = Mock(side_effect=lambda texto: esclarecer_intencao(texto, self.interpretador))
        self.assistente = AssistenteVoz(lambda: '', lambda _: None,
            executar=self.executar, aguardando_confirmacao=lambda: False,
            conversar=self.conversar, interpretar_intencao=self.analisar)

    def retornar(self, frase):
        self.cliente.gerar_resposta.return_value = json.dumps(dict(frase=frase))

    def test_corrigir_e_confirmar_sem_ativacao(self):
        self.retornar('O que é Kubernetes?')
        saida = self.assistente.processar('Astra, o que é cubernetes?')
        self.assertIn('Kubernetes', saida.fala)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()
        self.assistente.processar('sim')
        self.conversar.assert_called_once_with('O que é Kubernetes?')
        self.executar.assert_not_called()
        self.analisar.assert_called_once()

    def test_correcoes_de_acao_passam_pelo_planejador(self):
        self.retornar('pesquise sobre árvores')
        self.assistente.processar('Astra, esquise sobre árvores')
        self.executar.assert_not_called()
        self.assistente.processar('sim')
        self.conversar.assert_called_once_with('pesquise sobre árvores')
        self.executar.assert_not_called()

    def test_negacao_cancela(self):
        self.retornar('pesquise sobre árvores')
        self.assistente.processar('Astra, esquise sobre árvores')
        self.assertTrue(self.assistente.processar('não').aguardar_comando)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()

    def test_expiracao(self):
        self.retornar('pesquise sobre árvores')
        self.assistente.processar('Astra, esquise sobre árvores')
        with patch('voz.voz_principal.time.monotonic', return_value=10**12):
            self.assertIn('prazo', self.assistente.processar('sim').fala)
        self.conversar.assert_not_called()

    def test_resposta_ambigua_nao_confirma(self):
        self.retornar('pesquise sobre árvores')
        self.assistente.processar('Astra, esquise sobre árvores')
        self.assistente.processar('sim não')
        self.assistente.processar('abra o navegador')
        self.assertIsNone(self.assistente.processar('sim'))
        self.conversar.assert_not_called()
        self.executar.assert_not_called()

    def test_esclarecer(self):
        self.retornar('')
        self.assertTrue(self.assistente.processar('Astra, destruir').aguardar_comando)
        self.executar.assert_not_called()
        self.conversar.assert_not_called()

    def test_pergunta_com_palavra_chave_nao_executa_legado(self):
        frase = 'como abrir o navegador'
        self.retornar(frase)
        self.assistente.processar('Astra, ' + frase)
        self.conversar.assert_called_once_with(frase)
        self.executar.assert_not_called()

    def test_comando_tradicional_sem_ollama(self):
        self.executar.return_value = ResultadoComando(StatusComando.SUCESSO)
        self.assistente.processar('Astra, abra o navegador')
        self.executar.assert_called_once_with('abra o navegador')
        self.analisar.assert_not_called()

    def test_ia_desativada_preserva_comando(self):
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '0'}):
            self.assistente.processar('Astra, abra o navegador')
        self.executar.assert_called_once_with('abra o navegador')
        self.analisar.assert_not_called()

    def test_ollama_indisponivel_nao_executa(self):
        self.cliente.gerar_resposta.side_effect = RuntimeError('offline')
        self.assistente.processar('Astra, como abrir o navegador')
        self.executar.assert_not_called()
        self.conversar.assert_not_called()

    def test_metatexto_nao_vira_pedido_confirmavel(self):
        self.retornar('O texto faz sentido e o objetivo é compreensível')
        saida = self.assistente.processar('Astra, o que é linucs')
        self.assertIn('repetir', saida.fala)
        self.assertIsNone(self.assistente._intencao_pendente)
        self.conversar.assert_not_called()
        self.executar.assert_not_called()

    def test_novo_chamado_cancela_sugestao_anterior(self):
        self.retornar('pesquise sobre árvores')
        self.assistente.processar('Astra, esquise sobre árvores')
        self.retornar('o que e agua')
        self.assistente.processar('Astra, o que é água')
        self.assertIsNone(self.assistente._intencao_pendente)
        self.conversar.assert_called_once_with('o que e agua')

    def test_confirmacao_seguranca_prioritaria(self):
        self.assistente._aguardando_confirmacao = lambda: True
        self.assistente.processar('sim')
        self.executar.assert_called_once_with('sim')
        self.analisar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
