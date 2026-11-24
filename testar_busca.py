"""
Teste de busca em segundo plano (sem abrir janela).

Uso (pelo terminal, ou pelo botão Run do VS Code, que pergunta o assunto):
    python testar_busca.py buracos negros
    python testar_busca.py buracos negros --motor duckduckgo
    python testar_busca.py buracos negros --ver     (mostra a janela, para depurar)

Usa o Edge ou o Chrome que já estão instalados, com um perfil LIMPO
(sem seus logins, histórico ou cookies).
"""

import argparse
from urllib.parse import parse_qs, quote_plus, urlparse

from playwright.sync_api import sync_playwright


MOTORES = {
    "bing": {
        "url": "https://www.bing.com/search?q={consulta}&setlang=pt-BR",
        "resultado": "li.b_algo",
        "titulo": "h2 a",
        "resumo": ".b_caption p",
    },
    "duckduckgo": {
        "url": "https://html.duckduckgo.com/html/?q={consulta}&kl=br-pt",
        "resultado": "div.result",
        "titulo": "a.result__a",
        "resumo": ".result__snippet",
    },
}

# Frases que aparecem quando o site desconfia de robô.
SINAIS_DE_BLOQUEIO = (
    "captcha",
    "unusual traffic",
    "tráfego incomum",
    "verificar que você",
)


def _link_real(href):
    """
    O DuckDuckGo embrulha o link verdadeiro no parâmetro "uddg".
    """

    if "uddg=" in href:

        alvo = parse_qs(urlparse(href).query).get("uddg")

        if alvo:
            return alvo[0]

    return href


def _abrir_navegador(p, ver):
    """
    Tenta o Edge (já vem no Windows) e depois o Chrome.
    """

    for canal in ("msedge", "chrome"):

        try:
            return p.chromium.launch(channel=canal, headless=not ver)
        except Exception:
            continue

    raise RuntimeError("Não achei o Edge nem o Chrome instalados.")


def buscar(consulta, motor="bing", ver=False, quantidade=5):
    """
    Devolve (resultados, bloqueado).
    resultados = lista de {"titulo", "link", "resumo"}
    """

    config = MOTORES[motor]

    with sync_playwright() as p:

        navegador = _abrir_navegador(p, ver)

        try:

            # new_page cria um perfil novo e vazio a cada execução.
            pagina = navegador.new_page(locale="pt-BR")

            pagina.goto(
                config["url"].format(consulta=quote_plus(consulta)),
                wait_until="domcontentloaded",
                timeout=20000
            )

            pagina.wait_for_timeout(1500)

            texto = pagina.inner_text("body").lower()

            resultados = []

            for bloco in pagina.locator(config["resultado"]).all()[:quantidade]:

                titulo = bloco.locator(config["titulo"])

                if titulo.count() == 0:
                    continue

                resumo = bloco.locator(config["resumo"])

                resultados.append({
                    "titulo": titulo.first.inner_text().strip(),
                    "link": _link_real(titulo.first.get_attribute("href") or ""),
                    "resumo": (
                        resumo.first.inner_text().strip()
                        if resumo.count() else ""
                    ),
                })

            bloqueado = not resultados and any(
                sinal in texto for sinal in SINAIS_DE_BLOQUEIO
            )

            return resultados, bloqueado

        finally:
            navegador.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("consulta", nargs="*")
    parser.add_argument("--motor", choices=list(MOTORES), default="bing")
    parser.add_argument("--ver", action="store_true")
    argumentos = parser.parse_args()

    consulta = " ".join(argumentos.consulta).strip()

    # Se rodou pelo botão "Run" do VS Code, não vem pesquisa: pergunta.
    if not consulta:
        consulta = input("O que você quer pesquisar? ").strip()

    if not consulta:
        raise SystemExit("Nenhuma pesquisa informada.")

    print(f"Pesquisando '{consulta}' no {argumentos.motor}...")

    try:
        resultados, bloqueado = buscar(consulta, argumentos.motor, argumentos.ver)
    except Exception as erro:
        print(f"ERRO: {erro}")
        raise SystemExit(1)

    if bloqueado:
        print("O site pediu verificação anti-robô. Tente o outro motor.")

    elif not resultados:
        print("Nenhum resultado lido. A página pode ter mudado por dentro.")
        print("Rode de novo com --ver para ver o que o navegador mostra.")

    for i, r in enumerate(resultados, 1):
        print(f"\n{i}. {r['titulo']}\n   {r['link']}\n   {r['resumo']}")
