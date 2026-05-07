#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase8.py - Phase 8 automated tests for CodeRunner
#
# Created by skywind on 2026/05/07
# Last Modified: 2026/05/07 22:00:00
#
#======================================================================
import sys
import os
import unittest

# Force offscreen platform so tests run without display
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor

# Ensure single QApplication instance
_app = QApplication.instance()
if _app is None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    _app = QApplication(sys.argv)
    _app.setStyle('Fusion')

# Add parent dir to path so we can import CodeRunner
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from CodeRunner import (
    Settings, TabData, MainWindow, _init_font_defaults, CodeEditor,
    _strip_trailing_whitespace
)


class TestCommentUncomment (unittest.TestCase):
    """Test Ctrl+/ comment/uncomment toggle logic."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def _make_editor_with_content (self, content:str) -> CodeEditor:
        editor = self.window.editor
        tab = TabData(
            content=content, dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        return editor

    def test_comment_single_line (self):
        """Comment a single uncommented line."""
        editor = self._make_editor_with_content('int x = 0;')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        self.assertIn('// int x = 0;', text)

    def test_uncomment_single_line (self):
        """Uncomment a single commented line."""
        editor = self._make_editor_with_content('// int x = 0;')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        self.assertEqual('int x = 0;', text.strip())

    def test_comment_preserves_indent (self):
        """Comment adds // before first non-whitespace."""
        editor = self._make_editor_with_content('    int x = 0;')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        self.assertIn('    // int x = 0;', text)

    def test_uncomment_preserves_indent (self):
        """Uncomment removes // after indent."""
        editor = self._make_editor_with_content('    // int x = 0;')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        self.assertIn('    int x = 0;', text)

    def test_uncomment_removes_all_spaces (self):
        """Uncomment removes // and all trailing spaces after it."""
        editor = self._make_editor_with_content('//  hello')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        self.assertEqual('hello', text)

    def test_uncomment_no_spaces (self):
        """Uncomment removes // without trailing space."""
        editor = self._make_editor_with_content('//hello')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        self.assertEqual('hello', text)
        self.assertEqual('hello', text.strip())

    def test_comment_empty_line (self):
        """Whitespace-only line is skipped by comment/uncomment."""
        editor = self._make_editor_with_content('   ')
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText()
        # Whitespace-only lines are not touched
        self.assertNotIn('//', text)

    def test_toggle_cycle (self):
        """Comment then uncomment returns to original."""
        original = 'int x = 0;'
        editor = self._make_editor_with_content(original)
        editor._handle_comment_uncomment()
        editor._handle_comment_uncomment()
        text = editor.document().toPlainText().strip()
        self.assertEqual(original, text)

    def tearDown (self):
        # Don't close window in offscreen mode to avoid segfault
        pass


class TestIndentUnindent (unittest.TestCase):
    """Test Tab/Shift+Tab multi-line indent/unindent."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def _make_editor_with_content (self, content:str) -> CodeEditor:
        editor = self.window.editor
        tab = TabData(
            content=content, dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        return editor

    def test_indent_selection_tab_mode (self):
        """Indent selected lines with tab mode."""
        editor = self._make_editor_with_content('line1\nline2\nline3')
        # Select all lines
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.setTextCursor(cursor)
        editor._handle_indent_selection()
        text = editor.document().toPlainText()
        self.assertEqual('\tline1\n\tline2\n\tline3', text)

    def test_unindent_selection (self):
        """Unindent lines that have tab prefix."""
        editor = self._make_editor_with_content('\tline1\n\tline2')
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.setTextCursor(cursor)
        editor._handle_unindent_selection()
        text = editor.document().toPlainText()
        self.assertEqual('line1\nline2', text)

    def test_unindent_partial_spaces (self):
        """Unindent lines with fewer spaces than indent_size."""
        editor = self._make_editor_with_content('  line1')
        editor.indent_style = 'space'
        editor.indent_size = 4
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.setTextCursor(cursor)
        editor._handle_unindent_selection()
        text = editor.document().toPlainText()
        # 2 spaces removed (all that's available)
        self.assertEqual('line1', text)

    def tearDown (self):
        # Don't close window in offscreen mode to avoid segfault
        pass


class TestDuplicateLine (unittest.TestCase):
    """Test Ctrl+D duplicate line."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def _make_editor_with_content (self, content:str) -> CodeEditor:
        editor = self.window.editor
        tab = TabData(
            content=content, dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        return editor

    def test_duplicate_single_line (self):
        """Duplicate current line without selection."""
        editor = self._make_editor_with_content('hello')
        # Position cursor on the line
        cursor = editor.textCursor()
        cursor.setPosition(0)
        editor.setTextCursor(cursor)
        editor._handle_duplicate_line()
        text = editor.document().toPlainText()
        self.assertEqual('hello\nhello', text)

    def tearDown (self):
        # Don't close window in offscreen mode to avoid segfault
        pass


class TestDeleteLine (unittest.TestCase):
    """Test Ctrl+Shift+K delete line."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def _make_editor_with_content (self, content:str) -> CodeEditor:
        editor = self.window.editor
        tab = TabData(
            content=content, dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        return editor

    def test_delete_single_line (self):
        """Delete current line."""
        editor = self._make_editor_with_content('line1\nline2\nline3')
        # Position cursor on line 2
        block = editor.document().findBlockByNumber(1)
        cursor = editor.textCursor()
        cursor.setPosition(block.position())
        editor.setTextCursor(cursor)
        editor._handle_delete_line()
        text = editor.document().toPlainText()
        self.assertEqual('line1\nline3', text)

    def tearDown (self):
        # Don't close window in offscreen mode to avoid segfault
        pass


class TestTrailingWhitespace (unittest.TestCase):
    """Test trailing whitespace cleanup on save."""

    def test_strip_trailing_spaces (self):
        """Remove trailing spaces from each line."""
        text = 'hello   \nworld  \n'
        result = _strip_trailing_whitespace(text)
        self.assertEqual('hello\nworld\n', result)

    def test_strip_trailing_tabs (self):
        """Remove trailing tabs from each line."""
        text = 'hello\t\nworld\t\t\n'
        result = _strip_trailing_whitespace(text)
        self.assertEqual('hello\nworld\n', result)

    def test_preserve_indent_spaces (self):
        """Keep leading spaces (indent)."""
        text = '    hello   \n'
        result = _strip_trailing_whitespace(text)
        self.assertEqual('    hello\n', result)

    def test_preserve_indent_tabs (self):
        """Keep leading tabs (indent)."""
        text = '\thello\t\n'
        result = _strip_trailing_whitespace(text)
        self.assertEqual('\thello\n', result)

    def test_empty_line (self):
        """Empty line with only spaces becomes truly empty."""
        text = '   \n'
        result = _strip_trailing_whitespace(text)
        self.assertEqual('\n', result)

    def test_last_line_no_newline (self):
        """Last line without newline is still stripped."""
        text = 'hello   '
        result = _strip_trailing_whitespace(text)
        self.assertEqual('hello', result)


if __name__ == '__main__':
    unittest.main()