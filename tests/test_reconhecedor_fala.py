import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from configs import configuracoes_voz as config
from voz import reconhecedor_fala as rf


def segmento(texto, sem_fala=0.0):
    return SimpleNamespace(text=texto, no_speech_prob=sem_fala)


class ModeloFalso:
    """Imita o WhisperModel: guarda como foi chamado e devolve segmentos prontos."""

    def __init__(self, segmentos=(), erro=None):
        self.segmentos, self.erro, self.chamadas = list(segmentos), erro, []

    def transcribe(self, audio, **kwargs):
        self.chamadas.append((audio, kwargs))
        if self.erro:
            raise self.erro
        return iter(self.segmentos), None


class TestTranscricao(unittest.TestCase):

    def setUp(self):
        self.audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self.audio.close()
        self.addCleanup(os.remove, self.audio.name)
        self.modelo = ModeloFalso([segmento(" Ok Astra, "), segmento("que horas são? ")])
        for p in [
            mock.patch.object(rf, "_modelo", self.modelo),
            mock.patch.object(rf, "log", lambda *a, **k: None),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def test_junta_os_trechos(self):
        self.assertEqual(rf.converter_fala_para_texto(self.audio.name), "Ok Astra, que horas são?")

    def test_descarta_trecho_que_o_modelo_acha_que_nao_e_fala(self):
        self.modelo.segmentos = [segmento("Ok Astra", 0.01), segmento("Legendas pela comunidade", 0.95)]
        self.assertEqual(rf.converter_fala_para_texto(self.audio.name), "Ok Astra")

    def test_envia_a_dica_de_vocabulario_da_configuracao(self):
        with mock.patch.object(config, "DICA_VOCABULARIO_STT", "Ok Astra."):
            rf.converter_fala_para_texto(self.audio.name)
        self.assertEqual(self.modelo.chamadas[-1][1]["initial_prompt"], "Ok Astra.")

    def test_a_dica_pode_ser_desligada(self):
        with mock.patch.object(config, "DICA_VOCABULARIO_STT", None):
            rf.converter_fala_para_texto(self.audio.name)
        self.assertIsNone(self.modelo.chamadas[-1][1]["initial_prompt"])

    def test_configuracao_antiga_sem_a_dica_nao_quebra(self):
        # o arquivo de configuração de quem ainda não tem a chave nova
        with mock.patch.object(config, "DICA_VOCABULARIO_STT", create=True):
            del config.DICA_VOCABULARIO_STT
            self.assertEqual(rf.converter_fala_para_texto(self.audio.name), "Ok Astra, que horas são?")
        self.assertIsNone(self.modelo.chamadas[-1][1]["initial_prompt"])

    def test_idioma_e_filtro_de_silencio(self):
        rf.converter_fala_para_texto(self.audio.name)
        argumentos = self.modelo.chamadas[-1][1]
        self.assertEqual(argumentos["language"], config.IDIOMA_STT)
        self.assertTrue(argumentos["vad_filter"])
        self.assertFalse(argumentos["condition_on_previous_text"])

    def test_silencio_devolve_vazio(self):
        self.modelo.segmentos = []
        self.assertEqual(rf.converter_fala_para_texto(self.audio.name), "")

    def test_arquivo_inexistente_devolve_vazio(self):
        self.assertEqual(rf.converter_fala_para_texto("nao_existe.wav"), "")
        self.assertEqual(rf.converter_fala_para_texto(None), "")

    def test_erro_do_modelo_devolve_vazio_sem_derrubar(self):
        self.modelo.erro = RuntimeError("falhou")
        self.assertEqual(rf.converter_fala_para_texto(self.audio.name), "")


if __name__ == "__main__":
    unittest.main()
