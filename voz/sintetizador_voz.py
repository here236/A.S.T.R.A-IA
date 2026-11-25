import argparse
import os
import threading
import time

from configs import configuracoes_voz
from .utilitarios_voz import log

'''
    Texto → Voz

    Responsabilidade:
    Transformar resposta em áudio

    Motor: Kokoro-82M ONNX (voz neural), 100% offline: nada do que a assistente
    fala sai do computador, e nenhum áudio é gravado em arquivo (RN08).
    A voz (pf_dora) é baixada uma única vez com:
        python -m voz.baixar_voz

    Para testar a voz:
        python -m voz.sintetizador_voz            (fala frases de exemplo)
        python -m voz.sintetizador_voz --help     (todas as opções)
'''


# Faixa de velocidade aceita (1.0 = normal).
VELOCIDADE_MIN = 0.5
VELOCIDADE_MAX = 2.0

# O áudio é entregue à placa de som em blocos desta quantidade de bytes
# (2048 bytes = 1024 amostras, cerca de 0,05 s). Entre um bloco e outro
# confere-se se parar() foi chamada, e é isso que torna a interrupção rápida.
BYTES_POR_BLOCO = 2048


class VozNaoEncontradaError(Exception):
    """
    A voz pedida não existe, ou ainda não foi baixada. É problema de
    instalação (e não de fala), por isso é uma exceção e não um silêncio:
    assim fica claro o que fazer.
    """


# ESTADO

# Sinal de "pare de falar". Pode ser acionado de qualquer thread.
_parar = threading.Event()

# Vozes já carregadas na memória (carregar leva um ou dois segundos).
_vozes = {}
_trava_vozes = threading.Lock()

# Biblioteca de som, criada uma vez só.
_pyaudio = None


# VOZ

def _importar_kokoro():
    try:
        from kokoro_onnx import Kokoro
        from misaki.espeak import EspeakG2P
    except ImportError as erro:
        raise RuntimeError(
            "Instale as dependências: python -m pip install -r requirements.txt"
        ) from erro
    return Kokoro, EspeakG2P


class _VozKokoro:
    """Adapta o motor ONNX ao fluxo de áudio PCM existente."""

    sample_rate = 24000

    def __init__(self, modelo, arquivo_vozes, nome, idioma):
        Kokoro, EspeakG2P = _importar_kokoro()
        # CPU explícita: não exige GPU nem Ollama.
        os.environ["ONNX_PROVIDER"] = "CPUExecutionProvider"
        self.motor = Kokoro(modelo, arquivo_vozes)
        self.g2p = EspeakG2P(language=idioma)
        self.nome = nome

    def sintetizar(self, texto, velocidade, volume):
        import numpy as np
        fonemas, _ = self.g2p(texto)
        if not fonemas:
            return
        audio, taxa = self.motor.create(
            fonemas, voice=self.nome, speed=velocidade, is_phonemes=True
        )
        pcm = (np.clip(np.asarray(audio, dtype=np.float32) * volume,
                       -1.0, 1.0) * 32767).astype("<i2").tobytes()
        if pcm:
            yield taxa, pcm


def _info_da_voz(nome):

    try:
        return configuracoes_voz.VOZES_KOKORO[nome]

    except KeyError:

        disponiveis = ", ".join(configuracoes_voz.VOZES_KOKORO)

        raise VozNaoEncontradaError(
            f"A voz '{nome}' não existe. Vozes disponíveis: {disponiveis}"
        )


def _caminhos_da_voz(nome):
    """
    Devolve (arquivo do modelo, arquivo de vozes) da voz.
    """

    info = _info_da_voz(nome)

    pasta = os.path.join(configuracoes_voz.PASTA_VOZES, nome)

    return (
        os.path.join(pasta, info["modelo"]),
        os.path.join(pasta, info["vozes"])
    )


def carregar_voz(nome=None):
    """
    Carrega a voz na memória e a devolve.

    Pode ser chamada na inicialização do programa para que a primeira
    fala da assistente não espere o carregamento. Se não for, a primeira
    chamada de falar() carrega sozinha.

    Levanta VozNaoEncontradaError se a voz ainda não foi baixada.
    """

    nome = nome or configuracoes_voz.VOZ_TTS

    with _trava_vozes:

        if nome in _vozes:
            return _vozes[nome]

        modelo, configuracao = _caminhos_da_voz(nome)

        if not (os.path.isfile(modelo) and os.path.isfile(configuracao)):

            raise VozNaoEncontradaError(
                f"A voz '{nome}' ainda não foi baixada.\n"
                "Baixe uma vez (só nesse passo é preciso internet) com:\n"
                "    python -m voz.baixar_voz"
            )

        log(f"Carregando a voz '{nome}'...")
        inicio = time.perf_counter()
        try:
            _vozes[nome] = _VozKokoro(modelo, configuracao, nome, _info_da_voz(nome)["idioma"])
        except Exception as erro:
            raise VozNaoEncontradaError(
                f"Não foi possível carregar o Kokoro: {erro}. "
                "Verifique as dependências e rode python -m voz.baixar_voz."
            ) from erro

        log(f"Voz carregada em {time.perf_counter() - inicio:.1f}s.")

        return _vozes[nome]


def listar_vozes():
    """
    Devolve as vozes configuradas e se cada uma já foi baixada:
    [{"nome", "repositorio", "baixada"}].
    """

    vozes = []

    for nome, info in configuracoes_voz.VOZES_KOKORO.items():

        modelo, configuracao = _caminhos_da_voz(nome)

        vozes.append({
            "nome": nome,
            "repositorio": info["repositorio"],
            "baixada": os.path.isfile(modelo) and os.path.isfile(configuracao)
        })

    return vozes


# VELOCIDADE E VOLUME

def _fator_de_velocidade(velocidade):

    if velocidade is None:
        velocidade = configuracoes_voz.VELOCIDADE_FALA

    try:
        velocidade = float(velocidade)

    except (TypeError, ValueError):

        log(f"Velocidade inválida ({velocidade!r}). Usando a normal.", "AVISO")
        velocidade = 1.0

    return max(VELOCIDADE_MIN, min(VELOCIDADE_MAX, velocidade))


def _sintetizar(voz, texto, velocidade=None):
    volume = max(0.0, min(1.0, float(configuracoes_voz.VOLUME_FALA)))
    return voz.sintetizar(texto, _fator_de_velocidade(velocidade), volume)


# SAÍDA DE ÁUDIO

def _reamostrar(pcm, taxa_origem, taxa_destino):
    """
    Converte áudio PCM de 16 bits de uma taxa de amostragem para outra
    (interpolação linear). Só é usado quando a placa de som não aceita a
    taxa da voz.
    """

    import numpy as np

    amostras = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)

    if len(amostras) == 0:
        return pcm

    quantidade = max(1, int(round(len(amostras) * taxa_destino / taxa_origem)))

    posicoes = np.linspace(0, len(amostras) - 1, quantidade)

    novas = np.interp(posicoes, np.arange(len(amostras)), amostras)

    return np.clip(novas, -32768, 32767).astype(np.int16).tobytes()


def _obter_pyaudio():

    global _pyaudio

    if _pyaudio is None:

        try:
            import pyaudio

        except ImportError:

            raise RuntimeError(
                "O pacote PyAudio não está instalado. "
                "Rode: python -m pip install -r requirements.txt"
            )

        _pyaudio = pyaudio.PyAudio()

    return _pyaudio


class _Saida:
    """
    Fluxo de áudio de saída (alto-falante) em PCM de 16 bits, mono.
    Usa o PyAudio, que o projeto já tem por causa do microfone.
    """

    def __init__(self, taxa):

        import pyaudio

        pa = _obter_pyaudio()

        self._taxa_voz = taxa
        self._taxa = taxa

        try:
            self._fluxo = pa.open(
                format=pyaudio.paInt16, channels=1, rate=taxa, output=True
            )

        except OSError:

            # A placa de som não aceitou a taxa da voz: usa a dela e
            # converte o áudio.
            self._taxa = int(pa.get_default_output_device_info()["defaultSampleRate"])

            log(
                f"A placa de som não aceita {taxa} Hz. "
                f"Convertendo para {self._taxa} Hz.",
                "AVISO"
            )

            self._fluxo = pa.open(
                format=pyaudio.paInt16, channels=1, rate=self._taxa, output=True
            )

    def converter(self, pcm):

        if self._taxa == self._taxa_voz:
            return pcm

        return _reamostrar(pcm, self._taxa_voz, self._taxa)

    def escrever(self, pcm):

        self._fluxo.write(pcm)

    def terminar(self):
        """
        Espera o que já foi enviado terminar de tocar e fecha.
        """

        self._fluxo.stop_stream()
        self._fluxo.close()

    def abortar(self):
        """
        Fecha na hora, descartando o que ainda não tocou.
        """

        self._fluxo.close()


def _criar_saida(taxa):
    """
    Abre a saída de áudio (ponto único de contato com o PyAudio; os
    testes automatizados substituem esta função).
    """

    return _Saida(taxa)


def _tocar(saida, pcm):
    """
    Toca o áudio em blocos pequenos, conferindo parar() entre eles.
    Devolve False se foi interrompido.
    """

    pcm = saida.converter(pcm)

    for inicio in range(0, len(pcm), BYTES_POR_BLOCO):

        if _parar.is_set():
            return False

        saida.escrever(pcm[inicio:inicio + BYTES_POR_BLOCO])

    return True


# PREPARAÇÃO DO TEXTO

def preparar_texto_para_fala(texto):
    """
    Limpa o texto e o divide em frases, prontas para serem faladas.

    - "A.S.T.R.A." vira "Astra" (senão o motor soletra as letras).
    - Símbolos soltos, comuns no texto lido da tela por OCR, são
      removidos (o motor leria "barra vertical", "sublinhado" etc.).
    - Cada linha e cada frase viram um trecho: dá pausas naturais e
      permite interromper a fala entre os trechos.
    """

    import re

    if texto is None:
        return []

    texto = str(texto)

    texto = re.sub(r"\bA\.S\.T\.R\.A\b\.?", "Astra", texto, flags=re.IGNORECASE)

    texto = re.sub(r"[|_~^`<>{}\[\]\\=*#]", " ", texto)

    frases = []

    for linha in texto.splitlines():

        linha = re.sub(r"\s+", " ", linha).strip()

        if not linha:
            continue

        for frase in re.split(r"(?<=[.!?])\s+", linha):

            frase = frase.strip()

            # Descarta pedaços que sobraram só com pontuação.
            if re.search(r"\w", frase):
                frases.append(frase)

    return frases


def _aplicar_limite(frases):
    """
    Corta a lista de frases no limite de caracteres da configuração,
    sempre ao final de uma frase (nunca no meio dela).
    """

    limite = configuracoes_voz.LIMITE_CARACTERES_FALA

    if not limite:
        return frases

    mantidas = []
    total = 0

    for frase in frases:

        if mantidas and total + len(frase) > limite:

            log(
                f"Texto longo: falando só as primeiras {len(mantidas)} "
                f"frases (limite de {limite} caracteres).",
                "AVISO"
            )

            break

        mantidas.append(frase)
        total += len(frase)

    return mantidas


# FALAR

def _falar(texto, velocidade=None, voz=None):
    """
    Fala o texto em voz alta e só retorna quando termina de falar (ou
    quando parar() é chamada). Isso é proposital: enquanto a assistente
    fala, o microfone não pode estar gravando, senão ela transcreveria
    a própria voz.

    velocidade: 1.0 é o normal. Se None, usa VELOCIDADE_FALA.
    voz:        nome de uma voz de VOZES_KOKORO. Se None, usa VOZ_TTS.

    Devolve True se falou algo (inteiro ou até ser interrompido); False
    se o texto era vazio ou se ocorreu algum erro (que fica no log).

    Levanta VozNaoEncontradaError se a voz não existe ou não foi baixada.
    """

    frases = _aplicar_limite(preparar_texto_para_fala(texto))

    if not frases:
        return False

    _parar.clear()

    saida = None
    taxa = None
    falou = False
    interrompida = False

    inicio = time.monotonic()
    primeiro_som = None

    try:

        motor = carregar_voz(voz)

        for numero, frase in enumerate(frases):

            if _parar.is_set():
                interrompida = True
                break

            # Pequena pausa entre uma frase e a seguinte.
            if numero > 0 and taxa:

                silencio = b"\x00\x00" * int(
                    taxa * configuracoes_voz.PAUSA_ENTRE_FRASES
                )

                if not _tocar(saida, silencio):
                    interrompida = True
                    break

            for taxa_trecho, pcm in _sintetizar(motor, frase, velocidade):
                if _parar.is_set():
                    interrompida = True
                    break

                if saida is None:

                    # A saída só é aberta quando já existe áudio para
                    # tocar (um erro de síntese não mexe na placa de som).
                    taxa = taxa_trecho
                    saida = _criar_saida(taxa)

                if primeiro_som is None:
                    primeiro_som = time.monotonic()

                falou = True

                if not _tocar(saida, pcm):
                    interrompida = True
                    break

            if interrompida:
                break

    except VozNaoEncontradaError:

        _fechar_saida(saida, abortar=True)
        raise

    except Exception as erro:

        log(f"Erro ao falar: {erro}", "ERRO")

        _fechar_saida(saida, abortar=True)

        return False

    _fechar_saida(saida, abortar=interrompida)

    if falou and primeiro_som is not None:

        log(
            f"Falou em {time.monotonic() - inicio:.1f}s "
            f"(começou após {primeiro_som - inicio:.2f}s) "
            f"com a voz '{voz or configuracoes_voz.VOZ_TTS}'."
        )

    return falou


_trava_fala = threading.Lock()


def falar(texto, velocidade=None, voz=None):
    # Serializa chamadas concorrentes sem impedir parar() de outra thread.
    with _trava_fala:
        return _falar(texto, velocidade, voz)


def _fechar_saida(saida, abortar):
    """
    Fecha a saída de áudio. Se abortar for False, antes espera o que já
    foi enviado terminar de tocar; se for True, descarta na hora.
    """

    if saida is None:
        return

    try:

        if abortar:
            saida.abortar()

        else:
            saida.terminar()

    except Exception as erro:

        log(f"Erro ao fechar a saída de áudio: {erro}", "AVISO")


def parar():
    """
    Interrompe a fala em andamento (de qualquer thread). A voz é cortada
    entre blocos de reprodução. A inferência em andamento pode precisar terminar.
    """

    _parar.set()


# TESTES

FRASES_EXEMPLO = [
    "Olá! Eu sou a A.S.T.R.A., sua assistente virtual.",
    "Agora são 14 horas e 30 minutos.",
    "Abrindo o navegador.",
]


def _mostrar_vozes():

    vozes = listar_vozes()

    print(f"\nVozes configuradas ({len(vozes)}):")

    for voz in vozes:

        situacao = "baixada" if voz["baixada"] else "NÃO baixada (rode: python -m voz.baixar_voz)"
        usada = "   <-- será usada" if voz["nome"] == configuracoes_voz.VOZ_TTS else ""

        print(f"  {voz['nome']}  [{voz['repositorio']}]  {situacao}{usada}")

    print()


def _testar_repeticao(quantidade, voz, velocidade):
    """
    Fala a mesma frase várias vezes seguidas, para conferir se a voz
    não trava nem fica muda depois de algumas chamadas.
    """

    # Carrega a voz antes de contar o tempo: assim os números abaixo
    # mostram quanto cada fala demora de verdade, sem o carregamento.
    carregar_voz(voz)

    for numero in range(1, quantidade + 1):

        inicio = time.monotonic()

        ok = falar(f"Teste número {numero}.", velocidade, voz)

        print(
            f"  {numero}/{quantidade}: "
            f"{'ok' if ok else 'FALHOU'} em {time.monotonic() - inicio:.1f}s"
        )

        if not ok:
            break


def _testar_parar(voz, velocidade):
    """
    Começa uma fala longa e a interrompe sozinha depois de 2 segundos.
    """

    longo = " ".join(
        ["Esta é uma frase longa, feita para testar a interrupção da fala."] * 8
    )

    # Carrega a voz antes de iniciar o relógio: senão o pedido de parar
    # poderia chegar antes de a voz começar a falar.
    carregar_voz(voz)

    threading.Timer(2.0, parar).start()

    inicio = time.monotonic()

    falar(longo, velocidade, voz)

    print(
        f"Fala interrompida após {time.monotonic() - inicio:.1f}s "
        "(esperado: um pouco mais de 2s; se foi até o fim, a interrupção falhou)."
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Testa a voz usada pela A.S.T.R.A."
    )

    parser.add_argument("texto", nargs="?", help="texto a ser falado")
    parser.add_argument("--listar", action="store_true", help="só mostra as vozes configuradas")
    parser.add_argument("--voz", help="nome da voz (uma das configuradas em VOZES_KOKORO)")
    parser.add_argument("--velocidade", type=float, help="1.0 = normal, 0.8 = mais devagar, 1.3 = mais rápido")
    parser.add_argument("--repetir", type=int, metavar="N", help="fala N vezes seguidas (teste de estabilidade)")
    parser.add_argument("--teste-parar", action="store_true", help="testa a interrupção da fala")

    argumentos = parser.parse_args()

    try:

        _mostrar_vozes()

        if argumentos.listar:
            pass

        elif argumentos.repetir:
            _testar_repeticao(argumentos.repetir, argumentos.voz, argumentos.velocidade)

        elif argumentos.teste_parar:
            _testar_parar(argumentos.voz, argumentos.velocidade)

        elif argumentos.texto:
            falar(argumentos.texto, argumentos.velocidade, argumentos.voz)

        else:

            for frase in FRASES_EXEMPLO:

                print(f"Falando: {frase}")
                falar(frase, argumentos.velocidade, argumentos.voz)

    except VozNaoEncontradaError as erro:

        print(f"\n{erro}")
