# Organização da ASTRA

## Estrutura principal

```text
ASTRA/
├── arquivos/                 # Tudo que cria, lê, edita e formata arquivos
│   ├── __init__.py
│   ├── gerenciador_arquivos.py
│   └── estilo_planilha.py
├── captura_tela/             # Captura, OCR e identificação de elementos
├── configs/                  # Configurações e caminhos
├── pesquisa/                 # Busca web e leitura de páginas
├── voz/                      # Reconhecimento, comandos, diálogo e síntese
├── tests/                    # Testes automatizados
├── assets/                   # Recursos visuais
├── Audios/                   # Áudios de teste/temporários
├── main.py
└── requirements.txt
```

## Regra de organização

- `arquivos/`: operações sobre documentos, planilhas, apresentações, textos e pastas.
- `pesquisa/`: pesquisa na web e extração de conteúdo de páginas.
- `voz/`: entrada por voz, comandos e resposta falada. Não deve conter a implementação de manipulação de arquivos.
- `captura_tela/`: captura de tela, OCR e localização de texto/elementos.
- `configs/`: configurações compartilhadas.

## Imports atualizados

Use os imports novos:

```python
from arquivos.gerenciador_arquivos import gerenciador_arquivos
from arquivos import estilo_planilha
from pesquisa import pesquisa_web
```

O arquivo `voz/arquivos_voz.py` foi mantido apenas como uma camada de compatibilidade para scripts antigos. Novos códigos devem importar de `arquivos.gerenciador_arquivos`.

## Execução

Na raiz do projeto:

```powershell
python main.py
```

Ou, para iniciar diretamente o fluxo de voz:

```powershell
python -m voz.voz_principal
```

## Observações

- A pasta antiga `manipulacao_arquivos/` foi incorporada a `arquivos/`.
- `pesquisa/comandos_arquivos_pesquisa.py` permanece no pacote `pesquisa` porque contém o registro de comandos que conectam pesquisa e criação de arquivos; a implementação de gravação/edição está em `arquivos/`.
- A captura de tela depende do ambiente gráfico do Windows e não pode ser validada em ambientes sem display.
