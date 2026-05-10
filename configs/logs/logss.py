import logging
import configuracoes

logging.basicConfig(
    filename=configuracoes.CAMINHO_LOG,
    level=configuracoes.NIVEL_LOG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger("ASTRA")


logger.info("Tela Capturada")
logger.error("Elemento nãO encotrado")