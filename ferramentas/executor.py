"""Executor controlado para chamadas diretas ao catálogo de ferramentas."""

from datetime import date, datetime
from .politicas import validar_argumentos


class ExecutorFerramentas:
    def __init__(self, gerenciador_comandos, registro):
        self._gerenciador = gerenciador_comandos
        self._registro = registro

    def executar(self, nome: str, argumentos=None, *, confirmado: bool = False) -> dict:
        ferramenta = self._registro.obter(nome)
        if ferramenta is None:
            return self._resultado("nao_encontrada", "Ferramenta não cadastrada.")

        if not ferramenta.disponivel_para_ia:
            return self._resultado("nao_autorizada", "Esta ferramenta não está disponível para uso pela IA.")

        argumentos = argumentos or {}
        valido, erro = validar_argumentos(argumentos)
        if not valido:
            return self._resultado("argumentos_invalidos", erro)

        if ferramenta.requer_confirmacao and not confirmado:
            # Quando disponível, registra a ação no mesmo mecanismo de
            # confirmação por voz usado pelos comandos tradicionais.
            solicitar = getattr(self._gerenciador, "solicitar_confirmacao_ferramenta", None)
            if callable(solicitar):
                return solicitar(nome, argumentos.get("parametro", ""))
            return {
                "status": "confirmacao_necessaria",
                "ferramenta": nome,
                "mensagem": "A ação precisa de confirmação explícita do usuário antes da execução.",
                "executado": False,
            }

        parametro = argumentos.get("parametro", "")
        resultado = self._gerenciador.executar_ferramenta(
            nome,
            parametro,
            confirmado=confirmado,
        )
        return {
            "status": resultado.status.value,
            "ferramenta": resultado.comando or nome,
            "mensagem": resultado.mensagem,
            "resposta": resultado.resposta_falada,
            "dados": self._normalizar_dados(resultado.dados),
            "executado": resultado.status.value == "sucesso",
            "aguardando_confirmacao": resultado.status.value == "aguardando_confirmacao",
        }

    @classmethod
    def _normalizar_dados(cls, valor):
        """Mantém o retorno serializável para futuras APIs de modelos locais."""
        if valor is None or isinstance(valor, (str, int, float, bool)):
            return valor
        if isinstance(valor, (datetime, date)):
            return valor.isoformat()
        if isinstance(valor, dict):
            return {str(k): cls._normalizar_dados(v) for k, v in valor.items()}
        if isinstance(valor, (list, tuple, set)):
            return [cls._normalizar_dados(v) for v in valor]
        return str(valor)

    @staticmethod
    def _resultado(status: str, mensagem: str) -> dict:
        return {
            "status": status,
            "mensagem": mensagem,
            "executado": False,
        }
