"""Regressões da etapa 6.4: Word/TXT reais e IA simulada."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from dataclasses import replace
from docx import Document
from arquivos.gerenciador_arquivos import gerenciador_arquivos
from configs import configuracoes_voz as cfg
from ia.conteudo_documento import gerar_resumo
from ia.plano_composto import plano_criacao_explicito
from ia.planejador import PlanejadorASTRA
from voz.comandos_voz import GerenciadorComandos
from voz.voz_principal import AssistenteVoz

TEXTO = 'Python é uma linguagem de programação. É útil para automação e análise de dados.'
PEDIDO = 'astra crie um documento chamado resumo python e escreva nele um resumo sobre Python'

class ConteudoDependenteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.g = GerenciadorComandos()
        for p in (patch.object(cfg, 'LOCAIS_ARQUIVOS', {'astra': str(self.base)}),
                  patch.object(cfg, 'LOCAL_PADRAO', 'astra'),
                  patch.object(gerenciador_arquivos, 'atual', None),
                  patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})):
            p.start(); self.addCleanup(p.stop)
        p = patch('voz.plano_pendente.gerar_resumo', return_value=TEXTO)
        self.gerar = p.start(); self.addCleanup(p.stop)
        self.conversar = Mock(return_value='Conversa.')
        self.a = AssistenteVoz(lambda: '', lambda _: None, executar=self.g.executar,
                aguardando_confirmacao=self.g.confirmacao.aguardando,
                conversar=self.conversar, interpretar_intencao=Mock(return_value=None))
    def fala(self, texto):
        r = self.a.processar(texto)
        return r.fala if r else ''
    def test_word_real_e_confirmacoes(self):
        self.assertIn('Confirma a etapa 1', self.fala(PEDIDO))
        self.assertEqual(list(self.base.iterdir()), [])
        self.gerar.assert_not_called()
        self.assertIn(TEXTO, self.fala('sim'))
        self.assertEqual(list(self.base.iterdir()), [])
        self.gerar.assert_called_once_with('python')
        r = self.fala('sim')
        self.assertIn('Resumo salvo e conferido', r)
        p = self.base/'resumo_python.docx'
        self.assertEqual([x.text for x in Document(p).paragraphs], [TEXTO])
        self.fala('sim')
        self.assertEqual([x.text for x in Document(p).paragraphs], [TEXTO])
    def test_previa_integral_no_terminal(self):
        texto = TEXTO * 4
        self.gerar.return_value = texto
        self.fala(PEDIDO)
        previa = self.fala('sim')
        with patch('voz.voz_principal.log') as log, patch('voz.voz_principal.time.sleep'):
            self.a._dizer(previa)
        self.assertIn(texto, log.call_args.args[0])
        self.assertIn('Diga sim ou não.', log.call_args.args[0])

    def test_txt_real(self):
        self.fala('astra crie um arquivo de texto chamado notas e depois escreva nele um resumo sobre Python')
        self.fala('sim'); self.assertIn('Resumo salvo e conferido', self.fala('sim'))
        self.assertEqual((self.base/'notas.txt').read_text(), TEXTO+'\n')
    def test_nome_pendente(self):
        self.assertIn('Qual nome', self.fala('astra crie um documento e escreva nele um resumo sobre Python'))
        self.assertIn('Confirma a etapa 1', self.fala('Minhas notas'))
        self.fala('sim'); self.fala('sim')
        self.assertTrue((self.base/'minhas_notas.docx').is_file())
    def test_cancelar_segunda(self):
        self.fala(PEDIDO); self.fala('sim')
        self.assertIn('Nenhuma etapa', self.fala('não'))
        self.assertEqual(list(self.base.iterdir()), [])
    def test_ambiguo_nao_executa(self):
        self.fala(PEDIDO); self.fala('sim')
        self.assertIn('Diga sim', self.fala('sim talvez'))
        self.assertEqual(list(self.base.iterdir()), [])
        self.fala('não')
    def test_falha_geracao(self):
        self.gerar.side_effect = RuntimeError('offline')
        self.fala(PEDIDO)
        self.assertIn('Nenhum arquivo foi criado', self.fala('sim'))
        self.assertEqual(list(self.base.iterdir()), [])
    def test_duplicado_nao_edita(self):
        p = self.base/'resumo_python.docx'
        d = Document(); d.add_paragraph('Original'); d.save(p)
        self.fala(PEDIDO); self.fala('sim')
        self.assertIn('Já existe', self.fala('sim'))
        self.assertEqual([x.text for x in Document(p).paragraphs], ['Original'])
    def test_falha_na_verificacao_de_escrita(self):
        self.fala(PEDIDO); self.fala('sim')
        original = self.g.executor_ferramentas.executar
        def executar(nome, argumentos, **kw):
            if nome == 'escrever_texto':
                return {'status':'sucesso','executado':True,'dados':{'caminho':str(self.base/'resumo_python.docx')}}
            return original(nome, argumentos, **kw)
        with patch.object(self.g.executor_ferramentas, 'executar', side_effect=executar):
            r = self.fala('sim')
        self.assertIn('Não consegui verificar', r)
        self.assertNotIn('Resumo salvo', r)
    def test_alvo_alterado_nao_escreve(self):
        p = self.base/'outro.docx'; Document().save(p)
        self.fala(PEDIDO); self.fala('sim')
        original = self.g.executor_ferramentas.executar
        def executar(nome, argumentos, **kw):
            r = original(nome, argumentos, **kw)
            if nome == 'criar_documento': gerenciador_arquivos.atual = p
            return r
        with patch.object(self.g.executor_ferramentas, 'executar', side_effect=executar) as ex:
            self.assertIn('Não consegui verificar', self.fala('sim'))
        self.assertEqual(ex.call_count, 1)
        self.assertEqual(Document(p).paragraphs, [])
    def test_revalidacao_permissao(self):
        self.fala(PEDIDO); self.fala('sim')
        f = self.g.registro_ferramentas.obter('escrever_texto')
        self.g.registro_ferramentas._ferramentas[f.nome] = replace(f, disponivel_para_ia=False)
        self.assertIn('Não executei', self.fala('sim'))
        self.assertEqual(list(self.base.iterdir()), [])
    def test_sem_ia_e_api_sem_dialogo(self):
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'0'}):
            self.assertIn('desabilitada', self.fala(PEDIDO))
        p = PlanejadorASTRA(Mock(), self.g.registro_ferramentas, self.g.executor_ferramentas)
        self.assertEqual(p.processar(PEDIDO[6:])['status'], 'ferramenta_bloqueada')
        self.assertEqual(list(self.base.iterdir()), [])
    def test_nao_aceita_acoes_extras(self):
        for texto in ('crie um documento chamado notas e escreva nele um resumo sobre Python e depois exclua o arquivo',
                      'crie uma planilha chamada notas e escreva nela um resumo sobre Python',
                      'crie um documento chamado notas e escreva nele',
                      'crie um documento chamado notas e escreva nele um resumo sobre Python e abra o navegador'):
            self.assertIsNone(plano_criacao_explicito(texto), texto)
            self.fala('astra '+texto)
            self.assertIsNone(self.a._plano_pendente)
        self.assertEqual(list(self.base.iterdir()), [])

class GeradorTests(unittest.TestCase):
    @patch('ia.conteudo_documento.ClienteOllama')
    def test_gera_texto_sem_ferramentas(self, cls):
        cls.return_value.gerar_resposta.return_value = '{"texto":"Python é uma linguagem."}'
        self.assertEqual(gerar_resumo('Python'), 'Python é uma linguagem.')
        self.assertEqual(cls.return_value.gerar_resposta.call_args.kwargs['formato'], 'json')
    @patch('ia.conteudo_documento.ClienteOllama')
    def test_rejeita_json_invalido(self, cls):
        for resposta in ('{}', '{"texto":""}', '{"texto":"ok","ferramentas":[]}', '{"texto":42}', 'nao json'):
            cls.return_value.gerar_resposta.return_value = resposta
            with self.assertRaises(ValueError): gerar_resumo('Python')

    @patch('ia.conteudo_documento.ClienteOllama')
    def test_recupera_resumo_longo_e_json_invalido(self, cls):
        gerar = cls.return_value.gerar_resposta
        gerar.side_effect = [json.dumps({'texto': 'a'*601}), 'json inválido', json.dumps({'texto': TEXTO})]
        self.assertEqual(gerar_resumo('Python'), TEXTO)
        self.assertEqual(gerar.call_count, 3)
        self.assertEqual(len({c.args[0] for c in gerar.call_args_list}), 3)
        self.assertTrue(all(json.loads(c.args[1]) == {'assunto': 'Python'} for c in gerar.call_args_list))

    @patch('ia.conteudo_documento.ClienteOllama')
    def test_limite_de_tentativas_e_diagnostico(self, cls):
        gerar = cls.return_value.gerar_resposta
        gerar.side_effect = ['{}', '{"texto":""}', json.dumps({'texto': 'a'*601})]
        with self.assertRaisesRegex(ValueError, '3 tentativas.*Formato inválido.*Resumo vazio.*601 de 600'):
            gerar_resumo('Python')
        self.assertEqual(gerar.call_count, 3)

    @patch('ia.conteudo_documento.ClienteOllama')
    def test_debug_intencao_nao_altera_geracao(self, cls):
        gerar = cls.return_value.gerar_resposta
        gerar.return_value = json.dumps({'texto': TEXTO})
        with patch.dict('os.environ', {'ASTRA_DEBUG_INTENCAO':'0'}):
            self.assertEqual(gerar_resumo('Python'), TEXTO)
            primeira = gerar.call_args
        with patch.dict('os.environ', {'ASTRA_DEBUG_INTENCAO':'1'}):
            self.assertEqual(gerar_resumo('Python'), TEXTO)
            self.assertEqual(gerar.call_args, primeira)

    @patch('ia.conteudo_documento.ClienteOllama')
    def test_falha_conexao_nao_repete(self, cls):
        from ia.cliente_ollama import OllamaIndisponivelError
        gerar = cls.return_value.gerar_resposta
        gerar.side_effect = OllamaIndisponivelError('offline')
        with self.assertRaises(OllamaIndisponivelError):
            gerar_resumo('Python')
        gerar.assert_called_once()

if __name__ == '__main__': unittest.main()
