import builtins
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

from configs import configuracoes_voz as config
from voz import voz_principal as vp
from voz.ativacao_voz import DetectorAtivacao
from voz.comandos_voz import GerenciadorComandos, StatusComando
from voz.processador_linguagem import RESPOSTA_PADRAO


class Base(unittest.TestCase):
    """
    Monta o assistente com o detector de ativação e o registro de comandos
    REAIS; só o que depende de hardware ou do Windows é simulado (microfone,
    voz, navegador, taskkill).
    """

    def setUp(self):
        self.faladas = []
        self.fila = []
        self.navegador = []
        self.taskkill = []

        self.gerenciador = GerenciadorComandos()
        self.assistente = self.novo_assistente()

        def run(comando, **kwargs):
            self.taskkill.append(comando)
            return types.SimpleNamespace(returncode=0)

        for p in [
            mock.patch("webbrowser.open", lambda url, *a, **k: self.navegador.append(url)),
            mock.patch("subprocess.run", run),
            mock.patch.object(vp, "log", lambda *a, **k: None),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def novo_assistente(self, **extras):
        argumentos = dict(
            ouvir=self._ouvir,
            falar=self.faladas.append,
            executar=self.gerenciador.executar,
            aguardando_confirmacao=self.gerenciador.confirmacao.aguardando,
            detector=DetectorAtivacao(),
        )
        argumentos.update(extras)
        assistente = vp.AssistenteVoz(**argumentos)
        assistente.pausa_apos_fala = 0
        return assistente

    def _ouvir(self):
        if not self.fila:
            raise KeyboardInterrupt   # acabou o roteiro: encerra como um Ctrl+C
        return self.fila.pop(0)

    def conversa(self, *falas):
        """Roda o laço inteiro com este roteiro de falas do usuário."""
        self.fila = list(falas)
        self.assistente.rodar()
        return self.faladas[1:]   # sem a saudação inicial


class TestProcessar(Base):

    def test_fala_sem_chamado_e_ignorada(self):
        self.assertIsNone(self.assistente.processar("leia a tela"))
        self.assertIsNone(self.assistente.processar("vamos abrir o navegador mais tarde"))
        self.assertEqual(self.navegador, [])

    def test_vazio_sem_estado_nao_faz_nada(self):
        for vazio in ("", "   ", None):
            self.assertIsNone(self.assistente.processar(vazio))

    def test_chamado_com_comando(self):
        saida = self.assistente.processar("Ok Astra, que horas são?")
        self.assertTrue(saida.fala.startswith("Agora são"))
        self.assertFalse(saida.encerrar)

    def test_nome_no_fim_ou_no_meio_da_frase(self):
        self.assertTrue(self.assistente.processar("Que horas são, Astra?").fala.startswith("Agora são"))
        self.assertTrue(self.assistente.processar("Astra, que horas são?").fala.startswith("Agora são"))

    def test_so_o_chamado_pede_o_comando(self):
        saida = self.assistente.processar("Ok Astra")
        self.assertEqual(saida.fala, vp.FALA_CHAMADO)
        self.assertTrue(saida.aguardar_comando)

    def test_chamado_mal_transcrito_continua_sendo_so_um_chamado(self):
        # o detector devolve o resto antes do nome ("okay") como se fosse comando
        for texto in ("okay astra", "oca astra", "ó, Astra", "ok astro"):
            self.assertEqual(self.assistente.processar(texto).fala, vp.FALA_CHAMADO, texto)

    def test_depois_do_chamado_sozinho_o_comando_nao_precisa_do_nome(self):
        self.assistente.processar("Ok Astra")
        self.assistente.detector.ativar()   # o laço faz isto depois de ela falar
        self.assertTrue(self.assistente.processar("que horas são").fala.startswith("Agora são"))

    def test_depois_de_um_comando_e_preciso_chamar_de_novo(self):
        self.assistente.processar("Ok Astra, que horas são?")
        self.assertIsNone(self.assistente.processar("que horas são"))

    def test_a_janela_de_ativacao_expira(self):
        self.assistente.detector.tempo_ativa = 0
        self.assistente.detector.ativar()
        self.assertIsNone(self.assistente.processar("que horas são"))

    def test_silencio_com_a_assistente_ativa_nao_gera_resposta(self):
        self.assistente.detector.ativar()
        self.assertIsNone(self.assistente.processar(""))

    def test_conversa_quando_nao_e_comando(self):
        self.assertIn("Bom dia", self.assistente.processar("Ok Astra, bom dia").fala)

    def test_nao_entendeu(self):
        saida = self.assistente.processar("Ok Astra, quantas luas tem Júpiter")
        self.assertEqual(saida.fala, RESPOSTA_PADRAO)
        self.assertFalse(saida.aguardar_comando)

    def test_encerrar(self):
        saida = self.assistente.processar("Ok Astra, tchau")
        self.assertTrue(saida.encerrar)
        self.assertEqual(saida.fala, "Tudo bem. Até mais.")

    def test_formas_coloquiais_que_o_whisper_escreve(self):
        # escritas reais do Whisper: "pesquisa", "abre", "fecha" no lugar do imperativo formal
        self.assistente.processar("Ok, Aster, pesquisa e receita de bolo.")
        self.assertTrue(self.navegador[-1].startswith("https://www.google.com/search?q="))
        self.assistente.processar("Ok, hasta, abre o site YouTube.")
        self.assertEqual(self.navegador[-1], "https://www.youtube.com")
        self.assistente.processar("Ok Astra, abre o navegador")
        self.assertEqual(self.navegador[-1], "https://www.google.com")
        self.assertIn("sim", self.assistente.processar("Ok, Aster, fecha o navegador!").fala.lower())
        self.assertEqual(self.taskkill, [])     # ainda esperando o "sim"

    def test_abrir_site_e_pesquisar_levam_o_parametro(self):
        self.assistente.processar("Ok Astra, pesquise receita de bolo")
        self.assertTrue(self.navegador[-1].endswith("q=receita+de+bolo"))

    def test_leia_a_tela_fala_o_texto_do_ocr(self):
        capturador = types.ModuleType("captura_tela.capturador_tela")
        capturador.capturar_tela = lambda: "Prints/tela.png"
        leitor = types.ModuleType("captura_tela.leitor_ocr")
        leitor.extrair_texto = lambda caminho: f"Botão Salvar ({caminho})"
        pacote = types.ModuleType("captura_tela"); pacote.__path__ = []
        with mock.patch.dict(sys.modules, {
                "captura_tela": pacote,
                "captura_tela.capturador_tela": capturador,
                "captura_tela.leitor_ocr": leitor}):
            saida = self.assistente.processar("Ok Astra, leia a tela")
        self.assertEqual(saida.fala, "Botão Salvar (Prints/tela.png)")


class TestConfirmacao(Base):
    """RN03: fechar o navegador é crítico e só acontece depois do "sim"."""

    def test_pede_confirmacao_e_nao_executa_antes(self):
        saida = self.assistente.processar("Ok Astra, feche o navegador")
        self.assertIn("sim", saida.fala.lower())
        self.assertEqual(self.taskkill, [])

    def test_sim_sem_chamar_a_assistente_executa(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        saida = self.assistente.processar("sim")
        self.assertEqual(saida.fala, "Navegador fechado.")
        self.assertTrue(self.taskkill)

    def test_nao_cancela_sem_executar(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        self.assertEqual(self.assistente.processar("não").fala, "Ok, cancelei.")
        self.assertEqual(self.taskkill, [])

    def test_na_duvida_cancela(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        self.assistente.processar("sim, não")
        self.assertEqual(self.taskkill, [])

    def test_silencio_repete_a_pergunta_e_depois_aceita_o_sim(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        repetiu = self.assistente.processar("")
        self.assertIn("Não entendi", repetiu.fala)
        self.assertEqual(self.taskkill, [])
        self.assertEqual(self.assistente.processar("sim").fala, "Navegador fechado.")

    def test_sem_resposta_cancela_por_seguranca(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        falas = [self.assistente.processar("").fala for _ in range(config.TENTATIVAS_CONFIRMACAO + 1)]
        self.assertIn("cancelei por segurança", falas[-1])
        self.assertEqual(self.taskkill, [])

    def test_sim_solto_sem_nada_pendente_e_ignorado(self):
        self.assertIsNone(self.assistente.processar("sim"))
        self.assertEqual(self.taskkill, [])

    def test_confirmacao_vencida_nao_executa(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        with mock.patch.object(config, "TEMPO_LIMITE_CONFIRMACAO", 0):
            self.assertIsNone(self.assistente.processar("sim"))
        self.assertEqual(self.taskkill, [])

    def test_outro_comando_no_meio_da_confirmacao_nao_executa_nada(self):
        self.assistente.processar("Ok Astra, feche o navegador")
        saida = self.assistente.processar("Ok Astra, abra o navegador")
        self.assertIn("Não entendi", saida.fala)
        self.assertEqual((self.navegador, self.taskkill), ([], []))


class TestRodar(Base):

    def test_a_saudacao_e_a_primeira_fala(self):
        self.conversa()
        self.assertEqual(self.faladas[0], vp.SAUDACAO_INICIAL)

    def test_conversa_completa_ate_o_tchau(self):
        falas = self.conversa("bom dia", "Ok Astra que horas são", "Ok Astra tchau", "isto nunca é ouvido")
        self.assertEqual(len(falas), 2)
        self.assertTrue(falas[0].startswith("Agora são"))
        self.assertEqual(falas[1], "Tudo bem. Até mais.")
        self.assertEqual(self.fila, ["isto nunca é ouvido"])   # parou ao encerrar

    def test_chamado_sozinho_depois_o_comando(self):
        falas = self.conversa("Ok Astra", "abra o navegador")
        self.assertEqual(falas[0], vp.FALA_CHAMADO)
        self.assertEqual(self.navegador, ["https://www.google.com"])

    def test_chamado_sozinho_e_comando_fora_do_tempo_nao_executa(self):
        self.assistente.detector.tempo_ativa = 0
        self.conversa("Ok Astra", "abra o navegador")
        self.assertEqual(self.navegador, [])

    def test_confirmacao_pelo_laco(self):
        falas = self.conversa("Ok Astra, feche o navegador", "sim")
        self.assertIn("sim", falas[0].lower())
        self.assertEqual(falas[1], "Navegador fechado.")

    def test_silencio_e_conversa_alheia_nao_geram_fala(self):
        falas = self.conversa("", "", "leia a tela", "")
        self.assertEqual(falas, [])

    def test_ctrl_c_encerra_sem_erro(self):
        self.conversa()   # a fila vazia levanta KeyboardInterrupt dentro do laço

    def test_texto_vazio_nao_e_falado(self):
        self.assistente._dizer("")
        self.assertEqual(self.faladas, [])

    def test_erro_inesperado_nao_derruba_o_laco(self):
        chamadas = []

        def executar(texto):
            chamadas.append(texto)
            if len(chamadas) == 1:
                raise RuntimeError("falhou")
            return self.gerenciador.executar(texto)

        self.assistente = self.novo_assistente(executar=executar)
        falas = self.conversa("Ok Astra que horas são", "Ok Astra que horas são")
        self.assertEqual(len(falas), 1)   # a 1ª falhou, a 2ª respondeu
        self.assertTrue(falas[0].startswith("Agora são"))

    def test_erros_seguidos_demais_desistem(self):
        def executar(texto):
            raise RuntimeError("sempre falha")

        self.assistente = self.novo_assistente(executar=executar)
        self.fila = ["Ok Astra que horas são"] * 20
        with self.assertRaises(RuntimeError):
            self.assistente.rodar()
        self.assertEqual(len(self.fila), 20 - vp.ERROS_SEGUIDOS_ATE_DESISTIR)

    def test_microfone_indisponivel_sobe_para_quem_chamou(self):
        def ouvir():
            raise vp.MicrofoneIndisponivelError("sem microfone")

        self.assistente = self.novo_assistente(ouvir=ouvir)
        with self.assertRaises(vp.MicrofoneIndisponivelError):
            self.assistente.rodar()


class TestMicrofone(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.pasta, True))
        self.chamadas = []
        self.retornos = []
        self.transcricao = "ok astra"
        self.falha_na_transcricao = False

        def ouvir_microfone(calibrar=True, silencioso=False):
            self.chamadas.append({"calibrar": calibrar, "silencioso": silencioso})
            return self.retornos.pop(0)

        def converter(audio):
            if self.falha_na_transcricao:
                raise RuntimeError("erro na transcrição")
            return self.transcricao

        falso = types.ModuleType("voz.reconhecedor_fala")
        falso.ouvir_microfone = ouvir_microfone
        falso.converter_fala_para_texto = converter

        import voz

        for p in [
            # "from . import reconhecedor_fala" olha primeiro o atributo do
            # pacote e só depois o sys.modules: os dois precisam ser trocados,
            # senão o resultado dependeria de qual teste rodou antes.
            mock.patch.dict(sys.modules, {"voz.reconhecedor_fala": falso}),
            mock.patch.object(voz, "reconhecedor_fala", falso, create=True),
            mock.patch.object(vp, "log", lambda *a, **k: None),
            mock.patch.object(config, "MANTER_AUDIOS", False),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def audio(self):
        caminho = os.path.join(self.pasta, f"a{len(os.listdir(self.pasta))}.wav")
        open(caminho, "wb").close()
        return caminho

    def relogio(self, *duracoes):
        """Faz cada chamada a ouvir() 'durar' o tempo dado."""
        valores = []
        t = 0.0
        for d in duracoes:
            valores += [t, t + d]
            t += d + 1
        return mock.patch.object(vp.time, "monotonic", side_effect=valores)

    def test_calibra_so_na_primeira_vez_e_escuta_em_silencio(self):
        mic = vp.Microfone()
        self.retornos = [self.audio(), self.audio(), self.audio()]
        for _ in range(3):
            mic.ouvir()
        self.assertEqual([c["calibrar"] for c in self.chamadas], [True, False, False])
        self.assertTrue(all(c["silencioso"] for c in self.chamadas))

    def test_devolve_o_texto_e_apaga_o_audio(self):
        mic = vp.Microfone()
        self.retornos = [self.audio()]
        self.assertEqual(mic.ouvir(), "ok astra")
        self.assertEqual(os.listdir(self.pasta), [])   # RN08

    def test_apaga_o_audio_mesmo_se_a_transcricao_falhar(self):
        mic = vp.Microfone()
        self.retornos = [self.audio()]
        self.falha_na_transcricao = True
        with self.assertRaises(RuntimeError):
            mic.ouvir()
        self.assertEqual(os.listdir(self.pasta), [])

    def test_pode_manter_o_audio_para_depurar(self):
        mic = vp.Microfone()
        self.retornos = [self.audio()]
        with mock.patch.object(config, "MANTER_AUDIOS", True):
            mic.ouvir()
        self.assertEqual(len(os.listdir(self.pasta)), 1)

    def test_ninguem_falou_devolve_vazio_e_conta_como_calibrado(self):
        mic = vp.Microfone()
        self.retornos = [None, None]
        with self.relogio(6.0, 5.0):          # esperou o tempo todo: foi silêncio
            self.assertEqual(mic.ouvir(), "")
            mic.ouvir()
        self.assertEqual([c["calibrar"] for c in self.chamadas], [True, False])

    def test_falhas_rapidas_seguidas_levantam_erro(self):
        mic = vp.Microfone()
        self.retornos = [None] * vp.FALHAS_RAPIDAS_ATE_DESISTIR
        with self.relogio(*[0.01] * vp.FALHAS_RAPIDAS_ATE_DESISTIR):
            for _ in range(vp.FALHAS_RAPIDAS_ATE_DESISTIR - 1):
                self.assertEqual(mic.ouvir(), "")
            with self.assertRaises(vp.MicrofoneIndisponivelError):
                mic.ouvir()
        # nunca chegou a calibrar: continua tentando calibrar
        self.assertTrue(all(c["calibrar"] for c in self.chamadas))

    def test_silencio_de_verdade_zera_a_contagem_de_falhas(self):
        mic = vp.Microfone()
        self.retornos = [None, None, None, None, None]
        with self.relogio(0.01, 0.01, 6.0, 0.01, 0.01):
            for _ in range(5):
                mic.ouvir()     # nunca chega a 3 falhas rápidas SEGUIDAS


class TestIniciarConversa(unittest.TestCase):

    def executar(self, argv, digitado=()):
        saida = io.StringIO()
        with mock.patch.object(builtins, "input", side_effect=list(digitado)), \
                mock.patch.object(vp, "log", lambda *a, **k: None), \
                redirect_stdout(saida):
            codigo = vp.iniciar_conversa(argv)
        return codigo, saida.getvalue()

    def test_modo_teclado_sem_voz_roda_ate_o_tchau(self):
        with mock.patch("webbrowser.open"):
            codigo, _ = self.executar(["--teclado", "--sem-voz"], ["ok astra que horas são", "ok astra tchau"])
        self.assertEqual(codigo, 0)

    def test_fim_da_entrada_encerra(self):
        codigo, _ = self.executar(["--teclado", "--sem-voz"], [EOFError()])
        self.assertEqual(codigo, 0)

    def test_modelo_de_fala_nao_baixado_orienta_e_sai(self):
        from voz import reconhecedor_fala as rf
        erro = rf.ModeloNaoEncontradoError("rode: python -m voz.baixar_modelo")
        with mock.patch.object(rf, "carregar_modelo", side_effect=erro):
            codigo, texto = self.executar(["--sem-voz"])
        self.assertEqual(codigo, 1)
        self.assertIn("baixar_modelo", texto)

    def test_voz_nao_baixada_orienta_e_sai(self):
        from voz import sintetizador_voz as sv
        erro = sv.VozNaoEncontradaError("rode: python -m voz.baixar_voz")
        with mock.patch.object(sv, "carregar_voz", side_effect=erro):
            codigo, texto = self.executar(["--teclado"])
        self.assertEqual(codigo, 1)
        self.assertIn("baixar_voz", texto)

    def test_modo_teclado_nao_precisa_do_modelo_de_fala(self):
        from voz import reconhecedor_fala as rf
        with mock.patch.object(rf, "carregar_modelo", side_effect=AssertionError("não deveria carregar")):
            codigo, _ = self.executar(["--teclado", "--sem-voz"], [EOFError()])
        self.assertEqual(codigo, 0)

    def test_microfone_indisponivel_sai_com_erro(self):
        from voz import reconhecedor_fala as rf
        from voz import sintetizador_voz as sv
        falas = []
        with mock.patch.object(rf, "carregar_modelo"), \
                mock.patch.object(sv, "carregar_voz"), \
                mock.patch.object(sv, "falar", lambda t, *a, **k: falas.append(t) or True), \
                mock.patch.object(vp.Microfone, "ouvir", side_effect=vp.MicrofoneIndisponivelError("sem microfone")), \
                mock.patch.object(vp.time, "sleep"):
            codigo, texto = self.executar([])
        self.assertEqual(codigo, 1)
        self.assertIn("sem microfone", texto)
        self.assertIn("Não consegui usar o microfone.", falas)


if __name__ == "__main__":
    unittest.main()
