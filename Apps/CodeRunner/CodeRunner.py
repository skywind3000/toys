#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# CodeRunner.py - C++ Code Runner for OJ Practice
#
# Created by skywind on 2026/05/05
# Last Modified: 2026/05/07 22:00:00
#
#======================================================================
import sys
import os
import re
import copy
import math
import time
import json
import shlex
import locale
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QTabBar, QSplitter,
    QTextEdit, QLabel, QWidget, QAction, QMenu,
    QVBoxLayout, QShortcut, QFileDialog, QMessageBox,
    QInputDialog, QDialog, QTabWidget, QLineEdit,
    QSpinBox, QCheckBox, QFontComboBox, QTableWidget,
    QTableWidgetItem, QPushButton, QHBoxLayout,
    QHeaderView, QComboBox, QRadioButton,
    QPlainTextEdit as QPlainTextEditWidget
)
from PyQt5.QtCore import (
    Qt, QSize, QPointF, QTimer, QRect, QRegularExpression,
    QProcess, QProcessEnvironment, pyqtSignal, QObject,
    QtMsgType, qInstallMessageHandler
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
# Version info
#----------------------------------------------------------------------
CR_VERSION_MAJOR = 1
CR_VERSION_MINOR = 0
CR_VERSION_PATCH = 0

CR_VERSION_TEXT = '{}.{}.{}'.format(
    CR_VERSION_MAJOR, CR_VERSION_MINOR, CR_VERSION_PATCH)


#----------------------------------------------------------------------
# Flow state constants
#----------------------------------------------------------------------
_FLOW_IDLE = 'idle'
_FLOW_COMPILING = 'compiling'
_FLOW_RUNNING = 'running'

# Windows NTSTATUS codes for common crash scenarios
_DLL_NOT_FOUND = 0xC0000135      # STATUS_DLL_NOT_FOUND (-1073741515)
_ACCESS_VIOLATION = 0xC0000005   # STATUS_ACCESS_VIOLATION (-1073741819)
_STACK_OVERFLOW = 0xC00000FD     # STATUS_STACK_OVERFLOW (-1073741571)
_INTEGER_DIVIDE_BY_ZERO = 0xC0000094  # STATUS_INTEGER_DIVIDE_BY_ZERO (-1073741676)
_INTEGER_OVERFLOW = 0xC0000095  # STATUS_INTEGER_OVERFLOW (-1073741675)
_FLOAT_DIVIDE_BY_ZERO = 0xC0000090  # STATUS_FLOAT_DIVIDE_BY_ZERO (-1073741680)
_FLOAT_OVERFLOW = 0xC0000091    # STATUS_FLOAT_OVERFLOW (-1073741679)
_HEAP_CORRUPTION = 0xC0000374   # STATUS_HEAP_CORRUPTION (-1073740956)

# Common encodings for Reopen/Save with Encoding menu
_COMMON_ENCODINGS = [
    'UTF-8', 'GBK', 'GB18030', 'Big5', 'Shift_JIS',
    'EUC-JP', 'EUC-KR', 'ISO-8859-1', 'ISO-8859-2',
    'Windows-1252', 'Windows-1251',
]

# Output panel size limit (character count) -- prevents runaway programs
# from consuming excessive memory and degrading UI responsiveness
_OUTPUT_MAX_CHARS = 500000


def _describe_exit_code (exit_code:int) -> str:
    """Return human-readable description for Windows crash exit codes."""
    if sys.platform != 'win32':
        return ''
    if exit_code < 0:
        code = exit_code & 0xFFFFFFFF
        if code == _ACCESS_VIOLATION:
            return 'Access violation'
        if code == _STACK_OVERFLOW:
            return 'Stack overflow'
        if code == _INTEGER_DIVIDE_BY_ZERO:
            return 'Integer divide by zero'
        if code == _INTEGER_OVERFLOW:
            return 'Integer overflow'
        if code == _FLOAT_DIVIDE_BY_ZERO:
            return 'Float divide by zero'
        if code == _FLOAT_OVERFLOW:
            return 'Float overflow'
        if code == _DLL_NOT_FOUND:
            return 'DLL not found'
        if code == _HEAP_CORRUPTION:
            return 'Heap corruption'
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
    """Fill empty font family settings with platform-detected monospace.
    Called after load() so detected values only replace empty strings
    (e.g. from older JSON that didn't save font families)."""
    font = _detect_monospace_font()
    if not settings.editor_font_family:
        settings.editor_font_family = font
    if not settings.io_font_family:
        settings.io_font_family = font


def _ensure_dir (path:str) -> None:
    """Create directory if it does not exist."""
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _settings_path () -> str:
    """Return path to settings.json."""
    base = os.path.expanduser('~/.config/coderunner')
    return os.path.join(base, 'settings.json')


def _window_state_path () -> str:
    """Return path to window.json."""
    base = os.path.expanduser('~/.cache/coderunner')
    return os.path.join(base, 'window.json')


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
# Action definitions (data-driven creation)
#----------------------------------------------------------------------
_ACTION_DEFS = [
    # (attr_name, label, icon_key, shortcuts, tooltip)
    # icon_key: None or string key in self.icons dict
    # shortcuts: str, list of str, or None
    # tooltip: None = auto "Label (Shortcut)", '' = no tooltip, str = explicit
    ('act_new', 'New', 'new', 'Ctrl+N', None),
    ('act_save', 'Save', 'save', 'Ctrl+S', None),
    ('act_open', 'Open', 'open', 'Ctrl+O', None),
    ('act_save_as', 'Save As', None, 'Ctrl+Shift+S', None),
    ('act_close', 'Close', None, 'Ctrl+W', None),
    ('act_run', 'Run', 'run', 'F5', None),
    ('act_test', 'Test', 'test', 'F9', None),
    ('act_stop', 'Stop', 'stop', 'F7', None),
    ('act_settings', 'Settings', 'settings', None, 'Settings'),
    ('act_zoom_in', 'Zoom In', None, ['Ctrl++', 'Ctrl+='], None),
    ('act_zoom_out', 'Zoom Out', None, ['Ctrl+-'], None),
    ('act_undo', 'Undo', None, 'Ctrl+Z', None),
    ('act_redo', 'Redo', None, 'Ctrl+Y', None),
    ('act_cut', 'Cut', None, 'Ctrl+X', None),
    ('act_copy', 'Copy', None, 'Ctrl+C', None),
    ('act_paste', 'Paste', None, 'Ctrl+V', None),
    ('act_find', 'Find', None, 'Ctrl+F', None),
    ('act_replace', 'Replace', None, 'Ctrl+H', None),
    ('act_goto_line', 'Goto Line', None, 'Ctrl+G', None),
    ('act_comment', 'Comment/Uncomment', None, 'Ctrl+/', None),
    ('act_indent', 'Indent', None, 'Ctrl+]', None),
    ('act_unindent', 'Unindent', None, 'Ctrl+[', None),
    ('act_duplicate', 'Duplicate Line', None, 'Ctrl+D', None),
    ('act_delete_line', 'Delete Line', None, 'Ctrl+Shift+K', None),
    ('act_move_up', 'Move Line Up', None, 'Alt+Up', None),
    ('act_move_down', 'Move Line Down', None, 'Alt+Down', None),
    ('act_build', 'Build', None, 'Ctrl+B', None),
    ('act_about', 'About', None, None, ''),
]


#----------------------------------------------------------------------
# File encoding detection (inlined in _read_file)
#----------------------------------------------------------------------

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
    encoding = EncodingManager.platform_charset().upper()
    content = raw.decode(encoding, 'replace')
    return (content, encoding)


#----------------------------------------------------------------------
# Charset normalization: map Windows codepage names to standard names
# recognized by both Python codecs and GCC -fexec-charset/-finput-charset
#----------------------------------------------------------------------
_CHARSET_NORMALIZE = {
    'cp936': 'gbk',
    'cp932': 'shift_jis',
    'cp949': 'euc-kr',
    'cp950': 'big5',
    'cp1252': 'windows-1252',
    'cp1250': 'windows-1250',
    'cp1251': 'windows-1251',
    'cp1253': 'windows-1253',
    'cp1254': 'windows-1254',
    'cp1255': 'windows-1255',
    'cp1256': 'windows-1256',
    'cp1257': 'windows-1257',
    'cp1258': 'windows-1258',
}


#----------------------------------------------------------------------
# EncodingManager
#----------------------------------------------------------------------
class EncodingManager:
    """Encoding detection, compilation flags, and I/O conversion."""

    @staticmethod
    def platform_charset () -> str:
        raw = locale.getpreferredencoding(False).lower()
        return _CHARSET_NORMALIZE.get(raw, raw)

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
# Compiler path resolution
#----------------------------------------------------------------------
def _resolve_compiler_path (compiler_path:str) -> tuple:
    """Resolve compiler_path to (resolved_path, bin_dir).

    Returns:
        (resolved_path, bin_dir) where:
        - resolved_path: the actual compiler executable path to use
        - bin_dir: directory to prepend to PATH (empty string if none)

    Three cases:
        - Bare name (e.g. 'g++'): resolved_path stays as-is,
          bin_dir is '' (assumed already in PATH)
        - Absolute path (e.g. 'C:\\MinGW\\bin\\g++'): resolved_path
          stays as-is, bin_dir is the directory part
        - Relative path (e.g. '.\\g++' or '../bin/g++'): resolved
          relative to CodeRunner.py's directory, bin_dir is the
          resolved directory part
    """
    if not compiler_path:
        return (compiler_path, '')
    # Check if it's a bare name (no directory separator)
    dir_part = os.path.dirname(compiler_path)
    if not dir_part:
        # Bare name like 'g++' -- already in PATH
        return (compiler_path, '')
    if os.path.isabs(compiler_path):
        # Absolute path like C:\MinGW\bin\g++.exe
        bin_dir = os.path.dirname(compiler_path)
        return (compiler_path, bin_dir)
    # Relative path -- resolve against CodeRunner.py's directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    resolved = os.path.abspath(os.path.join(base_dir, compiler_path))
    bin_dir = os.path.dirname(resolved)
    return (resolved, bin_dir)


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
        '%CR_SET_PATH%\n'
        '%CR_ENV_SETUP%\n'
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
# Accepted source file extensions for Open / drag-drop
_SOURCE_EXTENSIONS = ('.cpp', '.c', '.cc', '.cxx', '.h', '.hpp', '.hh')

# Settings defaults
#----------------------------------------------------------------------
_SETTINGS_DEFAULTS = {
    'compiler_path': 'gcc',
    'compiler_flags': '',
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
    'compiler_mtime': 0,
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
        for key, value in copy.deepcopy(src).items():
            setattr(self, key, value)

    def copy (self):
        """Create an independent deep copy of this Settings instance."""
        return Settings(copy.deepcopy(self.__dict__))

    def apply_from (self, other):
        """Merge all attributes from other into this instance.
        Deep-copy mutable values to prevent shared reference issues."""
        for key, value in other.__dict__.items():
            if isinstance(value, (dict, list, set)):
                setattr(self, key, copy.deepcopy(value))
            else:
                setattr(self, key, value)

    def to_dict (self) -> dict:
        """Serialize Settings to a dict suitable for JSON."""
        return copy.deepcopy(self.__dict__)

    def load (self, path:str=None) -> int:
        """Load Settings from JSON file. Returns 0 success, -1 not found."""
        if path is None:
            path = _settings_path()
        if not os.path.exists(path):
            return -1
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (IOError, OSError, json.JSONDecodeError):
            return -1
        # Only load keys that exist in defaults (ignore unknown keys)
        for key in _SETTINGS_DEFAULTS:
            if key in data:
                value = data[key]
                if key == 'env_vars' and not isinstance(value, dict):
                    value = {}
                setattr(self, key, value)
        return 0

    def save (self, path:str=None) -> int:
        """Save Settings to JSON file. Returns 0 success, -1 error."""
        if path is None:
            path = _settings_path()
        _ensure_dir(os.path.dirname(path))
        data = self.to_dict()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except (IOError, OSError):
            return -1
        return 0


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
        # Multi-line comments FIRST so their format spans occupy positions
        # before single-line rules. Qt's format overlay uses "first-format-wins":
        # later setFormat calls cannot override already-set formats. By applying
        # comment format first, positions inside /* */ get green; then
        # __format_if_free sees them as non-free and skips, preserving green.
        self.__highlight_multiline_comments(text)
        # Single-line rules (first-match-wins, skip comment positions)
        for regex, fmt in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart()
                length = match.capturedLength()
                self.__format_if_free(start, length, fmt)

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

    def __is_position_masked (self, text:str, pos:int) -> bool:
        """Check if position is inside a string/char literal or SL comment.
        Used in deferred mode where format() hasn't been applied yet.
        Simulates first-match-wins: strings/chars mask // inside them."""
        # Collect string and char literal ranges first (higher semantic priority)
        masked = []
        for regex in (self._rules[1][0], self._rules[2][0]):  # strings, chars
            it = regex.globalMatch(text)
            while it.hasNext():
                m = it.next()
                masked.append((m.capturedStart(), m.capturedEnd()))
        # Find // comments not inside any string/char range
        it = self._rules[0][0].globalMatch(text)  # //[^\n]*
        while it.hasNext():
            m = it.next()
            start = m.capturedStart()
            inside_str = any(start >= s and start < e for s, e in masked)
            if not inside_str:
                masked.append((start, len(text)))
        # Check if pos falls inside any masked range
        return any(pos >= s and pos < e for s, e in masked)

    def __find_free_multi_start (self, text:str, offset:int = 0):
        """Find next /* that is not masked by string/char/SL comment.
        Returns match or None. Used in deferred mode."""
        match = self._multi_start.match(text, offset)
        while match.hasMatch():
            idx = match.capturedStart()
            if not self.__is_position_masked(text, idx):
                return match
            match = self._multi_start.match(text, match.capturedEnd())
        return None

    def __highlight_multiline_comments (self, text:str):
        start_state = self.previousBlockState()
        start_idx = 0
        if start_state != 1:
            # Find first /* not masked by string/char/SL comment (regex-based
            # check since we run BEFORE single-line rules, no format spans yet)
            match = self.__find_free_multi_start(text)
            if match:
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
            # Loop: continue looking for more /* */ pairs after closing */
            search_from = end_idx
            while True:
                next_start = self.__find_free_multi_start(text, search_from)
                if not next_start:
                    break
                ns = next_start.capturedStart()
                next_end = self._multi_end.match(text, ns)
                if next_end.hasMatch():
                    ne = next_end.capturedEnd()
                    self.setFormat(ns, ne - ns, self._multi_fmt)
                    search_from = ne
                else:
                    self.setFormat(ns, len(text) - ns, self._multi_fmt)
                    self.setCurrentBlockState(1)
                    break
        else:
            self.setFormat(start_idx, len(text) - start_idx,
                           self._multi_fmt)
            self.setCurrentBlockState(1)

    def __track_multiline_state (self, text:str):
        """Deferred mode: only track multiline comment state, no formatting.
        Uses __is_position_masked to simulate first-match-wins for // and strings."""
        start_state = self.previousBlockState()
        start_idx = 0
        if start_state != 1:
            match = self.__find_free_multi_start(text)
            if match:
                start_idx = match.capturedStart()
            else:
                self.setCurrentBlockState(0)
                return
        end_match = self._multi_end.match(text, start_idx)
        if end_match.hasMatch():
            self.setCurrentBlockState(0)
            # Loop: continue tracking more /* */ pairs
            search_from = end_match.capturedEnd()
            while True:
                next_start = self.__find_free_multi_start(text, search_from)
                if not next_start:
                    break
                next_end = self._multi_end.match(
                    text, next_start.capturedStart())
                if next_end.hasMatch():
                    search_from = next_end.capturedEnd()
                else:
                    self.setCurrentBlockState(1)
                    break
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
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.__process_highlight_batch)
            timer.start(0)
            self._batch_timer = timer
        else:
            self._batch_timer = None
            self._batch_editor = None

    def cancel_batch_highlight (self):
        """Cancel any in-progress batch highlighting."""
        if self._batch_timer is not None:
            self._batch_timer.stop()
            self._batch_timer.timeout.disconnect(self.__process_highlight_batch)
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
        self.output_scroll = 0

        self.encoding = encoding
        self.zoom_font_size = 0
        self.compiler_mtime = 0
        self._highlight_pending = True
        self.pinned_to_bottom = True  # auto-scroll when output is at bottom
        self.output_buffer = []      # [(color, text)] pending output entries

        # Set initial content without triggering modificationChanged
        self.editor_doc.blockSignals(True)
        if content:
            self.editor_doc.setPlainText(content)
        if not is_new:
            self.editor_doc.setModified(False)
        self.editor_doc.blockSignals(False)

        # Highlighter created in deferred mode (no format spans initially)
        self.highlighter = CppHighlighter(self.editor_doc, deferred=True)
        # Store on document so CodeEditor can find it via setDocument
        self.editor_doc._highlighter = self.highlighter

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
# TabManager (pure data manager -- no UI coupling)
#----------------------------------------------------------------------
class TabManager:

    def __init__ (self):
        self.tabs = []
        self.current_index = -1
        self.untitled_counter = 0

    def add_tab (self, tab:TabData) -> int:
        """Add tab to list, assign untitled number if needed. Returns index."""
        if tab.is_new:
            if tab.untitled_number <= 0:
                self.untitled_counter += 1
                tab.untitled_number = self.untitled_counter
            elif tab.untitled_number > self.untitled_counter:
                self.untitled_counter = tab.untitled_number
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
    run_finished = pyqtSignal(int, float, int, str, str)  # exit_code, elapsed, peak, reason, error_detail
    # reason: 'normal' / 'timeout' / 'killed' / 'failed_to_start'
    # error_detail: only populated for 'failed_to_start' (QProcess error string)

    def __init__ (self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings
        self.process = None
        self.busy = False
        self.mode = None  # 'compile' or 'test_run'
        self.target_tab = None
        self.start_time = 0.0
        self._peak_memory = 0
        self._memory_timer = None
        self._timeout_timer = None
        self._tracked_pid = 0
        self._tracked_process = None
        self._stdin_data = None
        self._enc_mgr = EncodingManager()
        self._stderr_buffer = ''
        self._finished_emitted = False

    def start_compile (self, command:list, work_dir:str,
                       env:QProcessEnvironment, timeout:int=20):
        self.busy = True
        self.mode = 'compile'
        self.start_time = time.time()
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
        # errorOccurred handles FailedToStart asynchronously
        error_signal_name = (
            'errorOccurred' if hasattr(QProcess, 'errorOccurred') else 'error')
        getattr(self.process, error_signal_name).connect(
            self._on_compile_error)
        # Start timeout timer BEFORE process to avoid gap
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_compile_timeout)
        self._timeout_timer.start(timeout * 1000)
        self.process.start(command[0], command[1:])

    def start_test_run (self, exe_path:str, work_dir:str,
                        env:QProcessEnvironment, stdin_data:bytes,
                        timeout:int=30):
        self.busy = True
        self.mode = 'test_run'
        self.start_time = time.time()
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
        # errorOccurred handles FailedToStart asynchronously
        error_signal_name = (
            'errorOccurred' if hasattr(QProcess, 'errorOccurred') else 'error')
        getattr(self.process, error_signal_name).connect(
            self._on_run_error)
        # Start timeout timer BEFORE process to avoid gap
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_run_timeout)
        self._timeout_timer.start(timeout * 1000)
        self.process.start(exe_path)

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
            except (RuntimeError, TypeError):
                pass
            try:
                self.process.readyReadStandardError.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                self.process.readyReadStandardOutput.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                self.process.started.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                error_signal_name = (
                    'errorOccurred' if hasattr(QProcess, 'errorOccurred')
                    else 'error')
                getattr(self.process, error_signal_name).disconnect()
            except (RuntimeError, TypeError):
                pass
            self.process.deleteLater()
            self.process = None
        self.busy = False
        self.mode = None
        self.target_tab = None
        self._stdin_data = None

    def _stop_timeout_timer (self):
        if self._timeout_timer:
            self._timeout_timer.stop()
            self._timeout_timer = None

    def drain_remaining_output (self) -> tuple:
        """Read and decode remaining stdout/stderr from process.
        Returns (stdout_text, stderr_text). Called before _cleanup to
        avoid losing buffered output."""
        stdout_text = ''
        stderr_text = ''
        if self.process:
            remaining = self.process.readAllStandardOutput()
            if remaining and bytes(remaining):
                stdout_text = self._enc_mgr.decode_stdout(bytes(remaining))
            remaining = self.process.readAllStandardError()
            if remaining and bytes(remaining):
                stderr_text = self._enc_mgr.decode_stderr(bytes(remaining))
        return (stdout_text, stderr_text)

    #----- Compile handlers -----

    def _on_compile_stderr_ready (self):
        if self.process is None:
            return
        raw = self.process.readAllStandardError()
        data = bytes(raw)
        if data:
            text = self._enc_mgr.decode_stderr(data)
            self._stderr_buffer += text

    def _on_compile_finished (self, exit_code:int, exit_status):
        if self._finished_emitted or self.process is None:
            return
        self._finished_emitted = True
        self._stop_timeout_timer()
        # Read any remaining stderr
        remaining = self.process.readAllStandardError()
        if remaining and bytes(remaining):
            self._stderr_buffer += self._enc_mgr.decode_stderr(
                bytes(remaining))
        stderr_text = self._stderr_buffer
        killed = exit_status != QProcess.NormalExit
        reason = 'killed' if killed else 'normal'
        self._cleanup()
        self.compile_finished.emit(exit_code, stderr_text, reason)

    def _on_compile_timeout (self):
        if self._finished_emitted:
            return
        if not self.process or self.process.state() == QProcess.NotRunning:
            return
        self._finished_emitted = True
        # Read any remaining stderr before cleanup
        remaining = self.process.readAllStandardError()
        if remaining and bytes(remaining):
            self._stderr_buffer += self._enc_mgr.decode_stderr(
                bytes(remaining))
        stderr_text = self._stderr_buffer
        self.process.kill()
        self._cleanup()
        self.compile_finished.emit(-1, stderr_text, 'timeout')

    def _on_compile_error (self, error):
        """Handle QProcess error for compile process."""
        if self._finished_emitted:
            return
        if error == QProcess.FailedToStart:
            self._finished_emitted = True
            self._stop_timeout_timer()
            err_msg = self.process.errorString()
            self._cleanup()
            self.compile_finished.emit(-1, err_msg, 'failed_to_start')

    #----- Run handlers -----

    def _on_run_started (self):
        self.process.write(self._stdin_data)
        self.process.closeWriteChannel()
        self.process.started.disconnect(self._on_run_started)
        self._stdin_data = None
        if _HAS_PSUTIL:
            self._start_memory_tracking(self.process.processId())

    def _on_run_stdout_ready (self):
        if self.process is None:
            return
        raw = self.process.readAllStandardOutput()
        data = bytes(raw)
        if data:
            text = self._enc_mgr.decode_stdout(data)
            self.run_stdout_ready.emit(text)

    def _on_run_stderr_ready (self):
        if self.process is None:
            return
        raw = self.process.readAllStandardError()
        data = bytes(raw)
        if data:
            text = self._enc_mgr.decode_stderr(data)
            self.run_stderr_ready.emit(text)

    def _on_run_finished (self, exit_code:int, exit_status):
        if self._finished_emitted or self.process is None:
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
        elapsed = time.time() - self.start_time
        peak = self._peak_memory
        self._stop_memory_tracking()
        self._cleanup()
        self.run_finished.emit(exit_code, elapsed, peak, reason, '')  # error_detail: unused

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
        elapsed = time.time() - self.start_time
        peak = self._peak_memory
        self.process.kill()
        self._cleanup()
        self.run_finished.emit(-1, elapsed, peak, 'timeout', '')  # error_detail: unused

    def _on_run_error (self, error):
        """Handle QProcess error for run process."""
        if self._finished_emitted:
            return
        if error == QProcess.FailedToStart:
            self._finished_emitted = True
            self._stop_timeout_timer()
            err_msg = self.process.errorString()
            self._cleanup()
            self.run_finished.emit(-1, 0, 0, 'failed_to_start', err_msg)

    #----- Memory tracking -----

    def _start_memory_tracking (self, pid:int):
        self._peak_memory = 0
        self._tracked_pid = pid
        self._tracked_process = _psutil.Process(pid)
        self._memory_timer = QTimer(self)
        self._memory_timer.timeout.connect(self._poll_memory)
        self._memory_timer.start(100)

    def _poll_memory (self):
        try:
            mem = self._tracked_process.memory_info()
            self._peak_memory = max(self._peak_memory, mem.rss)
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            pass

    def _stop_memory_tracking (self):
        if self._memory_timer:
            self._memory_timer.stop()
            self._memory_timer = None
        self._tracked_pid = 0
        self._tracked_process = None


#----------------------------------------------------------------------
# FlowController -- compile/run state machine
#----------------------------------------------------------------------
class FlowController (QObject):
    """Compile/run state machine. Manages state transitions and output
    content. UI presentation (status bar, scroll, dialogs) is delegated
    to MainWindow via signals."""

    state_changed = pyqtSignal(str)        # idle/compiling/running -> default status text
    status_message = pyqtSignal(str)       # specific result message -> override status text
    busy_message_requested = pyqtSignal()  # popup busy message
    terminal_requested = pyqtSignal(object)  # tab -> MainWindow execute launch_terminal
    output_clear = pyqtSignal(object)      # tab -> MainWindow clears output buffer + doc + pins to bottom
    output_append = pyqtSignal(object, object, str)  # tab, color(QColor/None), text -> MainWindow appends to buffer
    run_stdout_ready = pyqtSignal(str)     # forwarded from ProcessManager
    run_stderr_ready = pyqtSignal(str)     # forwarded from ProcessManager

    def __init__ (self, settings, enc_mgr):
        super().__init__()
        self.settings = settings
        self.enc_mgr = enc_mgr
        self.proc_mgr = ProcessManager(parent=None, settings=settings)
        self.state = _FLOW_IDLE
        self.intent = None   # 'build'/'test'/'run'
        self.tab = None      # TabData that initiated the flow

        # Connect ProcessManager signals to self
        self.proc_mgr.compile_finished.connect(self.on_compile_finished)
        self.proc_mgr.run_finished.connect(self.on_run_finished)
        # Forward stdout/stderr signals so MainWindow doesn't need to
        # reach into proc_mgr directly
        self.proc_mgr.run_stdout_ready.connect(self.run_stdout_ready.emit)
        self.proc_mgr.run_stderr_ready.connect(self.run_stderr_ready.emit)

    #----- Entry methods (called by MainWindow._action_*) -----

    def start_build (self, tab):
        if self.state != _FLOW_IDLE:
            self.busy_message_requested.emit()
            return
        if tab is None:
            return
        self.set_state(_FLOW_COMPILING, tab=tab, intent='build')
        self.clear_and_start_compile(tab)

    def start_test (self, tab):
        if self.state != _FLOW_IDLE:
            self.busy_message_requested.emit()
            return
        if tab is None:
            return
        if self.need_recompile(tab):
            self.set_state(_FLOW_COMPILING, tab=tab, intent='test')
            self.clear_and_start_compile(tab)
        else:
            self.set_state(_FLOW_RUNNING, tab=tab)
            self.start_test_run(tab)

    def start_run (self, tab):
        if self.state != _FLOW_IDLE:
            self.busy_message_requested.emit()
            return
        if tab is None:
            return
        if self.need_recompile(tab):
            self.set_state(_FLOW_COMPILING, tab=tab, intent='run')
            self.clear_and_start_compile(tab)
        else:
            # No recompile needed - launch terminal directly
            self.set_state(_FLOW_IDLE)
            self.terminal_requested.emit(tab)

    def kill_if_busy (self):
        if self.state in (_FLOW_COMPILING, _FLOW_RUNNING):
            self.proc_mgr.kill_process()

    def cancel_flow (self):
        """Cancel current flow: kill process, drain remaining output,
        cleanup, reset to IDLE. Emits output signals for drained data.
        Returns the tab that was being processed, or None if idle."""
        if self.state == _FLOW_IDLE:
            return None
        tab = self.tab
        proc_mgr = self.proc_mgr
        proc_mgr.kill_process()
        if proc_mgr.process and \
           proc_mgr.process.state() != QProcess.NotRunning:
            proc_mgr.process.waitForFinished(500)
        # Drain remaining output -- route all to tab's output regardless
        stdout_text, stderr_text = proc_mgr.drain_remaining_output()
        if stdout_text:
            self.output_append.emit(tab, None, stdout_text)
        if stderr_text:
            self.output_append.emit(tab, QColor(128, 128, 128), stderr_text)
        proc_mgr._cleanup()
        self.set_state(_FLOW_IDLE)
        return tab

    #----- State management -----

    def set_state (self, state, tab=None, intent=None):
        """Set flow state and emit signal for MainWindow to update
        status bar with default text (Ready/Compiling.../Running...)."""
        self.state = state
        if tab is not None:
            self.tab = tab
        if intent is not None:
            self.intent = intent
        self.state_changed.emit(state)

    #----- Compile/Run helpers -----

    def need_recompile (self, tab):
        """Check if recompilation is needed."""
        exe_path = self.get_exe_path(tab)
        if not exe_path or not os.path.exists(exe_path):
            return True
        try:
            source_mtime = os.path.getmtime(tab.file_path)
            exe_mtime = os.path.getmtime(exe_path)
        except OSError:
            return True
        if exe_mtime < source_mtime:
            return True
        if exe_mtime < tab.compiler_mtime:
            return True
        return False

    def get_exe_path (self, tab):
        """Get exe path corresponding to the source file."""
        if tab.is_new or not tab.file_path:
            return ''
        base = os.path.splitext(tab.file_path)[0]
        if sys.platform == 'win32':
            return base + '.exe'
        return base

    def build_compile_command (self, tab):
        """Construct the compile command list."""
        exe_path = self.get_exe_path(tab)
        flags = self.enc_mgr.build_flags(tab.encoding)
        resolved, _ = _resolve_compiler_path(self.settings.compiler_path)
        command = [resolved]
        command.extend(flags)
        if self.settings.compiler_flags:
            try:
                command.extend(shlex.split(self.settings.compiler_flags))
            except ValueError:
                # shlex can fail on unmatched quotes; fall back to plain split
                command.extend(self.settings.compiler_flags.split())
        source_path = tab.file_path
        if sys.platform == 'win32':
            source_path = source_path.replace('/', '\\')
            exe_path = exe_path.replace('/', '\\')
        command.append(source_path)
        command.append('-o')
        command.append(exe_path)
        command.append('-lstdc++')
        return command

    def make_process_env (self):
        """Build QProcessEnvironment from system env + user env_vars."""
        env = QProcessEnvironment.systemEnvironment()
        for key, value in self.settings.env_vars.items():
            expanded = _expand_env_vars(value)
            env.insert(key, expanded)
        _, bin_dir = _resolve_compiler_path(self.settings.compiler_path)
        if bin_dir:
            old_path = env.value('PATH', '')
            sep = ';' if sys.platform == 'win32' else ':'
            env.insert('PATH', bin_dir + sep + old_path)
        return env

    def clear_and_start_compile (self, tab):
        """Clear output and start compilation."""
        self.output_clear.emit(tab)
        self.output_append.emit(tab, QColor(128, 128, 128), 'Compiling...\n')
        command = self.build_compile_command(tab)
        work_dir = os.path.dirname(tab.file_path)
        if sys.platform == 'win32':
            work_dir = work_dir.replace('/', '\\')
        env = self.make_process_env()
        self.proc_mgr.target_tab = tab
        self.proc_mgr.start_compile(
            command, work_dir, env, self.settings.compile_timeout)

    def start_test_run (self, tab):
        """Start test run with stdin from InputPanel."""
        exe_path = self.get_exe_path(tab)
        if sys.platform == 'win32':
            exe_path = exe_path.replace('/', '\\')
        work_dir = os.path.dirname(exe_path)
        stdin_text = tab.input_doc.toPlainText()
        stdin_data = self.enc_mgr.encode_stdin(stdin_text)
        env = self.make_process_env()
        self.output_clear.emit(tab)
        self.proc_mgr.target_tab = tab
        self.proc_mgr.start_test_run(
            exe_path, work_dir, env, stdin_data,
            self.settings.run_timeout)

    def count_compile_errors (self, stderr_text):
        """Count the number of compile error lines in stderr output."""
        count = 0
        for line in stderr_text.splitlines():
            if ': error:' in line:
                count += 1
        if count > 0:
            return count
        return 1 if stderr_text.strip() else 0

    #----- ProcessManager signal handlers -----

    def on_compile_finished (self, exit_code, stderr_text, reason):
        if self.state != _FLOW_COMPILING:
            return
        tab = self.tab
        if not tab:
            self.set_state(_FLOW_IDLE)
            return
        if reason == 'failed_to_start':
            self.output_clear.emit(tab)
            compiler = self.settings.compiler_path
            self.output_append.emit(tab, QColor(Qt.red),
                'Failed to start compiler \'{}\'\n'.format(compiler))
            self.output_append.emit(tab, QColor(Qt.red),
                'Error: {}\n'.format(stderr_text))
            self.output_append.emit(tab, QColor(128, 128, 128),
                'Please check Settings to set the correct compiler path.\n')
            self.set_state(_FLOW_IDLE)
            self.status_message.emit('Failed to start compiler')
        elif reason == 'timeout':
            elapsed = time.time() - self.proc_mgr.start_time
            self.output_clear.emit(tab)
            self.output_append.emit(tab, QColor(Qt.red),
                'Compilation timeout after {} seconds (ran {:.3}s)\n'.format(
                    self.settings.compile_timeout, elapsed))
            self.set_state(_FLOW_IDLE)
            self.status_message.emit('Compilation timeout')
        elif reason == 'killed':
            elapsed = time.time() - self.proc_mgr.start_time
            self.output_clear.emit(tab)
            self.output_append.emit(tab, QColor(128, 128, 128),
                'Compilation stopped in {:.3}s\n'.format(elapsed))
            self.set_state(_FLOW_IDLE)
            self.status_message.emit('Compilation stopped')
        elif exit_code != 0:
            self.output_clear.emit(tab)
            self.output_append.emit(tab, QColor(Qt.red), stderr_text)
            n = self.count_compile_errors(stderr_text)
            self.set_state(_FLOW_IDLE)
            self.status_message.emit(
                'Build failed with {} error(s)'.format(n))
        else:
            # Compile succeeded -- check intent
            if self.intent == 'build':
                elapsed = time.time() - self.proc_mgr.start_time
                self.output_clear.emit(tab)
                self.output_append.emit(tab, QColor(128, 128, 128),
                    'Build OK in {:.3}s\n'.format(elapsed))
                self.set_state(_FLOW_IDLE)
                self.status_message.emit('Build successful')
            elif self.intent == 'test':
                self.set_state(_FLOW_RUNNING)
                self.start_test_run(tab)
            elif self.intent == 'run':
                elapsed = time.time() - self.proc_mgr.start_time
                self.output_clear.emit(tab)
                self.output_append.emit(tab, QColor(128, 128, 128),
                    'Build OK in {:.3}s\n'.format(elapsed))
                self.set_state(_FLOW_IDLE)
                self.terminal_requested.emit(tab)
            else:
                # Unknown intent -- reset to idle as a safeguard
                self.set_state(_FLOW_IDLE)
                self.status_message.emit('Ready')

    def on_run_finished (self, exit_code, elapsed, peak_memory,
                         reason, error_detail):
        if self.state != _FLOW_RUNNING:
            return
        tab = self.tab
        if not tab:
            self.set_state(_FLOW_IDLE)
            return
        if reason == 'failed_to_start':
            self.output_clear.emit(tab)
            self.output_append.emit(tab, QColor(Qt.red), 'Failed to start program\n')
            self.output_append.emit(tab, QColor(Qt.red), 'Error: {}\n'.format(error_detail))
            self.set_state(_FLOW_IDLE)
            self.status_message.emit('Failed to start program')
        elif reason == 'timeout':
            self.output_append.emit(tab, QColor(Qt.red), '\n')
            self.output_append.emit(tab, QColor(Qt.red),
                'Timeout after {} seconds (ran {:.3}s)\n'.format(
                    self.settings.run_timeout, elapsed))
            self.set_state(_FLOW_IDLE)
            self.status_message.emit(
                'Timeout after {} seconds'.format(
                    self.settings.run_timeout))
        elif reason == 'killed':
            detail = _describe_exit_code(exit_code)
            if detail:
                self.output_append.emit(tab, QColor(Qt.red), '\n')
                self.output_append.emit(tab, QColor(Qt.red),
                    'Program crashed: {} (exit code {})\n'.format(
                        detail, exit_code))
            else:
                self.output_append.emit(tab, QColor(128, 128, 128), '\n')
                self.output_append.emit(tab, QColor(128, 128, 128),
                    'Process stopped in {:.3}s\n'.format(elapsed))
            self.set_state(_FLOW_IDLE)
            if detail:
                self.status_message.emit(
                    'Program crashed: {}'.format(detail))
            else:
                self.status_message.emit('Process stopped')
        elif exit_code != 0:
            detail = _describe_exit_code(exit_code)
            self.output_append.emit(tab, QColor(Qt.red), '\n')
            line = 'Runtime Error (exit code {})\n'.format(exit_code)
            if detail:
                line = 'Runtime Error: {} (exit code {})\n'.format(
                    detail, exit_code)
            self.output_append.emit(tab, QColor(Qt.red), line)
            self.set_state(_FLOW_IDLE)
            msg = 'Runtime Error (exit code {})'.format(exit_code)
            if detail:
                msg = 'Runtime Error: {}'.format(detail)
            self.status_message.emit(msg)
        else:
            mem_str = ''
            if peak_memory > 0:
                mem_mb = peak_memory / (1024 * 1024)
                mem_str = ', {:.1f}MB'.format(mem_mb)
            self.output_append.emit(tab, QColor(128, 128, 128), '\n')
            line = 'exit with code {} in {:.3}s{}\n'.format(
                exit_code, elapsed, mem_str)
            self.output_append.emit(tab, QColor(128, 128, 128), line)
            self.set_state(_FLOW_IDLE)
            self.status_message.emit(
                'Program exited with code 0 in {:.3}s{}'.format(
                    elapsed, mem_str))


#----------------------------------------------------------------------
# FileDragMixin -- forward file drag-drop events to MainWindow
#----------------------------------------------------------------------
class FileDragMixin:
    """Mixin that ignores URL drag-drop (letting MainWindow handle it)
    while passing text drag-drop to the QTextEdit default behavior."""

    def dragEnterEvent (self, event):
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent (self, event):
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dragMoveEvent(event)

    def dropEvent (self, event):
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dropEvent(event)


class _IOPanelBase (FileDragMixin, QTextEdit):
    """Base class for InputPanel and OutputPanel -- shared setDocument."""

    def setDocument (self, doc):
        doc.setDefaultFont(self.font())
        super().setDocument(doc)


#----------------------------------------------------------------------
# _ClickableLabel -- status bar label that pops encoding menu on click
#----------------------------------------------------------------------
class _ClickableLabel (QLabel):
    """Clickable label in status bar for encoding selection menu."""

    def __init__ (self, text:str='', parent=None):
        super().__init__(text, parent)
        self._main_window = None
        self.setCursor(Qt.PointingHandCursor)

    def setMainWindow (self, mw):
        self._main_window = mw

    def mousePressEvent (self, event):
        if event.button() == Qt.LeftButton and self._main_window:
            self._main_window._show_encoding_menu(self)
        super().mousePressEvent(event)


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
class CodeEditor (FileDragMixin, QTextEdit):

    _LINE_NUM_COLOR = QColor(120, 120, 120)
    _LINE_NUM_BG = QColor(235, 235, 235)

    _BRACKET_OPEN = {'(': ')', '{': '}', '[': ']', '"': '"', "'": "'"}
    _BRACKET_CLOSE = {')': '(', '}': '{', ']': '['}
    _CURRENT_LINE_COLOR = QColor(245, 245, 220)
    _BRACKET_MATCH_COLOR = QColor(180, 220, 255)

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
        self._highlighter = None
        self.document().blockCountChanged.connect(
            self._update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(
            self.line_number_area.update)
        self._update_line_number_area_width()
        self.cursorPositionChanged.connect(self._update_extra_selections)

    def _update_tab_width (self):
        # Tab width = indent_size characters. IMPORTANT: tab width (pixels)
        # depends on the current font's char width. Whenever font/size changes
        # (SettingsDialog, zoom), must call updateFontMetrics() to
        # recalculate tab width and sync document.setDefaultFont().
        # Otherwise tab pixel value won't match new font, causing wrong
        # visual width (e.g. 4-char tab appearing as 5 chars).
        self.setTabStopWidth(
            self.fontMetrics().horizontalAdvance('x') * self.indent_size)

    def _line_number_width (self) -> int:
        digits = 1
        count = max(1, self.document().blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def _update_line_number_area_width (self):
        # Use isHidden() instead of isVisible() -- isVisible() returns False
        # when parent window hasn't been shown yet (during __init__),
        # causing viewport margins to stay 0 after session restore.
        shown = not self.line_number_area.isHidden()
        width = self._line_number_width() if shown else 0
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
        # Sync highlighter reference from document attribute
        self._highlighter = getattr(doc, '_highlighter', None)

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

        # Tab -- indent selection or insert tab/spaces
        if key == Qt.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._handle_indent_selection()
            else:
                if self.indent_style == 'tab':
                    cursor.insertText('\t')
                else:
                    cursor.insertText(' ' * self.indent_size)
            return

        # Shift+Tab -- unindent selection or current line
        if key == Qt.Key_Backtab:
            self._handle_unindent_selection()
            return

        # Enter key -- auto indent
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._handle_enter_key()
            return

        # Backspace -- smart space deletion and bracket deletion
        if key == Qt.Key_Backspace:
            if self._handle_backspace():
                return
            super().keyPressEvent(event)
            return

        # Bracket completion (extended: #include < and /* */)
        if text and self._bracket_completion_enabled:
            if text == '<':
                if self._handle_include_angle():
                    return
            if text == '*':
                if self._handle_star_for_comment_open():
                    return
            if text == '/':
                if self._handle_slash_for_comment():
                    return
            if text in self._BRACKET_OPEN:
                if self._handle_bracket_open(text):
                    return
                # In comment/string context, fall through to default input
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

    def _handle_comment_uncomment (self):
        """Toggle // comment on current line or selected lines."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            # If selection ends at start of a block, don't include that block
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block

        # Check if ALL non-blank lines are already commented
        all_commented = True
        has_non_blank = False
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            text = block.text()
            stripped = text.lstrip()
            if not stripped:
                # Skip blank lines in the "all commented" check
                pass
            elif stripped.startswith('//'):
                has_non_blank = True
            else:
                has_non_blank = True
                all_commented = False
                break
            block = block.next()
        # If no non-blank lines exist, do nothing
        if not has_non_blank:
            return

        cursor.beginEditBlock()
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            text = block.text()
            stripped = text.lstrip()
            # Skip blank lines -- comment/uncomment should not touch them
            if not stripped:
                block = block.next()
                continue
            cursor_pos = block.position()
            if all_commented:
                # Remove // and all spaces immediately after it
                stripped_len = len(text) - len(text.lstrip())
                comment_start = stripped_len
                if text[comment_start:comment_start + 2] == '//':
                    remove_end = comment_start + 2
                    while remove_end < len(text) and text[remove_end] == ' ':
                        remove_end += 1
                    c = QTextCursor(doc)
                    c.setPosition(cursor_pos + comment_start)
                    c.setPosition(cursor_pos + remove_end,
                                  QTextCursor.KeepAnchor)
                    c.removeSelectedText()
            else:
                # Add "// " before first non-whitespace
                stripped_len = len(text) - len(text.lstrip())
                c = QTextCursor(doc)
                c.setPosition(cursor_pos + stripped_len)
                c.insertText('// ')
            block = block.next()
        cursor.endEditBlock()

    def _handle_indent_selection (self):
        """Indent current line or all selected lines by one level."""
        doc = self.document()
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        if has_selection:
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        indent_char = '\t' if self.indent_style == 'tab' else \
            ' ' * self.indent_size
        start_num = start_block.blockNumber()
        end_num = end_block.blockNumber()
        if not has_selection:
            cursor_col = cursor.position() - cursor.block().position()
        cursor.beginEditBlock()
        for i in range(start_num, end_num + 1):
            block = doc.findBlockByNumber(i)
            c = QTextCursor(doc)
            c.setPosition(block.position())
            c.insertText(indent_char)
        cursor.endEditBlock()
        if has_selection:
            # Linewise: anchor at block start, position at end of block
            # range, so repeated indent/unindent never drifts
            new_start = doc.findBlockByNumber(start_num).position()
            new_end_block = doc.findBlockByNumber(end_num)
            new_end = new_end_block.position() + new_end_block.length()
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_start)
            new_cursor.setPosition(new_end, QTextCursor.KeepAnchor)
            self.setTextCursor(new_cursor)
        else:
            new_block = doc.findBlockByNumber(start_num)
            new_pos = new_block.position() + cursor_col + len(indent_char)
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_pos)
            self.setTextCursor(new_cursor)

    def _handle_unindent_selection (self):
        """Unindent current line or all selected lines by one level."""
        doc = self.document()
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        if has_selection:
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        start_num = start_block.blockNumber()
        end_num = end_block.blockNumber()
        if not has_selection:
            cursor_col = cursor.position() - cursor.block().position()
        removed_per_line = []
        for i in range(start_num, end_num + 1):
            block = doc.findBlockByNumber(i)
            text = block.text()
            remove_len = 0
            if text.startswith('\t'):
                remove_len = 1
            elif text.startswith(' ' * self.indent_size):
                remove_len = self.indent_size
            elif text.startswith(' '):
                count = 0
                for ch in text:
                    if ch == ' ' and count < self.indent_size:
                        count += 1
                    else:
                        break
                remove_len = count
            removed_per_line.append(remove_len)
        cursor.beginEditBlock()
        for i in range(start_num, end_num + 1):
            block = doc.findBlockByNumber(i)
            remove_len = removed_per_line[i - start_num]
            if remove_len > 0:
                c = QTextCursor(doc)
                c.setPosition(block.position())
                c.setPosition(
                    block.position() + remove_len,
                    QTextCursor.KeepAnchor)
                c.removeSelectedText()
        cursor.endEditBlock()
        if has_selection:
            # Linewise: anchor at block start, position at end of block
            # range, so repeated indent/unindent never drifts
            new_start = doc.findBlockByNumber(start_num).position()
            new_end_block = doc.findBlockByNumber(end_num)
            new_end = new_end_block.position() + new_end_block.length()
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_start)
            new_cursor.setPosition(new_end, QTextCursor.KeepAnchor)
            self.setTextCursor(new_cursor)
        else:
            removed = removed_per_line[0]
            new_block = doc.findBlockByNumber(start_num)
            new_col = max(0, cursor_col - removed)
            new_pos = new_block.position() + new_col
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_pos)
            self.setTextCursor(new_cursor)

    def _handle_duplicate_line (self):
        """Duplicate current line or selected lines below."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            text = cursor.selectedText()
            # QTextCursor.selectedText uses as paragraph separator
            text = text.replace('\u2029', '\n')
            end_pos = cursor.selectionEnd()
            c = QTextCursor(doc)
            c.setPosition(end_pos)
            c.insertText('\n' + text)
        else:
            block = cursor.block()
            text = block.text()
            # block.length includes the trailing newline char
            c = QTextCursor(doc)
            c.setPosition(block.position() + block.length() - 1)
            c.insertText('\n' + text)

    def _handle_delete_line (self):
        """Delete current line or selected lines."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            # Include end block even if selection ends at block start
            last_pos = end_block.position() + end_block.length()
            c = QTextCursor(doc)
            c.setPosition(start_block.position())
            c.setPosition(last_pos, QTextCursor.KeepAnchor)
            c.removeSelectedText()
        else:
            block = cursor.block()
            c = QTextCursor(doc)
            c.setPosition(block.position())
            next_block = block.next()
            if next_block.isValid():
                c.setPosition(
                    next_block.position(), QTextCursor.KeepAnchor)
            else:
                # Last line -- delete to end of document
                c.setPosition(
                    block.position() + block.length(),
                    QTextCursor.KeepAnchor)
            c.removeSelectedText()

    def _handle_move_line_up (self):
        """Move current line or selected lines up."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        prev_block = start_block.previous()
        if not prev_block.isValid():
            return
        # Swap prev_block with the range [start_block..end_block]
        cursor.beginEditBlock()
        # Collect text of blocks to move
        move_lines = []
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            move_lines.append(block.text())
            block = block.next()
        swap_line = prev_block.text()
        # Delete the moved range
        c = QTextCursor(doc)
        c.setPosition(start_block.position())
        last_block = end_block
        next_after = last_block.next()
        if next_after.isValid():
            c.setPosition(next_after.position(), QTextCursor.KeepAnchor)
        else:
            c.setPosition(
                last_block.position() + last_block.length(),
                QTextCursor.KeepAnchor)
        c.removeSelectedText()
        # Delete the swap line
        c2 = QTextCursor(doc)
        c2.setPosition(prev_block.position())
        next_prev = prev_block.next()
        if next_prev.isValid():
            c2.setPosition(next_prev.position(), QTextCursor.KeepAnchor)
        else:
            c2.setPosition(
                prev_block.position() + prev_block.length(),
                QTextCursor.KeepAnchor)
        c2.removeSelectedText()
        # Insert move_lines then swap_line at original prev position
        c3 = QTextCursor(doc)
        c3.setPosition(prev_block.position())
        c3.insertText('\n'.join(move_lines) + '\n' + swap_line)
        cursor.endEditBlock()
        # Restore cursor/selection in moved range
        new_start_pos = prev_block.position()
        new_end_pos = new_start_pos + len('\n'.join(move_lines))
        restore = QTextCursor(doc)
        restore.setPosition(new_start_pos)
        restore.setPosition(new_end_pos, QTextCursor.KeepAnchor)
        self.setTextCursor(restore)

    def _handle_move_line_down (self):
        """Move current line or selected lines down."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        next_block = end_block.next()
        if not next_block.isValid():
            return
        # Swap the range [start_block..end_block] with next_block
        cursor.beginEditBlock()
        move_lines = []
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            move_lines.append(block.text())
            block = block.next()
        swap_line = next_block.text()
        # Delete the moved range
        c = QTextCursor(doc)
        c.setPosition(start_block.position())
        next_after_range = end_block.next().next()
        if next_after_range.isValid():
            c.setPosition(
                next_after_range.position(), QTextCursor.KeepAnchor)
        else:
            # The next_block is last, so delete to end of next_block
            c.setPosition(
                next_block.position() + next_block.length(),
                QTextCursor.KeepAnchor)
        c.removeSelectedText()
        # Insert swap_line then move_lines at original start position
        c2 = QTextCursor(doc)
        c2.setPosition(start_block.position())
        c2.insertText(swap_line + '\n' + '\n'.join(move_lines))
        cursor.endEditBlock()
        # Restore cursor/selection in moved range (now shifted down)
        new_start_pos = start_block.position() + len(swap_line) + 1
        new_end_pos = new_start_pos + len('\n'.join(move_lines))
        restore = QTextCursor(doc)
        restore.setPosition(new_start_pos)
        restore.setPosition(new_end_pos, QTextCursor.KeepAnchor)
        self.setTextCursor(restore)

    def _handle_include_angle (self) -> bool:
        """Auto-complete #include < with >. Only if line starts with #include."""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text().lstrip()
        if text.startswith('#include'):
            cursor.beginEditBlock()
            cursor.insertText('<>')
            cursor.movePosition(QTextCursor.Left)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True
        return False

    def _handle_slash_for_comment (self) -> bool:
        """Skip over */ when typing / and right side has / from auto-close.
        After /* auto-completes */, the closing */ is to the right.
        When user types * then / (closing */), the / on the right is
        the auto-completed one -- skip over it."""
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        # */ skip: we just typed /, left char is *, right char is /
        if pos < doc.characterCount() and doc.characterAt(pos) == '/':
            if pos > 0 and doc.characterAt(pos - 1) == '*':
                cursor.movePosition(QTextCursor.Right)
                self.setTextCursor(cursor)
                return True
        return False

    def _handle_star_for_comment_open (self) -> bool:
        """Auto-complete /* with */. When user types * and left char is /.
        Only triggers if not inside an already-auto-completed /* */ pair."""
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        # Left char must be /
        if pos < 1 or doc.characterAt(pos - 1) != '/':
            return False
        # Don't trigger if right side is already ' */' (we're closing)
        remaining = doc.characterCount() - pos
        if remaining >= 3:
            right3 = ''
            for i in range(3):
                right3 += doc.characterAt(pos + i)
            if right3 == ' */':
                return False
        cursor.beginEditBlock()
        cursor.insertText('* */')
        # Move cursor between /* and */
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 3)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def contextMenuEvent (self, event):
        """Custom right-click context menu for CodeEditor."""
        menu = QMenu(self)
        win = self.window()
        if hasattr(win, 'act_undo'):
            menu.addAction(win.act_undo)
            menu.addAction(win.act_redo)
            menu.addSeparator()
            menu.addAction(win.act_cut)
            menu.addAction(win.act_copy)
            menu.addAction(win.act_paste)
            menu.addSeparator()
            menu.addAction(win.act_comment)
            menu.addAction(win.act_indent)
            menu.addAction(win.act_unindent)
            menu.addAction(win.act_duplicate)
            menu.addAction(win.act_delete_line)
        menu.exec_(event.globalPos())

    def set_bracket_completion (self, enabled:bool):
        self._bracket_completion_enabled = enabled

    def _handle_bracket_open (self, text:str) -> bool:
        """Handle bracket/quote auto-completion. Returns True if handled,
        False if in comment/string context (should use default input)."""
        cursor = self.textCursor()
        pos = cursor.position()
        # For quotes: if cursor is right before a matching quote, skip over
        # This must precede the comment/string check -- skipping over an
        # existing closing quote is a cursor action, not auto-completion.
        if text in ('"', "'"):
            doc = self.document()
            if pos < doc.characterCount():
                char_after = doc.characterAt(pos)
                if char_after == text:
                    cursor.movePosition(QTextCursor.Right)
                    self.setTextCursor(cursor)
                    return True
        # Skip auto-completion inside comments or string literals
        if self._is_bracket_in_comment_or_string(pos):
            return False
        # Insert open + close, place cursor between
        close = self._BRACKET_OPEN[text]
        cursor.beginEditBlock()
        cursor.insertText(text + close)
        cursor.movePosition(QTextCursor.Left)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _handle_bracket_close (self, text:str) -> bool:
        """Skip over auto-completed close bracket/quote. Returns True if
        skipped, False if not handled. Context-aware: does not skip inside
        comments or string literals."""
        pos = self.textCursor().position()
        if self._is_bracket_in_comment_or_string(pos):
            return False
        cursor = self.textCursor()
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
                # All spaces to the left, at indent boundary --
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
            if 0 < pos < doc.characterCount():
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

    def _update_extra_selections (self):
        """Update current line highlight and bracket match highlight."""
        if not self.isEnabled():
            self.setExtraSelections([])
            return
        selections = []
        # Current line highlight
        cursor = self.textCursor()
        line_sel = QTextEdit.ExtraSelection()
        line_sel.format.setBackground(QBrush(self._CURRENT_LINE_COLOR))
        line_sel.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        line_sel.cursor = cursor
        line_sel.cursor.movePosition(QTextCursor.StartOfLine)
        selections.append(line_sel)
        # Bracket match highlight
        match_sel = self._find_bracket_match_selections()
        if match_sel:
            selections.extend(match_sel)
        self.setExtraSelections(selections)

    def _find_bracket_match_selections (self):
        """Find matching bracket and return ExtraSelections for both."""
        cursor = self.textCursor()
        doc = self.document()
        pos = cursor.position()
        # Check char at cursor and char before cursor
        chars_to_check = []
        if pos < doc.characterCount():
            chars_to_check.append((pos, doc.characterAt(pos)))
        if pos > 0:
            chars_to_check.append((pos - 1, doc.characterAt(pos - 1)))
        brackets = '(){}[]'
        for check_pos, ch in chars_to_check:
            if ch not in brackets:
                continue
            match_pos = self._find_matching_bracket(check_pos, ch)
            if match_pos < 0:
                continue
            if self._is_bracket_in_comment_or_string(check_pos):
                continue
            selections = []
            for bp in (check_pos, match_pos):
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(QBrush(self._BRACKET_MATCH_COLOR))
                c = QTextCursor(doc)
                c.setPosition(bp)
                c.setPosition(bp + 1, QTextCursor.KeepAnchor)
                sel.cursor = c
                selections.append(sel)
            return selections
        return None

    def _find_matching_bracket (self, pos:int, ch:str) -> int:
        """Find matching bracket position. Returns -1 if not found."""
        doc = self.document()
        if ch in self._BRACKET_OPEN:
            # Search forward
            target = self._BRACKET_OPEN[ch]
            depth = 1
            p = pos + 1
            while p < doc.characterCount():
                c = doc.characterAt(p)
                if c == ch:
                    depth += 1
                elif c == target:
                    depth -= 1
                    if depth == 0:
                        return p
                p += 1
        elif ch in self._BRACKET_CLOSE:
            # Search backward
            target = self._BRACKET_CLOSE[ch]
            depth = 1
            p = pos - 1
            while p >= 0:
                c = doc.characterAt(p)
                if c == ch:
                    depth += 1
                elif c == target:
                    depth -= 1
                    if depth == 0:
                        return p
                p -= 1
        return -1

    def _is_bracket_in_comment_or_string (self, pos:int) -> bool:
        """Check if position is inside a comment or string literal.
        Uses self._highlighter (synced via setDocument) instead of
        traversing the window hierarchy."""
        block = self.document().findBlock(pos)
        if not block.isValid():
            return False
        block_pos = block.position()
        text = block.text()
        local_pos = pos - block_pos
        if local_pos < 0 or local_pos >= len(text):
            return False
        # Check highlighter format at this position
        highlighter = self._highlighter
        if highlighter and not highlighter._deferred:
            fmt = highlighter.format(local_pos)
            fg = fmt.foreground()
            if fg.style() and fg.color() != QColor():
                # Colored by highlighter = inside comment/string/char
                return True
        # In deferred mode or no highlighter: check block state for
        # multi-line comment and do a quick text-based check
        if block.previous().userState() == 1 or block.userState() == 1:
            return True
        # Quick regex check for strings and comments around local_pos
        # Check if local_pos is inside a quoted string
        in_string = False
        i = 0
        while i < local_pos:
            if text[i] == '"':
                in_string = not in_string
                # Skip escaped chars
                while in_string and i + 1 < len(text) and text[i + 1] == '\\':
                    i += 2
            elif text[i] == "'" and not in_string:
                # Character literal: skip until closing '
                end = text.find("'", i + 1)
                if end >= 0 and end < local_pos:
                    i = end + 1
                else:
                    return True
            i += 1
        if in_string:
            return True
        # Check single-line comment
        comment_pos = text.find('//')
        if comment_pos >= 0 and comment_pos <= local_pos:
            # Make sure it's not inside a string
            in_str = False
            for j in range(comment_pos):
                if text[j] == '"':
                    in_str = not in_str
            if not in_str:
                return True
        return False

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
class InputPanel (_IOPanelBase):

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)

    def keyPressEvent (self, event):
        if event.key() == Qt.Key_Tab:
            cursor = self.textCursor()
            cursor.insertText('\t')
        elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
            super().keyPressEvent(event)
            # Flush current tab's output buffer on Enter for interactive prompt visibility
            win = self.window()
            if hasattr(win, 'tab_manager'):
                tab = win.tab_manager.get_current()
                if tab and tab.output_buffer:
                    win._immediate_flush(tab)
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


def _strip_trailing_whitespace_in_doc (doc:QTextDocument) -> None:
    """Strip trailing whitespace from each line in a QTextDocument.
    Uses cursor operations so the change is recorded as a single undo step.
    After calling this, doc.toPlainText() and the on-disk content are consistent."""
    cursor = QTextCursor(doc)
    cursor.beginEditBlock()
    block = doc.begin()
    while block.isValid():
        text = block.text()
        stripped = text.rstrip()
        if stripped != text:
            # Select trailing whitespace and delete it
            block_pos = block.position()
            start = block_pos + len(stripped)
            end = block_pos + len(text)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        block = block.next()
    cursor.endEditBlock()


def _strip_trailing_whitespace (text:str) -> str:
    """Remove trailing spaces/tabs from each line."""
    return '\n'.join(line.rstrip() for line in text.split('\n'))


#----------------------------------------------------------------------
# OutputPanel
#----------------------------------------------------------------------
class OutputPanel (_IOPanelBase):

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

    def keyPressEvent (self, event):
        if (event.matches(QKeySequence.Copy)
                or (event.key() == Qt.Key_Insert
                    and event.modifiers() == Qt.ControlModifier)):
            self.copy()
            return
        # END key: re-enter auto-scroll mode, flush buffer, scroll to bottom
        if event.key() == Qt.Key_End:
            super().keyPressEvent(event)
            win = self.window()
            if hasattr(win, 'tab_manager'):
                tab = win.tab_manager.get_current()
                if tab:
                    tab.pinned_to_bottom = True
                    win._immediate_flush(tab)
            return
        super().keyPressEvent(event)


#----------------------------------------------------------------------
# Auto-detect compiler
#----------------------------------------------------------------------
_COMPILER_SEARCH_PATHS = [
    'C:\\MinGW\\bin\\g++.exe',
    'C:\\MinGW\\bin\\gcc.exe',
    'C:\\TDM-GCC-64\\bin\\g++.exe',
    'C:\\TDM-GCC-64\\bin\\gcc.exe',
    'C:\\Program Files\\Dev-Cpp\\MinGW64\\bin\\g++.exe',
    'C:\\Program Files\\Dev-Cpp\\MinGW64\\bin\\gcc.exe',
    'C:\\Program Files (x86)\\Dev-Cpp\\MinGW64\\bin\\g++.exe',
    'C:\\Program Files (x86)\\Dev-Cpp\\MinGW64\\bin\\gcc.exe',
    'C:\\msys64\\mingw64\\bin\\g++.exe',
    'C:\\msys64\\mingw64\\bin\\gcc.exe',
]


def _auto_detect_compiler () -> str:
    """Search common MinGW paths and PATH for g++/gcc. Returns path or ''."""
    if sys.platform == 'win32':
        for path in _COMPILER_SEARCH_PATHS:
            if os.path.exists(path):
                return path
    # Check PATH -- prefer g++, fallback to gcc
    ext = '.exe' if sys.platform == 'win32' else ''
    for dir_name in os.environ.get('PATH', '').split(os.pathsep):
        for name in ('g++', 'gcc'):
            candidate = os.path.join(dir_name, name + ext)
            if os.path.exists(candidate):
                return candidate
    return ''


#----------------------------------------------------------------------
# SettingsDialog
#----------------------------------------------------------------------
class SettingsDialog (QDialog):

    def __init__ (self, settings:Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setMinimumWidth(500)
        self._original = settings
        self._copy = settings.copy()
        self.__build_ui()
        self.__load_from_copy()

    def __build_ui (self):
        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Compiler page
        self.__build_compiler_page()
        # Editor page
        self.__build_editor_page()
        # Template page
        self.__build_template_page()

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton('OK')
        self.btn_cancel = QPushButton('Cancel')
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self.__on_ok)
        self.btn_cancel.clicked.connect(self.reject)
        # Live update template tab width when indent_size changes
        self.spin_indent_size.valueChanged.connect(
            self._update_template_tab_width)

    def __build_compiler_page (self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # Compiler path
        row = QHBoxLayout()
        row.addWidget(QLabel('Compiler Path:'))
        self.edit_compiler_path = QLineEdit()
        row.addWidget(self.edit_compiler_path)
        self.btn_browse_compiler = QPushButton('Browse...')
        self.btn_browse_compiler.clicked.connect(self.__on_browse_compiler)
        row.addWidget(self.btn_browse_compiler)
        self.btn_auto_detect = QPushButton('Auto Detect')
        self.btn_auto_detect.clicked.connect(self.__on_auto_detect)
        row.addWidget(self.btn_auto_detect)
        layout.addLayout(row)

        # Compiler flags
        row = QHBoxLayout()
        row.addWidget(QLabel('Compiler Flags:'))
        self.edit_compiler_flags = QLineEdit()
        row.addWidget(self.edit_compiler_flags)
        layout.addLayout(row)

        # Environment variables table
        layout.addWidget(QLabel('Environment Variables:'))
        self.env_table = QTableWidget(0, 2)
        self.env_table.setHorizontalHeaderLabels(['Key', 'Value'])
        header = self.env_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.env_table.setMinimumHeight(120)
        layout.addWidget(self.env_table)

        # Add row button for env vars
        row = QHBoxLayout()
        self.btn_add_env = QPushButton('Add Row')
        self.btn_add_env.clicked.connect(self.__on_add_env_row)
        row.addWidget(self.btn_add_env)
        row.addStretch()
        layout.addLayout(row)

        # Run timeout
        row = QHBoxLayout()
        row.addWidget(QLabel('Run Timeout (seconds):'))
        self.spin_run_timeout = QSpinBox()
        self.spin_run_timeout.setRange(1, 300)
        row.addWidget(self.spin_run_timeout)
        layout.addLayout(row)

        # Compile timeout
        row = QHBoxLayout()
        row.addWidget(QLabel('Compile Timeout (seconds):'))
        self.spin_compile_timeout = QSpinBox()
        self.spin_compile_timeout.setRange(1, 300)
        row.addWidget(self.spin_compile_timeout)
        layout.addLayout(row)

        layout.addStretch()
        self.tab_widget.addTab(page, 'Compiler')

    def __build_editor_page (self):
        page = QWidget()
        layout = QVBoxLayout(page)

        # Editor font
        row = QHBoxLayout()
        row.addWidget(QLabel('Editor Font:'))
        self.combo_editor_font = QFontComboBox()
        self.combo_editor_font.setFontFilters(
            QFontComboBox.MonospacedFonts)
        row.addWidget(self.combo_editor_font)
        layout.addLayout(row)

        # Editor font size
        row = QHBoxLayout()
        row.addWidget(QLabel('Editor Font Size:'))
        self.spin_editor_size = QSpinBox()
        self.spin_editor_size.setRange(6, 72)
        row.addWidget(self.spin_editor_size)
        layout.addLayout(row)

        # IO font
        row = QHBoxLayout()
        row.addWidget(QLabel('IO Panel Font:'))
        self.combo_io_font = QFontComboBox()
        self.combo_io_font.setFontFilters(
            QFontComboBox.MonospacedFonts)
        row.addWidget(self.combo_io_font)
        layout.addLayout(row)

        # IO font size
        row = QHBoxLayout()
        row.addWidget(QLabel('IO Panel Font Size:'))
        self.spin_io_size = QSpinBox()
        self.spin_io_size.setRange(6, 72)
        row.addWidget(self.spin_io_size)
        layout.addLayout(row)

        # Bracket completion
        self.chk_bracket = QCheckBox('Bracket Completion')
        layout.addWidget(self.chk_bracket)

        # Indent style
        row = QHBoxLayout()
        row.addWidget(QLabel('Indent Style:'))
        self.combo_indent_style = QComboBox()
        self.combo_indent_style.addItem('Tab')
        self.combo_indent_style.addItem('Space')
        row.addWidget(self.combo_indent_style)
        layout.addLayout(row)

        # Indent size (tab width / spaces per indent level)
        row = QHBoxLayout()
        row.addWidget(QLabel('Tab Width:'))
        self.spin_indent_size = QSpinBox()
        self.spin_indent_size.setRange(2, 16)
        row.addWidget(self.spin_indent_size)
        layout.addLayout(row)

        # Word wrap
        self.chk_word_wrap = QCheckBox('Word Wrap')
        layout.addWidget(self.chk_word_wrap)

        layout.addStretch()
        self.tab_widget.addTab(page, 'Editor')

    def __build_template_page (self):
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel('New File Template:'))
        self.edit_template = QPlainTextEditWidget()
        self.edit_template.setTabStopWidth(
            self.edit_template.fontMetrics().horizontalAdvance('x') * 4)
        self.edit_template.installEventFilter(self)
        layout.addWidget(self.edit_template)

        row = QHBoxLayout()
        self.btn_reset_template = QPushButton('Reset to Default')
        self.btn_reset_template.clicked.connect(self.__on_reset_template)
        row.addWidget(self.btn_reset_template)
        row.addStretch()
        layout.addLayout(row)

        self.tab_widget.addTab(page, 'Template')

    def __load_from_copy (self):
        """Load all widgets from the working copy of settings."""
        c = self._copy
        self.edit_compiler_path.setText(c.compiler_path)
        self.edit_compiler_flags.setText(c.compiler_flags)
        self.spin_run_timeout.setValue(c.run_timeout)
        self.spin_compile_timeout.setValue(c.compile_timeout)
        self.combo_editor_font.setCurrentFont(
            QFontDatabase().font(c.editor_font_family, '', 10))
        self.spin_editor_size.setValue(c.editor_font_size)
        self.combo_io_font.setCurrentFont(
            QFontDatabase().font(c.io_font_family, '', 10))
        self.spin_io_size.setValue(c.io_font_size)
        self.chk_bracket.setChecked(c.bracket_completion)
        if c.indent_style == 'tab':
            self.combo_indent_style.setCurrentIndex(0)
        else:
            self.combo_indent_style.setCurrentIndex(1)
        self.spin_indent_size.setValue(c.indent_size)
        self.chk_word_wrap.setChecked(c.word_wrap)
        # Update template editor tab width based on indent_size
        self._update_template_tab_width(c.indent_size)
        self.edit_template.setPlainText(c.template_text)

        # Populate env vars table
        self.env_table.setRowCount(0)
        for key, value in c.env_vars.items():
            self.__add_env_row(key, value)

    def __add_env_row (self, key:str='', value:str=''):
        row = self.env_table.rowCount()
        self.env_table.insertRow(row)
        item_key = QTableWidgetItem(key)
        item_val = QTableWidgetItem(value)
        item_val.setToolTip('Use $VAR_NAME to reference system env vars')
        self.env_table.setItem(row, 0, item_key)
        self.env_table.setItem(row, 1, item_val)

    def __on_add_env_row (self):
        self.__add_env_row()

    def __on_auto_detect (self):
        path = _auto_detect_compiler()
        if path:
            self.edit_compiler_path.setText(path)
        else:
            QMessageBox.information(
                self, 'Auto Detect',
                'No g++ compiler found in common paths or PATH.')

    def __on_browse_compiler (self):
        start_dir = ''
        current = self.edit_compiler_path.text().strip()
        if current and os.path.isabs(current):
            start_dir = os.path.dirname(current)
        elif current:
            base = os.path.dirname(os.path.abspath(__file__))
            resolved = os.path.abspath(os.path.join(base, current))
            if os.path.exists(os.path.dirname(resolved)):
                start_dir = os.path.dirname(resolved)
        if not start_dir:
            start_dir = os.environ.get('PROGRAMFILES', 'C:\\')
        filter_str = 'Executables (*.exe);;All Files (*)'
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Compiler', start_dir, filter_str)
        if path:
            self.edit_compiler_path.setText(path)

    def _update_template_tab_width (self, size=None):
        """Update template editor tab width to match indent_size."""
        if size is None:
            size = self.spin_indent_size.value()
        self.edit_template.setTabStopWidth(
            self.edit_template.fontMetrics().horizontalAdvance('x') * size)

    def eventFilter (self, obj, event):
        """Event filter for template editor: auto indent on Enter,
        Tab key respects indent_style setting."""
        if obj is self.edit_template and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                cursor = self.edit_template.textCursor()
                # Get current line's leading whitespace
                line = cursor.block().text()
                leading = ''
                for ch in line:
                    if ch in (' ', '\t'):
                        leading += ch
                    else:
                        break
                # Add extra indent if line ends with '{'
                stripped = line.rstrip()
                if stripped.endswith('{'):
                    if self.combo_indent_style.currentIndex() == 0:
                        leading += '\t'
                    else:
                        leading += ' ' * self.spin_indent_size.value()
                # Insert newline + leading whitespace
                cursor.insertText('\n' + leading)
                return True
            if event.key() == Qt.Key_Tab:
                if self.combo_indent_style.currentIndex() == 1:
                    # Space mode: insert indent_size spaces instead of \t
                    cursor = self.edit_template.textCursor()
                    cursor.insertText(' ' * self.spin_indent_size.value())
                    return True
        return super().eventFilter(obj, event)

    def __on_reset_template (self):
        self.edit_template.setPlainText(_SETTINGS_DEFAULTS['template_text'])

    def __collect_env_vars (self) -> dict:
        """Collect env vars from table into dict."""
        result = {}
        for row in range(self.env_table.rowCount()):
            item_key = self.env_table.item(row, 0)
            item_val = self.env_table.item(row, 1)
            if item_key and item_val:
                key = item_key.text().strip()
                val = item_val.text()
                if key:
                    result[key] = val
        return result

    def __on_ok (self):
        """Apply settings changes and save to JSON."""
        c = self._copy
        c.compiler_path = self.edit_compiler_path.text().strip()
        c.compiler_flags = self.edit_compiler_flags.text().strip()
        c.env_vars = self.__collect_env_vars()
        c.run_timeout = self.spin_run_timeout.value()
        c.compile_timeout = self.spin_compile_timeout.value()
        c.editor_font_family = self.combo_editor_font.currentFont().family()
        c.editor_font_size = self.spin_editor_size.value()
        c.io_font_family = self.combo_io_font.currentFont().family()
        c.io_font_size = self.spin_io_size.value()
        c.bracket_completion = self.chk_bracket.isChecked()
        c.indent_style = 'tab' if self.combo_indent_style.currentIndex() == 0 else 'space'
        c.indent_size = self.spin_indent_size.value()
        c.word_wrap = self.chk_word_wrap.isChecked()
        c.template_text = self.edit_template.toPlainText()

        # Warn if compiler path looks invalid (absolute/relative path
        # that doesn't exist on disk). Bare names like 'gcc' are OK --
        # they're resolved from PATH at compile time.
        compiler = c.compiler_path
        if compiler and os.path.dirname(compiler):
            # Has a directory component -- resolve relative paths
            if not os.path.isabs(compiler):
                base = os.path.dirname(os.path.abspath(__file__))
                resolved = os.path.abspath(os.path.join(base, compiler))
            else:
                resolved = compiler
            if not os.path.exists(resolved):
                result = QMessageBox.warning(
                    self, 'Compiler Path',
                    "The compiler path '{}' does not exist on disk.\n\n"
                    "Compilation may fail. Save anyway?".format(compiler),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No)
                if result == QMessageBox.No:
                    return

        # Check if compiler-related settings changed -> update mtime
        old = self._original
        compiler_changed = (
            old.compiler_path != c.compiler_path
            or old.compiler_flags != c.compiler_flags
            or old.env_vars != c.env_vars)
        if compiler_changed:
            c.compiler_mtime = time.time()

        # Apply to original settings and save
        old.apply_from(c)
        result = old.save()
        if result < 0:
            QMessageBox.warning(
                self, 'Save Error',
                'Failed to save settings to disk.\n'
                'Changes will be lost on restart.')
            self.accept()
            return
        self.accept()


#----------------------------------------------------------------------
# FindDialog
#----------------------------------------------------------------------
class FindDialog (QDialog):
    """Non-modal find dialog. Close hides, preserving state."""

    def __init__ (self, editor:QTextEdit, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle('Find')
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.__build_ui()

    def __build_ui (self):
        layout = QVBoxLayout(self)

        # Find text
        row = QHBoxLayout()
        row.addWidget(QLabel('Find:'))
        self.edit_find = QLineEdit()
        row.addWidget(self.edit_find)
        layout.addLayout(row)

        # Options
        row = QHBoxLayout()
        self.chk_case = QCheckBox('Case Sensitive')
        row.addWidget(self.chk_case)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.radio_down = QRadioButton('Down')
        self.radio_up = QRadioButton('Up')
        self.radio_down.setChecked(True)
        row.addWidget(self.radio_down)
        row.addWidget(self.radio_up)
        layout.addLayout(row)

        # Buttons
        row = QHBoxLayout()
        self.btn_find_next = QPushButton('Find Next')
        self.btn_close = QPushButton('Close')
        row.addWidget(self.btn_find_next)
        row.addWidget(self.btn_close)
        layout.addLayout(row)

        self.btn_find_next.clicked.connect(self._on_find_next)
        self.btn_close.clicked.connect(self.hide)

    def _on_find_next (self):
        text = self.edit_find.text()
        if not text:
            return
        flags = QTextDocument.FindFlag(0)
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        if self.radio_up.isChecked():
            flags |= QTextDocument.FindBackward
        cursor = self.editor.textCursor()
        found = self.editor.document().find(text, cursor, flags)
        if found.hasSelection():
            self.editor.setTextCursor(found)
            self.setWindowTitle('Find')
        else:
            # Try from beginning/end
            doc = self.editor.document()
            if flags & QTextDocument.FindBackward:
                start = QTextCursor(doc)
                start.movePosition(QTextCursor.End)
            else:
                start = QTextCursor(doc)
                start.movePosition(QTextCursor.Start)
            found = doc.find(text, start, flags)
            if found.hasSelection():
                self.editor.setTextCursor(found)
                self.setWindowTitle('Find')
            else:
                self.setWindowTitle('Find - Not found')


#----------------------------------------------------------------------
# ReplaceDialog
#----------------------------------------------------------------------
class ReplaceDialog (QDialog):
    """Non-modal replace dialog. Close hides, preserving state."""

    def __init__ (self, editor:QTextEdit, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle('Replace')
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.__build_ui()

    def __build_ui (self):
        layout = QVBoxLayout(self)

        # Find text
        row = QHBoxLayout()
        row.addWidget(QLabel('Find:'))
        self.edit_find = QLineEdit()
        row.addWidget(self.edit_find)
        layout.addLayout(row)

        # Replace text
        row = QHBoxLayout()
        row.addWidget(QLabel('Replace:'))
        self.edit_replace = QLineEdit()
        row.addWidget(self.edit_replace)
        layout.addLayout(row)

        # Options
        self.chk_case = QCheckBox('Case Sensitive')
        layout.addWidget(self.chk_case)

        # Buttons
        row = QHBoxLayout()
        self.btn_find_next = QPushButton('Find Next')
        self.btn_replace = QPushButton('Replace')
        self.btn_replace_all = QPushButton('Replace All')
        self.btn_close = QPushButton('Close')
        row.addWidget(self.btn_find_next)
        row.addWidget(self.btn_replace)
        row.addWidget(self.btn_replace_all)
        row.addWidget(self.btn_close)
        layout.addLayout(row)

        self.btn_find_next.clicked.connect(self._on_find_next)
        self.btn_replace.clicked.connect(self._on_replace)
        self.btn_replace_all.clicked.connect(self._on_replace_all)
        self.btn_close.clicked.connect(self.hide)

    def _find_flags (self) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def _on_find_next (self):
        text = self.edit_find.text()
        if not text:
            return
        flags = self._find_flags()
        cursor = self.editor.textCursor()
        found = self.editor.document().find(text, cursor, flags)
        if found.hasSelection():
            self.editor.setTextCursor(found)
            self.setWindowTitle('Replace')
        else:
            start = QTextCursor(self.editor.document())
            start.movePosition(QTextCursor.Start)
            found = self.editor.document().find(text, start, flags)
            if found.hasSelection():
                self.editor.setTextCursor(found)
                self.setWindowTitle('Replace')
            else:
                self.setWindowTitle('Replace - Not found')

    def _on_replace (self):
        cursor = self.editor.textCursor()
        find_text = self.edit_find.text()
        replace_text = self.edit_replace.text()
        if not find_text:
            return
        # Check if current selection matches find text
        selected = cursor.selectedText()
        case_match = self.chk_case.isChecked()
        if selected == find_text or (not case_match
                                     and selected.lower() == find_text.lower()):
            cursor.beginEditBlock()
            cursor.removeSelectedText()
            cursor.insertText(replace_text)
            cursor.endEditBlock()
            self.editor.setTextCursor(cursor)
        # Find next occurrence
        self._on_find_next()

    def _on_replace_all (self):
        find_text = self.edit_find.text()
        replace_text = self.edit_replace.text()
        if not find_text:
            return
        flags = self._find_flags()
        doc = self.editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        count = 0
        while True:
            found = doc.find(find_text, cursor, flags)
            if not found.hasSelection():
                break
            found.removeSelectedText()
            found.insertText(replace_text)
            cursor = found
            count += 1
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.setWindowTitle('Replace - {} replaced'.format(count))


#----------------------------------------------------------------------
# MainWindow
#----------------------------------------------------------------------
class MainWindow (QMainWindow):

    #===== Initialization =====

    def __init__ (self, settings=None):
        super().__init__()
        self.__init_settings(settings)
        self.__init_core_state()
        self.__init_widgets()
        self.__init_ui()
        self.__init_connections()
        self.__init_final()

    def __init_settings (self, settings):
        if settings is None:
            settings = Settings()
            settings.load()
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
        self._dpi = _dpi_factor()
        self.icons = _create_toolbar_icons()
        self.setWindowIcon(self.icons['run'])

    def __init_core_state (self):
        self.tab_manager = TabManager()
        self._tab_switching = False
        self.__programmatic_scroll = False
        self._last_file_dir = ''
        self._deferred_restore_tab = -1
        self._recent_files = []
        self.enc_mgr = EncodingManager()
        self.flow_ctrl = FlowController(self.settings, self.enc_mgr)
        self._find_dialog = None
        self._replace_dialog = None

    def __init_widgets (self):
        self.editor = CodeEditor()
        self.editor.indent_style = self.settings.indent_style
        self.editor.indent_size = self.settings.indent_size
        self.editor.set_bracket_completion(
            self.settings.bracket_completion)
        self.input_panel = InputPanel()
        self.output_panel = OutputPanel()
        # Apply Settings fonts
        editor_font = self.editor.font()
        editor_font.setFamily(self.settings.editor_font_family)
        editor_font.setPointSize(self.settings.editor_font_size)
        self.editor.setFont(editor_font)
        self.editor.updateFontMetrics()
        wrap_mode = QTextEdit.WidgetWidth if self.settings.word_wrap \
            else QTextEdit.NoWrap
        self.editor.setLineWrapMode(wrap_mode)
        io_font = self.input_panel.font()
        io_font.setFamily(self.settings.io_font_family)
        io_font.setPointSize(self.settings.io_font_size)
        self.input_panel.setFont(io_font)
        self.output_panel.setFont(io_font)
        self.input_panel.setTabStopWidth(
            self.input_panel.fontMetrics().horizontalAdvance('x') * self.settings.indent_size)
        # Placeholder docs for zero-tab state
        self.empty_editor_doc = QTextDocument(self)
        self.empty_input_doc = QTextDocument(self)
        self.empty_output_doc = QTextDocument(self)
        self.editor.setDocument(self.empty_editor_doc)
        self.input_panel.setDocument(self.empty_input_doc)
        self.output_panel.setDocument(self.empty_output_doc)

    def __init_ui (self):
        self.__create_actions()
        self.__build_menubar()
        self.__build_toolbar()
        self.__build_mainarea()
        self.__build_tabbar_and_layout()
        self.__build_statusbar()
        self._update_status_from_state(_FLOW_IDLE)

    def __init_connections (self):
        self._flush_output_timer = QTimer(self)
        self._flush_output_timer.setSingleShot(False)
        self._flush_output_timer.timeout.connect(
            self._on_flush_timer)
        self._flush_output_timer.start(50)  # never-stop timer
        self.__connect_signals()
        self.flow_ctrl.state_changed.connect(self._update_status_from_state)
        self.flow_ctrl.status_message.connect(self._update_status_message)
        self.flow_ctrl.busy_message_requested.connect(self._show_busy_message)
        self.flow_ctrl.terminal_requested.connect(self._on_terminal_requested)
        self.__setup_tab_switch_shortcuts()

    def __init_final (self):
        self.setAcceptDrops(True)
        self._enter_zero_tab_state()
        self._load_window_state()

    #===== UI Construction =====

    def __create_actions (self):
        for attr, label, icon_key, shortcuts, tooltip in _ACTION_DEFS:
            icon = self.icons.get(icon_key) if icon_key else None
            if icon:
                action = QAction(icon, label, self)
            else:
                action = QAction(label, self)
            if shortcuts:
                if isinstance(shortcuts, list):
                    action.setShortcuts([QKeySequence(s) for s in shortcuts])
                else:
                    action.setShortcut(QKeySequence(shortcuts))
            if tooltip is None:
                ks = shortcuts[0] if isinstance(shortcuts, list) else shortcuts
                if ks:
                    action.setToolTip('{} ({})'.format(label, ks))
                else:
                    action.setToolTip(label)
            elif tooltip:
                action.setToolTip(tooltip)
            setattr(self, attr, action)

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
        # Recent Files submenu
        self.menu_recent = self.menu_file.addMenu('Recent Files')
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
        self.menu_edit.addSeparator()
        self.menu_edit.addAction(self.act_comment)
        self.menu_edit.addAction(self.act_indent)
        self.menu_edit.addAction(self.act_unindent)
        self.menu_edit.addAction(self.act_duplicate)
        self.menu_edit.addAction(self.act_delete_line)
        self.menu_edit.addAction(self.act_move_up)
        self.menu_edit.addAction(self.act_move_down)

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
        self.status_info = _ClickableLabel('')
        self.status_info.setMainWindow(self)
        self.status_message.setAlignment(Qt.AlignLeft)
        self.status_info.setAlignment(Qt.AlignRight)
        statusbar.addWidget(self.status_message, 1)
        statusbar.addPermanentWidget(self.status_info, 0)

    #===== Signal Wiring =====

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

        # Edit extension actions -- direct to CodeEditor
        self.act_comment.triggered.connect(self.editor._handle_comment_uncomment)
        self.act_indent.triggered.connect(self.editor._handle_indent_selection)
        self.act_unindent.triggered.connect(self.editor._handle_unindent_selection)
        self.act_duplicate.triggered.connect(self.editor._handle_duplicate_line)
        self.act_delete_line.triggered.connect(self.editor._handle_delete_line)
        self.act_move_up.triggered.connect(self.editor._handle_move_line_up)
        self.act_move_down.triggered.connect(self.editor._handle_move_line_down)

        # Run actions
        self.act_build.triggered.connect(self._action_build)
        self.act_run.triggered.connect(self._action_run)
        self.act_test.triggered.connect(self._action_test)
        self.act_stop.triggered.connect(self._action_stop)

        # Help actions
        self.act_about.triggered.connect(self._action_about)

        # Settings
        self.act_settings.triggered.connect(self._action_settings)

        # Tabbar signals
        self.tabbar.currentChanged.connect(
            self._on_tabbar_current_changed)
        self.tabbar.tabCloseRequested.connect(
            self._on_tab_close_requested)
        self.tabbar.tabMoved.connect(self._on_tab_moved)

        # Editor cursor position -> update status bar
        self.editor.cursorPositionChanged.connect(
            self._on_cursor_position_changed)

        # FlowController signals (compile_finished/run_finished
        # are handled by FlowController internally; stdout/stderr are forwarded)
        self.flow_ctrl.run_stdout_ready.connect(
            self._on_run_stdout_ready)
        self.flow_ctrl.run_stderr_ready.connect(
            self._on_run_stderr_ready)
        self.flow_ctrl.output_clear.connect(
            self._on_output_clear)
        self.flow_ctrl.output_append.connect(
            self._on_output_append)

        # Output panel scroll -- detect user scroll-up to deactivate auto-scroll
        self.output_panel.verticalScrollBar().valueChanged.connect(
            self._on_output_scroll_changed)

    def __setup_tab_switch_shortcuts (self):
        # Alt+1~9 -> switch to tab 0~8, Alt+0 -> tab 9
        for i in range(1, 10):
            s = QShortcut(QKeySequence('Alt+{}'.format(i)), self)
            s.activated.connect(
                lambda idx=i - 1: self._switch_to_tab(idx))
        s0 = QShortcut(QKeySequence('Alt+0'), self)
        s0.activated.connect(lambda: self._switch_to_tab(9))

    #===== Action Handlers =====

    #--- File & Tab Lifecycle Actions ---

    def _action_new (self):
        tab = TabData(
            is_new=True, encoding='UTF-8',
            content=self.settings.template_text,
            dirty_callback=self._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        # Position cursor inside main() body (after first '{')
        cursor = QTextCursor(tab.editor_doc)
        search = tab.editor_doc.find('{', cursor)
        if search.hasSelection():
            block = search.block().next()
            if block.isValid():
                text = block.text()
                indent_len = len(text) - len(text.lstrip())
                cursor.setPosition(block.position() + indent_len)
        tab.cursor = cursor
        index = self.tab_manager.add_tab(tab)
        self.tabbar.addTab(tab.tab_name())
        self._switch_to_tab(index)

    def _open_file_path (self, path:str, add_recent:bool=True):
        """Open a file by path. If already open, switch to that tab.
        Returns True if a tab was opened/switched, False on error."""
        path = os.path.normpath(path)
        for i, t in enumerate(self.tab_manager.tabs):
            if not t.is_new and t.file_path and \
                    os.path.normpath(t.file_path) == path:
                self._switch_to_tab(i)
                # Refresh Recent Files order even when already open
                if add_recent:
                    self._add_recent_file(path)
                return True
        try:
            content, encoding = _read_file(path)
        except (IOError, OSError) as e:
            if add_recent:
                QMessageBox.warning(
                    self, 'Open Error',
                    'Failed to open file: {}'.format(e))
            return False
        tab = TabData(
            file_path=path, is_new=False,
            encoding=encoding, content=content,
            dirty_callback=self._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.tab_manager.add_tab(tab)
        self.tabbar.addTab(tab.tab_name())
        self._switch_to_tab(index)
        if add_recent:
            self._last_file_dir = os.path.dirname(path)
            self._add_recent_file(path)
        return True

    def _start_dir (self) -> str:
        """Return a valid starting directory for file dialogs.
        Uses _last_file_dir if it still exists on disk,
        otherwise falls back to home directory."""
        if self._last_file_dir and os.path.isdir(self._last_file_dir):
            return self._last_file_dir
        return os.path.expanduser('~')

    def _action_open (self):
        start_dir = self._start_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, 'Open File', start_dir,
            'C++ Files (*.cpp *.c *.cc *.cxx *.h *.hpp *.hh);;All Files (*)')
        if path:
            self._open_file_path(path)

    def _action_save (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        self._save_tab_data(tab)

    def _action_save_as (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        start_dir = self._start_dir()
        if tab.file_path:
            start_dir = os.path.dirname(tab.file_path)
        path, _ = QFileDialog.getSaveFileName(
            self, 'Save As', start_dir,
            'C++ Files (*.cpp *.c *.cc *.cxx *.h *.hpp *.hh);;All Files (*)')
        if not path:
            return
        path = os.path.normpath(path)
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
        self._add_recent_file(path)

    def _action_close (self):
        if self.tab_manager.current_index < 0:
            return
        self._handle_close_tab(self.tab_manager.current_index)

    #--- Edit & View Actions ---

    def _action_zoom_in (self):
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        base_size = self.settings.editor_font_size
        if base_size + tab.zoom_font_size >= 72:
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
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, QTextEdit):
            focus.undo()
        else:
            self.editor.undo()

    def _action_redo (self):
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, QTextEdit):
            focus.redo()
        else:
            self.editor.redo()

    def _action_cut (self):
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, QTextEdit) and not focus.isReadOnly():
            focus.cut()
        else:
            self.editor.cut()

    def _action_copy (self):
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, QTextEdit):
            focus.copy()
        else:
            self.editor.copy()

    def _action_paste (self):
        focus = QApplication.focusWidget()
        if focus and isinstance(focus, QTextEdit) and not focus.isReadOnly():
            focus.paste()
        else:
            self.editor.paste()

    def _action_find (self):
        if self._find_dialog is None:
            self._find_dialog = FindDialog(self.editor, self)
        self._find_dialog.show()
        self._find_dialog.activateWindow()
        self._find_dialog.edit_find.setFocus()
        self._find_dialog.edit_find.selectAll()

    def _action_replace (self):
        if self._replace_dialog is None:
            self._replace_dialog = ReplaceDialog(self.editor, self)
        self._replace_dialog.show()
        self._replace_dialog.activateWindow()
        self._replace_dialog.edit_find.setFocus()
        self._replace_dialog.edit_find.selectAll()

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
        if self.flow_ctrl.state != _FLOW_IDLE:
            self.flow_ctrl.busy_message_requested.emit()
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._save_if_dirty(tab) < 0:
            return
        self.flow_ctrl.start_build(tab)

    def _action_run (self):
        if self.flow_ctrl.state != _FLOW_IDLE:
            self.flow_ctrl.busy_message_requested.emit()
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._save_if_dirty(tab) < 0:
            return
        self.flow_ctrl.start_run(tab)

    def _action_test (self):
        if self.flow_ctrl.state != _FLOW_IDLE:
            self.flow_ctrl.busy_message_requested.emit()
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._save_if_dirty(tab) < 0:
            return
        self.flow_ctrl.start_test(tab)

    def _action_stop (self):
        self.flow_ctrl.kill_if_busy()

    def _action_about (self):
        QMessageBox.about(
            self, 'About CodeRunner',
            'CodeRunner\n\nAuthor: skywind3000\n{}'.format(
                time.strftime('%Y/%m/%d %H:%M:%S')))

    #===== Flow state signal handlers =====

    def _update_status_from_state (self, state):
        """Update status bar with default text for the given flow state."""
        if state == _FLOW_IDLE:
            self.status_message.setText('Ready')
        elif state == _FLOW_COMPILING:
            self.status_message.setText('Compiling...')
        elif state == _FLOW_RUNNING:
            self.status_message.setText('Running...')

    def _update_status_message (self, msg):
        """Override status bar with a specific result message."""
        self.status_message.setText(msg)

    def _show_busy_message (self):
        QMessageBox.information(
            self, 'Busy',
            'A process is currently running. '
            'Please wait or press Stop before starting a new operation.')

    def _on_terminal_requested (self, tab):
        """FlowController requests launching an external terminal."""
        ok = self._launch_terminal(tab)
        if ok:
            self.status_message.setText('Running in terminal')
        else:
            self._on_output_clear(tab)
            self._on_output_append(
                tab, QColor(Qt.red), 'Failed to launch terminal\n')
            self.status_message.setText('Failed to launch terminal')

    #===== Settings =====

    def _action_settings (self):
        old_font_size = self.settings.editor_font_size
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec_() == QDialog.Accepted:
            self._apply_settings(old_font_size)

    def _apply_settings (self, old_font_size:int=-1):
        """Apply current settings to all widgets (fonts, bracket completion).
        Only resets zoom if editor_font_size actually changed."""
        s = self.settings
        # If compiler-related settings changed, invalidate all tab mtime
        if hasattr(s, 'compiler_mtime') and s.compiler_mtime > 0:
            for t in self.tab_manager.tabs:
                t.compiler_mtime = max(t.compiler_mtime, s.compiler_mtime)
        # Editor font
        editor_font = self.editor.font()
        editor_font.setFamily(s.editor_font_family)
        editor_font.setPointSize(s.editor_font_size)
        self.editor.setFont(editor_font)
        self.editor.updateFontMetrics()
        # Bracket completion
        self.editor.set_bracket_completion(s.bracket_completion)
        # Word wrap
        wrap_mode = QTextEdit.WidgetWidth if s.word_wrap \
            else QTextEdit.NoWrap
        self.editor.setLineWrapMode(wrap_mode)
        # Indent style and size
        self.editor.indent_style = s.indent_style
        self.editor.indent_size = s.indent_size
        self.editor._update_tab_width()
        # Sync document default font for current tab
        tab = self.tab_manager.get_current()
        if tab:
            tab.editor_doc.setDefaultFont(self.editor.font())
        # IO fonts
        io_font = self.input_panel.font()
        io_font.setFamily(s.io_font_family)
        io_font.setPointSize(s.io_font_size)
        self.input_panel.setFont(io_font)
        self.output_panel.setFont(io_font)
        self.input_panel.setTabStopWidth(
            self.input_panel.fontMetrics().horizontalAdvance('x') * s.indent_size)
        if tab:
            tab.input_doc.setDefaultFont(self.input_panel.font())
            tab.output_doc.setDefaultFont(self.output_panel.font())
        # Update IO section labels
        for section, _panel in [
                (self.input_section, self.input_panel),
                (self.output_section, self.output_panel)]:
            label = section._section_label
            lbl_font = label.font()
            lbl_font.setFamily(s.io_font_family)
            lbl_font.setPointSize(s.io_font_size)
            label.setFont(lbl_font)
            label.setFixedHeight(label.sizeHint().height() + int(4 * self._dpi))
        # Reset zoom offset only if editor font size actually changed
        if old_font_size >= 0 and s.editor_font_size != old_font_size:
            for t in self.tab_manager.tabs:
                t.zoom_font_size = 0
            if tab:
                zoom_size = max(6, s.editor_font_size)
                self.editor.setFontSize(zoom_size)

    def _launch_terminal (self, tab:TabData) -> bool:
        """Launch exe in external terminal window. Returns True on success."""
        exe_path = self.flow_ctrl.get_exe_path(tab)
        if sys.platform == 'win32':
            exe_path = exe_path.replace('/', '\\')
        work_dir = os.path.dirname(exe_path)
        bat_path = _ensure_cmd_file()
        _, bin_dir = _resolve_compiler_path(self.settings.compiler_path)
        # Compute CR_SET_PATH: prepend bin_dir to PATH if needed
        if bin_dir:
            cr_set_path = 'set PATH={};%PATH%'.format(bin_dir)
        else:
            cr_set_path = 'rem no path prefix'
        # Compute CR_ENV_SETUP: batch set commands for user env vars
        expanded_env = {}
        for key, value in self.settings.env_vars.items():
            expanded_env[key] = _expand_env_vars(value)
        env_lines = []
        for key, value in expanded_env.items():
            if key.startswith('CR_'):
                continue  # Don't overwrite CR_* vars
            env_lines.append('set {}={}'.format(key, value))
        if env_lines:
            cr_env_setup = '\n'.join(env_lines)
        else:
            cr_env_setup = 'rem no custom env'
        # Only temporarily set CR_* prefixed vars in os.environ
        saved_env = {}
        try:
            for cr_key, cr_value in {
                'CR_COMMAND': '"{}"'.format(exe_path),
                'CR_PAUSE': 'pause',
                'CR_SET_PATH': cr_set_path,
                'CR_ENV_SETUP': cr_env_setup,
            }.items():
                saved_env[cr_key] = os.environ.get(cr_key)
                os.environ[cr_key] = cr_value
            ok = QProcess.startDetached(
                'cmd',
                ['/c', 'start', '', '/D', work_dir, bat_path])
        finally:
            for key, orig in saved_env.items():
                if orig is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = orig
        return ok

    def _is_output_at_bottom (self) -> bool:
        """Check if OutputPanel scrollbar is near the bottom (within 3px)."""
        sb = self.output_panel.verticalScrollBar()
        return sb.maximum() - sb.value() <= 3

    def _on_output_scroll_changed (self):
        """Detect user scrolling in output panel -- update pinned state.
        __programmatic_scroll=True means timer did the scroll, ignore it.
        User scroll away from bottom -> pinned=False; scroll to bottom -> pinned=True."""
        if self.__programmatic_scroll:
            return
        tab = self.tab_manager.get_current()
        if not tab:
            return
        if self._is_output_at_bottom():
            tab.pinned_to_bottom = True
        else:
            tab.pinned_to_bottom = False

    def _flush_output_buffer (self, tab:TabData):
        """Flush output_buffer to output_doc: merge adjacent same-color,
        write via QTextCursor, clear buffer. Truncates if size exceeds limit."""
        if not tab.output_buffer:
            return
        # Merge adjacent entries with same color
        merged = []
        for color, text in tab.output_buffer:
            if merged and merged[-1][0] == color:
                merged[-1] = (color, merged[-1][1] + text)
            else:
                merged.append((color, text))
        # Write merged entries to output_doc
        cursor = QTextCursor(tab.output_doc)
        cursor.movePosition(QTextCursor.End)
        cursor.beginEditBlock()
        for color, text in merged:
            fmt = QTextCharFormat()
            if color is not None:
                fmt.setForeground(QBrush(color))
            cursor.setCharFormat(fmt)
            cursor.insertText(text)
        cursor.endEditBlock()
        tab.output_buffer.clear()
        # Truncate from beginning if output exceeds size limit
        self._truncate_output_if_needed(tab)

    def _truncate_output_if_needed (self, tab:TabData):
        """Truncate output_doc from the beginning if it exceeds size limit.
        Removes roughly the first half and inserts a truncation notice."""
        doc = tab.output_doc
        if doc.characterCount() <= _OUTPUT_MAX_CHARS:
            return
        # Remove from start to approximately half of the document
        half_pos = doc.characterCount() // 2
        block = doc.findBlock(half_pos)
        cursor = QTextCursor(doc)
        cursor.setPosition(0)
        cursor.setPosition(block.position(), QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        # Insert truncation notice at the start
        cursor.movePosition(QTextCursor.Start)
        notice_fmt = QTextCharFormat()
        notice_fmt.setForeground(QBrush(QColor(128, 128, 128)))
        cursor.setCharFormat(notice_fmt)
        cursor.insertText('[...output truncated...]\n')

    def _immediate_flush (self, tab:TabData):
        """Immediately flush output buffer for a tab, then scroll if pinned.
        Used for stdin submit and large output protection."""
        self._flush_output_buffer(tab)
        if tab is self.tab_manager.get_current() and tab.pinned_to_bottom:
            self.__programmatic_scroll = True
            self.output_panel.verticalScrollBar().setValue(
                self.output_panel.verticalScrollBar().maximum())
            self.__programmatic_scroll = False

    def _check_buffer_overflow (self, tab:TabData):
        """Flush immediately if buffer exceeds size/count threshold.
        Prevents high-frequency output from inflating the buffer."""
        if len(tab.output_buffer) > 200:
            self._immediate_flush(tab)
            return
        if tab.output_buffer:
            total = sum(len(t) for _, t in tab.output_buffer)
            if total > 65536:
                self._immediate_flush(tab)

    def _on_flush_timer (self):
        """50ms global timer: flush all tab buffers + scroll current if pinned.
        Timer never stops -- empty ticks have negligible overhead."""
        for tab in self.tab_manager.tabs:
            self._flush_output_buffer(tab)
        # Scroll current tab to bottom if pinned
        tab = self.tab_manager.get_current()
        if tab and tab.pinned_to_bottom:
            self.__programmatic_scroll = True
            self.output_panel.verticalScrollBar().setValue(
                self.output_panel.verticalScrollBar().maximum())
            self.__programmatic_scroll = False

    def _on_run_stdout_ready (self, text:str):
        tab = self.flow_ctrl.tab
        if tab:
            tab.output_buffer.append((None, text))
            self._check_buffer_overflow(tab)

    def _on_run_stderr_ready (self, text:str):
        tab = self.flow_ctrl.tab
        if tab:
            tab.output_buffer.append((QColor(128, 128, 128), text))
            self._check_buffer_overflow(tab)

    def _on_output_clear (self, tab):
        """Handle FlowController output_clear signal."""
        tab.output_buffer.clear()
        _output_clear(tab.output_doc)
        tab.pinned_to_bottom = True

    def _on_output_append (self, tab, color, text):
        """Handle FlowController output_append signal."""
        tab.output_buffer.append((color, text))

    #===== Tab Management =====

    def _save_widget_state (self, tab:TabData):
        """Save current widget state (cursor, scroll) into tab data."""
        tab.cursor = self.editor.textCursor()
        tab.scroll_pos = self.editor.verticalScrollBar().value()
        tab.input_cursor = self.input_panel.textCursor()
        tab.input_scroll = self.input_panel.verticalScrollBar().value()
        tab.output_scroll = self.output_panel.verticalScrollBar().value()

    def _switch_to_tab (self, index:int):
        """Switch to tab: save old state, swap documents, restore new state."""
        tm = self.tab_manager
        if index < 0 or index >= len(tm.tabs):
            return
        old_index = tm.current_index

        # Save old tab state
        if 0 <= old_index < len(tm.tabs):
            old_tab = tm.tabs[old_index]
            self._save_widget_state(old_tab)
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

            # Flush new tab's buffer so scroll position is correct
            self._flush_output_buffer(new_tab)
        finally:
            # Unfreeze -- document content displayed immediately
            self.editor.setUpdatesEnabled(True)
            self.input_panel.setUpdatesEnabled(True)
            self.output_panel.setUpdatesEnabled(True)

            # Restore output scroll position
            if new_tab.pinned_to_bottom:
                self.__programmatic_scroll = True
                self.output_panel.verticalScrollBar().setValue(
                    self.output_panel.verticalScrollBar().maximum())
                self.__programmatic_scroll = False
            else:
                self.output_panel.verticalScrollBar().setValue(
                    new_tab.output_scroll)

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

        # Cancel running flow if this tab is the active target
        if self.flow_ctrl.state != _FLOW_IDLE and self.flow_ctrl.tab is tab:
            self.flow_ctrl.cancel_flow()
            self._flush_output_buffer(tab)

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
            self._save_widget_state(tm.tabs[tm.current_index])

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
        # Deferred save so cursor restore completes first
        QTimer.singleShot(0, self._save_window_state)
        return True

    #===== Status & Title =====

    #--- Status display ---

    def _update_status_info (self, tab:TabData):
        cursor = self.editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        total = self.editor.document().blockCount()
        mode = 'OVR' if self.editor.overwrite_mode else 'INS'
        text = 'Ln {}/{}, Col {} | {} | {}'.format(
            line, total, col, tab.encoding, mode)
        self.status_info.setText(text)

    def _show_encoding_menu (self, pos_widget):
        """Show encoding menu when status bar encoding label is clicked."""
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        menu = QMenu(self)
        reopen_menu = menu.addMenu('Reopen with Encoding')
        save_menu = menu.addMenu('Save with Encoding')
        for enc in _COMMON_ENCODINGS:
            action = reopen_menu.addAction(enc)
            action.setData(enc)
            action.triggered.connect(self._on_reopen_with_encoding)
            action2 = save_menu.addAction(enc)
            action2.setData(enc)
            action2.triggered.connect(self._on_save_with_encoding)
        menu.exec_(pos_widget.mapToGlobal(pos_widget.rect().bottomLeft()))

    #--- Encoding lifecycle (reopen/save with encoding) ---

    def _on_reopen_with_encoding (self, encoding:str=None):
        """Reopen current file with chosen encoding."""
        if encoding is None:
            action = self.sender()
            if action is None:
                return
            encoding = action.data()
        tab = self.tab_manager.get_current()
        if tab is None or tab.is_new:
            return
        # Check for unsaved changes before overwriting
        if tab.is_dirty or tab.editor_doc.isModified():
            result = self._confirm_reopen_encoding(tab)
            if result == 'save':
                if self._save_tab_data(tab) < 0:
                    return
            elif result == 'cancel':
                return
        try:
            with open(tab.file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except (IOError, OSError, UnicodeDecodeError) as e:
            QMessageBox.warning(
                self, 'Encoding Error',
                'Failed to read file with {}: {}'.format(encoding, e))
            return
        tab.encoding = encoding
        # Set content without triggering modificationChanged
        tab.editor_doc.blockSignals(True)
        tab.editor_doc.setPlainText(content)
        tab.editor_doc.setModified(False)
        tab.editor_doc.blockSignals(False)
        # Re-apply highlighter (document content changed)
        tab.highlighter.cancel_batch_highlight()
        tab.highlighter.rehighlight()
        tab._highlight_pending = False
        tab.is_dirty = False
        self._update_tab_name(
            self.tab_manager.find_tab_index(tab))
        self._update_window_title()
        self._update_status_info(tab)

    def _on_save_with_encoding (self, encoding:str=None):
        """Save current file with chosen encoding."""
        if encoding is None:
            action = self.sender()
            if action is None:
                return
            encoding = action.data()
        tab = self.tab_manager.get_current()
        if tab is None:
            return
        old_path = tab.file_path
        old_is_new = tab.is_new
        if tab.is_new:
            # Need to save to a path first
            start_dir = self._start_dir()
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save File', start_dir,
                'C++ Files (*.cpp *.c *.cc *.cxx *.h '
                '*.hpp *.hh);;All Files (*)')
            if not path:
                return
            path = os.path.normpath(path)
            tab.file_path = path
            tab.is_new = False
        content = tab.editor_doc.toPlainText()
        try:
            with open(tab.file_path, 'w', encoding=encoding) as f:
                f.write(content)
        except (IOError, OSError, UnicodeEncodeError) as e:
            # Rollback on failure
            tab.file_path = old_path
            tab.is_new = old_is_new
            QMessageBox.warning(
                self, 'Save Error',
                'Failed to save with {}: {}'.format(encoding, e))
            return
        # Update encoding and dirty state
        tab.encoding = encoding
        tab.editor_doc.setModified(False)
        tab.is_dirty = False
        self._update_tab_name(
            self.tab_manager.find_tab_index(tab))
        self._update_window_title()
        self._update_status_info(tab)
        self._add_recent_file(tab.file_path)
        self._last_file_dir = os.path.dirname(tab.file_path)
        self.status_message.setText(
            'Saved: {} ({})'.format(
                os.path.basename(tab.file_path), encoding))

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

    #===== File Save & Confirm Dialogs =====

    def _save_if_dirty (self, tab:TabData) -> int:
        """Save tab if it has unsaved changes. Returns 0 success/clean,
        -1 user cancelled save dialog, -2 write error.
        If tab is not dirty and not new, no save is needed -> returns 0."""
        if not tab.is_dirty and not tab.is_new:
            return 0
        return self._save_tab_data(tab)

    def _save_tab_data (self, tab:TabData) -> int:
        """Save tab to disk. Returns 0 success, -1 cancel, -2 error.
        Two-phase: prepare content on temp text, only commit to document
        after successful write, so failure/cancel leaves doc unchanged."""
        # Phase 1: prepare content (strip trailing whitespace on plain text)
        content = _strip_trailing_whitespace(tab.editor_doc.toPlainText())
        # Phase 2: write to disk
        if tab.is_new:
            start_dir = self._start_dir()
            path, _ = QFileDialog.getSaveFileName(
                self, 'Save File', start_dir,
                'C++ Files (*.cpp *.c *.cc *.cxx *.h '
                '*.hpp *.hh);;All Files (*)')
            if not path:
                return -1
            path = os.path.normpath(path)
            try:
                with open(path, 'w', encoding=tab.encoding) as f:
                    f.write(content)
            except (IOError, OSError, UnicodeEncodeError) as e:
                QMessageBox.warning(self, 'Save Error', str(e))
                return -2
            tab.file_path = path
            tab.is_new = False
            self._last_file_dir = os.path.dirname(path)
            self._add_recent_file(path)
        else:
            try:
                with open(tab.file_path, 'w', encoding=tab.encoding) as f:
                    f.write(content)
            except (IOError, OSError, UnicodeEncodeError) as e:
                QMessageBox.warning(self, 'Save Error', str(e))
                return -2

        # Phase 3: commit to document (only after write succeeded)
        _strip_trailing_whitespace_in_doc(tab.editor_doc)
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

    def _confirm_reopen_encoding (self, tab:TabData) -> str:
        """Confirm before Reopen with Encoding overwrites unsaved changes."""
        name = os.path.basename(tab.file_path)
        msg = QMessageBox(self)
        msg.setWindowTitle('Unsaved Changes')
        msg.setText(
            "Reopen with Encoding will discard unsaved changes in "
            "'{}'.".format(name))
        msg.setStandardButtons(
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Save)
        result = msg.exec_()
        if result == QMessageBox.Save:
            return 'save'
        elif result == QMessageBox.Discard:
            return 'discard'
        return 'cancel'

    #----- Signal handlers (tab lifecycle) -----

    def _on_tabbar_current_changed (self, index:int):
        if self._tab_switching:
            return
        if 0 <= index < len(self.tab_manager.tabs):
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
        self.editor.setExtraSelections([])
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

    #===== Window State & Lifecycle =====

    def closeEvent (self, event):
        for tab in list(self.tab_manager.tabs):
            if tab.is_dirty:
                choice = self._confirm_close_tab(tab)
                if choice == 'cancel':
                    event.ignore()
                    return
                elif choice == 'discard':
                    tab.is_dirty = False
                    tab.editor_doc.setModified(False)
                elif choice == 'save':
                    result = self._save_tab_data(tab)
                    if result < 0:
                        event.ignore()
                        return

        # Clean up any running process only after confirming all dirty tabs
        if self.flow_ctrl.proc_mgr.busy:
            self.flow_ctrl.proc_mgr.kill_process()
            self.flow_ctrl.proc_mgr._cleanup()

        # Save window state only after confirming all dirty tabs
        self._save_window_state()
        # Cancel all batch highlighting timers before Qt destruction
        for tab in self.tab_manager.tabs:
            tab.highlighter.cancel_batch_highlight()

        # Disconnect all signals before Qt destruction
        for tab in self.tab_manager.tabs:
            try:
                tab.editor_doc.modificationChanged.disconnect(
                    tab._on_modified_changed)
            except (RuntimeError, TypeError):
                pass
        event.accept()

    #----- Window state persistence -----

    def _save_window_state (self):
        """Save window geometry, splitter sizes, tabs, recent files to JSON."""
        path = _window_state_path()
        _ensure_dir(os.path.dirname(path))
        # Save current tab's widget state
        tab = self.tab_manager.get_current()
        if tab:
            self._save_widget_state(tab)
        # Use normalGeometry to avoid saving maximized/fullscreen coordinates
        geo = (self.normalGeometry() if self.isMaximized()
               else self.geometry())
        # Clamp to ensure title bar is visible on screen
        screen = QApplication.primaryScreen()
        min_y = 0
        min_x = 0
        if screen:
            avail = screen.availableGeometry()
            min_y = avail.y()
            min_x = avail.x()
        sx = max(geo.x(), min_x)
        sy = max(geo.y(), min_y)
        state = {
            'geometry': {
                'x': sx, 'y': sy,
                'w': geo.width(), 'h': geo.height()},
            'h_splitter': self.main_splitter.sizes(),
            'v_splitter': self.v_splitter.sizes(),
            'last_file_dir': self._last_file_dir,
            'tabs': [],
            'recent_files': self._recent_files[:10],
        }
        persisted_count = 0
        for i, t in enumerate(self.tab_manager.tabs):
            # Skip discarded new tabs (user chose "Discard" in close dialog)
            if t.is_new and not t.is_dirty:
                continue
            if i == self.tab_manager.current_index:
                state['active_tab'] = persisted_count
            entry = {}
            if t.is_new:
                entry['is_new'] = True
                entry['editor_text'] = t.editor_doc.toPlainText()
                entry['input_text'] = t.input_doc.toPlainText()
                entry['untitled_number'] = t.untitled_number
            else:
                entry['file_path'] = t.file_path
                entry['input_text'] = t.input_doc.toPlainText()
            state['tabs'].append(entry)
            persisted_count += 1
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=4, ensure_ascii=False)
        except (IOError, OSError):
            pass

    def _load_window_state (self):
        """Restore window geometry, splitter sizes, tabs, recent files."""
        path = _window_state_path()
        if not os.path.exists(path):
            return -1
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except (IOError, OSError, json.JSONDecodeError):
            return -1
        # Restore geometry (ensure title bar is visible)
        geo = state.get('geometry', {})
        if geo:
            x = geo.get('x', 100)
            y = geo.get('y', 100)
            w = geo.get('w', 1000)
            h = geo.get('h', 650)
            # Ensure title bar is visible on screen
            screen = QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
                # Clamp size so window fits on screen
                w = min(w, avail.width())
                h = min(h, avail.height())
                # Clamp y so title bar is at least partially visible
                y = max(y, avail.y())
                # Clamp x so window left edge is visible
                x = max(x, avail.x())
                # Clamp so window doesn't extend beyond right/bottom
                x = min(x, avail.x() + avail.width() - w)
                y = min(y, avail.y() + avail.height() - h)
                # Final safety: ensure both edges are visible
                y = max(y, avail.y())
                x = max(x, avail.x())
            self.setGeometry(x, y, w, h)
        # Restore splitter sizes
        h_sizes = state.get('h_splitter', [500, 500])
        v_sizes = state.get('v_splitter', [325, 325])
        if len(h_sizes) == 2:
            self.main_splitter.setSizes(h_sizes)
        if len(v_sizes) == 2:
            self.v_splitter.setSizes(v_sizes)
        # Restore last_file_dir
        self._last_file_dir = state.get('last_file_dir', '')
        # Restore recent files
        self._recent_files = [os.path.normpath(p)
                              for p in state.get('recent_files', [])]
        self._update_recent_menu()
        # Restore tabs
        tabs_data = state.get('tabs', [])
        for entry in tabs_data:
            if entry.get('is_new'):
                tab = TabData(
                    is_new=True, encoding='UTF-8',
                    content=entry.get('editor_text', ''),
                    dirty_callback=self._on_tab_dirty_changed)
                tab.untitled_number = entry.get('untitled_number', 1)
                # Restore InputPanel content
                tab.input_doc.setPlainText(
                    entry.get('input_text', ''))
                tab.is_dirty = True
                tab.editor_doc.setModified(True)
            else:
                file_path = entry.get('file_path', '')
                if not file_path:
                    continue
                # Skip deleted files during session restore
                if not os.path.exists(file_path):
                    continue
                try:
                    content, encoding = _read_file(file_path)
                except (IOError, OSError):
                    continue
                tab = TabData(
                    file_path=file_path, is_new=False,
                    encoding=encoding, content=content,
                    dirty_callback=self._on_tab_dirty_changed)
                tab.input_doc.setPlainText(
                    entry.get('input_text', ''))
            self.tab_manager.add_tab(tab)
            self.tabbar.addTab(tab.tab_name())
            tab.compiler_mtime = self.settings.compiler_mtime
        # Restore active tab
        active = state.get('active_tab', -1)
        if 0 <= active < len(self.tab_manager.tabs):
            self._switch_to_tab(active)
        elif len(self.tab_manager.tabs) > 0:
            self._switch_to_tab(0)
        else:
            self._enter_zero_tab_state()
        return 0

    #----- Recent files -----

    def _add_recent_file (self, path:str):
        """Add file to recent list, dedup, limit to 10."""
        path = os.path.normpath(path)
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        if len(self._recent_files) > 10:
            self._recent_files = self._recent_files[:10]
        self._update_recent_menu()

    def _update_recent_menu (self):
        """Rebuild Recent Files submenu from self._recent_files."""
        self.menu_recent.clear()
        for path in self._recent_files:
            action = QAction(path, self)
            action.setData(path)
            action.triggered.connect(self._on_recent_file)
            self.menu_recent.addAction(action)
        if not self._recent_files:
            action = QAction('(Empty)', self)
            action.setEnabled(False)
            self.menu_recent.addAction(action)

    def _on_recent_file (self):
        """Open a file from Recent Files menu."""
        action = self.sender()
        if action is None:
            return
        path = action.data()
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(
                self, 'File Not Found',
                'File not found: {}'.format(path))
            if path in self._recent_files:
                self._recent_files.remove(path)
                self._update_recent_menu()
            return
        self._open_file_path(path, add_recent=True)

    #===== Drag-Drop (file open via drop) =====

    def dragEnterEvent (self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and any(path.lower().endswith(ext)
                                for ext in _SOURCE_EXTENSIONS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent (self, event):
        if event.mimeData().hasUrls():
            opened = False
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and any(path.lower().endswith(ext)
                                for ext in _SOURCE_EXTENSIONS):
                    self._open_file_path(path, add_recent=True)
                    opened = True
            if opened:
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()


#----------------------------------------------------------------------
# Toolbar icon generation
#----------------------------------------------------------------------
_ICON_BASE = 24

_COLOR_NEW = QColor(120, 120, 120)
_COLOR_SAVE = QColor(60, 100, 200)
_COLOR_OPEN = QColor(220, 180, 40)
_COLOR_RUN = QColor(0, 160, 0)
_COLOR_TEST = QColor(50, 100, 220)
_COLOR_STOP = QColor(220, 50, 50)


def _icon_canvas (dpi:float=1.0):
    """Create icon pixmap and painter with standard setup.
    Returns (pixmap, painter). Caller draws and calls painter.end()."""
    size = int(_ICON_BASE * dpi)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpi)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(dpi, dpi)
    return (pixmap, painter)


def _generate_new_icon (dpi:float=1.0) -> QIcon:
    pixmap, p = _icon_canvas(dpi)
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
    pixmap, p = _icon_canvas(dpi)
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
    pixmap, p = _icon_canvas(dpi)
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
    pixmap, p = _icon_canvas(dpi)
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
    pixmap, p = _icon_canvas(dpi)
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
    pixmap, p = _icon_canvas(dpi)
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
    pixmap, p = _icon_canvas(dpi)
    color = _COLOR_STOP
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    margin = 4
    p.drawRoundedRect(margin, margin, _ICON_BASE - 2 * margin,
                      _ICON_BASE - 2 * margin, 2.0, 2.0)
    p.end()
    return QIcon(pixmap)


def _create_toolbar_icons () -> dict:
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
# Qt message handler -- suppress harmless Windows platform warnings
#----------------------------------------------------------------------
_SUPPRESSED_WARNINGS = ('setMouseGrabEnabled', 'setKeyboardGrabEnabled')


def _qt_message_handler (msg_type:QtMsgType, context, msg:str):
    if msg_type == QtMsgType.QtWarningMsg:
        for pattern in _SUPPRESSED_WARNINGS:
            if pattern in msg:
                return
    # Pass everything else through to default handler
    if _default_qt_handler:
        _default_qt_handler(msg_type, context, msg)


_default_qt_handler = qInstallMessageHandler(_qt_message_handler)


#----------------------------------------------------------------------
# Main entry
#----------------------------------------------------------------------
def main ():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    settings = Settings()
    settings.load()  # Load from ~/.config/coderunner/settings.json
    _init_font_defaults(settings)  # Fill empty font families with detected values
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
