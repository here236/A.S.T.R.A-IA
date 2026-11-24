"""Cliente HTTP mínimo para o Ollama, sem dependências externas obrigatórias."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaIndisponivelError(RuntimeError):
    """O servidor local do Ollama não respondeu ou retornou dados inválidos."""


class ClienteOllama:
    def __init__(self, url="http://localhost:11434", modelo="qwen2.5:1.5b",
                 timeout=45, temperatura=0.1, max_tokens=500):
        self.url = url.rstrip("/")
        self.modelo = modelo
        self.timeout = timeout
        self.temperatura = temperatura
        self.max_tokens = max_tokens

    def gerar_resposta(self, instrucao_sistema, mensagem_usuario):
        """Envia mensagens ao endpoint /api/chat e devolve o texto do modelo."""
        if not isinstance(mensagem_usuario, str) or not mensagem_usuario.strip():
            raise ValueError("A mensagem para o modelo não pode estar vazia.")

        payload = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": str(instrucao_sistema)},
                {"role": "user", "content": mensagem_usuario},
            ],
            "stream": False,
            "keep_alive": "10m",
            "format": {
                "type": "object",
                "properties": {
                    "acao": {"type": "string", "enum": ["executar", "responder"]},
                    "ferramentas": {"type": "array", "items": {
                        "type": "object", "properties": {
                            "nome": {"type": "string"},
                            "argumentos": {"type": "object", "properties": {
                                "parametro": {"type": "string"}},
                                "required": ["parametro"], "additionalProperties": False}},
                        "required": ["nome", "argumentos"], "additionalProperties": False}},
                    "resposta": {"type": "string"}},
                "required": ["acao", "ferramentas", "resposta"],
                "additionalProperties": False
            },
            "options": {
                "temperature": self.temperatura,
                "num_predict": self.max_tokens,
                "num_ctx": 8192,
            },
        }
        requisicao = Request(
            f"{self.url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(requisicao, timeout=self.timeout) as resposta_http:
                dados = json.loads(resposta_http.read().decode("utf-8"))
            conteudo = dados.get("message", {}).get("content")
            if not isinstance(conteudo, str) or not conteudo.strip():
                raise ValueError("O Ollama retornou uma resposta vazia.")
            return conteudo.strip()
        except (HTTPError, URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError) as erro:
            raise OllamaIndisponivelError(
                f"Não foi possível obter uma resposta válida do Ollama: {erro}"
            ) from erro
