#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase2.py - Phase 2 automated tests for CodeRunner
#
# Created by skywind on 2026/05/05
# Last Modified: 2026/05/05 00:00:00
#
#======================================================================
import sys
import os
import unittest
import tempfile

# Force offscreen platform so tests run without display
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextDocument, QTextCursor

# Ensure single QApplication instance
_app = QApplication.instance()
if _app is None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    _app = QApplication(sys.argv)
    _app.setStyle('Fusion')

# Add parent dir to path so we can import CodeRunner
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from CodeRunner import (
    Settings, TabData, TabManager, CppHighlighter,
    CodeEditor, InputPanel, OutputPanel, MainWindow,
    _init_font_defaults, _detect_encoding, _read_file
)


#----------------------------------------------------------------------
# TabData state logic
#----------------------------------------------------------------------
class TestTabData (unittest.TestCase):

    def test_new_tab_defaults (self):
        tab = TabData(is_new=True, encoding='UTF-8', content='')
        self.assertIsNone(tab.file_path)
        self.assertTrue(tab.is_new)
        self.assertTrue(tab.is_dirty)
        self.assertEqual(tab.encoding, 'UTF-8')
        self.assertEqual(tab.zoom_font_size, 0)
        self.assertEqual(tab.compiler_mtime, 0)

    def test_new_tab_with_template (self):
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=Settings.template_text)
        text = tab.editor_doc.toPlainText()
        self.assertEqual(text, Settings.template_text)
        self.assertTrue(tab.is_dirty)

    def test_opened_tab_defaults (self):
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='int main() {}')
        self.assertEqual(tab.file_path, '/tmp/test.cpp')
        self.assertFalse(tab.is_new)
        self.assertFalse(tab.is_dirty)
        self.assertEqual(tab.encoding, 'UTF-8')

    def tab_name_for (self, is_new, is_dirty, file_path=None,
                      untitled_number=1):
        tab = TabData(file_path=file_path, is_new=is_new,
                      encoding='UTF-8', content='')
        tab.is_dirty = is_dirty
        tab.untitled_number = untitled_number
        return tab.tab_name()

    def test_tab_name_new_dirty (self):
        name = self.tab_name_for(is_new=True, is_dirty=True)
        self.assertEqual(name, '*untitled1*')

    def test_tab_name_new_clean (self):
        name = self.tab_name_for(is_new=True, is_dirty=False)
        self.assertEqual(name, 'untitled1')

    def test_tab_name_saved_dirty (self):
        name = self.tab_name_for(is_new=False, is_dirty=True,
                                  file_path='/tmp/hello.cpp')
        self.assertEqual(name, '*hello.cpp*')

    def test_tab_name_saved_clean (self):
        name = self.tab_name_for(is_new=False, is_dirty=False,
                                  file_path='/tmp/hello.cpp')
        self.assertEqual(name, 'hello.cpp')

    def test_tab_name_untitled_number (self):
        name = self.tab_name_for(is_new=True, is_dirty=True,
                                  untitled_number=3)
        self.assertEqual(name, '*untitled3*')

    def test_tab_name_windows_path (self):
        name = self.tab_name_for(is_new=False, is_dirty=False,
                                  file_path='C:\\Users\\test\\main.cpp')
        self.assertEqual(name, 'main.cpp')

    def test_documents_are_independent (self):
        tab = TabData(is_new=True, content='hello')
        self.assertIsInstance(tab.editor_doc, QTextDocument)
        self.assertIsInstance(tab.input_doc, QTextDocument)
        self.assertIsInstance(tab.output_doc, QTextDocument)
        # Each doc is a separate instance
        self.assertIsNot(tab.editor_doc, tab.input_doc)
        self.assertIsNot(tab.editor_doc, tab.output_doc)

    def test_highlighter_attached (self):
        tab = TabData(is_new=True, content='')
        self.assertIsInstance(tab.highlighter, CppHighlighter)
        self.assertEqual(tab.highlighter.document(), tab.editor_doc)

    def test_dirty_callback_on_edit (self):
        changes = []
        def callback (t):
            changes.append(t)
        tab = TabData(is_new=False, encoding='UTF-8',
                      content='hello', dirty_callback=callback)
        # is_dirty starts False for opened tab
        self.assertFalse(tab.is_dirty)
        # Simulate edit: setModified(True)
        tab.editor_doc.setModified(True)
        self.assertTrue(tab.is_dirty)
        self.assertEqual(len(changes), 1)

    def test_dirty_callback_not_called_if_already_dirty (self):
        changes = []
        def callback (t):
            changes.append(t)
        tab = TabData(is_new=True, encoding='UTF-8',
                      content='hello', dirty_callback=callback)
        # is_dirty starts True for new tab
        self.assertTrue(tab.is_dirty)
        # Another modification: no transition, callback not called
        tab.editor_doc.setModified(True)
        self.assertEqual(len(changes), 0)

    def test_dirty_callback_on_set_modified_false (self):
        changes = []
        def callback (t):
            changes.append(t)
        tab = TabData(is_new=True, encoding='UTF-8',
                      content='hello', dirty_callback=callback)
        # Save: setModified(False) → is_dirty False
        tab.editor_doc.setModified(False)
        self.assertFalse(tab.is_dirty)
        self.assertEqual(len(changes), 1)

    def test_cursor_and_scroll_defaults (self):
        tab = TabData(is_new=True, content='')
        self.assertIsInstance(tab.cursor, QTextCursor)
        self.assertEqual(tab.scroll_pos, 0)
        self.assertEqual(tab.input_scroll, 0)


#----------------------------------------------------------------------
# Encoding detection
#----------------------------------------------------------------------
class TestEncodingDetection (unittest.TestCase):

    def test_utf8_bom (self):
        raw = b'\xef\xbb\xbfhello'
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_utf8_no_bom (self):
        raw = b'hello world'
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_utf8_chinese (self):
        raw = '你好世界'.encode('utf-8')
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_gbk_chinese (self):
        # GBK-encoded Chinese (not valid UTF-8)
        raw = '你好'.encode('gbk')
        # On Windows, should detect as 'gbk'
        if sys.platform == 'win32':
            self.assertEqual(_detect_encoding(raw), 'gbk')
        else:
            # On non-Windows, might still say utf-8 or system encoding
            enc = _detect_encoding(raw)
            self.assertTrue(enc in ('gbk', 'utf-8', 'latin-1'))

    def test_empty_file (self):
        raw = b''
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_mixed_invalid_bytes (self):
        # Bytes that are not valid UTF-8
        raw = b'\xff\xfe'
        if sys.platform == 'win32':
            self.assertEqual(_detect_encoding(raw), 'gbk')

    def test_read_file_utf8 (self):
        with tempfile.NamedTemporaryFile(
                mode='w', suffix='.cpp', encoding='utf-8',
                delete=False) as f:
            f.write('#include <iostream>\n')
            path = f.name
        try:
            content, encoding = _read_file(path)
            self.assertEqual(encoding, 'UTF-8')
            self.assertIn('#include <iostream>', content)
        finally:
            os.unlink(path)

    def test_read_file_utf8_bom (self):
        with tempfile.NamedTemporaryFile(
                mode='wb', suffix='.cpp', delete=False) as f:
            f.write(b'\xef\xbb\xbf#include <iostream>\n')
            path = f.name
        try:
            content, encoding = _read_file(path)
            self.assertEqual(encoding, 'UTF-8')
            self.assertIn('#include <iostream>', content)
            # BOM should be stripped
            self.assertFalse(content.startswith('﻿'))
        finally:
            os.unlink(path)

    def test_read_file_gbk (self):
        if sys.platform != 'win32':
            return  # GBK test only on Windows
        with tempfile.NamedTemporaryFile(
                mode='wb', suffix='.cpp', delete=False) as f:
            f.write('你好\n'.encode('gbk'))
            path = f.name
        try:
            content, encoding = _read_file(path)
            self.assertEqual(encoding, 'gbk')
            self.assertIn('你好', content)
        finally:
            os.unlink(path)


#----------------------------------------------------------------------
# CppHighlighter placeholder
#----------------------------------------------------------------------
class TestCppHighlighter (unittest.TestCase):

    def test_creation (self):
        doc = QTextDocument()
        hl = CppHighlighter(doc)
        self.assertEqual(hl.document(), doc)

    def test_highlightBlock_does_nothing (self):
        doc = QTextDocument()
        hl = CppHighlighter(doc)
        # Calling highlightBlock should not crash
        hl.highlightBlock('int main() {}')


#----------------------------------------------------------------------
# CodeEditor
#----------------------------------------------------------------------
class TestCodeEditor (unittest.TestCase):

    def test_creation (self):
        editor = CodeEditor()
        self.assertIsNotNone(editor)

    def test_tab_width_set (self):
        editor = CodeEditor()
        self.assertGreater(editor.tabStopWidth(), 0)


#----------------------------------------------------------------------
# TabManager basics
#----------------------------------------------------------------------
class TestTabManager (unittest.TestCase):

    def setUp (self):
        _init_font_defaults()
        self.window = MainWindow()

    def test_initial_state (self):
        tm = self.window.tab_manager
        self.assertEqual(len(tm.tabs), 0)
        self.assertEqual(tm.current_index, -1)
        self.assertEqual(tm.untitled_counter, 0)

    def test_add_tab_new (self):
        tm = self.window.tab_manager
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=Settings.template_text,
                      dirty_callback=self.window._on_tab_dirty_changed)
        index = tm.add_tab(tab)
        self.assertEqual(index, 0)
        self.assertEqual(len(tm.tabs), 1)
        self.assertEqual(tm.current_index, 0)
        self.assertEqual(tm.untitled_counter, 1)
        self.assertEqual(tab.untitled_number, 1)

    def test_add_multiple_tabs (self):
        tm = self.window.tab_manager
        tab1 = TabData(is_new=True, encoding='UTF-8',
                       content=Settings.template_text,
                       dirty_callback=self.window._on_tab_dirty_changed)
        tab2 = TabData(is_new=True, encoding='UTF-8',
                       content=Settings.template_text,
                       dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        self.assertEqual(tm.untitled_counter, 2)
        self.assertEqual(tab1.untitled_number, 1)
        self.assertEqual(tab2.untitled_number, 2)
        self.assertEqual(tm.current_index, 1)

    def test_get_current_none (self):
        tm = self.window.tab_manager
        self.assertIsNone(tm.get_current())

    def test_get_current_valid (self):
        tm = self.window.tab_manager
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=Settings.template_text,
                      dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab)
        self.assertEqual(tm.get_current(), tab)

    def test_switch_tab (self):
        tm = self.window.tab_manager
        tab1 = TabData(is_new=True, encoding='UTF-8',
                       content='content1',
                       dirty_callback=self.window._on_tab_dirty_changed)
        tab2 = TabData(is_new=True, encoding='UTF-8',
                       content='content2',
                       dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        # Current is tab2 (index 1)
        self.assertEqual(tm.current_index, 1)
        # Switch to tab1
        tm.switch_tab(0)
        self.assertEqual(tm.current_index, 0)
        # Editor should show tab1's content
        self.assertEqual(
            self.window.editor.document().toPlainText(),
            tab1.editor_doc.toPlainText())

    def test_close_tab_last (self):
        tm = self.window.tab_manager
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='',
                      dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab)
        result = tm.close_tab(0)
        self.assertTrue(result)
        self.assertEqual(len(tm.tabs), 0)
        self.assertEqual(tm.current_index, -1)
        self.assertFalse(self.window.editor.isEnabled())

    def test_close_tab_one_of_many (self):
        tm = self.window.tab_manager
        tab1 = TabData(file_path='/tmp/t1.cpp', is_new=False,
                       encoding='UTF-8', content='c1',
                       dirty_callback=self.window._on_tab_dirty_changed)
        tab2 = TabData(file_path='/tmp/t2.cpp', is_new=False,
                       encoding='UTF-8', content='c2',
                       dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        # Close tab1 (index 0)
        result = tm.close_tab(0)
        self.assertTrue(result)
        self.assertEqual(len(tm.tabs), 1)
        self.assertEqual(tm.current_index, 0)

    def test_tabbar_count_matches (self):
        tm = self.window.tab_manager
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=Settings.template_text,
                      dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab)
        self.assertEqual(self.window.tabbar.count(), 1)

    def test_exit_zero_tab_on_add (self):
        tm = self.window.tab_manager
        # Initially in zero-tab state
        self.assertFalse(self.window.editor.isEnabled())
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=Settings.template_text,
                      dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab)
        # Should be enabled now
        self.assertTrue(self.window.editor.isEnabled())


#----------------------------------------------------------------------
# Settings defaults (extended for Phase 2)
#----------------------------------------------------------------------
class TestSettingsPhase2 (unittest.TestCase):

    def test_defaults (self):
        _init_font_defaults()
        self.assertEqual(Settings.compiler_path, 'g++')
        self.assertEqual(Settings.compiler_flags, '-std=c++14')
        self.assertEqual(Settings.env_vars, {})
        self.assertEqual(Settings.run_timeout, 10)
        self.assertEqual(Settings.compile_timeout, 20)
        self.assertTrue(len(Settings.editor_font_family) > 0)
        self.assertEqual(Settings.editor_font_size, 11)
        self.assertTrue(len(Settings.io_font_family) > 0)
        self.assertEqual(Settings.io_font_size, 11)
        self.assertTrue(Settings.bracket_completion)

    def test_template_content (self):
        self.assertIn('#include <iostream>', Settings.template_text)
        self.assertIn('int main()', Settings.template_text)
        self.assertTrue(Settings.template_text.endswith('\n'))


if __name__ == '__main__':
    unittest.main()