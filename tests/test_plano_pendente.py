"""Testes de composição com confirmação usando arquivos reais temporários."""
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock, patch
from configs import configuracoes_voz as cfg
from arquivos.gerenciador_arquivos import gerenciador_arquivos
from ia.plano_composto import plano_criacao_explicito
from ia.planejador import PlanejadorASTRA
from voz.comandos_voz import GerenciadorComandos
from voz.intencao_voz import Esclarecimento
from voz.voz_principal import AssistenteVoz


class PlanoPendenteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.desktop = self.base/'desktop'
        self.desktop.mkdir()
        for p in (patch.object(cfg, 'LOCAIS_ARQUIVOS', {'astra': str(self.base), 'area de trabalho': str(self.desktop)}),
                  patch.object(cfg, 'LOCAL_PADRAO', 'astra'),
                  patch.object(gerenciador_arquivos, 'atual', None),
                  patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'1'})):
            p.start(); self.addCleanup(p.stop)
        self.g = GerenciadorComandos()
        self.interpretar = Mock(return_value=None)
        self.conversar = Mock(return_value='Conversa.')
        self.a = self.assistente()
        p = patch('webbrowser.open', return_value=True)
        self.abrir = p.start(); self.addCleanup(p.stop)

    def assistente(self, voz=False):
        return AssistenteVoz(lambda:'', lambda _:None, executar=self.g.executar,
            aguardando_confirmacao=self.g.confirmacao.aguardando,
            conversar=self.conversar, interpretar_intencao=self.interpretar, entrada_por_voz=voz)

    def fala(self, texto):
        r = self.a.processar(texto)
        return r.fala if r else ''

    def test_coleta_confirma_e_executa_uma_vez(self):
        self.assertIn('Qual nome', self.fala('astra abra o navegador e crie uma pasta'))
        self.assertIn('sim ou não', self.fala('Projetos'))
        self.abrir.assert_not_called()
        self.assertFalse((self.base/'projetos').exists())
        r = self.fala('sim')
        self.abrir.assert_called_once()
        self.assertTrue((self.base/'projetos').is_dir())
        self.assertIn(str(self.base/'projetos'), r)
        self.assertIn('Abrindo o navegador', r)
        self.assertIsNone(self.a._plano_pendente)
        self.fala('sim')
        self.abrir.assert_called_once()
        self.conversar.assert_not_called()

    def test_cancelar_no_nome_ou_confirmacao(self):
        self.fala('astra abra o navegador e crie uma pasta')
        self.assertIn('cancelei', self.fala('cancelar'))
        self.fala('astra abra o navegador e crie uma pasta chamada teste')
        self.assertIn('cancelei', self.fala('não'))
        self.abrir.assert_not_called()
        self.assertFalse((self.base/'teste').exists())

    def test_duas_criacoes_exigem_confirmacoes_distintas(self):
        self.assertIn('sim ou não', self.fala('astra crie uma pasta chamada projetos e depois crie um documento chamado notas'))
        self.assertIn('etapa 2', self.fala('sim'))
        self.assertFalse((self.base/'projetos').exists())
        self.assertFalse((self.base/'notas.docx').exists())
        self.assertIn('criado', self.fala('sim'))
        self.assertTrue((self.base/'projetos').is_dir())
        self.assertTrue((self.base/'notas.docx').is_file())

    def test_duas_criacoes_cancelar_segunda(self):
        self.fala('astra crie uma pasta chamada projetos e depois crie um documento chamado notas')
        self.fala('sim')
        self.fala('não')
        self.assertFalse((self.base/'projetos').exists())
        self.assertFalse((self.base/'notas.docx').exists())

    def test_documento_e_hora_ordem(self):
        self.fala('astra crie um documento chamado notas e depois diga as horas')
        r = self.fala('sim')
        self.assertTrue((self.base/'notas.docx').is_file())
        self.assertLess(r.index('criado'), r.index('Agora são'))

    def test_local_preservado_e_nome_literal(self):
        self.fala('astra abra o navegador e crie uma pasta na área de trabalho')
        self.assertIn('area de trabalho', self.fala('Projetos e estudos'))
        self.fala('sim')
        self.assertTrue((self.desktop/'projetos_e_estudos').is_dir())

    def test_expiracao_e_novo_comando(self):
        self.fala('astra abra o navegador e crie uma pasta chamada vencida')
        self.a._plano_pendente.prazo = 0
        self.assertIn('prazo', self.fala('sim'))
        self.fala('astra abra o navegador e crie uma pasta chamada cancelada')
        self.assertIn('Agora são', self.fala('astra que horas são'))
        self.fala('sim')
        self.abrir.assert_not_called()
        self.assertFalse((self.base/'vencida').exists())
        self.assertFalse((self.base/'cancelada').exists())

    def test_confirmacao_ambigua_e_ia_desabilitada(self):
        self.fala('astra abra o navegador e crie uma pasta chamada teste')
        self.assertIn('Diga sim', self.fala('sim talvez'))
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'0'}):
            self.assertIn('desabilitada', self.fala('sim'))
        self.abrir.assert_not_called()
        self.assertFalse((self.base/'teste').exists())

    def test_falha_na_primeira_etapa_interrompe(self):
        (self.base/'existente').mkdir()
        self.fala('astra crie uma pasta chamada existente e depois abra o navegador')
        r = self.fala('sim')
        self.assertIn('Já existe', r)
        self.assertIn('restantes não foram executadas', r)
        self.abrir.assert_not_called()

    def test_preflight_e_revalidacao(self):
        self.fala('astra abra o navegador e crie uma pasta chamada teste')
        f = self.g.registro_ferramentas.obter('criar_pasta')
        self.g.registro_ferramentas._ferramentas[f.nome] = replace(f, disponivel_para_ia=False)
        self.assertIn('Não executei', self.fala('sim'))
        self.abrir.assert_not_called()
        self.assertFalse((self.base/'teste').exists())

    def test_voz_e_fallback_semantico_nao_autorizam_criacao(self):
        self.a = self.assistente(voz=True)
        self.interpretar.return_value = Esclarecimento('Repita.')
        self.assertIn('Está correto', self.fala('astra abra o navegador e crie uma pasta chamada teste'))
        self.assertIn('Confirma a etapa', self.fala('sim'))
        self.abrir.assert_not_called()
        self.assertFalse((self.base/'teste').exists())
        self.fala('sim')
        self.abrir.assert_called_once()
        self.assertTrue((self.base/'teste').is_dir())

    def test_escopo_e_api_sem_dialogo(self):
        for texto in ('como abrir o navegador e crie uma pasta', 'não abra o navegador e crie uma pasta',
                      'pesquise sobre abra o navegador e crie uma pasta',
                      'crie uma pasta chamada abra o navegador e diga as horas',
                      'abra o navegador e crie um documento e escreva nele um resumo',
                      'abra o navegador e crie uma pasta e exclua o arquivo teste'):
            self.assertIsNone(plano_criacao_explicito(texto), texto)
        p = PlanejadorASTRA(Mock(), self.g.registro_ferramentas, self.g.executor_ferramentas)
        self.assertEqual(p.processar('abra o navegador e crie uma pasta')['status'], 'ferramenta_bloqueada')
        self.abrir.assert_not_called()

    def test_repeticao_e_desativada(self):
        self.assertIn('Não executei', self.fala('astra abra o navegador e crie uma pasta e crie uma pasta'))
        with patch.dict('os.environ', {'ASTRA_IA_HABILITADA':'0'}):
            self.assertIn('desabilitada', self.fala('astra abra o navegador e crie uma pasta'))
        self.abrir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
