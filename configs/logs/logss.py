import logging
from configs import configuracoes

logging.basicConfig(
    filename=configuracoes.CAMINHO_LOG,
    level=configuracoes.NIVEL_LOG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger("ASTRA")


# Exemplo de uso — só roda se este arquivo for executado diretamente,
# não quando outro módulo faz "import logss" pra pegar o logger configurado.
if __name__ == "__main__":
    logger.info("Tela Capturada")
    logger.error("Elemento não encontrado")