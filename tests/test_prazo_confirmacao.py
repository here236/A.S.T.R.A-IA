"""Reproduz o atraso de 17 s observado no teclado, com arquivos reais."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arquivos.gerenciador_arquivos import gerenciador_arquivos
from configs import configuracoes_voz as cfg
from voz.comandos_voz import GerenciadorComandos
from voz.voz_principal import AssistenteVoz


class PrazoConfirmacaoTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.relogio = Mock(return_value=100.0)
        self.conversa = Mock(return_value='Conversa')
        self.intencao = Mock(return_value=None)
        for p in (patch.object(cfg, 'LOCAIS_ARQUIVOS', {'astra': str(self.base)}),
                  patch.object(cfg, 'LOCAL_PADRAO', 'astra'),
                  patch.object(gerenciador_arquivos, 'atual', None),
                  patch('voz.confirmacao_voz.time.monotonic', self.relogio),
                  patch.dict('os.environ', {'ASTRA_IA_HABILITADA': '1'})):
            p.start()
            self.addCleanup(p.stop)
        self.g = GerenciadorComandos()
        self.a = AssistenteVoz(lambda: '', lambda _: None, executar=self.g.executar,
                aguardando_confirmacao=self.g.confirmacao.aguardando,
                conversar=self.conversa, interpretar_intencao=self.intencao)
        self.pasta = self.base / 'teste_memoria_conversa'

    def pedir(self):
        self.assertIn('sim ou não', self.a.processar('astra crie uma pasta chamada teste memoria conversa').fala)
        self.assertFalse(self.pasta.exists())

    def test_atraso_do_log_17_segundos(self):
        self.pedir()
        self.relogio.return_value += 17
        self.assertIn('criada', self.a.processar('sim').fala)
        self.assertTrue(self.pasta.is_dir())
        self.assertIn(str(self.pasta), self.a.processar('astra onde você criou a última pasta').fala)
        self.intencao.assert_not_called()
        self.conversa.assert_not_called()

    def test_59_segundos_ainda_valido(self):
        self.pedir()
        self.relogio.return_value += 59
        self.a.processar('sim')
        self.assertTrue(self.pasta.is_dir())

    def test_expiracao_aos_60_segundos(self):
        self.pedir()
        self.relogio.return_value += 60
        self.assertIn('prazo de confirmação terminou', self.a.processar('sim').fala)
        self.assertFalse(self.pasta.exists())
        self.assertIsNone(self.a.processar('sim'))
        self.assertIn('Não tenho registro', self.a.processar('astra onde você criou a última pasta').fala)

    def test_cancelamento_apos_17_segundos(self):
        self.pedir()
        self.relogio.return_value += 17
        self.assertIn('cancelei', self.a.processar('não').fala)
        self.assertFalse(self.pasta.exists())

    def test_renovacao_apos_fala(self):
        self.pedir()
        self.relogio.return_value += 20
        self.g.confirmacao.renovar_prazo()
        self.relogio.return_value += 59
        self.a.processar('sim')
        self.assertTrue(self.pasta.is_dir())

    def test_nova_chamada_apos_expiracao(self):
        self.pedir()
        self.relogio.return_value += 61
        self.assertIn('Agora são', self.a.processar('astra que horas são').fala)
        self.assertFalse(self.pasta.exists())


if __name__ == '__main__':
    unittest.main()
