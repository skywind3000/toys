#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# demo_codeeditor.py - Demo for CodeEditor library widget
#
# Created by skywind on 2026/05/07
# Last Modified: 2026/05/07 22:00:00
#
#======================================================================
import sys, os

# Import CodeEditor from library directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from CodeEditor import CodeEditor

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QMenuBar, QMenu
)
from PyQt5.QtGui import QFont


class DemoWindow (QMainWindow):

    def __init__ (self):
        super().__init__()
        self.setWindowTitle('CodeEditor Demo')
        self.resize(800, 600)

        # Create CodeEditor
        self.editor = CodeEditor()
        self.editor.createEditActions()
        self.setCentralWidget(self.editor)

        # Set a nice font
        font = QFont('Consolas', 11)
        self.editor.setFont(font)
        self.editor.updateFontMetrics()

        # Set sample C++ code
        self.editor.setPlainText(
            '#include <iostream>\n'
            '#include <vector>\n'
            'using namespace std;\n'
            '\n'
            'int main() {\n'
            '    vector<int> v = {1, 2, 3};\n'
            '    for (auto x : v) {\n'
            '        cout << x << endl;\n'
            '    }\n'
            '    return 0;\n'
            '}\n'
        )

        # Build menubar with editor actions
        menubar = self.menuBar()
        edit_menu = menubar.addMenu('Edit')

        # Standard actions
        edit_menu.addAction('Undo', self.editor.undo, 'Ctrl+Z')
        edit_menu.addAction('Redo', self.editor.redo, 'Ctrl+Y')
        edit_menu.addSeparator()
        edit_menu.addAction('Cut', self.editor.cut, 'Ctrl+X')
        edit_menu.addAction('Copy', self.editor.copy, 'Ctrl+C')
        edit_menu.addAction('Paste', self.editor.paste, 'Ctrl+V')
        edit_menu.addSeparator()

        # Edit extension actions from CodeEditor
        actions = self.editor.editActions()
        edit_menu.addAction(actions['act_comment'])
        edit_menu.addAction(actions['act_indent'])
        edit_menu.addAction(actions['act_unindent'])
        edit_menu.addAction(actions['act_duplicate'])
        edit_menu.addAction(actions['act_delete_line'])

        # Connect overwrite mode signal
        self.editor.overwriteModeChanged.connect(self._on_overwrite_changed)

        # Status bar shows cursor position
        self.statusBar().showMessage('Ready')

    def _on_overwrite_changed (self, overwrite):
        mode = 'OVR' if overwrite else 'INS'
        self.statusBar().showMessage('Mode: {}'.format(mode))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = DemoWindow()
    win.show()
    sys.exit(app.exec_())