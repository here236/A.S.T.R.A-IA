"""
Diagnóstico da pesquisa: mostra, passo a passo, o que funciona no seu PC.

Uso (na raiz do projeto, com o .venv ativo):
    python testar_pesquisa.py
    python testar_pesquisa.py buracos negros
    python testar_pesquisa.py buracos negros --navegador

--navegador também testa o navegador invisível (mais pesado e lento;
só é usado como reserva quando os sites bloqueiam o pedido direto).

No fim, ele diz qual MODO_BUSCA usar no configuracoes_voz.py.
"""

import argparse
import time 

from pesquisa import pesquisa_web
from pesquisa.pesquisa_web import ErroBusca


def passo(titulo):

    print(f"\n--- {titulo}")


def medir(funcao, *args):
    """
    Roda a função e devolve (resultado, erro, segundos).
    """

    inicio = time.perf_counter()

    try:
        return funcao(*args), None, time.perf_counter() - inicio
    except ErroBusca as erro:
        return None, erro, time.perf_counter() - inicio


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("assunto", nargs="*")
    parser.add_argument("--navegador", action="store_true")
    argumentos = parser.parse_args()

    assunto = " ".join(argumentos.assunto).strip() or "buracos negros"

    print(f"Assunto do teste: {assunto}")

    # 1) INTERNET

    passo("1) Conexão com a internet")

    _, erro, segundos = medir(pesquisa_web.buscar_wikipedia, "teste", 1)

    if erro:
        print(f"   FALHOU ({erro}) em {segundos:.1f}s")
        print("   Sem internet, nada abaixo vai funcionar. Confira a conexão.")
        return 1

    print(f"   ok ({segundos:.1f}s)")

    # 2) BUSCADORES PELO PEDIDO DIRETO

    funcionam = []
    primeiro_link = None

    for motor in ("duckduckgo", "bing"):

        passo(f"2) Buscador {motor} (pedido direto, sem navegador)")

        resultados, erro, segundos = medir(pesquisa_web._buscar_http, motor, assunto)

        if erro:
            print(f"   FALHOU: {erro} ({segundos:.1f}s)")
            continue

        if not resultados:
            print(f"   respondeu, mas sem resultados ({segundos:.1f}s)")
            print("   (pode ser que a página tenha mudado por dentro)")
            continue

        funcionam.append(motor)

        primeiro_link = primeiro_link or resultados[0].link

        print(f"   ok: {len(resultados)} resultados em {segundos:.1f}s")

        for resultado in resultados[:3]:
            print(f"     - {resultado.titulo[:70]}")
            print(f"       {resultado.link[:90]}")

    # 3) WIKIPÉDIA

    passo("3) Wikipédia (resumo do assunto)")

    resumo, erro, segundos = medir(pesquisa_web.resumo_wikipedia, assunto)

    if erro:
        print(f"   FALHOU: {erro}")
    elif resumo is None:
        print(f"   sem artigo relacionado a '{assunto}' ({segundos:.1f}s)")
    else:
        titulo, paragrafos, link = resumo
        print(f"   ok: artigo '{titulo}' ({segundos:.1f}s)")
        print(f"     {paragrafos[0][:120]}...")
        primeiro_link = primeiro_link or link

    # 4) LEITURA DE PÁGINA

    passo("4) Leitura de uma página (texto e tabelas)")

    if not primeiro_link:
        print("   pulado: nenhum link para ler")
    else:

        pagina, erro, segundos = medir(pesquisa_web.ler_pagina, primeiro_link)

        if erro:
            print(f"   FALHOU em {primeiro_link[:70]}: {erro}")
        else:
            print(f"   ok em {segundos:.1f}s: {primeiro_link[:70]}")
            print(f"     título: {pagina.titulo[:70]}")
            print(f"     parágrafos de texto: {len(pagina.paragrafos)}")
            print(f"     tabelas de dados: {len(pagina.tabelas)}")

    # 5) NAVEGADOR INVISÍVEL (opcional)

    navegador_ok = None

    if argumentos.navegador:

        passo("5) Navegador invisível (reserva)")

        resultados, erro, segundos = medir(
            pesquisa_web._buscar_no_navegador, "duckduckgo", assunto
        )

        if erro:
            navegador_ok = False
            print(f"   FALHOU: {erro} ({segundos:.1f}s)")
        else:
            navegador_ok = bool(resultados)
            print(f"   {'ok' if resultados else 'sem resultados'}: "
                  f"{len(resultados)} resultados em {segundos:.1f}s")

    # CONCLUSÃO

    passo("Conclusão")

    if funcionam:

        print(f"   Funcionam pelo pedido direto: {', '.join(funcionam)}.")
        print('   Use MODO_BUSCA = "leve" (mais rápido e leve) ou "automatico".')

        if len(funcionam) == 1:
            print(f'   Coloque "{funcionam[0]}" primeiro em MOTORES_DE_BUSCA.')

        return 0

    if navegador_ok:
        print('   O pedido direto foi bloqueado, mas o navegador invisível funciona.')
        print('   Use MODO_BUSCA = "navegador".')
        return 0

    print("   Nenhum buscador respondeu pelo pedido direto.")
    print("   A Wikipédia continua disponível como reserva.")

    if navegador_ok is None:
        print("   Rode de novo com --navegador para testar a outra via.")

    return 1


if __name__ == "__main__":

    raise SystemExit(main())
