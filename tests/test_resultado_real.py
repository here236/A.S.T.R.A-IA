"""Resultados reais de arquivos e proteção contra sucesso inventado."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from arquivos.gerenciador_arquivos import gerenciador_arquivos
from configs import configuracoes_voz as cfg
from voz.comandos_voz import GerenciadorComandos, StatusComando
from ia.planejador import PlanejadorASTRA


class ResultadoRealTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        for p in (patch.object(cfg, 'LOCAIS_ARQUIVOS', {'astra': str(self.base)}),
                  patch.object(cfg, 'LOCAL_PADRAO', 'astra'),
                  patch.object(gerenciador_arquivos, 'atual', None)):
            p.start(); self.addCleanup(p.stop)
        self.manager = GerenciadorComandos()
        self.executor = self.manager.executor_ferramentas
        self.cliente = Mock()
        self.planejador = PlanejadorASTRA(self.cliente, self.manager.registro_ferramentas, self.executor)

    def test_pasta_caminho_real(self):
        r = self.manager.executar('crie uma pasta chamada teste')
        self.assertEqual(r.status, StatusComando.AGUARDANDO_CONFIRMACAO)
        self.assertFalse((self.base/'teste').exists())
        r = self.manager.executar('sim')
        self.assertEqual(r.status, StatusComando.SUCESSO)
        self.assertTrue(Path(r.dados['caminho']).is_dir())
        self.assertIn(str(self.base/'teste'), r.resposta_falada)

    def test_pasta_duplicada_nao_e_sucesso(self):
        (self.base/'teste').mkdir()
        r = self.manager.executar('crie uma pasta chamada teste')
        self.assertEqual(r.status, StatusComando.AGUARDANDO_CONFIRMACAO)
        r = self.manager.executar('sim')
        self.assertEqual(r.status, StatusComando.ERRO)
        self.assertIn('Já existe', r.resposta_falada)

    def test_criacoes_com_nome_exigem_sim_no_modo_tradicional(self):
        casos = [('crie uma pasta chamada teste', 'teste'),
                 ('crie um documento chamado teste', 'teste.docx'),
                 ('crie uma planilha chamada teste', 'teste.xlsx'),
                 ('crie um arquivo de texto chamado teste', 'teste.txt'),
                 ('crie uma apresentacao chamada teste', 'teste.pptx')]
        for pedido, arquivo in casos:
            with self.subTest(pedido=pedido):
                alvo = self.base / arquivo
                r = self.manager.executar(pedido)
                self.assertEqual(r.status, StatusComando.AGUARDANDO_CONFIRMACAO)
                self.assertIn('sim ou não', r.resposta_falada)
                self.assertFalse(alvo.exists())
                r = self.manager.executar('sim talvez')
                self.assertEqual(r.status, StatusComando.AGUARDANDO_CONFIRMACAO)
                self.assertFalse(alvo.exists())
                r = self.manager.executar('não')
                self.assertEqual(r.status, StatusComando.CANCELADO)
                self.assertFalse(alvo.exists())
                r = self.manager.executar(pedido)
                self.assertEqual(r.status, StatusComando.AGUARDANDO_CONFIRMACAO)
                r = self.manager.executar('SIM')
                self.assertEqual(r.status, StatusComando.SUCESSO, r.resposta_falada)
                self.assertTrue(alvo.exists())
                self.assertEqual(Path(r.dados['caminho']), alvo)

    def test_criacoes_com_nome_exigem_sim_no_executor_ia(self):
        casos = [('criar_pasta', 'ia'), ('criar_documento', 'ia.docx'),
                 ('criar_planilha', 'ia.xlsx'), ('criar_texto', 'ia.txt'),
                 ('criar_apresentacao', 'ia.pptx')]
        for ferramenta, arquivo in casos:
            with self.subTest(ferramenta=ferramenta):
                alvo = self.base / arquivo
                r = self.executor.executar(ferramenta, {'parametro': 'ia'})
                self.assertEqual(r['status'], 'confirmacao_necessaria')
                self.assertFalse(r['executado'])
                self.assertFalse(alvo.exists())
                self.assertEqual(self.manager.executar('não').status, StatusComando.CANCELADO)
                self.assertFalse(alvo.exists())
                r = self.executor.executar(ferramenta, {'parametro': 'ia'})
                self.assertEqual(r['status'], 'confirmacao_necessaria')
                r = self.manager.executar('sim')
                self.assertEqual(r.status, StatusComando.SUCESSO, r.resposta_falada)
                self.assertTrue(alvo.exists())

    def test_chamada_direta_sem_confirmacao_nao_cria(self):
        r = self.manager.executar_ferramenta('criar_pasta', 'teste')
        self.assertEqual(r.status, StatusComando.AGUARDANDO_CONFIRMACAO)
        self.assertFalse((self.base/'teste').exists())

    def test_documento_real_e_duplicado_executor(self):
        r = self.executor.executar('criar_documento', {'parametro': 'teste'}, confirmado=True)
        self.assertTrue(r['executado'])
        self.assertTrue(Path(r['dados']['caminho']).is_file())
        r = self.executor.executar('criar_documento', {'parametro': 'teste'}, confirmado=True)
        self.assertFalse(r['executado'])
        self.assertEqual(r['status'], 'erro')

    def test_save_sem_arquivo_nao_e_sucesso(self):
        with patch('docx.Document', return_value=Mock()):
            r = self.executor.executar('criar_documento', {'parametro': 'fantasma'}, confirmado=True)
        self.assertFalse(r['executado'])
        self.assertIsNone(gerenciador_arquivos.atual)
        self.assertIn('verificar', r['resposta'])

    def test_modelo_inventa_criacao_sem_executar(self):
        self.cliente.gerar_resposta.return_value = '{"acao":"responder","ferramentas":[],"resposta":"Criei o documento."}'
        r = self.planejador.processar('crie um documento chamado fantasma')
        self.assertEqual(r['status'], 'acao_nao_executada')
        self.assertFalse(r['concluido'])
        self.assertFalse((self.base/'fantasma.docx').exists())

    def test_browser_recusa(self):
        with patch('webbrowser.open', return_value=False):
            r = self.manager.executar('abra o navegador')
        self.assertEqual(r.status, StatusComando.ERRO)

    def test_escrever_sem_arquivo_nao_e_sucesso(self):
        r = self.executor.executar('escrever_texto', {'parametro':'Olá'}, confirmado=True)
        self.assertEqual(r['status'], 'erro')
        self.assertFalse(r['executado'])

    def test_excluir_sem_remover_nao_e_sucesso(self):
        alvo = self.base/'teste.txt'
        alvo.write_text('teste')
        with patch('send2trash.send2trash'):
            r = self.executor.executar('excluir', {'parametro':'teste.txt'}, confirmado=True)
        self.assertFalse(r['executado'])
        self.assertTrue(alvo.exists())

if __name__ == '__main__':
    unittest.main()
