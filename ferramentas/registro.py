"""Registro único das ferramentas disponíveis na ASTRA."""

from typing import Iterable, Optional

from .modelos import Ferramenta
from .politicas import INSTRUCOES_SEGURANCA_IA, obter_politica


class RegistroFerramentas:
    def __init__(self):
        self._ferramentas: dict[str, Ferramenta] = {}

    def registrar(self, ferramenta: Ferramenta) -> None:
        if not ferramenta.nome or not ferramenta.nome.replace("_", "").isalnum():
            raise ValueError("Nome de ferramenta inválido.")
        if ferramenta.nome in self._ferramentas:
            raise ValueError(f"Ferramenta já registrada: {ferramenta.nome}")
        self._ferramentas[ferramenta.nome] = ferramenta

    def registrar_comando(self, comando) -> Ferramenta:
        """Adapta um comando legado para o catálogo sem alterar sua função."""
        politica = obter_politica(comando.nome)
        ferramenta = Ferramenta(
            nome=comando.nome,
            descricao=comando.descricao or f"Executa a capacidade {comando.nome} da ASTRA.",
            categoria=politica.categoria,
            parametros={
                "type": "object",
                "properties": {
                    "parametro": {
                        "type": "string",
                        "description": "Parâmetro textual da operação. Use string vazia quando não necessário.",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
            nivel_risco=politica.nivel_risco,
            requer_confirmacao=(comando.critico or politica.requer_confirmacao or politica.nivel_risco != "baixo"),
            disponivel_para_ia=politica.disponivel_para_ia,
        )
        self.registrar(ferramenta)
        return ferramenta

    def obter(self, nome: str) -> Optional[Ferramenta]:
        return self._ferramentas.get(nome)

    def listar(self, *, apenas_ia: bool = False) -> list[Ferramenta]:
        ferramentas = list(self._ferramentas.values())
        if apenas_ia:
            ferramentas = [f for f in ferramentas if f.disponivel_para_ia]
        return sorted(ferramentas, key=lambda f: (f.categoria, f.nome))

    def schemas_ia(self) -> list[dict]:
        return [f.como_schema_ia() for f in self.listar(apenas_ia=True)]

    @staticmethod
    def instrucoes_seguranca_ia() -> str:
        """Regras que devem acompanhar o catálogo no prompt do modelo."""
        return INSTRUCOES_SEGURANCA_IA

    def catalogo_ia(self) -> list[dict]:
        """Metadados completos para o planejador, além do schema de tool calling."""
        return [
            {
                "name": f.nome,
                "description": f.descricao,
                "category": f.categoria,
                "risk": f.nivel_risco,
                "requires_confirmation": f.requer_confirmacao,
                "parameters": f.parametros,
            }
            for f in self.listar(apenas_ia=True)
        ]

    def nomes(self, *, apenas_ia: bool = False) -> list[str]:
        return [f.nome for f in self.listar(apenas_ia=apenas_ia)]

    def __len__(self) -> int:
        return len(self._ferramentas)
