# A.S.T.R.A
projeto integrador FATEC Carapicuíba 

**A.S.T.R.A** é um assistente inteligente de acessibilidade que une leitura de tela e conversa por voz, pensado especialmente para pessoas com deficiência visual.

O projeto combina dois sistemas complementares:

- **Leitor de Tela com IA** — captura o conteúdo visível na tela (elementos de interface ou screenshot), extrai o texto por OCR e usa IA para interpretar e priorizar o que é relevante — botões, títulos, alertas — antes de descrever tudo em áudio para o usuário.

- **IA de Conversa por Voz** — ouve comandos falados, entende a intenção por trás deles e responde em voz de forma natural, no estilo de assistentes como Siri, Alexa ou Google Assistant.

Integrados, os dois sistemas formam um assistente completo: o usuário fala um comando como *"leia essa tela"*, a IA entende, captura o conteúdo, interpreta e responde em áudio — tornando a navegação em sistemas, sites e aplicações mais acessível e natural.

## Tecnologias

- Python
- Tesseract OCR para reconhecimento de texto
- UI Automation / captura de tela para leitura de interfaces
- Reconhecimento e síntese de voz (STT/TTS)
- Processamento de linguagem natural (NLP/LLM) para interpretação de comandos e contexto

## Estrutura do projeto
A.S.T.R.A-IA/
├── captura_tela/ # Captura de tela, detecção de elementos e OCR

├── voz/ # Reconhecimento de fala, NLP, diálogo e síntese de voz

├── configs/ # Configurações centralizadas do sistema

└── main.py # Ponto de entrada
