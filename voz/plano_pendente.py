"""Sessão de composição: coleta e confirmação antes de qualquer efeito.

Não recebe resultados de OCR/web como instruções. A sequência é congelada
antes da execução, e cada aprovação pertence a uma única etapa e argumento.
"""
from dataclasses import replace
from pathlib import Path
from ia.conteudo_documento import gerar_resumo
import time
from ia.plano_composto import CRIACOES
from ia.escopo_ferramentas import _COMPOSIVEIS
from ferramentas.politicas import validar_argumentos
from .gerenciador_dialogo import GerenciadorDialogo, ParametroPendente, parametro_faltante, CANCELAMENTOS
from .utilitarios_voz import normalizar_texto, log

TEMPO_PLANO = 60.0

CONFIRMACOES = CRIACOES | {'escrever_texto'}


class PlanoPendente:
    def __init__(self, gerenciador, etapas):
        self.gerenciador = gerenciador
        self.etapas = list(etapas)
        self.aprovadas = {}
        self.resultados = []
        self.pendente = None
        self.tipo = None
        self.prazo = 0.0
        self.ativo = True
        self.tentativas = 2

    def renovar_prazo(self):
        self.prazo = time.monotonic() + TEMPO_PLANO

    def cancelar(self, mensagem='Tudo bem, cancelei o plano. Nenhuma etapa foi executada.'):
        self.ativo = False
        self.pendente = None
        self.aprovadas.clear()
        return mensagem

    def _valido(self):
        if not 2 <= len(self.etapas) <= 4 or len({e.nome for e in self.etapas}) != len(self.etapas):
            return False
        for i, e in enumerate(self.etapas):
            f = self.gerenciador.registro_ferramentas.obter(e.nome)
            if f is None or not f.disponivel_para_ia or not validar_argumentos({'parametro': e.parametro})[0]:
                return False
            if e.nome == 'escrever_texto':
                if (len(self.etapas) != 2 or i != 1
                        or self.etapas[0].nome not in {'criar_documento', 'criar_texto'}
                        or not e.assunto.strip() or len(e.assunto) > 300
                        or len(e.parametro) > 600 or not f.requer_confirmacao
                        or f.nivel_risco != 'medio'):
                    return False
            elif e.assunto:
                return False
            elif e.nome in CRIACOES:
                if not f.requer_confirmacao or f.nivel_risco != 'medio':
                    return False
            elif e.nome not in _COMPOSIVEIS or e.parametro or f.requer_confirmacao or f.nivel_risco != 'baixo':
                return False
        return True

    def _descricao(self, etapa):
        if etapa.nome == 'escrever_texto':
            return f'escrever um resumo sobre {etapa.assunto} no arquivo criado'
        if etapa.nome not in CRIACOES:
            return etapa.nome.replace('_', ' ')
        from arquivos.gerenciador_arquivos import _limpar_nome, _separar_local, _separar_colunas
        from configs import configuracoes_voz as cfg
        base, colunas = _separar_colunas(etapa.parametro) if etapa.nome == 'criar_planilha' else (etapa.parametro, '')
        nome, local = _separar_local(base)
        return (f'{etapa.nome.replace("_", " ")} com nome {_limpar_nome(nome)} em {local or cfg.LOCAL_PADRAO}'
                + (f' com as colunas {colunas.strip()}' if colunas.strip() else ''))

    def avancar(self):
        if not self.ativo:
            return 'O plano não está mais ativo.'
        if not self._valido():
            return self.cancelar('Não executei o plano: ferramenta repetida, indisponível ou fora do escopo permitido.')
        # Antes de confirmar, recolhe TODOS os argumentos pendentes.
        for i, e in enumerate(self.etapas):
            pergunta = parametro_faltante(e.nome, e.parametro)
            if pergunta:
                self.pendente, self.tipo = i, 'parametro'
                self.renovar_prazo()
                return f'Para {e.nome.replace("_", " ")}: {pergunta}'
        for i, e in enumerate(self.etapas):
            if e.nome in CONFIRMACOES and self.aprovadas.get(i) != e:
                if e.nome == 'escrever_texto' and not e.parametro:
                    try:
                        texto = gerar_resumo(e.assunto)
                        if not isinstance(texto, str) or not texto.strip() or len(texto) > 600:
                            raise ValueError('Conteúdo inválido.')
                    except Exception as erro:
                        detalhe = f': {erro}' if isinstance(erro, ValueError) else ''
                        log(f'Falha ao gerar conteúdo: {type(erro).__name__}{detalhe}', 'AVISO')
                        return self.cancelar('Não consegui gerar o resumo. Cancelei o plano. Nenhum arquivo foi criado.')
                    e = replace(e, parametro=texto.strip())
                    self.etapas[i] = e
                self.pendente, self.tipo = i, 'confirmacao'
                self.tentativas = 2
                self.renovar_prazo()
                if e.nome == 'escrever_texto':
                    return (f'Confirma gravar no arquivo que será criado este resumo gerado pela IA: '
                            f'{e.parametro} Diga sim ou não.')
                plano = '; depois '.join(self._descricao(x) for x in self.etapas)
                return f'Plano: {plano}. Confirma a etapa {i+1}, {self._descricao(e)}? Diga sim ou não.'
        return self._executar()

    def responder(self, texto):
        if not self.ativo or time.monotonic() >= self.prazo:
            return self.cancelar('O prazo do plano terminou. Nenhuma etapa foi executada.')
        normalizado = normalizar_texto(texto)
        if normalizado in CANCELAMENTOS:
            return self.cancelar()
        if not normalizado:
            return ''
        i = self.pendente
        e = self.etapas[i]
        if self.tipo == 'parametro':
            pendente = ParametroPendente(e.nome, e.parametro, True, '', self.prazo)
            parametro = GerenciadorDialogo.completar(pendente, texto)
            if (normalizado == 'sim' or not parametro or len(parametro) > 4000
                    or parametro_faltante(e.nome, parametro)):
                return 'Informe o nome da criação ou diga cancelar.'
            self.etapas[i] = replace(e, parametro=parametro)
            return self.avancar()
        if normalizado != 'sim':
            self.tentativas -= 1
            if self.tentativas < 0:
                return self.cancelar('Não recebi uma confirmação válida. Cancelei o plano.')
            return 'Diga sim para confirmar esta etapa ou não para cancelar o plano.'
        self.aprovadas[i] = e
        return self.avancar()

    def _executar(self):
        # Revalida antes de qualquer efeito e antes de cada ferramenta. Não
        # reconsulta o modelo. Um erro não dispara nova tentativa automática.
        if not self._valido() or any(e.nome in CONFIRMACOES and self.aprovadas.get(i) != e
                                     for i, e in enumerate(self.etapas)):
            return self.cancelar('Não executei o plano: a autorização não está mais válida.')
        self.ativo = False
        self.pendente = None
        falas = []
        try:
            for i, e in enumerate(self.etapas):
                if not self._valido():
                    falas.append('As permissões mudaram. Interrompi as etapas restantes.')
                    break
                try:
                    if e.nome == 'escrever_texto':
                        r = self._escrever_no_criado(e, i)
                    else:
                        r = self.gerenciador.executor_ferramentas.executar(
                            e.nome, {'parametro': e.parametro}, confirmado=self.aprovadas.get(i) == e)
                except Exception as erro:
                    log(f'Falha na etapa {i+1}: {erro}', 'ERRO')
                    falas.append(f'Falha na etapa {i+1}. Interrompi o plano.')
                    break
                self.resultados.append(r)
                fala = r.get('resposta') or r.get('mensagem') or 'Sem resultado informado.'
                falas.append(fala)
                log(f'Plano etapa {i+1}/{len(self.etapas)}: {e.nome}: {r.get("status")}')
                if r.get('status') != 'sucesso' or r.get('executado') is not True:
                    # Não deixe uma pendência inesperada executar fora do plano.
                    self.gerenciador.confirmacao.cancelar()
                    self.gerenciador.dialogo.cancelar()
                    falas.append('Interrompi o plano. As etapas restantes não foram executadas.')
                    break
        finally:
            self.aprovadas.clear()
        return ' '.join(falas)

    def _escrever_no_criado(self, etapa, indice):
        """Só escreve no caminho comprovado pela criação imediatamente anterior."""
        from arquivos.gerenciador_arquivos import gerenciador_arquivos
        anterior = self.resultados[indice - 1]
        dados = anterior.get('dados') or {}
        caminho = dados.get('caminho')
        erro = {'status': 'erro', 'executado': False,
                'mensagem': 'Não consegui verificar a escrita no arquivo recém-criado.'}
        if (anterior.get('status') != 'sucesso' or anterior.get('executado') is not True
                or dados.get('verificacao') != 'existe' or not caminho
                or self.aprovadas.get(indice) != etapa):
            return erro
        destino = Path(caminho)
        atual = gerenciador_arquivos.atual
        extensao = '.docx' if self.etapas[indice - 1].nome == 'criar_documento' else '.txt'
        if (atual is None or destino.suffix != extensao or destino.is_symlink()
                or not destino.is_file() or destino.resolve() != Path(atual).resolve()):
            return erro
        if extensao == '.docx':
            from docx import Document
            if Document(destino).paragraphs:
                return erro
        elif destino.read_text(encoding='utf-8') != '':
            return erro
        resultado = self.gerenciador.executor_ferramentas.executar(
            'escrever_texto', {'parametro': etapa.parametro}, confirmado=True)
        if resultado.get('status') != 'sucesso' or resultado.get('executado') is not True:
            return resultado
        salvo = (resultado.get('dados') or {}).get('caminho')
        if not salvo or Path(salvo).resolve() != destino.resolve():
            return erro
        if extensao == '.docx':
            paragrafos = [p.text for p in Document(destino).paragraphs]
            confere = paragrafos == [etapa.parametro]
        else:
            confere = destino.read_text(encoding='utf-8') == etapa.parametro + '\n'
        if not confere:
            return erro
        resultado['dados']['verificacao'] = 'conteudo_conferido'
        resultado['resposta'] = f'Resumo salvo e conferido em {destino}.'
        return resultado
