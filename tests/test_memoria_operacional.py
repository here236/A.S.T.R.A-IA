"""Regressões de memória operacional usando criações reais em pasta temporária."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from arquivos.gerenciador_arquivos import gerenciador_arquivos
from configs import configuracoes_voz as cfg
from voz.comandos_voz import GerenciadorComandos, StatusComando
from voz.voz_principal import AssistenteVoz
from voz.memoria_operacional import MemoriaOperacional


class MemoriaOperacionalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.desktop = self.base / 'desktop'; self.desktop.mkdir()
        for p in (patch.object(cfg, 'LOCAIS_ARQUIVOS', {'astra': str(self.base), 'area de trabalho': str(self.desktop)}),
                  patch.object(cfg, 'LOCAL_PADRAO', 'astra'),
                  patch.object(gerenciador_arquivos, 'atual', None),
                  patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})):
            p.start(); self.addCleanup(p.stop)
        self.g = GerenciadorComandos()
        self.ia = Mock(return_value=None)
        self.conversa = Mock(return_value='Conversa')
        self.a = AssistenteVoz(lambda: '', lambda _: None, executar=self.g.executar,
                aguardando_confirmacao=self.g.confirmacao.aguardando,
                conversar=self.conversa, interpretar_intencao=self.ia)

    def fala(self, texto):
        r = self.a.processar(texto)
        return r.fala if r else ''

    def criar(self, pedido):
        self.assertEqual(self.g.executar(pedido).status, StatusComando.AGUARDANDO_CONFIRMACAO)
        self.assertEqual(self.g.executar('sim').status, StatusComando.SUCESSO)

    def test_tradicional_e_consulta_sem_ia(self):
        self.criar('crie uma pasta chamada projetos')
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '0'}):
            self.assertIn(str(self.base/'projetos'), self.fala('astra onde você criou a pasta projetos'))
        self.ia.assert_not_called(); self.conversa.assert_not_called()

    def test_executor_ia_mesma_memoria(self):
        r = self.g.executor_ferramentas.executar('criar_documento', {'parametro': 'relatorio'}, confirmado=True)
        self.assertEqual(r['status'], 'sucesso')
        self.assertIn(str(self.base/'relatorio.docx'), self.fala('astra onde você salvou o documento que acabou de criar'))
        self.ia.assert_not_called()

    def test_plano_composto_usa_mesma_memoria(self):
        self.fala('astra crie uma pasta chamada projetos e depois crie um documento chamado relatorio')
        self.fala('sim'); self.fala('sim')
        self.assertTrue((self.base/'relatorio.docx').is_file())
        self.assertIn(str(self.base/'projetos'), self.fala('astra onde você criou a última pasta'))
        self.assertIn(str(self.base/'relatorio.docx'), self.fala('astra onde você criou o último documento'))

    def test_plano_dependente_usa_mesma_memoria(self):
        with patch('voz.plano_pendente.gerar_resumo', return_value='Resumo de teste.'):
            self.fala('astra crie um documento chamado resumo e escreva nele um resumo sobre Python')
            self.fala('sim'); self.fala('sim')
        self.assertTrue((self.base/'resumo.docx').is_file())
        self.assertIn(str(self.base/'resumo.docx'), self.fala('astra onde você salvou o documento resumo'))

    def test_duplicado_sem_registro(self):
        (self.base/'externo').mkdir()
        self.g.executar('crie uma pasta chamada externo'); self.g.executar('sim')
        self.assertEqual('Não tenho registro dessa criação nesta sessão.', self.fala('astra onde você criou a pasta externo'))

    def test_cancelamento_sem_registro(self):
        self.g.executar('crie uma pasta chamada cancelada'); self.g.executar('não')
        self.assertIn('Não tenho registro', self.fala('astra onde você criou a pasta cancelada'))
        self.assertFalse((self.base/'cancelada').exists())

    def test_exclusao_externa(self):
        self.criar('crie uma pasta chamada projetos'); (self.base/'projetos').rmdir()
        self.assertIn('não está mais', self.fala('astra onde você criou a pasta projetos'))
        self.assertFalse((self.base/'projetos').exists())

    def test_exclusao_pela_astra(self):
        self.criar('crie uma pasta chamada projetos')
        with patch('send2trash.send2trash', side_effect=lambda p: Path(p).rmdir()):
            self.g.executar('exclua a pasta projetos'); self.g.executar('sim')
        self.assertIn('Esse item foi removido do local original.', self.fala('astra onde você criou a pasta projetos'))

    def test_nome_ambiguo(self):
        self.criar('crie uma pasta chamada projetos')
        self.criar('crie uma pasta chamada projetos na area de trabalho')
        r = self.fala('astra onde você criou a pasta projetos')
        self.assertIn('mais de um', r)
        self.assertIn(str(self.desktop/'projetos'), r)
        self.assertIn(str(self.base/'projetos'), r)

    def test_limpar_nao_exclui(self):
        self.criar('crie uma pasta chamada projetos')
        self.assertIn('Memória operacional limpa', self.fala('astra limpar memória operacional'))
        self.assertIn('Não tenho registro', self.fala('astra onde você criou a pasta projetos'))
        self.assertTrue((self.base/'projetos').is_dir())

    def test_sem_registro_inventado_e_limite(self):
        m = MemoriaOperacional(1)
        m.registrar('criar_pasta', {'caminho':str(self.base/'inventado')})
        self.assertIn('Não tenho registro', m.responder('onde você criou a pasta inventado'))
        for name in ('a1','a2'):
            p = self.base/name; p.mkdir()
            m.registrar('criar_pasta', {'caminho':str(p), 'verificacao':'existe'})
        self.assertIn('Não tenho registro', m.responder('onde você criou a pasta a1'))
        self.assertIn('a2', m.responder('onde você criou a pasta a2'))
        self.assertIsNone(m.responder('crie uma pasta chamada a3'))
        self.assertIsNone(m.responder('apague a pasta a2'))

    def test_consulta_nao_confirma_criacao_pendente(self):
        self.fala('astra crie uma pasta chamada pendente')
        self.fala('onde você criou a pasta pendente')
        self.assertFalse((self.base/'pendente').exists())
        self.fala('não')
        self.assertFalse((self.base/'pendente').exists())
