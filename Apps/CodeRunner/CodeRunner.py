#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# CodeRunner.py - C++ Code Runner for OJ Practice
#
# Created by skywind on 2026/05/05
# Last Modified: 2026/05/05 00:00:00
#
#======================================================================
import sys
import os
import copy
import math
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QTabBar, QSplitter,
    QTextEdit, QLabel, QWidget, QAction,
    QVBoxLayout, QShortcut, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QSize, QPointF, QTimer, QRect
from PyQt5.QtGui import (
    QKeySequence, QFontDatabase, QIcon, QPainter, QPixmap,
    QColor, QPen, QBrush, QPolygonF, QSyntaxHighlighter,
    QTextDocument, QTextCursor
)


#----------------------------------------------------------------------
# DPI factor
#----------------------------------------------------------------------
def _dpi_factor () -> float:
    """Calculate DPI scaling factor (logical DPI / 96)."""
    screen = QApplication.primaryScreen()
    if screen:
        return screen.logicalDotsPerInch() / 96.0
    return 1.0


#----------------------------------------------------------------------
# Platform monospace font detection
#----------------------------------------------------------------------
_MONOSPACE_PRIORITY = {
    'win32': ['Consolas', 'Courier New'],
    'darwin': ['Menlo', 'SF Mono'],
}

# Linux has many distros, use a common fallback list
_LINUX_MONOSPACE = ['DejaVu Sans Mono', 'Ubuntu Mono']


def _detect_monospace_font () -> str:
    """Detect the best available monospace font for the current platform."""
    db = QFontDatabase()
    available = db.families()
    candidates = _MONOSPACE_PRIORITY.get(sys.platform, _LINUX_MONOSPACE)
    for name in candidates:
        if name in available:
            return name
    return 'monospace'


def _init_font_defaults (settings) -> None:
    """Initialize Settings font defaults based on platform."""
    font = _detect_monospace_font()
    settings.editor_font_family = font
    settings.io_font_family = font


def _make_io_section (settings, label_text:str, text_edit:QWidget,
                      dpi:float=1.0) -> QWidget:
    """Wrap a text edit widget with a label header (INPUT or OUTPUT)."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    font = label.font()
    font.setBold(True)
    font.setPointSize(settings.io_font_size)
    label.setFont(font)
    label.setFixedHeight(label.sizeHint().height() + int(4 * dpi))
    layout.addWidget(label)
    layout.addWidget(text_edit, 1)
    container._section_label = label
    return container


#----------------------------------------------------------------------
# Toolbar icon generation
#----------------------------------------------------------------------
_ICON_BASE = 24

# Custom colors for semantic toolbar icons
_COLOR_NEW = QColor(120, 120, 120)  # gray: neutral
_COLOR_SAVE = QColor(60, 100, 200)  # blue: floppy disk
_COLOR_OPEN = QColor(220, 180, 40)  # yellow: folder
_COLOR_RUN = QColor(0, 160, 0)  # green: go
_COLOR_TEST = QColor(50, 100, 220)  # blue: experiment
_COLOR_STOP = QColor(220, 50, 50)  # red: halt


def _generate_new_icon (dpi:float=1.0) -> QIcon:
    """Generate a New icon: document with folded corner,
    gray border/white fill."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    border = _COLOR_NEW
    fill = QColor(255, 255, 255)
    margin = 3
    fold = 5
    polygon = QPolygonF([
        QPointF(margin, margin),
        QPointF(_ICON_BASE - margin, margin),
        QPointF(_ICON_BASE - margin, _ICON_BASE - margin - fold),
        QPointF(_ICON_BASE - margin - fold, _ICON_BASE - margin),
        QPointF(margin, _ICON_BASE - margin),
    ])
    p.setPen(QPen(border, 1.2))
    p.setBrush(QBrush(fill))
    p.drawPolygon(polygon)
    fold_fill = QColor(180, 180, 180)
    p.setBrush(QBrush(fold_fill))
    p.setPen(QPen(border, 0.8))
    fold_tri = QPolygonF([
        QPointF(_ICON_BASE - margin, _ICON_BASE - margin - fold),
        QPointF(_ICON_BASE - margin - fold, _ICON_BASE - margin),
        QPointF(_ICON_BASE - margin, _ICON_BASE - margin),
    ])
    p.drawPolygon(fold_tri)
    p.setPen(QPen(QColor(30, 30, 30), 1.3))
    line_y1 = margin + 7
    line_y2 = margin + 11
    line_left = margin + 3
    line_right = _ICON_BASE - margin - fold - 1
    p.drawLine(QPointF(line_left, line_y1), QPointF(line_right, line_y1))
    p.drawLine(QPointF(line_left, line_y2), QPointF(line_right - 3, line_y2))
    p.end()
    return QIcon(pixmap)


def _generate_save_icon (dpi:float=1.0) -> QIcon:
    """Generate a Save icon: 3.5-inch floppy disk, blue."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    color = _COLOR_SAVE
    lighter = QColor(color.red() + 60, color.green() + 60, color.blue() + 40)
    darker = QColor(color.red() - 20, color.green() - 20, color.blue() - 30)
    m = 3
    p.setPen(QPen(darker, 1.0))
    p.setBrush(QBrush(color))
    p.drawRoundedRect(m, m, _ICON_BASE - 2 * m, _ICON_BASE - 2 * m, 1.5, 1.5)
    sl_m = 5
    sl_h = 7
    p.setPen(QPen(darker, 0.8))
    p.setBrush(QBrush(lighter))
    p.drawRect(m + sl_m, m, _ICON_BASE - 2 * m - 2 * sl_m, sl_h)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    hole_w = _ICON_BASE - 2 * m - 2 * sl_m - 6
    hole_h = 3
    p.drawRect(m + sl_m + 3, m + 2, hole_w, hole_h)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    lb_m = 5
    lb_h = 6
    lb_top = _ICON_BASE - m - lb_h - 2
    p.setPen(QPen(darker, 0.8))
    p.setBrush(QBrush(QColor(255, 255, 255, 230)))
    p.drawRect(m + lb_m, lb_top, _ICON_BASE - 2 * m - 2 * lb_m, lb_h)
    p.end()
    return QIcon(pixmap)


def _generate_open_icon (dpi:float=1.0) -> QIcon:
    """Generate an Open icon: Win2K-style folder, yellow."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    color = _COLOR_OPEN
    darker = QColor(color.red() - 50, color.green() - 50, color.blue() - 10)
    p.setPen(QPen(darker, 1.0))
    p.setBrush(QBrush(color))
    m = 3
    p.drawRoundedRect(m, 6, _ICON_BASE - 2 * m, _ICON_BASE - m - 6, 1.0, 1.0)
    tab_w = 8
    p.setBrush(QBrush(darker))
    p.drawRoundedRect(m, 2, tab_w, 6, 1.0, 1.0)
    flap_m = m + 3
    flap_top = 8
    p.setBrush(QBrush(color))
    p.drawRoundedRect(flap_m, flap_top, _ICON_BASE - flap_m - m,
                      _ICON_BASE - m - flap_top, 1.0, 1.0)
    p.setPen(QPen(QColor(255, 255, 255, 100), 1.0))
    p.drawLine(QPointF(flap_m + 1, flap_top + 0.5),
               QPointF(_ICON_BASE - m - 1, flap_top + 0.5))
    p.end()
    return QIcon(pixmap)


def _generate_test_icon (dpi:float=1.0) -> QIcon:
    """Generate a Test icon: Erlenmeyer flask shape (experiment/test), blue."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    color = _COLOR_TEST
    p.setPen(QPen(color, 1.2))
    p.setBrush(QBrush(color))
    body_bottom = _ICON_BASE - 4.0
    neck_w = 5.0
    body_w = 15.0
    body_h = 11.0
    neck_h = 5.0
    cx = _ICON_BASE / 2.0
    neck_left = cx - neck_w / 2.0
    neck_right = cx + neck_w / 2.0
    neck_top = body_bottom - body_h - neck_h
    neck_bottom = body_bottom - body_h
    body_left = cx - body_w / 2.0
    body_right = cx + body_w / 2.0
    polygon = QPolygonF([
        QPointF(neck_left, neck_top),
        QPointF(neck_right, neck_top),
        QPointF(neck_right, neck_bottom),
        QPointF(body_right, body_bottom),
        QPointF(body_left, body_bottom),
        QPointF(neck_left, neck_bottom),
    ])
    p.drawPolygon(polygon)
    p.setPen(QPen(color, 1.5))
    liquid_y = body_bottom - 4.0
    liquid_left = body_left + 2.5
    liquid_right = body_right - 2.5
    p.drawLine(QPointF(liquid_left, liquid_y),
               QPointF(liquid_right, liquid_y))
    p.end()
    return QIcon(pixmap)


def _generate_settings_icon (dpi:float=1.0) -> QIcon:
    """Generate a Settings icon: simple gear/cog shape."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    color = QApplication.palette().windowText().color()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    cx = cy = _ICON_BASE / 2.0
    body_r = 5.5
    tooth_len = 3.5
    tooth_w = 3.5
    num_teeth = 6
    for i in range(num_teeth):
        angle = 2.0 * math.pi * i / num_teeth - math.pi / 2.0
        tx = cx + (body_r + tooth_len / 2.0) * math.cos(angle)
        ty = cy + (body_r + tooth_len / 2.0) * math.sin(angle)
        p.save()
        p.translate(tx, ty)
        p.rotate(math.degrees(angle) + 90.0)
        p.drawRoundedRect(int(-tooth_w / 2), int(-tooth_len / 2),
                          int(tooth_w), int(tooth_len), 1, 1)
        p.restore()
    p.setBrush(QBrush(color))
    p.drawEllipse(QPointF(cx, cy), body_r, body_r)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)
    p.end()
    return QIcon(pixmap)


def _generate_run_icon (dpi:float=1.0) -> QIcon:
    """Generate a Run icon: play triangle, green."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    color = _COLOR_RUN
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    margin = 3.0
    tri_top = margin
    tri_bottom = _ICON_BASE - margin
    tri_left = margin
    tri_right = _ICON_BASE - margin
    mid_y = (tri_top + tri_bottom) / 2.0
    polygon = QPolygonF([
        QPointF(tri_left, tri_top),
        QPointF(tri_right, mid_y),
        QPointF(tri_left, tri_bottom),
    ])
    p.drawPolygon(polygon)
    p.end()
    return QIcon(pixmap)


def _generate_stop_icon (dpi:float=1.0) -> QIcon:
    """Generate a Stop icon: filled square, red."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(dpi, dpi)
    color = _COLOR_STOP
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    margin = 4
    p.drawRoundedRect(margin, margin, _ICON_BASE - 2 * margin,
                      _ICON_BASE - 2 * margin, 2.0, 2.0)
    p.end()
    return QIcon(pixmap)


def _create_toolbar_icons () -> dict:
    """Create all toolbar icons as self-drawn, color-coded."""
    dpi = _dpi_factor()
    icons = {}
    icons['new'] = _generate_new_icon(dpi)
    icons['save'] = _generate_save_icon(dpi)
    icons['open'] = _generate_open_icon(dpi)
    icons['run'] = _generate_run_icon(dpi)
    icons['test'] = _generate_test_icon(dpi)
    icons['stop'] = _generate_stop_icon(dpi)
    icons['settings'] = _generate_settings_icon(dpi)
    return icons


#----------------------------------------------------------------------
# File encoding detection
#----------------------------------------------------------------------
def _detect_encoding (raw:bytes) -> str:
    """Detect file encoding: UTF-8 BOM → UTF-8 strict → system encoding."""
    if raw[:3] == b'\xef\xbb\xbf':
        return 'UTF-8'
    try:
        raw.decode('utf-8', 'strict')
        return 'UTF-8'
    except UnicodeDecodeError:
        pass
    if sys.platform == 'win32':
        return 'gbk'
    return 'utf-8'


def _read_file (path:str) -> tuple:
    """Read file with auto encoding detection. Returns (content, encoding).
    Detects and decodes in one pass to avoid double-decoding UTF-8 files."""
    with open(path, 'rb') as f:
        raw = f.read()
    # UTF-8 BOM: strip BOM and decode
    if raw[:3] == b'\xef\xbb\xbf':
        content = raw[3:].decode('utf-8', 'replace')
        return (content, 'UTF-8')
    # Try UTF-8 strict decode
    try:
        content = raw.decode('utf-8', 'strict')
        return (content, 'UTF-8')
    except UnicodeDecodeError:
        pass
    # Fall back to system encoding
    encoding = 'gbk' if sys.platform == 'win32' else 'utf-8'
    content = raw.decode(encoding, 'replace')
    return (content, encoding)


#----------------------------------------------------------------------
# Settings defaults
#----------------------------------------------------------------------
_SETTINGS_DEFAULTS = {
    'compiler_path': 'g++',
    'compiler_flags': '-std=c++14',
    'env_vars': {},
    'run_timeout': 10,
    'compile_timeout': 20,
    'editor_font_family': '',
    'editor_font_size': 11,
    'io_font_family': '',
    'io_font_size': 11,
    'bracket_completion': True,
    'word_wrap': False,
    'template_text': (
        '#include <iostream>\n'
        '#include <cstdio>\n'
        'using namespace std;\n'
        'int main() {\n'
        '    return 0;\n'
        '}\n'
    ),
}


#----------------------------------------------------------------------
# Settings (instance-based)
#----------------------------------------------------------------------
class Settings:

    def __init__ (self, defaults:dict=None):
        src = defaults or _SETTINGS_DEFAULTS
        for key, value in src.items():
            setattr(self, key, value)

    def copy (self):
        """Create an independent deep copy of this Settings instance."""
        return Settings(copy.deepcopy(self.__dict__))

    def apply_from (self, other):
        """Merge all attributes from other into this instance."""
        for key, value in other.__dict__.items():
            setattr(self, key, value)


#----------------------------------------------------------------------
# CppHighlighter (placeholder for Phase 4)
#----------------------------------------------------------------------
class CppHighlighter (QSyntaxHighlighter):

    def __init__ (self, parent:QTextDocument=None):
        super().__init__(parent)

    def highlightBlock (self, text:str):
        pass


#----------------------------------------------------------------------
# TabData
#----------------------------------------------------------------------
class TabData:

    def __init__ (self, file_path:str=None, is_new:bool=True,
                  encoding:str='UTF-8', content:str='',
                  dirty_callback=None):
        self.file_path = file_path
        self.is_new = is_new
        self.is_dirty = is_new
        self.untitled_number = 0
        self._dirty_callback = dirty_callback

        self.editor_doc = QTextDocument()
        self.input_doc = QTextDocument()
        self.output_doc = QTextDocument()

        self.cursor = QTextCursor(self.editor_doc)
        self.scroll_pos = 0
        self.input_cursor = QTextCursor(self.input_doc)
        self.input_scroll = 0

        self.encoding = encoding
        self.zoom_font_size = 0
        self.compiler_mtime = 0

        # Set initial content without triggering modificationChanged
        self.editor_doc.blockSignals(True)
        if content:
            self.editor_doc.setPlainText(content)
        if not is_new:
            self.editor_doc.setModified(False)
        self.editor_doc.blockSignals(False)

        # Highlighter created but deferred — not attached to editor_doc yet.
        self.highlighter = CppHighlighter()

        # Connect dirty tracking via modificationChanged
        self.editor_doc.modificationChanged.connect(
            self._on_modified_changed)

    def _on_modified_changed (self, modified:bool):
        old_dirty = self.is_dirty
        self.is_dirty = modified
        if old_dirty != self.is_dirty and self._dirty_callback:
            self._dirty_callback(self)

    def tab_name (self) -> str:
        if self.is_new:
            name = 'untitled{}'.format(self.untitled_number)
        else:
            name = os.path.basename(self.file_path)
        if self.is_dirty:
            return '*{}*'.format(name)
        return name


#----------------------------------------------------------------------
# TabManager (pure data manager — no UI coupling)
#----------------------------------------------------------------------
class TabManager:

    def __init__ (self):
        self.tabs = []
        self.current_index = -1
        self.untitled_counter = 0

    def add_tab (self, tab:TabData) -> int:
        """Add tab to list, assign untitled number if needed. Returns index."""
        if tab.is_new:
            self.untitled_counter += 1
            tab.untitled_number = self.untitled_counter
        self.tabs.append(tab)
        return len(self.tabs) - 1

    def remove_tab (self, index:int):
        """Remove and return tab at index."""
        return self.tabs.pop(index)

    def reorder_tabs (self, from_index:int, to_index:int) -> None:
        """Reorder tabs list after visual drag move."""
        tab = self.tabs.pop(from_index)
        self.tabs.insert(to_index, tab)

    def get_current (self) -> TabData:
        """Return current TabData, or None if no active tab."""
        if 0 <= self.current_index < len(self.tabs):
            return self.tabs[self.current_index]
        return None

    def get_tab_name (self, index:int) -> str:
        """Return tab name string for given index."""
        if 0 <= index < len(self.tabs):
            return self.tabs[index].tab_name()
        return ''

    def find_tab_index (self, tab:TabData) -> int:
        """Find index of a specific TabData instance."""
        for i, t in enumerate(self.tabs):
            if t is tab:
                return i
        return -1


#----------------------------------------------------------------------
# LineNumberArea
#----------------------------------------------------------------------
class LineNumberArea (QWidget):

    def __init__ (self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent (self, event):
        self.editor._paint_line_numbers(event)

    def sizeHint (self):
        return QSize(self.editor._line_number_width(), 0)


#----------------------------------------------------------------------
# CodeEditor (uses QTextEdit for setDocument compatibility)
#----------------------------------------------------------------------
class CodeEditor (QTextEdit):

    _LINE_NUM_COLOR = QColor(120, 120, 120)
    _LINE_NUM_BG = QColor(235, 235, 235)

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self._update_tab_width()
        self.line_number_area = LineNumberArea(self)
        self.document().blockCountChanged.connect(
            self._update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(
            self.line_number_area.update)
        self._update_line_number_area_width()

    def _update_tab_width (self):
        self.setTabStopWidth(self.fontMetrics().width('    '))

    def _line_number_width (self) -> int:
        digits = 1
        count = max(1, self.document().blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 3 + self.fontMetrics().width('9') * digits
        return space

    def _update_line_number_area_width (self):
        visible = self.line_number_area.isVisible()
        width = self._line_number_width() if visible else 0
        margins = self.viewportMargins()
        self.setViewportMargins(
            width, margins.top(), margins.right(), margins.bottom())
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), width, cr.height()))
        self.line_number_area.update()

    def setDocument (self, doc):
        old_doc = self.document()
        if old_doc:
            try:
                old_doc.blockCountChanged.disconnect(
                    self._update_line_number_area_width)
            except (RuntimeError, TypeError):
                pass
        super().setDocument(doc)
        doc.blockCountChanged.connect(
            self._update_line_number_area_width)
        self._update_line_number_area_width()

    def resizeEvent (self, event):
        super().resizeEvent(event)
        self._update_line_number_area_width()

    def _on_font_changed (self):
        self._update_tab_width()
        self._update_line_number_area_width()

    def _estimate_first_visible_block (self) -> int:
        """Estimate first visible block number from scroll position
        and average block height. Avoids iterating from block 0 for
        large documents."""
        scroll_y = self.verticalScrollBar().value()
        if scroll_y <= 0:
            return 0
        layout = self.document().documentLayout()
        total_h = layout.documentSize().height()
        count = max(1, self.document().blockCount())
        avg = total_h / count
        if avg <= 0:
            return 0
        est = int(scroll_y / avg)
        return max(0, est - 5)

    def _paint_line_numbers (self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self._LINE_NUM_BG)
        scroll_y = self.verticalScrollBar().value()
        start_num = self._estimate_first_visible_block()
        block = self.document().findBlockByNumber(start_num)
        while block.isValid():
            layout = self.document().documentLayout()
            block_rect = layout.blockBoundingRect(block)
            y = block_rect.y() - scroll_y
            height = block_rect.height()
            if y > event.rect().bottom():
                break
            if y + height >= event.rect().top():
                painter.setPen(self._LINE_NUM_COLOR)
                painter.drawText(
                    0, int(y), self._line_number_width() - 3,
                    int(height),
                    Qt.AlignRight | Qt.AlignVCenter,
                    str(block.blockNumber() + 1))
            block = block.next()
        painter.end()

    def keyPressEvent (self, event):
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText('\t')
        else:
            super().keyPressEvent(event)


#----------------------------------------------------------------------
# InputPanel
#----------------------------------------------------------------------
class InputPanel (QTextEdit):

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabStopWidth(self.fontMetrics().width('    '))

    def keyPressEvent (self, event):
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText('\t')
        else:
            super().keyPressEvent(event)


#----------------------------------------------------------------------
# OutputPanel
#----------------------------------------------------------------------
class OutputPanel (QTextEdit):

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)


#----------------------------------------------------------------------
# MainWindow
#----------------------------------------------------------------------
class MainWindow (QMainWindow):

    def __init__ (self, settings=None):
        super().__init__()
        if settings is None:
            settings = Settings()
            _init_font_defaults(settings)
        self.settings = settings
        self.setWindowTitle('CodeRunner')
        self.resize(1000, 650)

        # Center window on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            y = (geo.height() - self.height()) // 2 + geo.y()
            self.move(x, y)

        # DPI factor for scaled drawing
        self._dpi = _dpi_factor()

        # Create icons
        self.icons = _create_toolbar_icons()

        # Create editor and IO panels
        self.editor = CodeEditor()
        self.input_panel = InputPanel()
        self.output_panel = OutputPanel()

        # Apply Settings fonts to widgets
        editor_font = self.editor.font()
        editor_font.setFamily(self.settings.editor_font_family)
        editor_font.setPointSize(self.settings.editor_font_size)
        self.editor.setFont(editor_font)
        self.editor._on_font_changed()

        io_font = self.input_panel.font()
        io_font.setFamily(self.settings.io_font_family)
        io_font.setPointSize(self.settings.io_font_size)
        self.input_panel.setFont(io_font)
        self.output_panel.setFont(io_font)
        self.input_panel.setTabStopWidth(
            self.input_panel.fontMetrics().width('    '))

        # Create standalone placeholder docs for zero-tab state
        self.empty_editor_doc = QTextDocument(self)
        self.empty_input_doc = QTextDocument(self)
        self.empty_output_doc = QTextDocument(self)
        self.editor.setDocument(self.empty_editor_doc)
        self.input_panel.setDocument(self.empty_input_doc)
        self.output_panel.setDocument(self.empty_output_doc)

        # Tab management (pure data — no UI coupling)
        self.tab_manager = TabManager()
        self._tab_switching = False
        self._last_file_dir = ''
        self._deferred_restore_tab = -1

        # Create actions first (needed by menubar and toolbar)
        self.__create_actions()

        # Build UI in correct order
        self.__build_menubar()
        self.__build_toolbar()
        self.__build_mainarea()
        self.__build_tabbar_and_layout()
        self.__build_statusbar()

        # Connect signals
        self.__connect_signals()

        # Alt shortcuts for tab switching
        self.__setup_tab_switch_shortcuts()

        # Start in zero-tab state
        self._enter_zero_tab_state()

    def __create_actions (self):
        self.act_new = QAction(self.icons['new'], 'New', self)
        self.act_new.setShortcut(QKeySequence('Ctrl+N'))
        self.act_new.setToolTip('New (Ctrl+N)')

        self.act_save = QAction(self.icons['save'], 'Save', self)
        self.act_save.setShortcut(QKeySequence('Ctrl+S'))
        self.act_save.setToolTip('Save (Ctrl+S)')

        self.act_open = QAction(self.icons['open'], 'Open', self)
        self.act_open.setShortcut(QKeySequence('Ctrl+O'))
        self.act_open.setToolTip('Open (Ctrl+O)')

        self.act_save_as = QAction('Save As', self)
        self.act_save_as.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self.act_save_as.setToolTip('Save As (Ctrl+Shift+S)')

        self.act_close = QAction('Close', self)
        self.act_close.setShortcut(QKeySequence('Ctrl+W'))
        self.act_close.setToolTip('Close (Ctrl+W)')

        self.act_run = QAction(self.icons['run'], 'Run', self)
        self.act_run.setShortcut(QKeySequence('F5'))
        self.act_run.setToolTip('Run (F5)')

        self.act_test = QAction(self.icons['test'], 'Test', self)
        self.act_test.setShortcut(QKeySequence('F9'))
        self.act_test.setToolTip('Test (F9)')

        self.act_stop = QAction(self.icons['stop'], 'Stop', self)
        self.act_stop.setShortcut(QKeySequence('F7'))
        self.act_stop.setToolTip('Stop (F7)')

        self.act_settings = QAction(
            self.icons['settings'], 'Settings', self)
        self.act_settings.setToolTip('Settings')

        self.act_zoom_in = QAction('Zoom In', self)
        self.act_zoom_in.setShortcuts([
            QKeySequence('Ctrl++'), QKeySequence('Ctrl+=')])
        self.act_zoom_in.setToolTip('Zoom In (Ctrl++)')

        self.act_zoom_out = QAction('Zoom Out', self)
        self.act_zoom_out.setShortcuts([
            QKeySequence('Ctrl+-')])
        self.act_zoom_out.setToolTip('Zoom Out (Ctrl+-)')

    def __build_menubar (self):
        menubar = self.menuBar()
        self.menu_file = menubar.addMenu('File')
        self.menu_edit = menubar.addMenu('Edit')
        self.menu_run = menubar.addMenu('Run')
        self.menu_view = menubar.addMenu('View')
        self.menu_view.addAction(self.act_zoom_in)
        self.menu_view.addAction(self.act_zoom_out)

        # Populate File menu
        self.menu_file.addAction(self.act_new)
        self.menu_file.addAction(self.act_open)
        self.menu_file.addAction(self.act_save)
        self.menu_file.addAction(self.act_save_as)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_close)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_settings)

    def __build_toolbar (self):
        toolbar = self.addToolBar('Main')
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(_ICON_BASE, _ICON_BASE))

        toolbar.addAction(self.act_new)
        toolbar.addAction(self.act_save)
        toolbar.addAction(self.act_open)
        toolbar.addSeparator()
        toolbar.addAction(self.act_run)
        toolbar.addAction(self.act_test)
        toolbar.addAction(self.act_stop)
        toolbar.addSeparator()
        toolbar.addAction(self.act_settings)

    def __build_mainarea (self):
        # Wrap IO panels with label headers
        self.input_section = _make_io_section(
            self.settings, 'INPUT', self.input_panel, self._dpi)
        self.output_section = _make_io_section(
            self.settings, 'OUTPUT', self.output_panel, self._dpi)

        # Vertical splitter
        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.addWidget(self.input_section)
        self.v_splitter.addWidget(self.output_section)
        self.v_splitter.setSizes([325, 325])

        # Horizontal splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.editor)
        self.main_splitter.addWidget(self.v_splitter)
        self.main_splitter.setSizes([500, 500])

    def __build_tabbar_and_layout (self):
        self.tabbar = QTabBar(self)
        self.tabbar.setTabsClosable(True)
        self.tabbar.setMovable(True)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QVBoxLayout(self.central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabbar)
        layout.addWidget(self.main_splitter)

    def __build_statusbar (self):
        statusbar = self.statusBar()
        self.status_message = QLabel('')
        self.status_info = QLabel('')
        self.status_message.setAlignment(Qt.AlignLeft)
        self.status_info.setAlignment(Qt.AlignRight)
        statusbar.addWidget(self.status_message, 1)
        statusbar.addPermanentWidget(self.status_info, 0)

    def __connect_signals (self):
        # Toolbar/menu actions
        self.act_new.triggered.connect(self._action_new)
        self.act_open.triggered.connect(self._action_open)
        self.act_save.triggered.connect(self._action_save)
        self.act_save_as.triggered.connect(self._action_save_as)
        self.act_close.triggered.connect(self._action_close)
        self.act_zoom_in.triggered.connect(self._action_zoom_in)
        self.act_zoom_out.triggered.connect(self._action_zoom_out)

        # Tabbar signals
        self.tabbar.currentChanged.connect(
            self._on_tabbar_current_changed)
        self.tabbar.tabCloseRequested.connect(
            self._on_tab_close_requested)
        self.tabbar.tabMoved.connect(self._on_tab_moved)

        # Editor cursor position → update status bar
        self.editor.cursorPositionChanged.connect(
            self._on_cursor_position_changed)

    def __setup_tab_switch_shortcuts (self):
        # Alt+1~9 → switch to tab 0~8, Alt+0 → tab 9
        for i in range(1, 10):
            s = QShortcut(QKeySequence('Alt+{}'.format(i)), self)
            s.activated.connect(
                lambda idx=i - 1: self._switch_to_tab(idx))
        s0 = QShortcut(QKeySequence('Alt+0'), self)
        s0.activated.connect(lambda: self._switch_to_tab(9))

    #----- Action handlers -----

    def _action_new (self):
        tab = TabData(
            is_new=True, encoding='UTF-8',
            content=self.settings.template_text,
            dirty_callback=self._on_tab_dirty_changed)
        index = self.tab_manager.add_tab(tab)
        self.tabbar.addTab(tab.tab_name())
        self._switch_to_tab(index)

    def _action_open (self):
        start_dir = self._last_file_dir or os.path.expanduser('~')
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open File', start_dir,
            'C++ Files (*.cpp *.c *.cc *.cxx *.h *.hpp *.hh);;All Files (*)')
        if not path:
            return
        content, encoding = _read_file(path)
        tab = TabData(
            file_path=path, is_new=False,
            encoding=encoding, content=content,
            dirty_callback=self._on_tab_dirty_changed)
        index = self.tab_manager.add_tab(tab)
        self.tabbar.addTab(tab.tab_name())
        self._switch_to_tab(index)
        self._last_file_dir = os.path.dirname(path)

    def _action_save (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        self._save_tab_data(tab)

    def _action_save_as (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        start_dir = self._last_file_dir or os.path.expanduser('~')
        if tab.file_path:
            start_dir = os.path.dirname(tab.file_path)
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save As', start_dir,
            'C++ Files (*.cpp *.c *.cc *.cxx *.h *.hpp *.hh);;All Files (*)')
        if not path:
            return
        old_path = tab.file_path
        old_is_new = tab.is_new
        tab.file_path = path
        tab.is_new = False
        result = self._save_tab_data(tab)
        if result < 0:
            # Rollback on failure
            tab.file_path = old_path
            tab.is_new = old_is_new
            return
        self._last_file_dir = os.path.dirname(path)

    def _action_close (self):
        if self.tab_manager.current_index < 0:
            return
        self._handle_close_tab(self.tab_manager.current_index)

    def _action_zoom_in (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        tab.zoom_font_size += 1
        self._apply_zoom(tab)

    def _action_zoom_out (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        base_size = self.settings.editor_font_size
        if base_size + tab.zoom_font_size <= 6:
            return
        tab.zoom_font_size -= 1
        self._apply_zoom(tab)

    def _apply_zoom (self, tab):
        zoom_size = max(6, self.settings.editor_font_size + tab.zoom_font_size)
        font = self.editor.font()
        font.setPointSize(zoom_size)
        self.editor.setFont(font)
        self.editor._on_font_changed()

    #----- Tab management (UI operations) -----

    def _switch_to_tab (self, index:int):
        """Switch to tab: save old state, swap documents, restore new state."""
        tm = self.tab_manager
        if index < 0 or index >= len(tm.tabs):
            return
        old_index = tm.current_index

        # Save old tab state
        if old_index >= 0 and old_index < len(tm.tabs):
            old_tab = tm.tabs[old_index]
            old_tab.cursor = self.editor.textCursor()
            old_tab.scroll_pos = self.editor.verticalScrollBar().value()
            old_tab.input_cursor = self.input_panel.textCursor()
            old_tab.input_scroll = self.input_panel.verticalScrollBar().value()

        tm.current_index = index
        new_tab = tm.tabs[index]

        # Exit zero-tab state if needed
        if old_index == -1:
            self._exit_zero_tab_state()

        # Freeze redraw to prevent flicker
        self.editor.setUpdatesEnabled(False)
        self.input_panel.setUpdatesEnabled(False)
        self.output_panel.setUpdatesEnabled(False)

        # Swap documents
        self.editor.setDocument(new_tab.editor_doc)
        self.input_panel.setDocument(new_tab.input_doc)
        self.output_panel.setDocument(new_tab.output_doc)

        # Restore IO cursors (fast, small documents)
        self.input_panel.setTextCursor(new_tab.input_cursor)
        self.input_panel.verticalScrollBar().setValue(new_tab.input_scroll)

        # Restore zoom font size
        base_size = self.settings.editor_font_size
        zoom_size = max(6, base_size + new_tab.zoom_font_size)
        font = self.editor.font()
        font.setPointSize(zoom_size)
        self.editor.setFont(font)
        self.editor._on_font_changed()

        # Unfreeze — document content displayed immediately
        self.editor.setUpdatesEnabled(True)
        self.input_panel.setUpdatesEnabled(True)
        self.output_panel.setUpdatesEnabled(True)

        # Update tabbar current index
        self._tab_switching = True
        self.tabbar.setCurrentIndex(index)
        self._tab_switching = False

        # Update status bar (with default cursor for now)
        self._update_status_info(new_tab)

        # Deferred editor cursor/scroll restore
        self._deferred_restore_tab = index
        QTimer.singleShot(0, self._restore_deferred_cursor)

    def _handle_close_tab (self, index:int) -> bool:
        """Close tab: confirm/save if dirty, disconnect, remove, adjust UI."""
        tm = self.tab_manager
        if index < 0 or index >= len(tm.tabs):
            return False
        tab = tm.tabs[index]

        if tab.is_dirty:
            choice = self._confirm_close_tab(tab)
            if choice == 'cancel':
                return False
            elif choice == 'save':
                result = self._save_tab_data(tab)
                if result < 0:
                    return False

        # Disconnect signal before removing
        try:
            tab.editor_doc.modificationChanged.disconnect(
                tab._on_modified_changed)
        except (RuntimeError, TypeError):
            pass

        # Save current tab's widget state if it's not the one being closed
        if tm.current_index >= 0 and tm.current_index != index \
           and tm.current_index < len(tm.tabs):
            old_tab = tm.tabs[tm.current_index]
            old_tab.cursor = self.editor.textCursor()
            old_tab.scroll_pos = self.editor.verticalScrollBar().value()
            old_tab.input_cursor = self.input_panel.textCursor()
            old_tab.input_scroll = self.input_panel.verticalScrollBar().value()

        # Mark no active tab so switch won't try to save old state
        tm.current_index = -1

        # Block currentChanged during tabbar manipulation
        self._tab_switching = True
        self.tabbar.removeTab(index)
        self._tab_switching = False

        # Remove from data
        tm.remove_tab(index)

        if len(tm.tabs) == 0:
            self._enter_zero_tab_state()
        else:
            new_index = min(index, len(tm.tabs) - 1)
            self._switch_to_tab(new_index)
        return True

    def _update_status_info (self, tab:TabData):
        """Update status bar right side with cursor position and encoding."""
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        mode = 'INS'
        text = 'Ln {}, Col {} | {} | {}'.format(
            line, col, tab.encoding, mode)
        self.status_info.setText(text)

    def _update_tab_name (self, index:int):
        """Update tabbar text for given index."""
        if 0 <= index < len(self.tab_manager.tabs):
            name = self.tab_manager.tabs[index].tab_name()
            self.tabbar.setTabText(index, name)

    def _update_all_tab_names (self):
        """Update all tabbar texts."""
        for i in range(len(self.tab_manager.tabs)):
            self._update_tab_name(i)

    #----- Helpers -----

    def _save_tab_data (self, tab:TabData) -> int:
        """Save tab to disk. Returns 0 success, -1 cancel, -2 error."""
        if tab.is_new:
            start_dir = self._last_file_dir or os.path.expanduser('~')
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save File', start_dir,
                'C++ Files (*.cpp *.c *.cc *.cxx *.h '
                '*.hpp *.hh);;All Files (*)')
            if not path:
                return -1
            content = tab.editor_doc.toPlainText()
            try:
                with open(path, 'w', encoding=tab.encoding) as f:
                    f.write(content)
            except (IOError, OSError) as e:
                QMessageBox.warning(self, 'Save Error', str(e))
                return -2
            tab.file_path = path
            tab.is_new = False
            self._last_file_dir = os.path.dirname(path)
        else:
            content = tab.editor_doc.toPlainText()
            try:
                with open(tab.file_path, 'w', encoding=tab.encoding) as f:
                    f.write(content)
            except (IOError, OSError) as e:
                QMessageBox.warning(self, 'Save Error', str(e))
                return -2

        tab.editor_doc.setModified(False)
        self._update_all_tab_names()
        self.status_message.setText(
            'Saved: {}'.format(os.path.basename(tab.file_path)))
        return 0

    def _confirm_close_tab (self, tab:TabData) -> str:
        """Ask about unsaved changes. Returns save/discard/cancel."""
        if tab.is_new:
            name = 'untitled{}'.format(tab.untitled_number)
        else:
            name = os.path.basename(tab.file_path)
        msg = QMessageBox(self)
        msg.setWindowTitle('Save Changes?')
        msg.setText("File '{}' has unsaved changes.".format(name))
        msg.setStandardButtons(
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Save)
        result = msg.exec_()
        if result == QMessageBox.Save:
            return 'save'
        elif result == QMessageBox.Discard:
            return 'discard'
        return 'cancel'

    #----- Signal handlers -----

    def _on_tabbar_current_changed (self, index:int):
        if self._tab_switching:
            return
        if index >= 0 and index < len(self.tab_manager.tabs):
            self._switch_to_tab(index)

    def _on_tab_close_requested (self, index:int):
        self._handle_close_tab(index)

    def _on_tab_moved (self, from_index:int, to_index:int):
        self.tab_manager.reorder_tabs(from_index, to_index)
        self.tab_manager.current_index = self.tabbar.currentIndex()

    def _on_tab_dirty_changed (self, tab:TabData):
        index = self.tab_manager.find_tab_index(tab)
        if index >= 0:
            self._update_tab_name(index)

    def _on_cursor_position_changed (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            self.status_info.setText('')
            return
        self._update_status_info(tab)

    #----- Zero-tab state -----

    def _enter_zero_tab_state (self):
        self.editor.setDocument(self.empty_editor_doc)
        self.input_panel.setDocument(self.empty_input_doc)
        self.output_panel.setDocument(self.empty_output_doc)
        self.editor.setEnabled(False)
        self.editor.line_number_area.hide()
        self.input_section.setEnabled(False)
        self.output_section.setEnabled(False)
        self.status_info.setText('')
        self._deferred_restore_tab = -1

    def _exit_zero_tab_state (self):
        self.editor.setEnabled(True)
        self.editor.line_number_area.show()
        self.input_section.setEnabled(True)
        self.output_section.setEnabled(True)

    def _restore_deferred_cursor (self):
        """Deferred cursor/scroll restore after _switch_to_tab."""
        index = self._deferred_restore_tab
        if index < 0 or index != self.tab_manager.current_index:
            return
        if index >= len(self.tab_manager.tabs):
            return
        tab = self.tab_manager.tabs[index]
        self.editor.setTextCursor(tab.cursor)
        self.editor.verticalScrollBar().setValue(tab.scroll_pos)
        self._deferred_restore_tab = -1
        self._update_status_info(tab)

    #----- Window close -----

    def closeEvent (self, event):
        for tab in list(self.tab_manager.tabs):
            if tab.is_dirty:
                idx = self.tab_manager.find_tab_index(tab)
                self._switch_to_tab(idx)
                choice = self._confirm_close_tab(tab)
                if choice == 'cancel':
                    event.ignore()
                    return
                elif choice == 'save':
                    result = self._save_tab_data(tab)
                    if result < 0:
                        event.ignore()
                        return
        # Disconnect all signals before Qt destruction
        for tab in self.tab_manager.tabs:
            try:
                tab.editor_doc.modificationChanged.disconnect(
                    tab._on_modified_changed)
            except RuntimeError:
                pass
        event.accept()


#----------------------------------------------------------------------
# Main entry
#----------------------------------------------------------------------
def main ():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    settings = Settings()
    _init_font_defaults(settings)
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
