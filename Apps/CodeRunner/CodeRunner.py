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
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QTabBar, QSplitter,
    QPlainTextEdit, QTextEdit, QLabel, QWidget, QAction,
    QVBoxLayout
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QKeySequence


#----------------------------------------------------------------------
# Settings
#----------------------------------------------------------------------
class Settings:

    compiler_path = 'g++'
    compiler_flags = '-std=c++14'
    env_vars = {}
    run_timeout = 10
    compile_timeout = 20
    editor_font_family = 'Consolas'
    editor_font_size = 11
    io_font_family = 'Consolas'
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

        # Create editor and IO panels
        self.editor = QPlainTextEdit()
        self.input_panel = InputPanel()
        self.output_panel = OutputPanel()

        # Save placeholder docs for zero-tab state
        self.empty_editor_doc = self.editor.document()
        self.empty_input_doc = self.input_panel.document()
        self.empty_output_doc = self.output_panel.document()

        # Build UI in correct order: splitters -> tabbar -> layout -> menu/toolbar/status
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

        self.act_new = QAction('New', self)
        self.act_new.setShortcut(QKeySequence('Ctrl+N'))
        self.act_new.setToolTip('New (Ctrl+N)')
        toolbar.addAction(self.act_new)

        self.act_save = QAction('Save', self)
        self.act_save.setShortcut(QKeySequence('Ctrl+S'))
        self.act_save.setToolTip('Save (Ctrl+S)')
        toolbar.addAction(self.act_save)

        self.act_open = QAction('Open', self)
        self.act_open.setShortcut(QKeySequence('Ctrl+O'))
        self.act_open.setToolTip('Open (Ctrl+O)')
        toolbar.addAction(self.act_open)

        toolbar.addSeparator()

        self.act_run = QAction('Run', self)
        self.act_run.setShortcut(QKeySequence('F5'))
        self.act_run.setToolTip('Run (F5)')
        toolbar.addAction(self.act_run)

        self.act_test = QAction('Test', self)
        self.act_test.setShortcut(QKeySequence('F9'))
        self.act_test.setToolTip('Test (F9)')
        toolbar.addAction(self.act_test)

        self.act_stop = QAction('Stop', self)
        self.act_stop.setShortcut(QKeySequence('F7'))
        self.act_stop.setToolTip('Stop (F7)')
        toolbar.addAction(self.act_stop)

        toolbar.addSeparator()

        self.act_settings = QAction('Settings', self)
        self.act_settings.setToolTip('Settings')
        toolbar.addAction(self.act_settings)

    def __build_mainarea (self):
        # Vertical splitter: InputPanel (top) / OutputPanel (bottom)
        self.v_splitter = QSplitter(Qt.Vertical)
        self.v_splitter.addWidget(self.input_panel)
        self.v_splitter.addWidget(self.output_panel)
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
        self.input_panel.setEnabled(False)
        self.output_panel.setEnabled(False)
        self.status_info.setText('')

    def _exit_zero_tab_state (self):
        self.editor.setEnabled(True)
        self.input_panel.setEnabled(True)
        self.output_panel.setEnabled(True)


#----------------------------------------------------------------------
# Main entry
#----------------------------------------------------------------------
def main ():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()