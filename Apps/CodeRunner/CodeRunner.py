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
import math
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QTabBar, QSplitter,
    QPlainTextEdit, QTextEdit, QLabel, QWidget, QAction,
    QVBoxLayout
)
from PyQt5.QtCore import Qt, QSize, QPointF
from PyQt5.QtGui import (
    QKeySequence, QFontDatabase, QIcon, QPainter, QPixmap,
    QColor, QPen, QBrush, QPolygonF
)


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


def _init_font_defaults () -> None:
    """Initialize Settings font defaults based on platform."""
    font = _detect_monospace_font()
    Settings.editor_font_family = font
    Settings.io_font_family = font


def _make_io_section (label_text:str, text_edit:QWidget) -> QWidget:
    """Wrap a text edit widget with a label header (INPUT or OUTPUT)."""
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    label = QLabel(label_text)
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    font = label.font()
    font.setBold(True)
    font.setPointSize(Settings.io_font_size)
    label.setFont(font)
    label.setFixedHeight(label.sizeHint().height() + 4)
    layout.addWidget(label)
    layout.addWidget(text_edit, 1)
    container._section_label = label
    return container


#----------------------------------------------------------------------
# Toolbar icon generation
#----------------------------------------------------------------------
_ICON_SIZE = 24

# Custom colors for semantic toolbar icons
_COLOR_NEW  = QColor(120, 120, 120)   # gray: neutral
_COLOR_SAVE = QColor(60, 100, 200)    # blue: floppy disk
_COLOR_OPEN = QColor(220, 180, 40)    # yellow: folder
_COLOR_RUN  = QColor(0, 160, 0)      # green: go
_COLOR_TEST = QColor(50, 100, 220)   # blue: experiment
_COLOR_STOP = QColor(220, 50, 50)    # red: halt
_COLOR_STOP = QColor(220, 50, 50)    # red


def _generate_new_icon () -> QIcon:
    """Generate a New icon: document with folded corner, gray border/white fill."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    border = _COLOR_NEW
    fill = QColor(255, 255, 255)
    margin = 3
    fold = 5
    # Document shape with folded bottom-right corner
    polygon = QPolygonF([
        QPointF(margin, margin),
        QPointF(size - margin, margin),
        QPointF(size - margin, size - margin - fold),
        QPointF(size - margin - fold, size - margin),
        QPointF(margin, size - margin),
    ])
    p.setPen(QPen(border, 1.2))
    p.setBrush(QBrush(fill))
    p.drawPolygon(polygon)
    # Fold triangle (gray fill, darker than border to show depth)
    fold_fill = QColor(180, 180, 180)
    p.setBrush(QBrush(fold_fill))
    p.setPen(QPen(border, 0.8))
    fold_tri = QPolygonF([
        QPointF(size - margin, size - margin - fold),
        QPointF(size - margin - fold, size - margin),
        QPointF(size - margin, size - margin),
    ])
    p.drawPolygon(fold_tri)
    # Text lines inside (black)
    p.setPen(QPen(QColor(30, 30, 30), 1.3))
    line_y1 = margin + 7
    line_y2 = margin + 11
    line_left = margin + 3
    line_right = size - margin - fold - 1
    p.drawLine(QPointF(line_left, line_y1), QPointF(line_right, line_y1))
    p.drawLine(QPointF(line_left, line_y2), QPointF(line_right - 3, line_y2))
    p.end()
    return QIcon(pixmap)


def _generate_save_icon () -> QIcon:
    """Generate a Save icon: 3.5-inch floppy disk, blue."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = _COLOR_SAVE
    lighter = QColor(color.red() + 60, color.green() + 60, color.blue() + 40)
    darker = QColor(color.red() - 20, color.green() - 20, color.blue() - 30)
    m = 3
    # Disk body (outer rectangle with rounded corners)
    p.setPen(QPen(darker, 1.0))
    p.setBrush(QBrush(color))
    p.drawRoundedRect(m, m, size - 2 * m, size - 2 * m, 1.5, 1.5)
    # Metal slider at top (indented rectangle)
    sl_m = 5  # slider left/right margin from disk edge
    sl_h = 7
    p.setPen(QPen(darker, 0.8))
    p.setBrush(QBrush(lighter))
    p.drawRect(m + sl_m, m, size - 2 * m - 2 * sl_m, sl_h)
    # Hole inside slider (two small rectangles)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    hole_w = size - 2 * m - 2 * sl_m - 6
    hole_h = 3
    p.drawRect(m + sl_m + 3, m + 2, hole_w, hole_h)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    # Label area at bottom (white rectangle with thin border)
    lb_m = 5
    lb_h = 6
    lb_top = size - m - lb_h - 2
    p.setPen(QPen(darker, 0.8))
    p.setBrush(QBrush(QColor(255, 255, 255, 230)))
    p.drawRect(m + lb_m, lb_top, size - 2 * m - 2 * lb_m, lb_h)
    p.end()
    return QIcon(pixmap)


def _generate_open_icon () -> QIcon:
    """Generate an Open icon: Win2K-style folder, yellow."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = _COLOR_OPEN
    darker = QColor(color.red() - 50, color.green() - 50, color.blue() - 10)
    p.setPen(QPen(darker, 1.0))
    p.setBrush(QBrush(color))
    m = 3
    # Back panel (full folder rectangle)
    p.drawRoundedRect(m, 6, size - 2 * m, size - m - 6, 1.0, 1.0)
    # Tab at top-left sticking up (folder tab)
    tab_w = 8
    p.setBrush(QBrush(darker))
    p.drawRoundedRect(m, 2, tab_w, 6, 1.0, 1.0)
    # Front flap (open, offset forward — the "open" look)
    # Draw as a slightly shifted rectangle that overlaps the bottom part
    flap_m = m + 3  # shifted right to show depth
    flap_top = 8
    p.setBrush(QBrush(color))
    p.drawRoundedRect(flap_m, flap_top, size - flap_m - m, size - m - flap_top, 1.0, 1.0)
    # Highlight line on front flap top edge (simulates open folder crease)
    p.setPen(QPen(QColor(255, 255, 255, 100), 1.0))
    p.drawLine(QPointF(flap_m + 1, flap_top + 0.5), QPointF(size - m - 1, flap_top + 0.5))
    p.end()
    return QIcon(pixmap)


def _generate_test_icon () -> QIcon:
    """Generate a Test icon: Erlenmeyer flask shape (experiment/test), blue."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = _COLOR_TEST
    p.setPen(QPen(color, 1.2))
    p.setBrush(QBrush(color))
    # Flask: narrow neck + wider conical body
    # Align bottom with Stop icon (margin=4 → bottom = size - 4)
    body_bottom = size - 4.0
    neck_w = 5.0
    body_w = 15.0
    body_h = 11.0
    neck_h = 5.0
    cx = size / 2.0
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
    # Liquid line inside the body
    p.setPen(QPen(color, 1.5))
    liquid_y = body_bottom - 4.0
    liquid_left = body_left + 2.5
    liquid_right = body_right - 2.5
    p.drawLine(QPointF(liquid_left, liquid_y), QPointF(liquid_right, liquid_y))
    p.end()
    return QIcon(pixmap)


def _generate_settings_icon () -> QIcon:
    """Generate a Settings icon: simple gear/cog shape."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = QApplication.palette().windowText().color()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    cx = cy = size / 2.0
    body_r = 5.5
    tooth_len = 3.5
    tooth_w = 3.5
    num_teeth = 6
    # Draw teeth as small rounded rectangles around the circle
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
    # Draw gear body (filled circle)
    p.setBrush(QBrush(color))
    p.drawEllipse(QPointF(cx, cy), body_r, body_r)
    # Draw center hole (small circle, transparent to show through)
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)
    p.end()
    return QIcon(pixmap)


def _generate_run_icon () -> QIcon:
    """Generate a Run icon: play triangle, green."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = _COLOR_RUN
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    # Play triangle pointing right, centered vertically
    margin = 3.0
    tri_top = margin
    tri_bottom = size - margin
    tri_left = margin
    tri_right = size - margin
    mid_y = (tri_top + tri_bottom) / 2.0
    polygon = QPolygonF([
        QPointF(tri_left, tri_top),
        QPointF(tri_right, mid_y),
        QPointF(tri_left, tri_bottom),
    ])
    p.drawPolygon(polygon)
    p.end()
    return QIcon(pixmap)


def _generate_stop_icon () -> QIcon:
    """Generate a Stop icon: filled square, red."""
    size = _ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    color = _COLOR_STOP
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))
    margin = 4
    p.drawRoundedRect(margin, margin, size - 2 * margin, size - 2 * margin, 2.0, 2.0)
    p.end()
    return QIcon(pixmap)


def _create_toolbar_icons () -> dict:
    """Create all toolbar icons as self-drawn, color-coded."""
    icons = {}
    icons['new'] = _generate_new_icon()
    icons['save'] = _generate_save_icon()
    icons['open'] = _generate_open_icon()
    icons['run'] = _generate_run_icon()
    icons['test'] = _generate_test_icon()
    icons['stop'] = _generate_stop_icon()
    icons['settings'] = _generate_settings_icon()
    return icons


#----------------------------------------------------------------------
# Settings
#----------------------------------------------------------------------
class Settings:

    compiler_path = 'g++'
    compiler_flags = '-std=c++14'
    env_vars = {}
    run_timeout = 10
    compile_timeout = 20
    editor_font_family = ''   # set by _init_font_defaults()
    editor_font_size = 11
    io_font_family = ''      # set by _init_font_defaults()
    io_font_size = 11
    bracket_completion = True
    template_text = (
        '#include <iostream>\n'
        '#include <cstdio>\n'
        'using namespace std;\n'
        'int main() {\n'
        '    return 0;\n'
        '}\n'
    )


#----------------------------------------------------------------------
# InputPanel
#----------------------------------------------------------------------
class InputPanel (QPlainTextEdit):

    def __init__ (self, parent:QWidget=None):
        super().__init__(parent)
        self.setTabStopWidth(self.fontMetrics().width('    '))


#----------------------------------------------------------------------
# OutputPanel
#----------------------------------------------------------------------
class OutputPanel (QTextEdit):

    def __init__ (self, parent:QWidget=None):
        super().__init__(parent)
        self.setReadOnly(True)


#----------------------------------------------------------------------
# MainWindow
#----------------------------------------------------------------------
class MainWindow (QMainWindow):

    def __init__ (self):
        super().__init__()
        self.setWindowTitle('CodeRunner')
        self.resize(1000, 650)

        # Center window on screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2 + geo.x()
            y = (geo.height() - self.height()) // 2 + geo.y()
            self.move(x, y)

        # Create icons
        self.icons = _create_toolbar_icons()

        # Create editor and IO panels
        self.editor = QPlainTextEdit()
        self.input_panel = InputPanel()
        self.output_panel = OutputPanel()

        # Save placeholder docs for zero-tab state
        self.empty_editor_doc = self.editor.document()
        self.empty_input_doc = self.input_panel.document()
        self.empty_output_doc = self.output_panel.document()

        # Build UI in correct order
        self.__build_menubar()
        self.__build_toolbar()
        self.__build_mainarea()
        self.__build_tabbar_and_layout()
        self.__build_statusbar()

        # Start in zero-tab state
        self._enter_zero_tab_state()

    def __build_menubar (self):
        menubar = self.menuBar()
        self.menu_file = menubar.addMenu('File')
        self.menu_edit = menubar.addMenu('Edit')
        self.menu_run = menubar.addMenu('Run')
        self.menu_view = menubar.addMenu('View')

    def __build_toolbar (self):
        toolbar = self.addToolBar('Main')
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))

        self.act_new = QAction(self.icons['new'], 'New', self)
        self.act_new.setShortcut(QKeySequence('Ctrl+N'))
        self.act_new.setToolTip('New (Ctrl+N)')
        toolbar.addAction(self.act_new)

        self.act_save = QAction(self.icons['save'], 'Save', self)
        self.act_save.setShortcut(QKeySequence('Ctrl+S'))
        self.act_save.setToolTip('Save (Ctrl+S)')
        toolbar.addAction(self.act_save)

        self.act_open = QAction(self.icons['open'], 'Open', self)
        self.act_open.setShortcut(QKeySequence('Ctrl+O'))
        self.act_open.setToolTip('Open (Ctrl+O)')
        toolbar.addAction(self.act_open)

        toolbar.addSeparator()

        self.act_run = QAction(self.icons['run'], 'Run', self)
        self.act_run.setShortcut(QKeySequence('F5'))
        self.act_run.setToolTip('Run (F5)')
        toolbar.addAction(self.act_run)

        self.act_test = QAction(self.icons['test'], 'Test', self)
        self.act_test.setShortcut(QKeySequence('F9'))
        self.act_test.setToolTip('Test (F9)')
        toolbar.addAction(self.act_test)

        self.act_stop = QAction(self.icons['stop'], 'Stop', self)
        self.act_stop.setShortcut(QKeySequence('F7'))
        self.act_stop.setToolTip('Stop (F7)')
        toolbar.addAction(self.act_stop)

        toolbar.addSeparator()

        self.act_settings = QAction(self.icons['settings'], 'Settings', self)
        self.act_settings.setToolTip('Settings')
        toolbar.addAction(self.act_settings)

    def __build_mainarea (self):
        # Wrap IO panels with label headers
        self.input_section = _make_io_section('INPUT', self.input_panel)
        self.output_section = _make_io_section('OUTPUT', self.output_panel)

        # Vertical splitter: InputSection (top) / OutputSection (bottom)
        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.addWidget(self.input_section)
        self.v_splitter.addWidget(self.output_section)
        self.v_splitter.setSizes([325, 325])

        # Horizontal splitter: CodeEditor (left) / v_splitter (right)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.editor)
        self.main_splitter.addWidget(self.v_splitter)
        self.main_splitter.setSizes([500, 500])

    def __build_tabbar_and_layout (self):
        self.tabbar = QTabBar(self)
        self.tabbar.setTabsClosable(True)
        self.tabbar.setMovable(True)

        # Central widget: tabbar on top, main_splitter below
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

    def _enter_zero_tab_state (self):
        self.editor.setDocument(self.empty_editor_doc)
        self.input_panel.setDocument(self.empty_input_doc)
        self.output_panel.setDocument(self.empty_output_doc)
        self.editor.setEnabled(False)
        self.input_section.setEnabled(False)
        self.output_section.setEnabled(False)
        self.status_info.setText('')

    def _exit_zero_tab_state (self):
        self.editor.setEnabled(True)
        self.input_section.setEnabled(True)
        self.output_section.setEnabled(True)


#----------------------------------------------------------------------
# Main entry
#----------------------------------------------------------------------
def main ():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    _init_font_defaults()
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()