import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
from types import SimpleNamespace
from unittest import mock

from configs import configuracoes_voz as config
from voz import sintetizador_voz as st

TAXA = 22050


class TrechoFalso:
    """Imita o AudioChunk do Piper."""

    def __init__(self, bytes_):
        self.sample_rate = TAXA
        self.audio_int16_bytes = bytes_


class VozPiperFalsa:
    """Imita o PiperVoice: um trecho de áudio por frase, como o Piper real."""

    def __init__(self, tamanho_trecho=4000, trechos_por_frase=1, falha_na_frase=None):
        self.config = SimpleNamespace(length_scale=1.0, sample_rate=TAXA)
        self.tamanho, self.trechos = tamanho_trecho, trechos_por_frase
        self.falha_na_frase = falha_na_frase
        self.sintetizadas = []   # (texto, configuracao)

    def synthesize(self, texto, configuracao):
        self.sintetizadas.append((texto, configuracao))
        if texto == self.falha_na_frase:
            raise RuntimeError("falha na síntese")
        for _ in range(self.trechos):
            yield TrechoFalso(b"\x01\x00" * (self.tamanho // 2))


class PiperFalso:
    """Imita a classe PiperVoice (só o load)."""

    carregadas = []
    voz_a_devolver = None

    @staticmethod
    def load(modelo, config_path=None):
        PiperFalso.carregadas.append((modelo, config_path))
        return PiperFalso.voz_a_devolver


class ConfigSinteseFalsa:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class SaidaFalsa:
    """Imita a saída de áudio (alto-falante)."""

    def __init__(self, taxa):
        self.taxa = taxa
        self.escritas = []
        self.terminou = self.abortou = False
        self.ao_escrever = None

    def converter(self, pcm):
        return pcm

    def escrever(self, pcm):
        self.escritas.append(pcm)
        if self.ao_escrever:
            self.ao_escrever(len(self.escritas))

    def terminar(self):
        self.terminou = True

    def abortar(self):
        self.abortou = True

    @property
    def total(self):
        return sum(len(e) for e in self.escritas)


class Base(unittest.TestCase):

    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)

        self.voz = VozPiperFalsa()
        PiperFalso.carregadas = []
        PiperFalso.voz_a_devolver = self.voz
        self.saidas = []

        def criar_saida(taxa):
            saida = SaidaFalsa(taxa)
            self.saidas.append(saida)
            return saida

        for p in [
            mock.patch.object(config, "PASTA_VOZES", self.pasta),
            mock.patch.object(config, "VOZ_TTS", "razo"),
            mock.patch.object(config, "VELOCIDADE_FALA", 1.0),
            mock.patch.object(config, "VOLUME_FALA", 1.0),
            mock.patch.object(config, "PAUSA_ENTRE_FRASES", 0.15),
            mock.patch.object(config, "LIMITE_CARACTERES_FALA", None),
            mock.patch.object(st, "_importar_piper", lambda: (PiperFalso, ConfigSinteseFalsa)),
            mock.patch.object(st, "_criar_saida", criar_saida),
            mock.patch.object(st, "log", lambda *a, **k: None),
        ]:
            p.start()
            self.addCleanup(p.stop)

        st._vozes.clear()
        st._parar.clear()

    def baixar_voz_falsa(self):
        """Cria os arquivos que o baixar_voz criaria."""
        info = config.VOZES_PIPER["razo"]
        pasta = os.path.join(self.pasta, "razo")
        os.makedirs(pasta)
        for nome in (info["modelo"], info["config"]):
            with open(os.path.join(pasta, nome), "wb") as arquivo:
                arquivo.write(b"0")
        return pasta


class TestPreparacaoDoTexto(unittest.TestCase):

    def test_astra_nao_e_soletrado(self):
        self.assertEqual(
            st.preparar_texto_para_fala("Eu sou a A.S.T.R.A., sua assistente virtual."),
            ["Eu sou a Astra, sua assistente virtual."])

    def test_astra_no_fim_da_frase(self):
        self.assertEqual(st.preparar_texto_para_fala("Quem é a A.S.T.R.A.?"), ["Quem é a Astra?"])

    def test_remove_simbolos_de_ocr(self):
        self.assertEqual(st.preparar_texto_para_fala("Botão | Salvar _ Cancelar #"), ["Botão Salvar Cancelar"])

    def test_cada_linha_e_cada_frase_viram_um_trecho(self):
        self.assertEqual(
            st.preparar_texto_para_fala("Primeira frase. Segunda frase!\n\nTerceira linha"),
            ["Primeira frase.", "Segunda frase!", "Terceira linha"])

    def test_numero_decimal_nao_e_dividido(self):
        self.assertEqual(st.preparar_texto_para_fala("Custa 3.5 reais"), ["Custa 3.5 reais"])

    def test_vazio_e_so_pontuacao(self):
        for entrada in (None, "", "   \n  ", "...", "| _ |"):
            self.assertEqual(st.preparar_texto_para_fala(entrada), [], repr(entrada))


class TestVelocidade(Base):

    def test_fator(self):
        f = st._fator_de_velocidade
        self.assertEqual(f(1.0), 1.0)
        self.assertEqual(f(None), 1.0)
        self.assertEqual(f(1.3), 1.3)
        self.assertEqual(f(0.01), 0.5)    # nunca abaixo do mínimo do Piper
        self.assertEqual(f(50), 2.0)      # nem acima do máximo
        self.assertEqual(f("abc"), 1.0)   # inválida volta ao normal

    def test_usa_a_velocidade_da_configuracao(self):
        with mock.patch.object(config, "VELOCIDADE_FALA", 1.5):
            self.assertEqual(st._fator_de_velocidade(None), 1.5)


class TestVozes(Base):

    def test_carrega_com_config_explicita_e_so_uma_vez(self):
        pasta = self.baixar_voz_falsa()
        info = config.VOZES_PIPER["razo"]
        a = st.carregar_voz()
        b = st.carregar_voz("razo")
        self.assertIs(a, b)
        self.assertEqual(len(PiperFalso.carregadas), 1)
        self.assertEqual(PiperFalso.carregadas[0],
                         (os.path.join(pasta, info["modelo"]), os.path.join(pasta, info["config"])))

    def test_voz_nao_baixada_orienta_o_que_fazer(self):
        with self.assertRaises(st.VozNaoEncontradaError) as ctx:
            st.carregar_voz()
        self.assertIn("voz.baixar_voz", str(ctx.exception))

    def test_so_um_dos_arquivos_conta_como_nao_baixada(self):
        pasta = self.baixar_voz_falsa()
        os.remove(os.path.join(pasta, config.VOZES_PIPER["razo"]["config"]))
        with self.assertRaises(st.VozNaoEncontradaError):
            st.carregar_voz()

    def test_voz_desconhecida_lista_as_disponiveis(self):
        with self.assertRaises(st.VozNaoEncontradaError) as ctx:
            st.carregar_voz("zeca")
        self.assertIn("razo", str(ctx.exception))

    def test_listar_vozes(self):
        self.assertEqual([(v["nome"], v["baixada"]) for v in st.listar_vozes()], [("razo", False)])
        self.baixar_voz_falsa()
        self.assertEqual([(v["nome"], v["baixada"]) for v in st.listar_vozes()], [("razo", True)])

    def test_registro_da_razo_aponta_para_os_arquivos_reais_do_repositorio(self):
        info = config.VOZES_PIPER["razo"]
        self.assertEqual(info["repositorio"], "Lucasllfs/Razo-piper-voice")
        self.assertEqual(info["modelo"], "pt-BR-razo-medium.onnx")
        self.assertEqual(info["config"], "config.json")
        self.assertEqual(len(info["revisao"]), 40)   # commit fixo, não "main"


class TestFalar(Base):

    def setUp(self):
        super().setUp()
        self.baixar_voz_falsa()

    def test_fala_e_so_termina_depois_de_tocar_tudo(self):
        self.assertTrue(st.falar("Olá, bom dia."))
        self.assertEqual(len(self.saidas), 1)
        saida = self.saidas[0]
        self.assertEqual(saida.total, 4000)
        self.assertTrue(saida.terminou)        # esperou o que faltava tocar
        self.assertFalse(saida.abortou)
        self.assertEqual(saida.taxa, TAXA)     # abre a saída na taxa da voz

    def test_audio_e_entregue_em_blocos_pequenos(self):
        self.voz.tamanho = 5000
        st.falar("Uma frase.")
        escritas = self.saidas[0].escritas
        self.assertTrue(all(len(e) <= st.BYTES_POR_BLOCO for e in escritas))
        self.assertEqual(sum(len(e) for e in escritas), 5000)

    def test_varias_frases_na_ordem_com_pausa_entre_elas(self):
        st.falar("Primeira. Segunda.\nTerceira")
        self.assertEqual([t for t, _ in self.voz.sintetizadas], ["Primeira.", "Segunda.", "Terceira"])
        pausa = int(TAXA * 0.15) * 2   # bytes de silêncio (16 bits)
        self.assertEqual(self.saidas[0].total, 3 * 4000 + 2 * pausa)   # 2 pausas, nenhuma no fim

    def test_pausa_configuravel_e_pode_ser_zero(self):
        with mock.patch.object(config, "PAUSA_ENTRE_FRASES", 0):
            st.falar("Primeira. Segunda.")
        self.assertEqual(self.saidas[0].total, 2 * 4000)

    def test_texto_vazio_nao_carrega_voz_nem_abre_a_saida(self):
        self.assertFalse(st.falar(""))
        self.assertFalse(st.falar(None))
        self.assertFalse(st.falar("..."))
        self.assertEqual(self.saidas, [])
        self.assertEqual(PiperFalso.carregadas, [])

    def test_velocidade_vira_length_scale_sobre_o_valor_da_voz(self):
        self.voz.config.length_scale = 1.2
        st.falar("Oi", velocidade=2.0)
        st.falar("Oi", velocidade=0.5)
        st.falar("Oi")
        escalas = [round(c.length_scale, 3) for _, c in self.voz.sintetizadas]
        self.assertEqual(escalas, [0.6, 2.4, 1.2])

    def test_volume_vai_para_a_sintese_e_e_limitado(self):
        with mock.patch.object(config, "VOLUME_FALA", 0.5):
            st.falar("Oi")
        with mock.patch.object(config, "VOLUME_FALA", 7):
            st.falar("Oi")
        self.assertEqual([c.volume for _, c in self.voz.sintetizadas], [0.5, 1.0])

    def test_voz_carregada_uma_vez_entre_falas(self):
        for _ in range(5):
            st.falar("Teste")
        self.assertEqual(len(PiperFalso.carregadas), 1)

    def test_voz_nao_baixada_a_excecao_chega_a_quem_chamou(self):
        shutil.rmtree(os.path.join(self.pasta, "razo"))
        with self.assertRaises(st.VozNaoEncontradaError):
            st.falar("Oi")
        self.assertEqual(self.saidas, [])

    def test_erro_de_sintese_devolve_false_sem_derrubar(self):
        self.voz.falha_na_frase = "Segunda."
        self.assertFalse(st.falar("Primeira. Segunda."))
        self.assertTrue(self.saidas[0].abortou)     # não deixa o alto-falante aberto

    def test_erro_de_sintese_antes_de_qualquer_audio_nao_abre_a_saida(self):
        self.voz.falha_na_frase = "Unica."
        self.assertFalse(st.falar("Unica."))
        self.assertEqual(self.saidas, [])

    def test_pacote_nao_instalado_nao_derruba(self):
        def sem_pacote():
            raise RuntimeError("O pacote piper-tts não está instalado.")
        with mock.patch.object(st, "_importar_piper", sem_pacote):
            self.assertFalse(st.falar("Oi"))

    def test_falha_ao_abrir_o_alto_falante_nao_derruba(self):
        def sem_som(taxa):
            raise RuntimeError("O pacote PyAudio não está instalado.")
        with mock.patch.object(st, "_criar_saida", sem_som):
            self.assertFalse(st.falar("Oi"))

    def test_limite_de_caracteres_corta_ao_fim_de_uma_frase(self):
        with mock.patch.object(config, "LIMITE_CARACTERES_FALA", 25):
            st.falar("Primeira frase aqui. Segunda frase aqui. Terceira frase aqui.")
        self.assertEqual([t for t, _ in self.voz.sintetizadas], ["Primeira frase aqui."])

    def test_limite_nunca_deixa_sem_falar_nada(self):
        with mock.patch.object(config, "LIMITE_CARACTERES_FALA", 3):
            st.falar("Uma frase bem maior que o limite.")
        self.assertEqual(len(self.voz.sintetizadas), 1)

    def test_frase_com_varios_trechos_toca_todos(self):
        self.voz.trechos = 3
        st.falar("Uma frase.")
        self.assertEqual(self.saidas[0].total, 3 * 4000)


class TestParar(Base):

    def setUp(self):
        super().setUp()
        self.baixar_voz_falsa()

    def test_parar_no_meio_de_um_trecho_descarta_o_resto(self):
        self.voz.tamanho = 20000   # ~10 blocos
        original = st._criar_saida

        def criar(taxa):
            saida = original(taxa)
            saida.ao_escrever = lambda n: st.parar() if n == 3 else None
            return saida

        with mock.patch.object(st, "_criar_saida", criar):
            self.assertTrue(st.falar("Uma frase longa. Outra frase."))

        saida = self.saidas[0]
        self.assertEqual(len(saida.escritas), 3)       # parou logo após o 3º bloco
        self.assertTrue(saida.abortou)                  # descartou, sem esperar tocar
        self.assertFalse(saida.terminou)
        self.assertEqual(len(self.voz.sintetizadas), 1)  # a 2ª frase nem foi sintetizada

    def test_parar_entre_frases(self):
        original = st._criar_saida

        def criar(taxa):
            saida = original(taxa)
            saida.ao_escrever = lambda n: st.parar() if n == 2 else None   # fim do trecho 1
            return saida

        self.voz.tamanho = 4096   # exatamente 2 blocos
        with mock.patch.object(st, "_criar_saida", criar):
            st.falar("Primeira. Segunda. Terceira.")
        self.assertEqual([t for t, _ in self.voz.sintetizadas], ["Primeira."])
        self.assertTrue(self.saidas[0].abortou)

    def test_parar_chamado_antes_nao_afeta_a_fala_seguinte(self):
        st.parar()
        self.assertTrue(st.falar("Oi de novo"))
        self.assertEqual(self.saidas[0].total, 4000)
        self.assertTrue(self.saidas[0].terminou)

    def test_parar_de_outra_thread(self):
        self.voz.tamanho = 400000
        original = st._criar_saida

        def criar(taxa):
            saida = original(taxa)
            # a outra thread pede para parar quando o 2º bloco é tocado
            saida.ao_escrever = lambda n: threading.Thread(target=st.parar).start() if n == 2 else None
            return saida

        with mock.patch.object(st, "_criar_saida", criar):
            st.falar("Frase muito longa.")
        # parou muito antes de tocar os ~196 blocos
        self.assertLess(len(self.saidas[0].escritas), 20)


class TestThreads(Base):

    def test_funciona_em_outra_thread_e_compartilha_a_voz(self):
        self.baixar_voz_falsa()
        st.falar("Na thread principal")
        resultado = []
        t = threading.Thread(target=lambda: resultado.append(st.falar("Em outra thread")))
        t.start(); t.join()
        self.assertEqual(resultado, [True])
        self.assertEqual(len(PiperFalso.carregadas), 1)


class TestReamostrar(unittest.TestCase):

    def test_tamanho_e_formato(self):
        import numpy as np
        pcm = (np.sin(np.linspace(0, 50, 22050)) * 10000).astype(np.int16).tobytes()
        novo = st._reamostrar(pcm, 22050, 48000)
        self.assertEqual(len(novo) // 2, 48000)
        self.assertEqual(len(st._reamostrar(pcm, 22050, 11025)) // 2, 11025)
        self.assertEqual(st._reamostrar(b"", 22050, 48000), b"")

    def test_nao_estoura_o_limite_de_16_bits(self):
        import numpy as np
        pcm = np.array([32767, -32768] * 100, dtype=np.int16).tobytes()
        saida = np.frombuffer(st._reamostrar(pcm, 22050, 48000), dtype=np.int16)
        self.assertTrue(saida.max() <= 32767 and saida.min() >= -32768)


class TestSaidaPyAudio(unittest.TestCase):
    """A classe _Saida de verdade, com um PyAudio falso."""

    def setUp(self):
        self.aberturas = []
        outer = self

        class Fluxo:
            def __init__(s): s.escritas, s.chamadas = [], []
            def write(s, d): s.escritas.append(d)
            def stop_stream(s): s.chamadas.append("stop_stream")
            def close(s): s.chamadas.append("close")

        class PyAudioFalso:
            aceita = {TAXA, 48000}
            def open(s, format, channels, rate, output):
                outer.aberturas.append(rate)
                if rate not in s.aceita:
                    raise OSError("Invalid sample rate")
                f = Fluxo(); outer.fluxo = f; return f
            def get_default_output_device_info(s): return {"defaultSampleRate": 48000.0}

        modulo = types.ModuleType("pyaudio")
        modulo.paInt16 = 8
        modulo.PyAudio = PyAudioFalso
        self.PyAudioFalso = PyAudioFalso
        mock.patch.dict(sys.modules, {"pyaudio": modulo}).start()
        self.addCleanup(mock.patch.stopall)
        st._pyaudio = None
        self.addCleanup(setattr, st, "_pyaudio", None)
        mock.patch.object(st, "log", lambda *a, **k: None).start()

    def test_terminar_espera_tocar_e_abortar_descarta(self):
        s = st._Saida(TAXA)
        s.terminar()
        self.assertEqual(self.fluxo.chamadas, ["stop_stream", "close"])   # stop_stream espera o áudio acabar
        s = st._Saida(TAXA)
        s.abortar()
        self.assertEqual(self.fluxo.chamadas, ["close"])                  # só close: descarta na hora

    def test_taxa_aceita_nao_converte(self):
        s = st._Saida(TAXA)
        self.assertEqual(self.aberturas, [TAXA])
        self.assertEqual(s.converter(b"\x01\x00" * 100), b"\x01\x00" * 100)

    def test_placa_que_nao_aceita_a_taxa_usa_a_dela_e_converte(self):
        self.PyAudioFalso.aceita = {48000}
        s = st._Saida(TAXA)
        self.assertEqual(self.aberturas, [TAXA, 48000])
        convertido = s.converter(b"\x01\x00" * 22050)
        self.assertEqual(len(convertido) // 2, 48000)

    def test_pacote_ausente_da_mensagem_clara(self):
        with mock.patch.dict(sys.modules, {"pyaudio": None}):
            st._pyaudio = None
            with self.assertRaises((RuntimeError, ImportError)):
                st._Saida(TAXA)


@unittest.skipUnless(
    os.path.isfile(os.path.join(
        config.PASTA_VOZES, config.VOZ_TTS, config.VOZES_PIPER[config.VOZ_TTS]["modelo"])),
    "voz não baixada (rode: python -m voz.baixar_voz)")
class TestVozReal(unittest.TestCase):
    """
    Usa a voz DE VERDADE (Piper), sem tocar som. Só roda depois de baixar
    a voz; é o teste que confirma que ela funciona neste computador.
    """

    def test_sintetiza_audio_de_verdade(self):
        saidas = []

        def criar(taxa):
            saidas.append(SaidaFalsa(taxa))
            return saidas[-1]

        st._vozes.clear()
        with mock.patch.object(st, "_criar_saida", criar), \
                mock.patch.object(st, "log", lambda *a, **k: None):
            self.assertTrue(st.falar("Olá, eu sou a A.S.T.R.A., sua assistente virtual."))

        segundos = saidas[0].total / 2 / saidas[0].taxa
        self.assertGreater(segundos, 1.0)    # uma frase dessas tem alguns segundos
        self.assertLess(segundos, 15.0)


if __name__ == "__main__":
    unittest.main()
