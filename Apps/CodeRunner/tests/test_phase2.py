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
from unittest.mock import patch

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
    _init_font_defaults, _read_file,
    _window_state_path
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
        s = Settings()
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=s.template_text)
        text = tab.editor_doc.toPlainText()
        self.assertEqual(text, s.template_text)
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
        self.assertIsNot(tab.editor_doc, tab.input_doc)
        self.assertIsNot(tab.editor_doc, tab.output_doc)

    def test_highlighter_created (self):
        tab = TabData(is_new=True, content='')
        self.assertIsInstance(tab.highlighter, CppHighlighter)
        # Highlighter is now attached to editor_doc (Phase 4)
        self.assertIs(tab.highlighter.document(), tab.editor_doc)

    def test_dirty_callback_on_edit (self):
        changes = []
        def callback (t):
            changes.append(t)
        tab = TabData(is_new=False, encoding='UTF-8',
                      content='hello', dirty_callback=callback)
        self.assertFalse(tab.is_dirty)
        tab.editor_doc.setModified(True)
        self.assertTrue(tab.is_dirty)
        self.assertEqual(len(changes), 1)

    def test_dirty_callback_not_called_if_already_dirty (self):
        changes = []
        def callback (t):
            changes.append(t)
        tab = TabData(is_new=True, encoding='UTF-8',
                      content='hello', dirty_callback=callback)
        self.assertTrue(tab.is_dirty)
        tab.editor_doc.setModified(True)
        self.assertEqual(len(changes), 0)

    def test_dirty_callback_on_set_modified_false (self):
        changes = []
        def callback (t):
            changes.append(t)
        tab = TabData(is_new=True, encoding='UTF-8',
                      content='hello', dirty_callback=callback)
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

    def _write_and_read (self, raw_bytes):
        """Write raw bytes to a temp file, read back with _read_file,
        return (content, encoding)."""
        with tempfile.NamedTemporaryFile(
                mode='wb', suffix='.cpp', delete=False) as f:
            f.write(raw_bytes)
            path = f.name
        try:
            return _read_file(path)
        finally:
            os.unlink(path)

    def test_utf8_bom (self):
        _, enc = self._write_and_read(b'\xef\xbb\xbfhello')
        self.assertEqual(enc, 'UTF-8')

    def test_utf8_no_bom (self):
        _, enc = self._write_and_read(b'hello world')
        self.assertEqual(enc, 'UTF-8')

    def test_utf8_chinese (self):
        _, enc = self._write_and_read('你好世界'.encode('utf-8'))
        self.assertEqual(enc, 'UTF-8')

    def test_gbk_chinese (self):
        _, enc = self._write_and_read('你好'.encode('gbk'))
        if sys.platform == 'win32':
            self.assertEqual(enc, 'gbk')
        else:
            self.assertTrue(enc in ('gbk', 'utf-8', 'latin-1'))

    def test_empty_file (self):
        _, enc = self._write_and_read(b'')
        self.assertEqual(enc, 'UTF-8')

    def test_mixed_invalid_bytes (self):
        _, enc = self._write_and_read(b'\xff\xfe')
        if sys.platform == 'win32':
            self.assertEqual(enc, 'gbk')

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
            self.assertFalse(content.startswith('﻿'))
        finally:
            os.unlink(path)

    def test_read_file_gbk (self):
        if sys.platform != 'win32':
            return
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
# TabManager (pure data)
#----------------------------------------------------------------------
class TestTabManager (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_initial_state (self):
        tm = self.window.tab_manager
        self.assertEqual(len(tm.tabs), 0)
        self.assertEqual(tm.current_index, -1)
        self.assertEqual(tm.untitled_counter, 0)

    def test_add_tab_new (self):
        tm = self.window.tab_manager
        s = self.window.settings
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=s.template_text,
                      dirty_callback=self.window._on_tab_dirty_changed)
        index = tm.add_tab(tab)
        self.assertEqual(index, 0)
        self.assertEqual(len(tm.tabs), 1)
        self.assertEqual(tm.untitled_counter, 1)
        self.assertEqual(tab.untitled_number, 1)

    def test_add_multiple_tabs (self):
        tm = self.window.tab_manager
        s = self.window.settings
        tab1 = TabData(is_new=True, encoding='UTF-8',
                       content=s.template_text,
                       dirty_callback=self.window._on_tab_dirty_changed)
        tab2 = TabData(is_new=True, encoding='UTF-8',
                       content=s.template_text,
                       dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        self.assertEqual(tm.untitled_counter, 2)
        self.assertEqual(tab1.untitled_number, 1)
        self.assertEqual(tab2.untitled_number, 2)

    def test_get_current_none (self):
        tm = self.window.tab_manager
        self.assertIsNone(tm.get_current())

    def test_get_current_valid (self):
        tm = self.window.tab_manager
        s = self.window.settings
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=s.template_text,
                      dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab)
        tm.current_index = 0
        self.assertEqual(tm.get_current(), tab)

    def test_find_tab_index (self):
        tm = self.window.tab_manager
        s = self.window.settings
        tab1 = TabData(is_new=True, encoding='UTF-8',
                       content='c1',
                       dirty_callback=self.window._on_tab_dirty_changed)
        tab2 = TabData(is_new=True, encoding='UTF-8',
                       content='c2',
                       dirty_callback=self.window._on_tab_dirty_changed)
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        self.assertEqual(tm.find_tab_index(tab1), 0)
        self.assertEqual(tm.find_tab_index(tab2), 1)

    def test_remove_tab (self):
        tm = self.window.tab_manager
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='')
        tm.add_tab(tab)
        removed = tm.remove_tab(0)
        self.assertEqual(removed, tab)
        self.assertEqual(len(tm.tabs), 0)

    def test_reorder_tabs (self):
        tm = self.window.tab_manager
        tab1 = TabData(file_path='/tmp/a.cpp', is_new=False,
                       encoding='UTF-8', content='a')
        tab2 = TabData(file_path='/tmp/b.cpp', is_new=False,
                       encoding='UTF-8', content='b')
        tab3 = TabData(file_path='/tmp/c.cpp', is_new=False,
                       encoding='UTF-8', content='c')
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        tm.add_tab(tab3)
        tm.reorder_tabs(0, 2)
        self.assertEqual(tm.tabs[0], tab2)
        self.assertEqual(tm.tabs[1], tab3)
        self.assertEqual(tm.tabs[2], tab1)

    def test_no_main_window_attribute (self):
        tm = self.window.tab_manager
        self.assertFalse(hasattr(tm, 'main_window'))


#----------------------------------------------------------------------
# Settings defaults (Phase 2)
#----------------------------------------------------------------------
class TestSettingsPhase2 (unittest.TestCase):

    def test_defaults (self):
        s = Settings()
        _init_font_defaults(s)
        self.assertEqual(s.compiler_path, 'gcc')
        self.assertEqual(s.compiler_flags, '')
        self.assertEqual(s.env_vars, {})
        self.assertEqual(s.run_timeout, 10)
        self.assertEqual(s.compile_timeout, 20)
        self.assertTrue(len(s.editor_font_family) > 0)
        self.assertEqual(s.editor_font_size, 11)
        self.assertTrue(len(s.io_font_family) > 0)
        self.assertEqual(s.io_font_size, 11)
        self.assertTrue(s.bracket_completion)

    def test_template_content (self):
        s = Settings()
        self.assertIn('#include <iostream>', s.template_text)
        self.assertIn('int main()', s.template_text)
        self.assertTrue(s.template_text.endswith('\n'))


#----------------------------------------------------------------------
# MainWindow tab operations (migrated from TabManager)
#----------------------------------------------------------------------
class TestMainWindowTabOps (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_switch_to_tab (self):
        w = self.window
        s = w.settings
        tab1 = TabData(is_new=True, encoding='UTF-8',
                       content='content1',
                       dirty_callback=w._on_tab_dirty_changed)
        tab2 = TabData(is_new=True, encoding='UTF-8',
                       content='content2',
                       dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab1)
        w.tabbar.addTab(tab1.tab_name())
        w.tab_manager.add_tab(tab2)
        w.tabbar.addTab(tab2.tab_name())
        w._switch_to_tab(1)
        self.assertEqual(w.tab_manager.current_index, 1)
        w._switch_to_tab(0)
        self.assertEqual(w.tab_manager.current_index, 0)
        self.assertEqual(
            w.editor.document().toPlainText(),
            tab1.editor_doc.toPlainText())

    def test_handle_close_tab_last (self):
        w = self.window
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        result = w._handle_close_tab(0)
        self.assertTrue(result)
        self.assertEqual(len(w.tab_manager.tabs), 0)
        self.assertEqual(w.tab_manager.current_index, -1)
        self.assertFalse(w.editor.isEnabled())

    def test_handle_close_tab_one_of_many (self):
        w = self.window
        tab1 = TabData(file_path='/tmp/t1.cpp', is_new=False,
                       encoding='UTF-8', content='c1',
                       dirty_callback=w._on_tab_dirty_changed)
        tab2 = TabData(file_path='/tmp/t2.cpp', is_new=False,
                       encoding='UTF-8', content='c2',
                       dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab1)
        w.tabbar.addTab(tab1.tab_name())
        w.tab_manager.add_tab(tab2)
        w.tabbar.addTab(tab2.tab_name())
        w._switch_to_tab(1)
        result = w._handle_close_tab(0)
        self.assertTrue(result)
        self.assertEqual(len(w.tab_manager.tabs), 1)
        self.assertEqual(w.tab_manager.current_index, 0)

    def test_tabbar_count_matches (self):
        w = self.window
        s = w.settings
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=s.template_text,
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        self.assertEqual(w.tabbar.count(), 1)

    def test_exit_zero_tab_on_add (self):
        w = self.window
        self.assertFalse(w.editor.isEnabled())
        s = w.settings
        tab = TabData(is_new=True, encoding='UTF-8',
                      content=s.template_text,
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        self.assertTrue(w.editor.isEnabled())


#----------------------------------------------------------------------
# Mock event for closeEvent testing
#----------------------------------------------------------------------
class _MockCloseEvent:
    """Mock QCloseEvent for testing closeEvent without Qt event system."""
    def __init__ (self):
        self._accepted = False

    def accept (self):
        self._accepted = True

    def ignore (self):
        self._accepted = False

    def isAccepted (self):
        return self._accepted


#----------------------------------------------------------------------
# P0: close_tab state corruption fix
#----------------------------------------------------------------------
class TestCloseTabStateFix (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_close_current_tab_preserves_remaining_state (self):
        w = self.window
        tab_a = TabData(file_path='/tmp/a.cpp', is_new=False,
                        encoding='UTF-8', content='aaa\nbbb\nccc\n',
                        dirty_callback=w._on_tab_dirty_changed)
        tab_c = TabData(file_path='/tmp/c.cpp', is_new=False,
                        encoding='UTF-8', content='line1\nline2\nline3\n',
                        dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab_a)
        w.tabbar.addTab(tab_a.tab_name())
        w.tab_manager.add_tab(tab_c)
        w.tabbar.addTab(tab_c.tab_name())
        w._switch_to_tab(1)
        cursor = w.editor.textCursor()
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, 2)
        w.editor.setTextCursor(cursor)
        w._switch_to_tab(0)
        cursor = w.editor.textCursor()
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, 1)
        w.editor.setTextCursor(cursor)
        c_cursor_pos_before = tab_c.cursor.position()
        w._handle_close_tab(0)
        self.assertEqual(tab_c.cursor.position(), c_cursor_pos_before)

    def test_close_non_current_tab_saves_current_state (self):
        w = self.window
        tab_a = TabData(file_path='/tmp/a.cpp', is_new=False,
                        encoding='UTF-8', content='aaa\nbbb\n',
                        dirty_callback=w._on_tab_dirty_changed)
        tab_b = TabData(file_path='/tmp/b.cpp', is_new=False,
                        encoding='UTF-8', content='xxx\nyyy\nzzz\n',
                        dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab_a)
        w.tabbar.addTab(tab_a.tab_name())
        w.tab_manager.add_tab(tab_b)
        w.tabbar.addTab(tab_b.tab_name())
        w._switch_to_tab(1)
        cursor = w.editor.textCursor()
        cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, 2)
        w.editor.setTextCursor(cursor)
        expected_pos = w.editor.textCursor().position()
        w._handle_close_tab(0)
        self.assertEqual(tab_b.cursor.position(), expected_pos)


#----------------------------------------------------------------------
# P1: closeEvent signal disconnect
#----------------------------------------------------------------------
class TestCloseEventSignalDisconnect (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_close_event_disconnects_all_signals (self):
        w = self.window
        tab1 = TabData(file_path='/tmp/t1.cpp', is_new=False,
                       encoding='UTF-8', content='c1',
                       dirty_callback=w._on_tab_dirty_changed)
        tab2 = TabData(file_path='/tmp/t2.cpp', is_new=False,
                       encoding='UTF-8', content='c2',
                       dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab1)
        w.tabbar.addTab(tab1.tab_name())
        w.tab_manager.add_tab(tab2)
        w.tabbar.addTab(tab2.tab_name())
        w._switch_to_tab(0)
        event = _MockCloseEvent()
        w.closeEvent(event)
        self.assertTrue(event.isAccepted())
        for tab in w.tab_manager.tabs:
            with self.assertRaises(TypeError):
                tab.editor_doc.modificationChanged.disconnect(
                    tab._on_modified_changed)


#----------------------------------------------------------------------
# P1: Save As delegation to _save_tab_data
#----------------------------------------------------------------------
class TestSaveAsDelegation (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_save_as_delegates_to_save (self):
        w = self.window
        tab = TabData(is_new=True, encoding='UTF-8',
                      content='test content',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        with tempfile.NamedTemporaryFile(
                suffix='.cpp', delete=False) as f:
            save_path = f.name
        try:
            with patch('CodeRunner.QFileDialog.getSaveFileName',
                       return_value=(save_path, '')):
                w._action_save_as()
            with open(save_path, 'r', encoding='UTF-8') as f:
                self.assertEqual(f.read(), 'test content')
            self.assertFalse(tab.is_new)
            self.assertEqual(tab.file_path, save_path)
            self.assertFalse(tab.is_dirty)
        finally:
            os.unlink(save_path)

    def test_save_as_rollback_on_write_failure (self):
        w = self.window
        tab = TabData(is_new=True, encoding='UTF-8', content='test',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        old_path = tab.file_path
        old_is_new = tab.is_new
        bad_path = os.path.join(tempfile.gettempdir(),
                                'nonexistent_dir_42', 'test.cpp')
        with patch('CodeRunner.QFileDialog.getSaveFileName',
                   return_value=(bad_path, '')):
            with patch('CodeRunner.QMessageBox.warning'):
                w._action_save_as()
        self.assertEqual(tab.file_path, old_path)
        self.assertEqual(tab.is_new, old_is_new)


if __name__ == '__main__':
    unittest.main()