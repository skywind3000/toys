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
import re
import copy
import math
import time
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QTabBar, QSplitter,
    QTextEdit, QLabel, QWidget, QAction,
    QVBoxLayout, QShortcut, QFileDialog, QMessageBox,
    QInputDialog
)
from PyQt5.QtCore import (
    Qt, QSize, QPointF, QTimer, QRect, QRegularExpression,
    QProcess, QProcessEnvironment, pyqtSignal, QObject
)
from PyQt5.QtGui import (
    QKeySequence, QFontDatabase, QIcon, QPainter, QPixmap,
    QColor, QPen, QBrush, QPolygonF, QSyntaxHighlighter,
    QTextDocument, QTextCursor, QTextCharFormat
)

# Optional psutil for memory tracking
try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _psutil = None
    _HAS_PSUTIL = False


#----------------------------------------------------------------------
# Flow state constants
#----------------------------------------------------------------------
_FLOW_IDLE = 'idle'
_FLOW_COMPILING = 'compiling'
_FLOW_RUNNING = 'running'

# Windows NTSTATUS codes for common crash scenarios
_DLL_NOT_FOUND = 0xC0000135   # STATUS_DLL_NOT_FOUND (-1073741515)
_ACCESS_VIOLATION = 0xC0000005  # STATUS_ACCESS_VIOLATION (-1073741819)


def _describe_exit_code (exit_code:int) -> str:
    """Return human-readable description for Windows crash exit codes."""
    if sys.platform != 'win32':
        return ''
    if exit_code < 0:
        code = exit_code & 0xFFFFFFFF
        if code == _DLL_NOT_FOUND:
            return 'DLL not found'
        if code == _ACCESS_VIOLATION:
            return 'Access violation'
    return ''


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
    margin = 4.0
    tri_top = 3.0
    tri_bottom = _ICON_BASE - 3.0
    tri_left = margin
    tri_right = _ICON_BASE - 3.0
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
# EncodingManager
#----------------------------------------------------------------------
class EncodingManager (object):
    """Encoding detection, compilation flags, and I/O conversion."""

    @staticmethod
    def platform_charset () -> str:
        if sys.platform == 'win32':
            return 'gbk'
        return 'utf-8'

    @staticmethod
    def build_flags (source_encoding:str) -> list:
        flags = []
        pc = EncodingManager.platform_charset()
        flags.append('-fexec-charset={}'.format(pc))
        if source_encoding.lower().replace('-', '') == 'utf8':
            flags.append('-finput-charset=UTF-8')
        return flags

    @staticmethod
    def encode_stdin (text:str) -> bytes:
        charset = EncodingManager.platform_charset()
        return text.encode(charset, 'replace')

    @staticmethod
    def decode_stdout (raw:bytes) -> str:
        charset = EncodingManager.platform_charset()
        return raw.decode(charset, 'replace')

    @staticmethod
    def decode_stderr (raw:bytes) -> str:
        charset = EncodingManager.platform_charset()
        return raw.decode(charset, 'replace')


#----------------------------------------------------------------------
# Environment variable expansion
#----------------------------------------------------------------------
def _expand_env_vars (value:str) -> str:
    """Expand $VAR_NAME references in environment variable values."""
    def replacer (match):
        var_name = match.group(1)
        return os.environ.get(var_name, '')
    return re.sub(r'\$([A-Za-z_][A-Za-z0-9_]*)', replacer, value)


#----------------------------------------------------------------------
# Run external terminal helper
#----------------------------------------------------------------------
def _ensure_cmd_file () -> str:
    """Create %TEMP%\\coderunner.cmd if needed. Returns bat file path."""
    bat_path = os.path.join(
        os.environ.get('TEMP', os.environ.get('TMP', '')),
        'coderunner.cmd')
    content = (
        '@echo off\n'
        'call %CR_COMMAND%\n'
        'set CR_EXITCODE=%ERRORLEVEL%\n'
        'call %CR_PAUSE%\n'
        'exit %CR_EXITCODE%\n'
    )
    need_write = True
    if os.path.exists(bat_path):
        try:
            with open(bat_path, 'r') as f:
                existing = f.read()
            if existing == content:
                need_write = False
        except (IOError, OSError):
            need_write = True
    if need_write:
        with open(bat_path, 'w') as f:
            f.write(content)
    return bat_path


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
    'indent_style': 'tab',
    'indent_size': 4,
    'word_wrap': False,
    'template_text': (
        '#include <iostream>\n'
        '#include <cstdio>\n'
        'using namespace std;\n'
        'int main() {\n'
        '\treturn 0;\n'
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
# CppHighlighter
#----------------------------------------------------------------------
_CPP_KEYWORDS = (
    'int|float|double|char|void|bool|long|short|unsigned|signed|'
    'const|static|extern|inline|virtual|override|final|class|struct|'
    'enum|union|namespace|using|template|typename|public|private|'
    'protected|if|else|while|for|do|switch|case|default|break|'
    'continue|return|try|catch|throw|new|delete|this|nullptr|true|'
    'false|sizeof|typedef|auto|register|volatile|friend|operator|'
    'explicit|mutable|constexpr|decltype|static_assert|noexcept|'
    'thread_local|alignas|alignof'
)

_CPP_PREPROCESSOR = (
    'include|define|ifdef|ifndef|endif|if|elif|else|pragma|error|warning'
)


class CppHighlighter (QSyntaxHighlighter):

    def __init__ (self, parent:QTextDocument=None, deferred:bool=False):
        super().__init__(parent)
        self._rules = []
        self._deferred = deferred
        self._batch_block_number = 0
        self._batch_timer = None
        self._batch_editor = None
        self._batch_size = 100
        self.__init_rules()

    def __init_rules (self):
        # Rule order determines first-match-wins priority. Strings and
        # comments must come before keywords so that text inside
        # "int x" or // return 0 is not mis-highlighted as keyword.

        # 1. Single-line comments (highest priority)
        fmt_comment_single = QTextCharFormat()
        fmt_comment_single.setForeground(QBrush(QColor(0, 128, 0)))
        self._rules.append((
            QRegularExpression(r'//[^\n]*'),
            fmt_comment_single))

        # 2. Strings
        fmt_string = QTextCharFormat()
        fmt_string.setForeground(QBrush(QColor(163, 21, 21)))
        self._rules.append((
            QRegularExpression(r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"'),
            fmt_string))

        # 3. Character literals
        fmt_char = QTextCharFormat()
        fmt_char.setForeground(QBrush(QColor(163, 21, 21)))
        self._rules.append((
            QRegularExpression(r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'"),
            fmt_char))

        # 4. Keywords
        fmt_keyword = QTextCharFormat()
        fmt_keyword.setForeground(QBrush(QColor(0, 0, 255)))
        self._rules.append((
            QRegularExpression(
                r'\b(' + _CPP_KEYWORDS + r')\b'),
            fmt_keyword))

        # 5. Preprocessor directives
        fmt_preproc = QTextCharFormat()
        fmt_preproc.setForeground(QBrush(QColor(0, 0, 255)))
        self._rules.append((
            QRegularExpression(
                r'^#\s*(' + _CPP_PREPROCESSOR + r')\b'),
            fmt_preproc))

        # 6. Numbers
        fmt_number = QTextCharFormat()
        fmt_number.setForeground(QBrush(QColor(0, 0, 128)))
        self._rules.append((
            QRegularExpression(
                r'\b(0[xX][0-9a-fA-F]+[uUlL]*'
                r'|0[bB][01]+[uUlL]*'
                r'|[0-9]+(\.[0-9]*)?([eE][+-]?[0-9]+)?[fFlLuU]*'
                r')\b'),
            fmt_number))

        # 7. Symbols / operators
        fmt_symbol = QTextCharFormat()
        fmt_symbol.setForeground(QBrush(QColor(0, 128, 128)))
        self._rules.append((
            QRegularExpression(
                r'(::|->|\.\*|->\*|<<=|>>=|<<|>>'
                r'|==|!=|<=|>=|&&|\|\|'
                r'|\+=|-=|\*=|/=|%=|&=|\|=|\^='
                r'|\+\+|--|\.\.\.'
                r'|[+\-*/%&|^~!=<>?:;,]'
                r')'),
            fmt_symbol))

        # Multi-line comments (handled separately in highlightBlock)
        fmt_comment_multi = QTextCharFormat()
        fmt_comment_multi.setForeground(QBrush(QColor(0, 128, 0)))
        self._multi_start = QRegularExpression(r'/\*')
        self._multi_end = QRegularExpression(r'\*/')
        self._multi_fmt = fmt_comment_multi

    def highlightBlock (self, text:str):
        if self._deferred:
            self.__track_multiline_state(text)
            return
        # First: apply single-line rules (first-match-wins)
        for regex, fmt in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart()
                length = match.capturedLength()
                # Only apply if not already formatted by a higher-priority rule
                self.__format_if_free(start, length, fmt)

        # Multi-line comment handling
        self.__highlight_multiline_comments(text)

    def __format_if_free (self, start:int, length:int, fmt):
        """Apply format only to unformatted positions (first-match-wins).
        Iterates through the range and formats contiguous free segments,
        skipping positions already formatted by a higher-priority rule."""
        seg_start = -1
        end = start + length
        for i in range(start, end):
            existing = self.format(i)
            fg = existing.foreground()
            is_free = not fg.style() or fg.color() == QColor()
            if is_free:
                if seg_start < 0:
                    seg_start = i
            else:
                if seg_start >= 0:
                    self.setFormat(seg_start, i - seg_start, fmt)
                    seg_start = -1
        if seg_start >= 0:
            self.setFormat(seg_start, end - seg_start, fmt)

    def __highlight_multiline_comments (self, text:str):
        start_state = self.previousBlockState()
        start_idx = 0
        if start_state != 1:
            match = self._multi_start.match(text)
            if match.hasMatch():
                start_idx = match.capturedStart()
            else:
                self.setCurrentBlockState(0)
                return
        end_match = self._multi_end.match(text, start_idx)
        if end_match.hasMatch():
            end_idx = end_match.capturedEnd()
            self.setFormat(start_idx, end_idx - start_idx,
                           self._multi_fmt)
            self.setCurrentBlockState(0)
            # Continue looking for more /* after */
            next_start = self._multi_start.match(text, end_idx)
            if next_start.hasMatch():
                ns = next_start.capturedStart()
                next_end = self._multi_end.match(text, ns)
                if next_end.hasMatch():
                    ne = next_end.capturedEnd()
                    self.setFormat(ns, ne - ns, self._multi_fmt)
                else:
                    self.setFormat(ns, len(text) - ns, self._multi_fmt)
                    self.setCurrentBlockState(1)
        else:
            self.setFormat(start_idx, len(text) - start_idx,
                           self._multi_fmt)
            self.setCurrentBlockState(1)

    def __track_multiline_state (self, text:str):
        """Deferred mode: only track multiline comment state, no formatting."""
        start_state = self.previousBlockState()
        start_idx = 0
        if start_state != 1:
            match = self._multi_start.match(text)
            if match.hasMatch():
                start_idx = match.capturedStart()
            else:
                self.setCurrentBlockState(0)
                return
        end_match = self._multi_end.match(text, start_idx)
        if end_match.hasMatch():
            self.setCurrentBlockState(0)
            next_start = self._multi_start.match(text, end_match.capturedEnd())
            if next_start.hasMatch():
                next_end = self._multi_end.match(
                    text, next_start.capturedStart())
                if not next_end.hasMatch():
                    self.setCurrentBlockState(1)
        else:
            self.setCurrentBlockState(1)

    def start_batch_highlight (self, editor_widget, batch_size:int=100):
        """Start progressive highlighting in batches to keep UI responsive.
        Processes blocks from the beginning, rehighlighting batch_size blocks
        per timer tick. Deferred mode is disabled once highlighting starts."""
        if self._batch_timer is not None:
            self._batch_timer.stop()
            self._batch_timer = None
        self._deferred = False
        self._batch_block_number = 0
        self._batch_editor = editor_widget
        self._batch_size = batch_size
        self.__process_highlight_batch()

    def __process_highlight_batch (self):
        """Process one batch of blocks, then schedule next batch via timer."""
        doc = self.document()
        block = doc.findBlockByNumber(self._batch_block_number)
        editor = self._batch_editor
        if not editor or not block.isValid():
            self._batch_timer = None
            self._batch_editor = None
            return
        count = 0
        editor.setUpdatesEnabled(False)
        while block.isValid() and count < self._batch_size:
            self.rehighlightBlock(block)
            block = block.next()
            count += 1
        editor.setUpdatesEnabled(True)
        if block.isValid():
            self._batch_block_number += count
            self._batch_timer = QTimer.singleShot(
                0, self.__process_highlight_batch)
        else:
            self._batch_timer = None
            self._batch_editor = None

    def cancel_batch_highlight (self):
        """Cancel any in-progress batch highlighting."""
        if self._batch_timer is not None:
            self._batch_timer.stop()
            self._batch_timer = None
        self._batch_editor = None
        self._deferred = True


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
        self._highlight_pending = True

        # Set initial content without triggering modificationChanged
        self.editor_doc.blockSignals(True)
        if content:
            self.editor_doc.setPlainText(content)
        if not is_new:
            self.editor_doc.setModified(False)
        self.editor_doc.blockSignals(False)

        # Highlighter created in deferred mode (no format spans initially)
        self.highlighter = CppHighlighter(self.editor_doc, deferred=True)

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
# ProcessManager
#----------------------------------------------------------------------
class ProcessManager (QObject):
    """Manages compile and test-run processes via QProcess."""

    compile_finished = pyqtSignal(int, str, str)  # exit_code, stderr, reason
    run_stdout_ready = pyqtSignal(str)
    run_stderr_ready = pyqtSignal(str)
    run_finished = pyqtSignal(int, float, int, str, str)  # exit_code, elapsed, peak, reason, stderr_text
    # reason: 'normal' / 'timeout' / 'killed' / 'failed_to_start'

    def __init__ (self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.process = None
        self.busy = False
        self.mode = None  # 'compile' or 'test_run'
        self.target_tab = None
        self._start_time = 0.0
        self._peak_memory = 0
        self._memory_timer = None
        self._timeout_timer = None
        self._tracked_pid = 0
        self._stdin_data = None
        self._enc_mgr = EncodingManager()
        self._stderr_buffer = ''
        self._finished_emitted = False

    def start_compile (self, command:list, work_dir:str,
                       env:QProcessEnvironment, timeout:int=20):
        self.busy = True
        self.mode = 'compile'
        self._start_time = time.time()
        self._stderr_buffer = ''
        self._peak_memory = 0
        self._finished_emitted = False
        self.process = QProcess(self)
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(work_dir)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardError.connect(
            self._on_compile_stderr_ready)
        self.process.finished.connect(self._on_compile_finished)
        # Start timeout timer BEFORE process to avoid gap
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_compile_timeout)
        self._timeout_timer.start(timeout * 1000)
        self.process.start(command[0], command[1:])
        if not self.process.waitForStarted(5000):
            self._stop_timeout_timer()
            err_msg = self.process.errorString()
            self._cleanup()
            self._finished_emitted = True
            self.compile_finished.emit(-1, err_msg, 'failed_to_start')
            return

    def start_test_run (self, exe_path:str, work_dir:str,
                        env:QProcessEnvironment, stdin_data:bytes,
                        timeout:int=30):
        self.busy = True
        self.mode = 'test_run'
        self._start_time = time.time()
        self._peak_memory = 0
        self._stdin_data = stdin_data
        self._finished_emitted = False
        self.process = QProcess(self)
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(work_dir)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(
            self._on_run_stdout_ready)
        self.process.readyReadStandardError.connect(
            self._on_run_stderr_ready)
        self.process.started.connect(self._on_run_started)
        self.process.finished.connect(self._on_run_finished)
        # Start timeout timer BEFORE process to avoid gap
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_run_timeout)
        self._timeout_timer.start(timeout * 1000)
        self.process.start(exe_path)
        if not self.process.waitForStarted(5000):
            self._stop_timeout_timer()
            err_msg = self.process.errorString()
            self._cleanup()
            self._finished_emitted = True
            self.run_finished.emit(-1, 0, 0, 'failed_to_start',
                                   err_msg)
            return

    def kill_process (self):
        """Kill current process. finished signal will arrive with reason='killed'."""
        if self.process and self.process.state() != QProcess.NotRunning:
            self._stop_timeout_timer()
            self.process.kill()

    def _cleanup (self):
        """Clean up timers and process references. Disconnect signals
        to prevent finished/readyRead signals leaking after cleanup."""
        self._stop_memory_tracking()
        self._stop_timeout_timer()
        if self.process:
            try:
                self.process.finished.disconnect()
            except TypeError:
                pass
            try:
                self.process.readyReadStandardError.disconnect()
            except TypeError:
                pass
            try:
                self.process.readyReadStandardOutput.disconnect()
            except TypeError:
                pass
            try:
                self.process.started.disconnect()
            except TypeError:
                pass
            self.process.deleteLater()
            self.process = None
        self.busy = False
        self.mode = None
        self._stdin_data = None

    def _stop_timeout_timer (self):
        if self._timeout_timer:
            self._timeout_timer.stop()
            self._timeout_timer = None

    #----- Compile handlers -----

    def _on_compile_stderr_ready (self):
        raw = self.process.readAllStandardError()
        data = bytes(raw)
        if data:
            text = self._enc_mgr.decode_stderr(data)
            self._stderr_buffer += text

    def _on_compile_finished (self, exit_code:int, _exit_status):
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._stop_timeout_timer()
        # Read any remaining stderr
        remaining = self.process.readAllStandardError()
        if remaining and bytes(remaining):
            self._stderr_buffer += self._enc_mgr.decode_stderr(
                bytes(remaining))
        stderr_text = self._stderr_buffer
        self._cleanup()
        self.compile_finished.emit(exit_code, stderr_text, 'normal')

    def _on_compile_timeout (self):
        if self._finished_emitted:
            return
        if not self.process or self.process.state() == QProcess.NotRunning:
            return
        self._finished_emitted = True
        self._stop_timeout_timer()
        self.process.kill()
        self.compile_finished.emit(-1, '', 'timeout')

    #----- Run handlers -----

    def _on_run_started (self):
        self.process.write(self._stdin_data)
        self.process.closeWriteChannel()
        self.process.started.disconnect(self._on_run_started)
        self._stdin_data = None
        if _HAS_PSUTIL:
            self._start_memory_tracking(self.process.processId())

    def _on_run_stdout_ready (self):
        raw = self.process.readAllStandardOutput()
        data = bytes(raw)
        if data:
            text = self._enc_mgr.decode_stdout(data)
            self.run_stdout_ready.emit(text)

    def _on_run_stderr_ready (self):
        raw = self.process.readAllStandardError()
        data = bytes(raw)
        if data:
            text = self._enc_mgr.decode_stderr(data)
            self.run_stderr_ready.emit(text)

    def _on_run_finished (self, exit_code:int, exit_status):
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self._stop_timeout_timer()
        killed = exit_status != QProcess.NormalExit
        reason = 'killed' if killed else 'normal'
        # Read any remaining buffered data
        remaining_stdout = self.process.readAllStandardOutput()
        if remaining_stdout and bytes(remaining_stdout):
            text = self._enc_mgr.decode_stdout(bytes(remaining_stdout))
            self.run_stdout_ready.emit(text)
        remaining_stderr = self.process.readAllStandardError()
        if remaining_stderr and bytes(remaining_stderr):
            text = self._enc_mgr.decode_stderr(bytes(remaining_stderr))
            self.run_stderr_ready.emit(text)
        elapsed = time.time() - self._start_time
        peak = self._peak_memory
        self._stop_memory_tracking()
        self._cleanup()
        self.run_finished.emit(exit_code, elapsed, peak, reason, '')

    def _on_run_timeout (self):
        if self._finished_emitted:
            return
        if not self.process or self.process.state() == QProcess.NotRunning:
            return
        # Read any data before killing
        remaining_stdout = self.process.readAllStandardOutput()
        if remaining_stdout and bytes(remaining_stdout):
            text = self._enc_mgr.decode_stdout(bytes(remaining_stdout))
            self.run_stdout_ready.emit(text)
        remaining_stderr = self.process.readAllStandardError()
        if remaining_stderr and bytes(remaining_stderr):
            text = self._enc_mgr.decode_stderr(bytes(remaining_stderr))
            self.run_stderr_ready.emit(text)
        self._finished_emitted = True
        self._stop_timeout_timer()
        elapsed = time.time() - self._start_time
        peak = self._peak_memory
        self.process.kill()
        self.run_finished.emit(-1, elapsed, peak, 'timeout', '')

    #----- Memory tracking -----

    def _start_memory_tracking (self, pid:int):
        self._peak_memory = 0
        self._tracked_pid = pid
        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._poll_memory)
        self._memory_timer.start(100)

    def _poll_memory (self):
        try:
            proc = _psutil.Process(self._tracked_pid)
            mem = proc.memory_info()
            self._peak_memory = max(self._peak_memory, mem.rss)
        except Exception:
            pass

    def _stop_memory_tracking (self):
        if self._memory_timer:
            self._memory_timer.stop()
            self._memory_timer = None
        self._tracked_pid = 0


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

    _BRACKET_OPEN = {'(': ')', '{': '}', '[': ']', '"': '"', "'": "'"}
    _BRACKET_CLOSE = {')': '(', '}': '{', ']': '['}

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.indent_style = 'tab'
        self.indent_size = 4
        self._update_tab_width()
        self.line_number_area = LineNumberArea(self)
        self.overwrite_mode = False
        self._bracket_completion_enabled = True
        self.document().blockCountChanged.connect(
            self._update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(
            self.line_number_area.update)
        self._update_line_number_area_width()

    def _update_tab_width (self):
        # Tab width = 4 characters. IMPORTANT: tab width (pixels) depends
        # on the current font's char width. Whenever font/size changes
        # (SettingsDialog, zoom), must call updateFontMetrics() to
        # recalculate tab width and sync document.setDefaultFont().
        # Otherwise tab pixel value won't match new font, causing wrong
        # visual width (e.g. 4-char tab appearing as 5 chars).
        self.setTabStopWidth(
            self.fontMetrics().horizontalAdvance('x') * 4)

    def _line_number_width (self) -> int:
        digits = 1
        count = max(1, self.document().blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
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
        # Sync document's defaultFont to editor widget font, so that
        # tab stops and layout use the same font metrics. Without this,
        # the document uses its own defaultFont (often system default)
        # while setTabStopWidth is calculated from the editor font,
        # causing mismatch (e.g. 4-char tab appearing as 5 chars).
        doc.setDefaultFont(self.font())
        super().setDocument(doc)
        doc.blockCountChanged.connect(
            self._update_line_number_area_width)
        self._update_line_number_area_width()

    def resizeEvent (self, event):
        super().resizeEvent(event)
        self._update_line_number_area_width()

    def updateFontMetrics (self):
        """Refresh tab width, line number area, and document font."""
        self._update_tab_width()
        self._update_line_number_area_width()
        # Keep document's default font in sync with widget font
        # so layout and tab stops use the correct metrics
        doc = self.document()
        if doc:
            doc.setDefaultFont(self.font())

    def setFontSize (self, point_size:int):
        """Set font point size and refresh metrics."""
        font = self.font()
        font.setPointSize(point_size)
        self.setFont(font)
        self.updateFontMetrics()

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
        key = event.key()
        text = event.text()

        # Insert key toggles overwrite mode
        if key == Qt.Key_Insert:
            self.overwrite_mode = not self.overwrite_mode
            self._notify_overwrite_changed()
            return

        # Tab key
        if key == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText('\t')
            return

        # Enter key — auto indent
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._handle_enter_key()
            return

        # Backspace — smart space deletion and bracket deletion
        if key == Qt.Key_Backspace:
            if self._handle_backspace():
                return
            super().keyPressEvent(event)
            return

        # Bracket completion
        if text and self._bracket_completion_enabled:
            if text in self._BRACKET_OPEN:
                self._handle_bracket_open(text)
                return
            if text in self._BRACKET_CLOSE:
                if self._handle_bracket_close(text):
                    return

        # Overwrite mode: normal character input
        if text and self.overwrite_mode and key != Qt.Key_Backspace:
            cursor = self.textCursor()
            if not cursor.hasSelection():
                cursor.beginEditBlock()
                if not cursor.atBlockEnd():
                    cursor.deleteChar()
                cursor.insertText(text)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    def set_bracket_completion (self, enabled:bool):
        self._bracket_completion_enabled = enabled

    def _handle_bracket_open (self, text:str):
        cursor = self.textCursor()
        # For quotes: if cursor is inside a matching pair, skip over
        if text in ('"', "'"):
            pos = cursor.position()
            doc = self.document()
            if pos < doc.characterCount():
                char_after = doc.characterAt(pos)
                if char_after == text:
                    cursor.movePosition(QTextCursor.Right)
                    self.setTextCursor(cursor)
                    return
        # Insert open + close, place cursor between
        close = self._BRACKET_OPEN[text]
        cursor.beginEditBlock()
        cursor.insertText(text + close)
        cursor.movePosition(QTextCursor.Left)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _handle_bracket_close (self, text:str) -> bool:
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        if pos < doc.characterCount():
            char_after = doc.characterAt(pos)
            if char_after == text:
                cursor.movePosition(QTextCursor.Right)
                self.setTextCursor(cursor)
                return True
        return False

    def _handle_backspace (self) -> bool:
        """Handle backspace: batch-delete spaces at indent boundaries,
        or delete paired brackets."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        col = cursor.columnNumber()
        if col > 0 and col % self.indent_size == 0:
            line_text = cursor.block().text()
            prefix = line_text[:col]
            if prefix and all(ch == ' ' for ch in prefix):
                # All spaces to the left, at indent boundary —
                # delete indent_size spaces at once
                cursor.beginEditBlock()
                for _i in range(self.indent_size):
                    cursor.deletePreviousChar()
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True
        # Bracket pair deletion
        if self._bracket_completion_enabled:
            pos = cursor.position()
            doc = self.document()
            if pos > 0 and pos < doc.characterCount():
                char_before = doc.characterAt(pos - 1)
                char_after = doc.characterAt(pos)
                if char_before in self._BRACKET_OPEN:
                    expected_close = self._BRACKET_OPEN[char_before]
                    if char_after == expected_close:
                        cursor.beginEditBlock()
                        cursor.deleteChar()
                        cursor.deletePreviousChar()
                        cursor.endEditBlock()
                        self.setTextCursor(cursor)
                        return True
        return False

    def _handle_enter_key (self):
        cursor = self.textCursor()
        block = cursor.block()
        line_text = block.text()
        indent = self.__extract_indent(line_text)
        pos = cursor.position()
        doc = self.document()
        char_before = ''
        char_after = ''
        if pos > 0:
            char_before = doc.characterAt(pos - 1)
        if pos < doc.characterCount():
            char_after = doc.characterAt(pos)

        extra_indent = ''
        if char_before == '{':
            if self.indent_style == 'tab':
                extra_indent = '\t'
            else:
                extra_indent = ' ' * self.indent_size

        new_indent = indent + extra_indent
        if char_before == '{' and char_after == '}':
            cursor.beginEditBlock()
            cursor.insertText('\n' + new_indent + '\n' + indent)
            cursor.endEditBlock()
            new_pos = pos + 1 + len(new_indent)
            cursor.setPosition(new_pos)
            self.setTextCursor(cursor)
        else:
            cursor.beginEditBlock()
            cursor.insertText('\n' + new_indent)
            cursor.endEditBlock()
            self.setTextCursor(cursor)

    def __extract_indent (self, line:str) -> str:
        result = []
        for ch in line:
            if ch in (' ', '\t'):
                result.append(ch)
            else:
                break
        return ''.join(result)

    def _notify_overwrite_changed (self):
        """Update status bar INS/OVR display and cursor shape."""
        if self.overwrite_mode:
            self.setCursorWidth(self.fontMetrics().horizontalAdvance('x'))
        else:
            self.setCursorWidth(1)
        win = self.window()
        if hasattr(win, '_update_status_info'):
            tab = win.tab_manager.get_current()
            if tab:
                win._update_status_info(tab)


#----------------------------------------------------------------------
# InputPanel
#----------------------------------------------------------------------
class InputPanel (QTextEdit):

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabStopWidth(
            self.fontMetrics().horizontalAdvance('x') * 4)

    def setDocument (self, doc):
        doc.setDefaultFont(self.font())
        super().setDocument(doc)

    def keyPressEvent (self, event):
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText('\t')
        else:
            super().keyPressEvent(event)


#----------------------------------------------------------------------
# Output rendering utilities
#----------------------------------------------------------------------
def _output_clear (doc:QTextDocument):
    """Clear all content from an output document."""
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.Document)
    cursor.removeSelectedText()


def _output_append (doc:QTextDocument, text:str, color:QColor=None):
    """Append text to an output document with optional foreground color.
    color=None uses default foreground (stdout default)."""
    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.End)
    fmt = QTextCharFormat()
    if color is not None:
        fmt.setForeground(QBrush(color))
    cursor.setCharFormat(fmt)
    cursor.insertText(text)


#----------------------------------------------------------------------
# OutputPanel
#----------------------------------------------------------------------
class OutputPanel (QTextEdit):

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def setDocument (self, doc):
        doc.setDefaultFont(self.font())
        super().setDocument(doc)

    def keyPressEvent (self, event):
        if event.matches(QKeySequence.Copy) or \
                (event.key() == Qt.Key_Insert and
                 event.modifiers() == Qt.ControlModifier):
            self.copy()
            return
        super().keyPressEvent(event)


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
        self.setWindowIcon(self.icons['run'])

        # Create editor and IO panels
        self.editor = CodeEditor()
        self.editor.indent_style = self.settings.indent_style
        self.editor.indent_size = self.settings.indent_size
        self.editor.set_bracket_completion(
            self.settings.bracket_completion)
        self.input_panel = InputPanel()
        self.output_panel = OutputPanel()

        # Apply Settings fonts to widgets
        editor_font = self.editor.font()
        editor_font.setFamily(self.settings.editor_font_family)
        editor_font.setPointSize(self.settings.editor_font_size)
        self.editor.setFont(editor_font)
        self.editor.updateFontMetrics()

        io_font = self.input_panel.font()
        io_font.setFamily(self.settings.io_font_family)
        io_font.setPointSize(self.settings.io_font_size)
        self.input_panel.setFont(io_font)
        self.output_panel.setFont(io_font)
        self.input_panel.setTabStopWidth(
            self.input_panel.fontMetrics().horizontalAdvance('x') * 4)

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

        # Process management and flow state
        self.enc_mgr = EncodingManager()
        self.proc_mgr = ProcessManager(parent=self, settings=self.settings)
        self._flow_state = _FLOW_IDLE
        self._flow_intent = None  # 'build', 'test', 'run'
        self._flow_tab = None     # TabData that initiated the flow

        # Create actions first (needed by menubar and toolbar)
        self.__create_actions()

        # Build UI in correct order
        self.__build_menubar()
        self.__build_toolbar()
        self.__build_mainarea()
        self.__build_tabbar_and_layout()
        self.__build_statusbar()

        # Set initial status bar text
        self._set_flow_state(_FLOW_IDLE)

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

        # Edit actions
        self.act_undo = QAction('Undo', self)
        self.act_undo.setShortcut(QKeySequence('Ctrl+Z'))
        self.act_undo.setToolTip('Undo (Ctrl+Z)')

        self.act_redo = QAction('Redo', self)
        self.act_redo.setShortcut(QKeySequence('Ctrl+Y'))
        self.act_redo.setToolTip('Redo (Ctrl+Y)')

        self.act_cut = QAction('Cut', self)
        self.act_cut.setShortcut(QKeySequence('Ctrl+X'))
        self.act_cut.setToolTip('Cut (Ctrl+X)')

        self.act_copy = QAction('Copy', self)
        self.act_copy.setShortcut(QKeySequence('Ctrl+C'))
        self.act_copy.setToolTip('Copy (Ctrl+C)')

        self.act_paste = QAction('Paste', self)
        self.act_paste.setShortcut(QKeySequence('Ctrl+V'))
        self.act_paste.setToolTip('Paste (Ctrl+V)')

        self.act_find = QAction('Find', self)
        self.act_find.setShortcut(QKeySequence('Ctrl+F'))
        self.act_find.setToolTip('Find (Ctrl+F)')

        self.act_replace = QAction('Replace', self)
        self.act_replace.setShortcut(QKeySequence('Ctrl+H'))
        self.act_replace.setToolTip('Replace (Ctrl+H)')

        self.act_goto_line = QAction('Goto Line', self)
        self.act_goto_line.setShortcut(QKeySequence('Ctrl+G'))
        self.act_goto_line.setToolTip('Goto Line (Ctrl+G)')

        # Build action
        self.act_build = QAction('Build', self)
        self.act_build.setShortcut(QKeySequence('Ctrl+B'))
        self.act_build.setToolTip('Build (Ctrl+B)')

        # About action
        self.act_about = QAction('About', self)

    def __build_menubar (self):
        menubar = self.menuBar()
        self.menu_file = menubar.addMenu('File')
        self.menu_edit = menubar.addMenu('Edit')
        self.menu_run = menubar.addMenu('Run')
        self.menu_view = menubar.addMenu('View')
        self.menu_help = menubar.addMenu('Help')

        # Populate File menu
        self.menu_file.addAction(self.act_new)
        self.menu_file.addAction(self.act_open)
        self.menu_file.addAction(self.act_save)
        self.menu_file.addAction(self.act_save_as)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_close)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_settings)

        # Populate Edit menu
        self.menu_edit.addAction(self.act_undo)
        self.menu_edit.addAction(self.act_redo)
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.act_cut)
        self.menu_edit.addAction(self.act_copy)
        self.menu_edit.addAction(self.act_paste)
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.act_find)
        self.menu_edit.addAction(self.act_replace)
        self.menu_edit.addAction(self.act_goto_line)

        # Populate Run menu
        self.menu_run.addAction(self.act_build)
        self.menu_run.addSeparator()
        self.menu_run.addAction(self.act_test)
        self.menu_run.addAction(self.act_run)
        self.menu_run.addAction(self.act_stop)

        # Populate View menu
        self.menu_view.addAction(self.act_zoom_in)
        self.menu_view.addAction(self.act_zoom_out)

        # Populate Help menu
        self.menu_help.addAction(self.act_about)

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

        # Edit actions
        self.act_undo.triggered.connect(self._action_undo)
        self.act_redo.triggered.connect(self._action_redo)
        self.act_cut.triggered.connect(self._action_cut)
        self.act_copy.triggered.connect(self._action_copy)
        self.act_paste.triggered.connect(self._action_paste)
        self.act_find.triggered.connect(self._action_find)
        self.act_replace.triggered.connect(self._action_replace)
        self.act_goto_line.triggered.connect(self._action_goto_line)

        # Run actions
        self.act_build.triggered.connect(self._action_build)
        self.act_run.triggered.connect(self._action_run)
        self.act_test.triggered.connect(self._action_test)
        self.act_stop.triggered.connect(self._action_stop)

        # Help actions
        self.act_about.triggered.connect(self._action_about)

        # Settings (placeholder until Phase 6)
        self.act_settings.triggered.connect(self._action_settings)

        # Tabbar signals
        self.tabbar.currentChanged.connect(
            self._on_tabbar_current_changed)
        self.tabbar.tabCloseRequested.connect(
            self._on_tab_close_requested)
        self.tabbar.tabMoved.connect(self._on_tab_moved)

        # Editor cursor position → update status bar
        self.editor.cursorPositionChanged.connect(
            self._on_cursor_position_changed)

        # ProcessManager signals
        self.proc_mgr.compile_finished.connect(
            self._on_compile_finished)
        self.proc_mgr.run_stdout_ready.connect(
            self._on_run_stdout_ready)
        self.proc_mgr.run_stderr_ready.connect(
            self._on_run_stderr_ready)
        self.proc_mgr.run_finished.connect(
            self._on_run_finished)

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
        try:
            content, encoding = _read_file(path)
        except (IOError, OSError) as e:
            QMessageBox.warning(
                self, 'Open Error',
                'Failed to open file: {}'.format(e))
            return
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
            idx = self.tab_manager.find_tab_index(tab)
            if idx >= 0:
                self._update_tab_name(idx)
            self._update_window_title()
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
        self.editor.setFontSize(zoom_size)

    def _action_undo (self):
        self.editor.undo()

    def _action_redo (self):
        self.editor.redo()

    def _action_cut (self):
        self.editor.cut()

    def _action_copy (self):
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, QTextEdit):
            focus.copy()
        else:
            self.editor.copy()

    def _action_paste (self):
        self.editor.paste()

    def _action_find (self):
        # TODO: implement FindDialog
        pass

    def _action_replace (self):
        # TODO: implement ReplaceDialog
        pass

    def _action_goto_line (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        max_line = self.editor.document().blockCount()
        line, ok = QInputDialog.getInt(
            self, 'Goto Line', 'Line number (1-{}):'.format(max_line),
            1, 1, max_line)
        if ok and line > 0:
            block = self.editor.document().findBlockByNumber(line - 1)
            cursor = self.editor.textCursor()
            cursor.setPosition(block.position())
            self.editor.setTextCursor(cursor)
            self.editor.centerCursor()

    def _action_build (self):
        if self._flow_state != _FLOW_IDLE:
            QMessageBox.information(
                self, 'Busy',
                'A process is currently running. '
                'Please wait or press Stop before starting a new operation.')
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._save_if_dirty(tab) < 0:
            return
        self._set_flow_state(_FLOW_COMPILING, tab=tab, intent='build')
        self._clear_and_start_compile(tab)

    def _action_run (self):
        if self._flow_state != _FLOW_IDLE:
            QMessageBox.information(
                self, 'Busy',
                'A process is currently running. '
                'Please wait or press Stop before starting a new operation.')
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._save_if_dirty(tab) < 0:
            return
        if self._need_recompile(tab):
            self._set_flow_state(_FLOW_COMPILING, tab=tab, intent='run')
            self._clear_and_start_compile(tab)
        else:
            self._launch_terminal(tab)
            self.status_message.setText('Running in terminal')

    def _action_test (self):
        if self._flow_state != _FLOW_IDLE:
            QMessageBox.information(
                self, 'Busy',
                'A process is currently running. '
                'Please wait or press Stop before starting a new operation.')
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._save_if_dirty(tab) < 0:
            return
        if self._need_recompile(tab):
            self._set_flow_state(_FLOW_COMPILING, tab=tab, intent='test')
            self._clear_and_start_compile(tab)
        else:
            self._set_flow_state(_FLOW_RUNNING, tab=tab)
            self._start_test_run(tab)

    def _action_stop (self):
        if self._flow_state in (_FLOW_COMPILING, _FLOW_RUNNING):
            self.proc_mgr.kill_process()

    def _action_about (self):
        QMessageBox.about(
            self, 'About CodeRunner',
            'CodeRunner\n\nAuthor: skywind3000\n{}'.format(
                time.strftime('%Y/%m/%d %H:%M:%S')))

    def _set_flow_state (self, state, tab=None, intent=None):
        """Set flow state and update status bar accordingly."""
        self._flow_state = state
        if tab is not None:
            self._flow_tab = tab
        if intent is not None:
            self._flow_intent = intent
        if state == _FLOW_IDLE:
            self.status_message.setText('Ready')
        elif state == _FLOW_COMPILING:
            self.status_message.setText('Compiling...')
        elif state == _FLOW_RUNNING:
            self.status_message.setText('Running...')

    def _action_settings (self):
        # TODO: implement SettingsDialog (Phase 6)
        self.status_message.setText('Settings: not yet implemented')

    #----- Compile/run helper methods -----

    def _need_recompile (self, tab:TabData) -> bool:
        """Check if recompilation is needed."""
        exe_path = self._get_exe_path(tab)
        if not exe_path or not os.path.exists(exe_path):
            return True
        source_mtime = os.path.getmtime(tab.file_path)
        exe_mtime = os.path.getmtime(exe_path)
        if exe_mtime < source_mtime:
            return True
        if exe_mtime < tab.compiler_mtime:
            return True
        return False

    def _get_exe_path (self, tab:TabData) -> str:
        """Get exe path corresponding to the source file."""
        if tab.is_new or not tab.file_path:
            return ''
        base = os.path.splitext(tab.file_path)[0]
        return base + '.exe'

    def _build_compile_command (self, tab:TabData) -> list:
        """Construct the compile command list."""
        exe_path = self._get_exe_path(tab)
        flags = self.enc_mgr.build_flags(tab.encoding)
        command = [self.settings.compiler_path]
        command.extend(flags)
        if self.settings.compiler_flags:
            command.extend(self.settings.compiler_flags.split())
        source_path = tab.file_path
        if sys.platform == 'win32':
            source_path = source_path.replace('/', '\\')
            exe_path = exe_path.replace('/', '\\')
        command.append(source_path)
        command.append('-o')
        command.append(exe_path)
        return command

    def _make_process_env (self) -> QProcessEnvironment:
        """Build QProcessEnvironment from system env + user env_vars."""
        env = QProcessEnvironment()
        for key in os.environ:
            env.insert(key, os.environ[key])
        for key, value in self.settings.env_vars.items():
            expanded = _expand_env_vars(value)
            env.insert(key, expanded)
        return env

    def _clear_and_start_compile (self, tab:TabData):
        """Clear output and start compilation."""
        _output_clear(tab.output_doc)
        _output_append(tab.output_doc, 'Compiling...\n',
                       QColor(128, 128, 128))
        command = self._build_compile_command(tab)
        work_dir = os.path.dirname(tab.file_path)
        if sys.platform == 'win32':
            work_dir = work_dir.replace('/', '\\')
        env = self._make_process_env()
        self.proc_mgr.target_tab = tab
        self.proc_mgr.start_compile(
            command, work_dir, env, self.settings.compile_timeout)

    def _start_test_run (self, tab:TabData):
        """Start test run with stdin from InputPanel."""
        exe_path = self._get_exe_path(tab)
        if sys.platform == 'win32':
            exe_path = exe_path.replace('/', '\\')
        work_dir = os.path.dirname(exe_path)
        stdin_text = tab.input_doc.toPlainText()
        stdin_data = self.enc_mgr.encode_stdin(stdin_text)
        env = self._make_process_env()
        _output_clear(tab.output_doc)
        self.proc_mgr.target_tab = tab
        self.proc_mgr.start_test_run(
            exe_path, work_dir, env, stdin_data,
            self.settings.run_timeout)

    def _launch_terminal (self, tab:TabData):
        """Launch exe in external terminal window."""
        exe_path = self._get_exe_path(tab)
        if sys.platform == 'win32':
            exe_path = exe_path.replace('/', '\\')
        work_dir = os.path.dirname(exe_path)
        bat_path = _ensure_cmd_file()
        os.environ['CR_COMMAND'] = '"{}"'.format(exe_path)
        os.environ['CR_PAUSE'] = 'pause'
        ok = QProcess.startDetached(
            'cmd',
            ['/c', 'start', '', '/D', work_dir, bat_path])
        del os.environ['CR_COMMAND']
        del os.environ['CR_PAUSE']
        if not ok:
            _output_clear(tab.output_doc)
            _output_append(tab.output_doc,
                           'Failed to launch terminal\n',
                           QColor(Qt.red))

    def _count_compile_errors (self, stderr_text:str) -> int:
        """Count the number of compile error lines in stderr output."""
        count = 0
        for line in stderr_text.splitlines():
            if ': error:' in line:
                count += 1
        return max(1, count) if stderr_text.strip() else 0

    #----- ProcessManager signal handlers -----

    def _on_compile_finished (self, exit_code:int, stderr_text:str,
                              reason:str):
        if self._flow_state != _FLOW_COMPILING:
            return
        tab = self._flow_tab
        if not tab:
            return
        if reason == 'failed_to_start':
            _output_clear(tab.output_doc)
            compiler = self.settings.compiler_path
            _output_append(
                tab.output_doc,
                'Failed to start compiler \'{}\'\n'.format(compiler),
                QColor(Qt.red))
            _output_append(
                tab.output_doc,
                'Error: {}\n'.format(stderr_text),
                QColor(Qt.red))
            _output_append(
                tab.output_doc,
                'Please check Settings to set the correct compiler path.\n',
                QColor(128, 128, 128))
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText(
                'Failed to start compiler')
        elif reason == 'timeout':
            elapsed = time.time() - self.proc_mgr._start_time
            _output_clear(tab.output_doc)
            _output_append(
                tab.output_doc,
                'Compilation timeout after {} seconds (ran {:.3}s)\n'.format(
                    self.settings.compile_timeout, elapsed),
                QColor(Qt.red))
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText(
                'Compilation timeout')
        elif reason == 'killed':
            elapsed = time.time() - self.proc_mgr._start_time
            _output_append(
                tab.output_doc,
                'Compilation stopped in {:.3}s\n'.format(elapsed),
                QColor(128, 128, 128))
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText('Compilation stopped')
        elif exit_code != 0:
            _output_clear(tab.output_doc)
            _output_append(tab.output_doc, stderr_text, QColor(Qt.red))
            n = self._count_compile_errors(stderr_text)
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText(
                'Build failed with {} error(s)'.format(n))
        else:
            # Compile succeeded — check intent
            if self._flow_intent == 'build':
                elapsed = time.time() - self.proc_mgr._start_time
                _output_clear(tab.output_doc)
                _output_append(
                    tab.output_doc,
                    'Build OK in {:.3}s\n'.format(elapsed),
                    QColor(128, 128, 128))
                self._set_flow_state(_FLOW_IDLE)
                self.status_message.setText('Build successful')
            elif self._flow_intent == 'test':
                self._set_flow_state(_FLOW_RUNNING)
                self._start_test_run(tab)
            elif self._flow_intent == 'run':
                self._launch_terminal(tab)
                self._set_flow_state(_FLOW_IDLE)
                self.status_message.setText('Running in terminal')

    def _on_run_stdout_ready (self, text:str):
        tab = self.proc_mgr.target_tab
        if tab:
            _output_append(tab.output_doc, text)

    def _on_run_stderr_ready (self, text:str):
        tab = self.proc_mgr.target_tab
        if tab:
            _output_append(tab.output_doc, text, QColor(128, 128, 128))

    def _on_run_finished (self, exit_code:int, elapsed:float,
                          peak_memory:int, reason:str, stderr_text:str):
        if self._flow_state != _FLOW_RUNNING:
            return
        tab = self._flow_tab
        if not tab:
            return
        if reason == 'failed_to_start':
            _output_clear(tab.output_doc)
            _output_append(tab.output_doc,
                           'Failed to start program\n',
                           QColor(Qt.red))
            _output_append(tab.output_doc,
                           'Error: {}\n'.format(stderr_text),
                           QColor(Qt.red))
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText('Failed to start program')
        elif reason == 'timeout':
            _output_append(
                tab.output_doc,
                'Timeout after {} seconds (ran {:.3}s)\n'.format(
                    self.settings.run_timeout, elapsed),
                QColor(Qt.red))
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText(
                'Timeout after {} seconds'.format(
                    self.settings.run_timeout))
        elif reason == 'killed':
            detail = _describe_exit_code(exit_code)
            if detail:
                _output_append(
                    tab.output_doc,
                    'Program crashed: {} (exit code {})\n'.format(
                        detail, exit_code),
                    QColor(Qt.red))
                self.status_message.setText(
                    'Program crashed: {}'.format(detail))
            else:
                _output_append(tab.output_doc,
                               'Process stopped in {:.3}s\n'.format(elapsed),
                               QColor(128, 128, 128))
                self.status_message.setText('Process stopped')
            self._set_flow_state(_FLOW_IDLE)
        elif exit_code != 0:
            detail = _describe_exit_code(exit_code)
            line = 'Runtime Error (exit code {})\n'.format(exit_code)
            if detail:
                line = 'Runtime Error: {} (exit code {})\n'.format(
                    detail, exit_code)
            _output_append(tab.output_doc, line, QColor(Qt.red))
            self._set_flow_state(_FLOW_IDLE)
            msg = 'Runtime Error (exit code {})'.format(exit_code)
            if detail:
                msg = 'Runtime Error: {}'.format(detail)
            self.status_message.setText(msg)
        else:
            mem_str = ''
            if peak_memory > 0:
                mem_mb = peak_memory / (1024 * 1024)
                mem_str = ', {:.1f}MB'.format(mem_mb)
            line = 'exit with code {} in {:.3}s{}\n'.format(
                exit_code, elapsed, mem_str)
            _output_append(tab.output_doc, line, QColor(128, 128, 128))
            self._set_flow_state(_FLOW_IDLE)
            self.status_message.setText(
                'Program exited with code 0 in {:.3}s{}'.format(
                    elapsed, mem_str))

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
            # Cancel batch highlighting on old tab to avoid editor flicker
            if old_tab.highlighter._batch_timer is not None:
                old_tab.highlighter.cancel_batch_highlight()
                old_tab._highlight_pending = True

        tm.current_index = index
        new_tab = tm.tabs[index]

        # Exit zero-tab state if needed
        if old_index == -1:
            self._exit_zero_tab_state()

        # Freeze redraw to prevent flicker
        self.editor.setUpdatesEnabled(False)
        self.input_panel.setUpdatesEnabled(False)
        self.output_panel.setUpdatesEnabled(False)
        try:
            # Swap documents
            self.editor.setDocument(new_tab.editor_doc)
            self.input_panel.setDocument(new_tab.input_doc)
            self.output_panel.setDocument(new_tab.output_doc)

            # Restore IO cursors (fast, small documents)
            self.input_panel.setTextCursor(new_tab.input_cursor)
            self.input_panel.verticalScrollBar().setValue(new_tab.input_scroll)

            # Restore zoom font size
            zoom_size = max(6, self.settings.editor_font_size + new_tab.zoom_font_size)
            self.editor.setFontSize(zoom_size)
        finally:
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
        self._update_window_title()

        # Deferred editor cursor/scroll restore
        self._deferred_restore_tab = index
        QTimer.singleShot(0, self._restore_deferred_cursor)

        # Start progressive highlighting for deferred tabs
        if new_tab._highlight_pending:
            QTimer.singleShot(0, lambda: self._start_batch_highlight(new_tab))

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

        # Cancel batch highlighting before removing
        tab.highlighter.cancel_batch_highlight()

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
        total = self.editor.document().blockCount()
        mode = 'OVR' if self.editor.overwrite_mode else 'INS'
        text = 'Ln {}/{}, Col {} | {} | {}'.format(
            line, total, col, tab.encoding, mode)
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

    def _update_window_title (self):
        """Update main window title based on current tab state."""
        tab = self.tab_manager.get_current()
        if tab is None or tab.is_new:
            self.setWindowTitle('CodeRunner')
        else:
            name = os.path.basename(tab.file_path)
            dir_path = os.path.dirname(tab.file_path)
            if sys.platform == 'win32':
                dir_path = dir_path.replace('/', '\\')
            self.setWindowTitle(
                '{} ({}) - CodeRunner'.format(name, dir_path))

    #----- Helpers -----

    def _save_if_dirty (self, tab:TabData) -> int:
        """Save tab if it has unsaved changes. Returns 0 success/clean,
        -1 user cancelled save dialog, -2 write error.
        If tab is not dirty and not new, no save is needed → returns 0."""
        if not tab.is_dirty and not tab.is_new:
            return 0
        return self._save_tab_data(tab)

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
        # modificationChanged signal already updates this tab's name
        self.status_message.setText(
            'Saved: {}'.format(os.path.basename(tab.file_path)))
        self._update_window_title()
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
        if index == self.tab_manager.current_index:
            self._update_window_title()

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
        self.setWindowTitle('CodeRunner')

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

    def _start_batch_highlight (self, tab:TabData):
        """Start progressive syntax highlighting for a newly opened tab."""
        if not tab._highlight_pending:
            return
        # Verify the tab still exists and is the currently displayed tab
        idx = self.tab_manager.find_tab_index(tab)
        if idx < 0 or idx != self.tab_manager.current_index:
            return
        tab.highlighter.start_batch_highlight(self.editor)
        tab._highlight_pending = False

    #----- Window close -----

    def closeEvent (self, event):
        for tab in list(self.tab_manager.tabs):
            if tab.is_dirty:
                choice = self._confirm_close_tab(tab)
                if choice == 'cancel':
                    event.ignore()
                    return
                elif choice == 'save':
                    result = self._save_tab_data(tab)
                    if result < 0:
                        event.ignore()
                        return
        # Cancel all batch highlighting timers before Qt destruction
        for tab in self.tab_manager.tabs:
            tab.highlighter.cancel_batch_highlight()

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
