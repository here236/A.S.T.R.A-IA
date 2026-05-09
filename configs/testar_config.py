# testar_config.py
import os
import configs.configuracoes as configuracoes

print("=== TESTANDO CONFIG ===")
print()

# Testa o caminho do Tesseract
print("1. Caminho do Tesseract:")
if os.path.exists(configuracoes.TESSERACT_PATH):
    print("Encontrado:", configuracoes.TESSERACT_PATH)
else:
    print("NÃO encontrado — verifique o caminho no config.py")

print()

# Testa se as pastas foram criadas
print("2. Pasta de logs:")
if os.path.exists(configuracoes.LOG_DIR):
    print("Criada:", configuracoes.LOG_DIR)
else:
    print("Não foi criada")

print()

print("3. Pasta de screenshots:")
if os.path.exists(configuracoes.SCREENSHOT_DIR):
    print("Criada:", configuracoes.SCREENSHOT_DIR)
else:
    print("Não foi criada")

print()

# Mostra as configurações carregadas
print("4. Configurações carregadas:")
print("   Idioma OCR:", configuracoes.IDIOMA_OCR)
print("   Intervalo de captura:", configuracoes.INTERVALO_CAPTURA, "segundos")
print("   Modo debug:", configuracoes.MODO_DEBUG)
print("   Salvar screenshot:", configuracoes.SALVAR_SCREENSHOT)

print()
print("=== TESTE CONCLUÍDO ===")