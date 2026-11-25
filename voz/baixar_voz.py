"""Baixa os arquivos ONNX uma vez e verifica a síntese local."""
import argparse
import os
from urllib.request import urlopen, Request
import shutil
from configs import configuracoes_voz as config
from .utilitarios_voz import log


def baixar_voz(nome=None):
    nome = nome or config.VOZ_TTS
    info = config.VOZES_KOKORO.get(nome)
    if info is None:
        log(f"Voz desconhecida: {nome}. Use {config.VOZ_TTS}.", "ERRO")
        return False
    pasta = os.path.join(config.PASTA_VOZES, nome)
    try:
        os.makedirs(pasta, exist_ok=True)
        for arquivo in (info["modelo"], info["vozes"]):
            destino = os.path.join(pasta, arquivo)
            if os.path.isfile(destino) and os.path.getsize(destino) > 0:
                continue
            url = f"https://github.com/{info['repositorio']}/releases/download/{info['revisao']}/{arquivo}"
            temporario = destino + ".part"
            log(f"Baixando {arquivo}...")
            try:
                with urlopen(Request(url, headers={"User-Agent": "ASTRA"}), timeout=120) as origem, open(temporario, "wb") as saida:
                    shutil.copyfileobj(origem, saida)
                os.replace(temporario, destino)
            finally:
                if os.path.exists(temporario):
                    os.remove(temporario)
        from . import sintetizador_voz as st
        voz = st.carregar_voz(nome)
        total = sum(len(pcm) / 2 / taxa for taxa, pcm in st._sintetizar(voz, "Olá, eu sou a Astra."))
        if total <= 0:
            raise RuntimeError("Nenhum áudio gerado.")
        log(f"Voz {nome} verificada: {total:.1f}s de áudio.")
        return True
    except Exception as erro:
        log(f"Falha ao baixar ou verificar Kokoro: {erro}", "ERRO")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baixa Kokoro para a ASTRA")
    parser.add_argument("--voz", default=config.VOZ_TTS)
    raise SystemExit(0 if baixar_voz(parser.parse_args().voz) else 1)
