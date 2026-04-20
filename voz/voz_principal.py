'''
    Cérebro do sistema de voz

    Responsabilidade:
    Controlar todo o fluxo da conversa
    Integrar os módulos
'''
def iniciar_conversa():
    while True:
        # fala = ouvir_usuario()
        # texto = converter_para_texto(fala)
        # resposta = processar_texto(texto)
        # falar_resposta(resposta)
        pass


"""
    Microfone
    ↓
    reconhecedor_fala → texto
    ↓
    processador_linguagem → intenção
    ↓
    comandos_voz → ação (se necessário)
    ↓
    gerar_resposta
    ↓
    sintetizador_voz → áudio
"""