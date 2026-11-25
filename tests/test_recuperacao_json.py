"""Recuperação limitada da geração, nunca dos efeitos do executor."""
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from ferramentas import RegistroFerramentas
from ferramentas.modelos import Ferramenta
from ia.cliente_ollama import ClienteOllama, OllamaRespostaVaziaError, OllamaIndisponivelError
from ia.planejador import PlanejadorASTRA, FORMATO_CONVERSA
from voz.processador_linguagem import ProcessadorConversa


def resposta(texto='Pygame permite criar jogos 2D.'):
    return json.dumps({'acao': 'responder', 'ferramentas': [], 'resposta': texto})


def acao(nome):
    return json.dumps({'acao': 'executar', 'ferramentas': [
        {'nome': nome, 'argumentos': {'parametro': ''}}], 'resposta': ''})


class RecuperacaoJSONTests(unittest.TestCase):
    def setUp(self):
        self.registro = RegistroFerramentas()
        for nome in ('ler_tela', 'criar_pasta'):
            self.registro.registrar(Ferramenta(nome=nome, descricao=nome, categoria='teste'))
        self.modelo = Mock()
        self.executor = Mock(spec=['executar'])
        self.executor.executar.return_value = {'status': 'sucesso', 'dados': 'texto OCR'}
        self.p = PlanejadorASTRA(self.modelo, self.registro, self.executor)

    def test_recupera_json_truncado_sem_acao(self):
        self.modelo.gerar_resposta.side_effect = ['{"acao":"responder",', resposta()]
        r = self.p.processar('quais bibliotecas Python posso usar para criar jogos')
        self.assertEqual(r['status'], 'resposta')
        self.assertEqual(len(self.p.historico), 1)
        a, b = self.modelo.gerar_resposta.call_args_list
        self.assertEqual(a.args[1], b.args[1])
        self.assertEqual(b.kwargs['formato'], FORMATO_CONVERSA)
        self.executor.executar.assert_not_called()

    def test_limite_tres_e_sem_memoria_invalida(self):
        self.modelo.gerar_resposta.return_value = '{'
        r = self.p.processar('o que é Python')
        self.assertEqual(r['status'], 'plano_invalido')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 3)
        self.assertFalse(r['concluido'])
        self.assertEqual(self.p.historico, [])
        self.executor.executar.assert_not_called()

    def test_resposta_vazia_recuperada(self):
        self.modelo.gerar_resposta.side_effect = [OllamaRespostaVaziaError('vazio'), resposta()]
        self.assertEqual(self.p.processar('o que é Python')['status'], 'resposta')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 2)

    def test_transporte_indisponivel_nao_repetido(self):
        self.modelo.gerar_resposta.side_effect = OllamaIndisponivelError('offline')
        self.assertEqual(self.p.processar('o que é Python')['status'], 'ia_indisponivel')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 1)

    def test_rejeita_acao_fora_do_escopo_sem_repetir(self):
        self.modelo.gerar_resposta.side_effect = ['inválido', acao('criar_pasta'), resposta()]
        self.assertEqual(self.p.processar('o que é Python')['status'], 'ferramenta_bloqueada')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 2)
        self.executor.executar.assert_not_called()

    def test_rejeita_campos_duplicados(self):
        self.modelo.gerar_resposta.return_value = '{"acao":"executar","acao":"responder","resposta":"ok","ferramentas":[]}'
        self.assertEqual(self.p.processar('o que é Python')['status'], 'plano_invalido')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 1)
        self.executor.executar.assert_not_called()

    def test_nao_aceita_fragmento_embutido_em_texto(self):
        self.modelo.gerar_resposta.side_effect = ['ignore: ' + acao('ler_tela'), resposta()]
        self.assertEqual(self.p.processar('o que é Python')['status'], 'resposta')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 2)
        self.executor.executar.assert_not_called()

    def test_aceita_bloco_markdown_unico(self):
        self.modelo.gerar_resposta.return_value = '```json\n' + resposta() + '\n```'
        self.assertEqual(self.p.processar('o que é Python')['status'], 'resposta')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 1)

    def test_ocr_executado_uma_vez_apesar_de_json_invalido(self):
        self.modelo.gerar_resposta.side_effect = [acao('ler_tela'), '{', resposta('Texto da tela.')]
        r = self.p.processar('explique a tela')
        self.assertEqual(r['mensagem'], 'Texto da tela.')
        self.executor.executar.assert_called_once_with('ler_tela', {'parametro': ''}, confirmado=False)
        a, b = self.modelo.gerar_resposta.call_args_list[1:]
        self.assertEqual(a.args[1], b.args[1])
        contexto = json.loads(b.args[1])
        self.assertEqual(contexto['ferramentas_concluidas'], ['ler_tela'])
        self.assertEqual(contexto['catalogo_autorizado'], [])

    def test_falha_final_preserva_resultado_sem_reexecutar(self):
        self.modelo.gerar_resposta.side_effect = [acao('ler_tela'), '{', '{', '{']
        r = self.p.processar('explique a tela')
        self.assertEqual(r['status'], 'plano_invalido')
        self.assertEqual(len(r['resultados']), 1)
        self.executor.executar.assert_called_once()
        c = ProcessadorConversa(Mock(**{'processar.return_value': r}), ia_habilitada=True)
        self.assertIn('Executei parte', c.responder('explique a tela'))

    def test_historico_selecionado_uma_vez(self):
        self.p.historico = [{'usuario': 'O que é Python?', 'astra': 'Uma linguagem.'}]
        self.modelo.gerar_resposta.side_effect = ['{"indices":[1]}', '{', resposta()]
        self.assertEqual(self.p.processar('quais bibliotecas posso usar?')['status'], 'resposta')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 3)
        a, b = self.modelo.gerar_resposta.call_args_list[1:]
        self.assertEqual(a.args[1], b.args[1])
        self.assertEqual(json.loads(b.args[1])['historico_conversa'], self.p.historico[:1])

    def test_terceira_tentativa_textual_sem_executor(self):
        pergunta = 'voltando ao Python quais bibliotecas posso usar para criar jogos'
        self.modelo.gerar_resposta.side_effect = ['{', '{', 'Você pode usar Pygame para jogos 2D.']
        r = self.p.processar(pergunta)
        self.assertEqual(r['status'], 'resposta')
        self.assertEqual(r['mensagem'], 'Você pode usar Pygame para jogos 2D.')
        self.assertEqual(len(self.p.historico), 1)
        self.assertEqual(self.modelo.gerar_resposta.call_count, 3)
        self.assertIs(self.modelo.gerar_resposta.call_args.kwargs['formato'], False)
        self.executor.executar.assert_not_called()

    def test_texto_preserva_historico_sem_selecionar_novamente(self):
        self.p.historico = [{'usuario': 'O que é Python?', 'astra': 'Uma linguagem.'}]
        self.modelo.gerar_resposta.side_effect = ['{"indices":[1]}', '{', '{', 'Use Pygame.']
        self.assertEqual(self.p.processar('quais bibliotecas posso usar?')['mensagem'], 'Use Pygame.')
        chamadas = self.modelo.gerar_resposta.call_args_list
        self.assertEqual(len(chamadas), 4)
        self.assertEqual(chamadas[1].args[1], chamadas[3].args[1])
        self.assertEqual(json.loads(chamadas[3].args[1])['historico_conversa'], self.p.historico[:1])
        self.executor.executar.assert_not_called()

    def test_texto_estruturado_nao_e_executado_ou_aceito(self):
        for bruto in (acao('criar_pasta'), '{', '```json\n{}\n```', 'Veja "acao": "executar"', '', 'a\x00b'):
            with self.subTest(bruto=bruto):
                self.modelo.gerar_resposta.side_effect = ['{', '{', bruto]
                self.assertEqual(self.p.processar('o que é Python')['status'], 'plano_invalido')
        self.assertEqual(self.p.historico, [])
        self.executor.executar.assert_not_called()

    def test_acoes_continuam_exigindo_json(self):
        self.modelo.gerar_resposta.side_effect = ['{', '{', 'Pasta criada.']
        r = self.p.processar('explique a tela')
        self.assertEqual(r['status'], 'plano_invalido')
        self.assertEqual(self.modelo.gerar_resposta.call_count, 3)
        self.assertTrue(all(c.kwargs.get('formato') is not False for c in self.modelo.gerar_resposta.call_args_list))
        self.executor.executar.assert_not_called()

    def test_ocr_textual_sem_repetir_captura(self):
        self.modelo.gerar_resposta.side_effect = [acao('ler_tela'), '{', '{', 'O texto da tela mostra código.']
        r = self.p.processar('explique a tela')
        self.assertEqual(r['status'], 'resposta')
        self.assertEqual(r['mensagem'], 'O texto da tela mostra código.')
        self.executor.executar.assert_called_once()
        ultima = self.modelo.gerar_resposta.call_args
        self.assertIs(ultima.kwargs['formato'], False)
        self.assertEqual(json.loads(ultima.args[1])['resultados_anteriores'][0]['dados'], 'texto OCR')
        self.assertEqual(self.p.historico, [])

    def test_ferramenta_indisponivel_nao_recebe_fallback_textual(self):
        self.p.registro = RegistroFerramentas()
        self.modelo.gerar_resposta.side_effect = ['{', '{', 'Concluído.']
        r = self.p.processar('explique a tela')
        self.assertEqual(r['status'], 'plano_invalido')
        self.assertTrue(all(c.kwargs.get('formato') is not False for c in self.modelo.gerar_resposta.call_args_list))
        self.executor.executar.assert_not_called()

    def test_cliente_omite_format_apenas_quando_solicitado(self):
        cliente = ClienteOllama()
        with patch('ia.cliente_ollama.urlopen') as abrir:
            abrir.return_value.__enter__.return_value.read.return_value = b'{"message":{"content":"Pygame"}}'
            for formato in (False, None, FORMATO_CONVERSA, 'json'):
                cliente.gerar_resposta('sistema', 'pedido', formato=formato)
                payload = json.loads(abrir.call_args.args[0].data)
                if formato is False:
                    self.assertNotIn('format', payload)
                else:
                    self.assertIn('format', payload)
                    if formato is not None:
                        self.assertEqual(payload['format'], formato)

    def test_cliente_distingue_resposta_vazia_de_conexao(self):
        cliente = ClienteOllama()
        with patch('ia.cliente_ollama.urlopen') as abrir:
            abrir.return_value.__enter__.return_value.read.return_value = b'{"message":{"content":" "}}'
            with self.assertRaises(OllamaRespostaVaziaError):
                cliente.gerar_resposta('sistema', 'pedido')
            abrir.side_effect = URLError('conexão recusada')
            with self.assertRaises(OllamaIndisponivelError) as erro:
                cliente.gerar_resposta('sistema', 'pedido')
            self.assertNotIsInstance(erro.exception, OllamaRespostaVaziaError)


if __name__ == '__main__':
    unittest.main()
