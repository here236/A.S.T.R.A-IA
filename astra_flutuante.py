import sys
import math
import re
import wave
import struct
import tempfile
from pathlib import Path

from PySide6.QtCore import (
    Qt, QRectF, QUrl, QTimer, Signal, QPointF,
    QPropertyAnimation, QVariantAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient, QPen,
    QPixmap, QFont, QPainterPath, QGuiApplication,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QGraphicsOpacityEffect, QMenu,
)
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray


# Caminho da logo. Aceita .svg ou .png com fundo transparente.
# Se nao existir, desenha um "A".
LOGO_PATH = Path(__file__).parent / "assets" / "favicon.svg"

# Cor aplicada na logo quando ela e SVG (o Qt nao entende o modo escuro do CSS do SVG)
COR_LOGO = "#ffffff"

# Sons personalizados (.wav). O que nao for informado usa um bipe gerado automaticamente.
# Exemplo: "iniciando": "sons/iniciando.wav"
SONS_PERSONALIZADOS = {
    "iniciando": None,
    "pronta": None,
    "erro": None,
    "encerrando": None,
}

# Volume dos avisos sonoros, de 0.0 a 1.0
VOLUME_SONS = 0.6

# Tamanhos da interface
TAMANHO_LOGO = 88
LARGURA_PAINEL = 210
ALTURA_PAINEL = 58
LARGURA_CONECTOR = 40
MARGEM_JANELA = 8


def gerar_tom(caminho, notas, volume=0.5):
    # Gera um arquivo .wav simples a partir de uma lista de (frequencia_hz, duracao_s)
    taxa = 44100
    quadros = bytearray()
    for freq, dur in notas:
        total = int(taxa * dur)
        for i in range(total):
            # Envelope curto no inicio e no fim para evitar estalos
            env = min(1.0, i / (taxa * 0.01), (total - i) / (taxa * 0.03))
            valor = math.sin(2 * math.pi * freq * i / taxa) * env * volume
            quadros += struct.pack("<h", int(valor * 32767))
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(bytes(quadros))


class GerenciadorSons:
    # Notas dos sons padrao de cada evento
    NOTAS_PADRAO = {
        "iniciando": [(523, 0.12), (659, 0.12), (784, 0.20)],
        "pronta": [(880, 0.10), (1175, 0.22)],
        "erro": [(300, 0.15), (220, 0.30)],
        "encerrando": [(784, 0.12), (587, 0.12), (392, 0.22)],
    }

    def __init__(self):
        self._efeitos = {}
        self._pasta_tmp = Path(tempfile.mkdtemp(prefix="astra_sons_"))
        for evento, notas in self.NOTAS_PADRAO.items():
            personalizado = SONS_PERSONALIZADOS.get(evento)
            if personalizado and Path(personalizado).exists():
                caminho = Path(personalizado)
            else:
                caminho = self._pasta_tmp / f"{evento}.wav"
                gerar_tom(caminho, notas)
            efeito = QSoundEffect()
            efeito.setSource(QUrl.fromLocalFile(str(caminho)))
            efeito.setVolume(VOLUME_SONS)
            self._efeitos[evento] = efeito

    def tocar(self, evento):
        efeito = self._efeitos.get(evento)
        if efeito:
            efeito.play()


def carregar_logo(caminho, tamanho):
    # Carrega a logo como QPixmap. Para SVG, remove o CSS e forca a cor definida em COR_LOGO
    if not caminho.exists():
        return None
    if caminho.suffix.lower() == ".svg":
        texto = caminho.read_text(encoding="utf-8")
        texto = re.sub(r"<style>.*?</style>", "", texto, flags=re.S)
        texto = texto.replace("<svg ", f'<svg fill="{COR_LOGO}" ', 1)
        renderer = QSvgRenderer(QByteArray(texto.encode("utf-8")))
        if not renderer.isValid():
            return None
        # Renderiza em tamanho grande para ficar nitida em telas HiDPI
        proporcao = renderer.defaultSize().height() / max(1, renderer.defaultSize().width())
        largura = tamanho * 3
        img = QPixmap(largura, int(largura * proporcao))
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        return img
    img = QPixmap(str(caminho))
    return None if img.isNull() else img


def desenhar_borda_gradiente(p, rect, raio, brilho=0.0):
    # Fundo escuro com brilho azul no canto inferior direito, igual ao mockup
    caminho = QPainterPath()
    caminho.addRoundedRect(rect, raio, raio)

    fundo = QLinearGradient(rect.topLeft(), rect.bottomRight())
    fundo.setColorAt(0.0, QColor(18, 12, 24))
    fundo.setColorAt(0.5, QColor(5, 5, 9))
    fundo.setColorAt(1.0, QColor(8, 6, 40))
    p.fillPath(caminho, fundo)

    brilho_canto = QRadialGradient(rect.bottomRight(), rect.width() * 0.9)
    brilho_canto.setColorAt(0.0, QColor(70, 50, 255, int(110 + 100 * brilho)))
    brilho_canto.setColorAt(1.0, QColor(70, 50, 255, 0))
    p.fillPath(caminho, brilho_canto)

    # Borda: ciano embaixo a esquerda, cinza no meio, roxo embaixo a direita
    borda = QLinearGradient(rect.bottomLeft(), rect.bottomRight() - QPointF(0, rect.height() * 0.4))
    borda.setColorAt(0.0, QColor(47, 164, 255))
    borda.setColorAt(0.5, QColor(70, 70, 90))
    borda.setColorAt(1.0, QColor(110, 80, 255))
    p.setPen(QPen(borda, 1.6))
    p.setBrush(Qt.NoBrush)
    p.drawPath(caminho)

    # Halo extra usado quando a IA esta iniciando
    if brilho > 0:
        p.setPen(QPen(QColor(90, 120, 255, int(150 * brilho)), 3))
        p.drawPath(caminho)


class BotaoLogo(QWidget):
    clicado = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedSize(TAMANHO_LOGO, TAMANHO_LOGO)
        self.setCursor(Qt.PointingHandCursor)
        self._brilho = 0.0
        self._press_pos = None
        self._arrastando = False
        self._logo = carregar_logo(LOGO_PATH, TAMANHO_LOGO)

    def set_brilho(self, valor):
        self._brilho = valor
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        desenhar_borda_gradiente(p, rect, 24, self._brilho)

        if self._logo and not self._logo.isNull():
            lado = int(TAMANHO_LOGO * 0.62)
            img = self._logo.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - img.width()) / 2
            y = (self.height() - img.height()) / 2
            p.drawPixmap(int(x), int(y), img)
        else:
            p.setPen(QColor("white"))
            fonte = QFont()
            fonte.setPointSize(30)
            fonte.setBold(True)
            p.setFont(fonte)
            p.drawText(self.rect(), Qt.AlignCenter, "A")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._arrastando = False

    def mouseMoveEvent(self, e):
        # Depois de mover alguns pixels, entrega o arrasto para o sistema (funciona no Windows, X11 e Wayland)
        if self._press_pos is None or self._arrastando:
            return
        delta = e.globalPosition().toPoint() - self._press_pos
        if abs(delta.x()) + abs(delta.y()) > 6:
            self._arrastando = True
            handle = self.window().windowHandle()
            if handle:
                handle.startSystemMove()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and not self._arrastando:
            self.clicado.emit()
        self._press_pos = None


class Conector(QWidget):
    # Linha horizontal com um ponto em cada ponta, ligando o painel a logo
    def __init__(self):
        super().__init__()
        self.setFixedSize(LARGURA_CONECTOR, ALTURA_PAINEL)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = self.height() / 2
        x1, x2 = 6, self.width() - 6
        p.setPen(QPen(QColor(70, 110, 255, 200), 1.4))
        p.drawLine(QPointF(x1, y), QPointF(x2, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(60, 110, 255))
        p.drawEllipse(QPointF(x1, y), 3.2, 3.2)
        p.drawEllipse(QPointF(x2, y), 3.2, 3.2)


class PainelAcao(QWidget):
    clicado = Signal()

    def __init__(self, texto, icone):
        super().__init__()
        self.texto = texto
        self.icone = icone
        self._hover = False
        self.setFixedSize(LARGURA_PAINEL, ALTURA_PAINEL)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, _):
        self._hover = True
        self.update()

    def leaveEvent(self, _):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        desenhar_borda_gradiente(p, rect, 16, 0.5 if self._hover else 0.0)

        p.setPen(QColor(235, 235, 245))
        fonte_icone = QFont()
        fonte_icone.setPointSize(17)
        p.setFont(fonte_icone)
        p.drawText(QRectF(18, 0, 34, self.height()), Qt.AlignCenter, self.icone)

        fonte_texto = QFont()
        fonte_texto.setPointSize(13)
        p.setFont(fonte_texto)
        p.drawText(QRectF(62, 0, self.width() - 70, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self.texto)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicado.emit()


class AstraFlutuante(QWidget):
    # Pode ser emitido de qualquer thread da IA: ponte.estado_mudou.emit("pronta")
    estado_mudou = Signal(str)

    def __init__(self):
        super().__init__()

        # Janela sem borda, sempre no topo e sem aparecer na barra de tarefas
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.sons = GerenciadorSons()

        # Painel que aparece na lateral esquerda da logo
        self.painel = PainelAcao("Configurações", "⚙")
        self.painel.clicado.connect(self.abrir_configuracoes)
        self.conector = Conector()
        self.logo = BotaoLogo()
        self.logo.clicado.connect(self.alternar_painel)

        # Agrupa painel e conector para poder aplicar o efeito de fade nos dois juntos
        self.extra = QWidget()
        layout_extra = QHBoxLayout(self.extra)
        layout_extra.setContentsMargins(0, 0, 0, 0)
        layout_extra.setSpacing(0)
        layout_extra.addWidget(self.painel)
        layout_extra.addWidget(self.conector)
        self.opacidade = QGraphicsOpacityEffect(self.extra)
        self.opacidade.setOpacity(0.0)
        self.extra.setGraphicsEffect(self.opacidade)
        self.extra.hide()

        # Ordem da esquerda para a direita: painel, conector, logo
        layout = QHBoxLayout(self)
        layout.setContentsMargins(MARGEM_JANELA, MARGEM_JANELA, MARGEM_JANELA, MARGEM_JANELA)
        layout.setSpacing(0)
        layout.addWidget(self.extra)
        layout.addWidget(self.logo)

        self.aberto = False
        self.anim_fade = QPropertyAnimation(self.opacidade, b"opacity", self)
        self.anim_fade.setDuration(180)
        self.anim_fade.setEasingCurve(QEasingCurve.OutCubic)

        # Pulso do brilho enquanto a IA esta iniciando
        self.pulso = QVariantAnimation(self)
        self.pulso.setDuration(1400)
        self.pulso.setStartValue(0.0)
        self.pulso.setKeyValueAt(0.5, 1.0)
        self.pulso.setEndValue(0.0)
        self.pulso.setLoopCount(-1)
        self.pulso.valueChanged.connect(self.logo.set_brilho)

        self.estado_mudou.connect(self.aplicar_estado)
        self.adjustSize()

    def aplicar_estado(self, estado):
        # Troca o visual e toca o aviso sonoro de cada estado da IA
        if estado == "iniciando":
            self.pulso.start()
        else:
            self.pulso.stop()
            self.logo.set_brilho(0.0)
        self.sons.tocar(estado)

    def alternar_painel(self):
        self.fechar_painel() if self.aberto else self.abrir_painel()

    def _limitar_na_tela(self, x, y):
        tela = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        area = tela.availableGeometry()
        x = max(area.left(), min(x, area.right() - self.width() + 1))
        y = max(area.top(), min(y, area.bottom() - self.height() + 1))
        return x, y

    def abrir_painel(self):
        self.aberto = True
        largura_antiga = self.width()
        self.extra.show()
        self.adjustSize()
        # Cresce para a esquerda, mantendo a logo no mesmo lugar
        x = self.x() - (self.width() - largura_antiga)
        self.move(*self._limitar_na_tela(x, self.y()))
        self.anim_fade.stop()
        self.anim_fade.setStartValue(self.opacidade.opacity())
        self.anim_fade.setEndValue(1.0)
        self.anim_fade.start()

    def fechar_painel(self):
        self.aberto = False
        self.anim_fade.stop()
        self.anim_fade.setStartValue(self.opacidade.opacity())
        self.anim_fade.setEndValue(0.0)
        self.anim_fade.start()
        QTimer.singleShot(self.anim_fade.duration() + 20, self._finalizar_fechamento)

    def _finalizar_fechamento(self):
        if self.aberto:
            return
        largura_antiga = self.width()
        self.extra.hide()
        self.adjustSize()
        x = self.x() + (largura_antiga - self.width())
        self.move(*self._limitar_na_tela(x, self.y()))

    def abrir_configuracoes(self):
        # Coloque aqui a abertura da sua tela de configuracoes
        print("Abrir configuracoes")

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        menu.addAction("Configurações", self.abrir_configuracoes)
        menu.addAction("Sair", self.encerrar)
        menu.exec(e.globalPos())

    def encerrar(self):
        self.estado_mudou.emit("encerrando")
        QTimer.singleShot(700, QApplication.instance().quit)


def main():
    app = QApplication(sys.argv)
    janela = AstraFlutuante()

    # Posicao inicial: canto direito da tela, na altura do meio
    area = QGuiApplication.primaryScreen().availableGeometry()
    janela.move(area.right() - janela.width() - 24, area.center().y() - janela.height() // 2)
    janela.show()

    # Aviso sonoro de inicializacao
    janela.estado_mudou.emit("iniciando")

    # Troque este timer pelo momento real em que sua IA terminar de carregar
    QTimer.singleShot(2500, lambda: janela.estado_mudou.emit("pronta"))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
