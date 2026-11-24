"""Modelos de dados do catálogo unificado de ferramentas da ASTRA."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Ferramenta:
    """Descrição declarativa de uma capacidade executável da ASTRA."""

    nome: str
    descricao: str
    categoria: str
    parametros: dict[str, Any] = field(default_factory=dict)
    nivel_risco: str = "baixo"
    requer_confirmacao: bool = False
    disponivel_para_ia: bool = True
    origem: str = "comando_tradicional"

    def como_schema_ia(self) -> dict[str, Any]:
        """Formato simples e independente de fornecedor para tool calling."""
        return {
            "type": "function",
            "function": {
                "name": self.nome,
                "description": self.descricao,
                "parameters": self.parametros or {
                    "type": "object",
                    "properties": {
                        "parametro": {
                            "type": "string",
                            "description": "Informação necessária para executar a ação."
                        }
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
