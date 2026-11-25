"""Regressões de coleta de parâmetros com arquivos reais em pasta temporária."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arquivos.gerenciador_arquivos import gerenciador_arquivos
from configs import configuracoes_voz as config
from ia.planejador import PlanejadorASTRA
from voz import voz_principal as vp
from voz.comandos_voz import GerenciadorComandos, StatusComando
from voz.processador_linguagem import ProcessadorConversa


class TestDialogoPendente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.desktop = self.base / 'desktop'
        self.desktop.mkdir()
        for p in [mock.patch.dict(os.environ, {"ASTRA_IA_HABILITADA": "1"}),
                  mock.patch.object(config, 'LOCAIS_ARQUIVOS', {'astra': str(self.base), 'area de trabalho': str(self.desktop)}),
                  mock.patch.object(config, 'LOCAL_PADRAO', 'astra'),
                  mock.patch.object(gerenciador_arquivos, 'atual', None)]:
            p.start(); self.addCleanup(p.stop)
        self.manager = GerenciadorComandos()
        self.cliente = mock.Mock()
        self.planejador = PlanejadorASTRA(self.cliente, self.manager.registro_ferramentas, self.manager.executor_ferramentas)
        self.conversa = ProcessadorConversa(self.planejador, ia_habilitada=True)
        self.astra = vp.AssistenteVoz(lambda: '', lambda _: None,
            executar=self.manager.executar, aguardando_confirmacao=self.manager.confirmacao.aguardando,
            conversar=self.conversa.responder, interpretar_intencao=lambda _: None)
        self.astra.pausa_apos_fala = 0

    def fala(self, texto):
        saida = self.astra.processar(texto)
        return saida.fala if saida is not None else None

    def test_documento_legado_nome_e_confirmacao_sem_ativacao(self):
        self.assertIn('Qual nome', self.fala('astra cria um documento'))
        self.assertIn('Confirma', self.fala('Teste'))
        self.assertFalse((self.base/'teste.docx').exists())
        self.assertIn('criado', self.fala('sim'))
        self.assertTrue((self.base/'teste.docx').is_file())
        self.cliente.gerar_resposta.assert_not_called()

    def test_documento_ia_pede_nome_antes_de_confirmar(self):
        self.assertIn('Qual nome', self.fala('astra planeje criar documento'))
        self.assertIn('Confirma', self.fala('Relatório'))
        self.assertFalse((self.base/'relatorio.docx').exists())
        self.assertIn('criado', self.fala('sim'))
        self.assertTrue((self.base/'relatorio.docx').is_file())
        self.cliente.gerar_resposta.assert_not_called()

    def test_executor_ia_com_parametro_vazio(self):
        resultado = self.manager.executor_ferramentas.executar('criar_pasta', {'parametro': ''})
        self.assertEqual(resultado['status'], 'aguardando_parametro')
        self.assertFalse(resultado['executado'])
        self.assertFalse(self.manager.confirmacao.aguardando())
        self.assertIn('Confirma', self.fala('Projetos'))
        self.assertFalse((self.base/'projetos').exists())
        self.fala('sim')
        self.assertTrue((self.base/'projetos').is_dir())

    def test_cancelar_na_coleta(self):
        self.fala('astra crie uma pasta')
        self.assertIn('cancelei', self.fala('cancelar'))
        self.assertFalse(self.manager.dialogo.aguardando())
        self.assertIsNone(self.fala('Teste'))
        self.assertFalse((self.base/'teste').exists())

    def test_cancelar_na_confirmacao(self):
        self.fala('astra crie uma pasta')
        self.fala('Projetos')
        self.fala('não')
        self.assertFalse((self.base/'projetos').exists())

    def test_nova_chamada_abandona_coleta(self):
        self.fala('astra crie uma pasta')
        self.assertIn('Agora são', self.fala('astra que horas são'))
        self.assertFalse(self.manager.dialogo.aguardando())
        self.assertIsNone(self.fala('Teste'))

    def test_expiracao_ignora_nome_atrasado(self):
        self.fala('astra crie uma pasta')
        self.manager.dialogo.pendente.prazo = 0
        self.assertIsNone(self.fala('Teste'))
        self.assertFalse((self.base/'teste').exists())

    def test_sim_nao_e_um_nome(self):
        self.fala('astra crie uma pasta')
        self.assertIn('Qual nome', self.fala('sim'))
        self.assertFalse(self.manager.confirmacao.aguardando())
        self.assertFalse((self.base/'sim').exists())

    def test_local_original_preservado(self):
        self.assertIn('Qual nome', self.fala('astra crie uma pasta na area de trabalho'))
        self.fala('teste')
        self.fala('sim')
        self.assertTrue((self.desktop/'teste').is_dir())
        self.assertFalse((self.base/'teste').exists())

    def test_local_conflitante_nao_troca_destino(self):
        self.fala('astra crie uma pasta na area de trabalho')
        self.assertIn('Qual nome', self.fala('teste em astra'))
        self.assertTrue(self.manager.dialogo.aguardando())
        self.assertFalse(self.manager.confirmacao.aguardando())

    def test_confirmacao_exata_nao_aceita_frase_ambigua(self):
        self.fala('astra crie uma pasta')
        self.fala('teste')
        self.fala('sim talvez')
        self.assertFalse((self.base/'teste').exists())
        self.fala('sim')
        self.assertTrue((self.base/'teste').is_dir())

    def test_sem_ia_fluxo_tradicional(self):
        with mock.patch.dict(os.environ, {'ASTRA_IA_HABILITADA': '0'}):
            self.fala('astra crie uma pasta')
            self.fala('teste')
            self.fala('sim')
        self.assertTrue((self.base/'teste').is_dir())
        self.cliente.gerar_resposta.assert_not_called()

    def test_pesquisa_faltando_assunto(self):
        with mock.patch('webbrowser.open') as abrir:
            self.assertIn('pesquisar', self.fala('astra pesquise'))
            abrir.assert_not_called()
            self.fala('árvores')
            abrir.assert_called_once()

    def test_planilha_colunas_preservadas(self):
        self.fala('astra crie uma planilha com as colunas nome, idade')
        self.fala('alunos')
        self.fala('sim')
        from openpyxl import load_workbook
        livro = load_workbook(self.base/'alunos.xlsx')
        try:
            self.assertEqual([c.value for c in livro.active[1]], ['nome','idade'])
        finally:
            livro.close()
