#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase3.py - Phase 3 automated tests for CodeRunner
#
# Created by skywind on 2026/05/05
# Last Modified: 2026/05/05 00:00:00
#
#======================================================================
import sys
import os
import unittest
import copy

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
    Settings, _SETTINGS_DEFAULTS, TabData, TabManager,
    CodeEditor, MainWindow, _init_font_defaults,
    _dpi_factor, _ICON_BASE, _create_toolbar_icons,
    _read_file, _window_state_path
)


#----------------------------------------------------------------------
# Settings instance-based (Fix 2)
#----------------------------------------------------------------------
class TestSettingsInstance (unittest.TestCase):

    def test_defaults_from_dict (self):
        s = Settings()
        for key, value in _SETTINGS_DEFAULTS.items():
            self.assertEqual(getattr(s, key), value,
                             f'Default mismatch for {key}')

    def test_instance_attributes (self):
        s = Settings()
        self.assertTrue(hasattr(s, 'compiler_path'))
        self.assertTrue(hasattr(s, 'editor_font_family'))
        self.assertTrue(hasattr(s, 'template_text'))

    def test_independent_instances (self):
        s1 = Settings()
        s2 = Settings()
        s1.compiler_path = 'clang++'
        self.assertEqual(s1.compiler_path, 'clang++')
        self.assertEqual(s2.compiler_path, 'gcc')

    def test_copy_creates_independent_instance (self):
        s = Settings()
        _init_font_defaults(s)
        s2 = s.copy()
        self.assertIsInstance(s2, Settings)
        # Same values initially
        self.assertEqual(s.compiler_path, s2.compiler_path)
        self.assertEqual(s.editor_font_family, s2.editor_font_family)
        # Modify copy — original unaffected
        s2.compiler_path = 'clang++'
        s2.editor_font_size = 14
        self.assertEqual(s.compiler_path, 'gcc')
        self.assertEqual(s.editor_font_size, 11)

    def test_copy_deep_copies_env_vars (self):
        s = Settings()
        s.env_vars = {'PATH': '/usr/bin', 'HOME': '/home'}
        s2 = s.copy()
        s2.env_vars['PATH'] = '/changed'
        self.assertEqual(s.env_vars['PATH'], '/usr/bin')

    def test_apply_from_merges_changes (self):
        s = Settings()
        _init_font_defaults(s)
        s2 = s.copy()
        s2.compiler_path = 'clang++'
        s2.run_timeout = 30
        s.apply_from(s2)
        self.assertEqual(s.compiler_path, 'clang++')
        self.assertEqual(s.run_timeout, 30)
        # Other values also copied
        self.assertEqual(s.editor_font_family, s2.editor_font_family)

    def test_custom_defaults (self):
        custom = copy.deepcopy(_SETTINGS_DEFAULTS)
        custom['compiler_path'] = 'clang++'
        custom['editor_font_size'] = 14
        s = Settings(custom)
        self.assertEqual(s.compiler_path, 'clang++')
        self.assertEqual(s.editor_font_size, 14)
        # Non-customized values use custom dict
        self.assertEqual(s.compiler_flags, '')

    def test_init_font_defaults_modifies_instance (self):
        s = Settings()
        _init_font_defaults(s)
        self.assertTrue(len(s.editor_font_family) > 0)
        self.assertTrue(len(s.io_font_family) > 0)


#----------------------------------------------------------------------
# TabManager pure data (Fix 3)
#----------------------------------------------------------------------
class TestTabManagerPureData (unittest.TestCase):

    def test_no_main_window_reference (self):
        tm = TabManager()
        self.assertFalse(hasattr(tm, 'main_window'))

    def test_initial_state (self):
        tm = TabManager()
        self.assertEqual(len(tm.tabs), 0)
        self.assertEqual(tm.current_index, -1)
        self.assertEqual(tm.untitled_counter, 0)

    def test_add_tab_assigns_untitled_number (self):
        tm = TabManager()
        tab1 = TabData(is_new=True, content='a')
        tab2 = TabData(is_new=True, content='b')
        idx1 = tm.add_tab(tab1)
        idx2 = tm.add_tab(tab2)
        self.assertEqual(idx1, 0)
        self.assertEqual(idx2, 1)
        self.assertEqual(tab1.untitled_number, 1)
        self.assertEqual(tab2.untitled_number, 2)
        self.assertEqual(tm.untitled_counter, 2)

    def test_add_tab_non_new_no_counter (self):
        tm = TabManager()
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      content='hello')
        idx = tm.add_tab(tab)
        self.assertEqual(idx, 0)
        self.assertEqual(tm.untitled_counter, 0)
        self.assertEqual(tab.untitled_number, 0)

    def test_remove_tab (self):
        tm = TabManager()
        tab = TabData(file_path='/tmp/x.cpp', is_new=False, content='x')
        tm.add_tab(tab)
        removed = tm.remove_tab(0)
        self.assertIs(removed, tab)
        self.assertEqual(len(tm.tabs), 0)

    def test_remove_tab_out_of_range (self):
        tm = TabManager()
        with self.assertRaises(IndexError):
            tm.remove_tab(0)

    def test_reorder_tabs (self):
        tm = TabManager()
        tabs = [TabData(file_path='/tmp/a.cpp', is_new=False, content='a'),
                TabData(file_path='/tmp/b.cpp', is_new=False, content='b'),
                TabData(file_path='/tmp/c.cpp', is_new=False, content='c')]
        for t in tabs:
            tm.add_tab(t)
        tm.reorder_tabs(0, 2)
        self.assertEqual(tm.tabs[0], tabs[1])
        self.assertEqual(tm.tabs[1], tabs[2])
        self.assertEqual(tm.tabs[2], tabs[0])

    def test_find_tab_index (self):
        tm = TabManager()
        tab1 = TabData(is_new=True, content='a')
        tab2 = TabData(is_new=True, content='b')
        tm.add_tab(tab1)
        tm.add_tab(tab2)
        self.assertEqual(tm.find_tab_index(tab1), 0)
        self.assertEqual(tm.find_tab_index(tab2), 1)
        self.assertEqual(tm.find_tab_index(TabData()), -1)

    def test_get_tab_name (self):
        tm = TabManager()
        tab = TabData(file_path='/tmp/hello.cpp', is_new=False, content='')
        tm.add_tab(tab)
        self.assertEqual(tm.get_tab_name(0), 'hello.cpp')
        self.assertEqual(tm.get_tab_name(1), '')
        self.assertEqual(tm.get_tab_name(-1), '')

    def test_get_current_none (self):
        tm = TabManager()
        self.assertIsNone(tm.get_current())

    def test_get_current_valid (self):
        tm = TabManager()
        tab = TabData(is_new=True, content='')
        tm.add_tab(tab)
        tm.current_index = 0
        self.assertIs(tm.get_current(), tab)

    def test_get_current_out_of_range (self):
        tm = TabManager()
        tm.current_index = 5
        self.assertIsNone(tm.get_current())


#----------------------------------------------------------------------
# MainWindow tab operations (Fix 3 migration)
#----------------------------------------------------------------------
class TestMainWindowTabOps (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_switch_to_tab_updates_document (self):
        w = self.window
        tab1 = TabData(is_new=True, encoding='UTF-8', content='doc1',
                       dirty_callback=w._on_tab_dirty_changed)
        tab2 = TabData(is_new=True, encoding='UTF-8', content='doc2',
                       dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab1)
        w.tabbar.addTab(tab1.tab_name())
        w.tab_manager.add_tab(tab2)
        w.tabbar.addTab(tab2.tab_name())
        w._switch_to_tab(0)
        self.assertIn('doc1',
                      w.editor.document().toPlainText())
        w._switch_to_tab(1)
        self.assertIn('doc2',
                      w.editor.document().toPlainText())

    def test_handle_close_tab_clean (self):
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

    def test_handle_close_tab_returns_false_invalid (self):
        w = self.window
        result = w._handle_close_tab(-1)
        self.assertFalse(result)
        result = w._handle_close_tab(99)
        self.assertFalse(result)

    def test_update_tab_name (self):
        w = self.window
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab('old_name')
        w._switch_to_tab(0)
        w._update_tab_name(0)
        self.assertEqual(w.tabbar.tabText(0), 'test.cpp')

    def test_update_all_tab_names (self):
        w = self.window
        tab1 = TabData(file_path='/tmp/a.cpp', is_new=False,
                       encoding='UTF-8', content='',
                       dirty_callback=w._on_tab_dirty_changed)
        tab2 = TabData(file_path='/tmp/b.cpp', is_new=False,
                       encoding='UTF-8', content='',
                       dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab1)
        w.tabbar.addTab('x')
        w.tab_manager.add_tab(tab2)
        w.tabbar.addTab('y')
        w._switch_to_tab(0)
        w._update_all_tab_names()
        self.assertEqual(w.tabbar.tabText(0), 'a.cpp')
        self.assertEqual(w.tabbar.tabText(1), 'b.cpp')

    def test_update_status_info (self):
        w = self.window
        tab = TabData(is_new=True, encoding='UTF-8', content='',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        w._update_status_info(tab)
        text = w.status_info.text()
        self.assertIn('UTF-8', text)
        self.assertIn('INS', text)

    def test_on_tab_dirty_changed (self):
        w = self.window
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        # Make tab dirty
        tab.editor_doc.setModified(True)
        w._on_tab_dirty_changed(tab)
        self.assertEqual(w.tabbar.tabText(0), '*test.cpp*')

    def test_settings_reference (self):
        w = self.window
        self.assertIsInstance(w.settings, Settings)
        self.assertTrue(len(w.settings.compiler_path) > 0)


#----------------------------------------------------------------------
# CodeEditor line number optimization (Fix 1)
#----------------------------------------------------------------------
class TestCodeEditorLineNumbers (unittest.TestCase):

    def test_estimate_first_visible_block_at_top (self):
        editor = CodeEditor()
        # At scroll position 0, estimate should be 0
        self.assertEqual(editor._estimate_first_visible_block(), 0)

    def test_estimate_first_visible_block_with_content (self):
        editor = CodeEditor()
        # Create a document with many lines
        doc = QTextDocument()
        lines = ['line {}\n'.format(i) for i in range(100)]
        doc.setPlainText(''.join(lines))
        editor.setDocument(doc)
        # At top, estimate is 0
        est = editor._estimate_first_visible_block()
        self.assertEqual(est, 0)

    def test_estimate_returns_non_negative (self):
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('line\n' * 50)
        editor.setDocument(doc)
        est = editor._estimate_first_visible_block()
        self.assertGreaterEqual(est, 0)

    def test_estimate_with_empty_doc (self):
        editor = CodeEditor()
        est = editor._estimate_first_visible_block()
        self.assertEqual(est, 0)

    def test_paint_line_numbers_no_crash (self):
        editor = CodeEditor()
        doc = QTextDocument()
        content = ''.join('line {}\n'.format(i) for i in range(20))
        doc.setPlainText(content)
        editor.setDocument(doc)
        editor.show()
        # Trigger a repaint — should not crash
        editor.line_number_area.update()
        editor.line_number_area.repaint()

    def test_paint_line_numbers_large_doc_no_crash (self):
        editor = CodeEditor()
        doc = QTextDocument()
        content = ''.join('line {}\n'.format(i) for i in range(5000))
        doc.setPlainText(content)
        editor.setDocument(doc)
        editor.show()
        editor.line_number_area.update()
        editor.line_number_area.repaint()


#----------------------------------------------------------------------
# DPI factor (Fix 6)
#----------------------------------------------------------------------
class TestDPIFactor (unittest.TestCase):

    def test_dpi_factor_is_positive (self):
        factor = _dpi_factor()
        self.assertGreater(factor, 0)

    def test_dpi_factor_at_least_one (self):
        factor = _dpi_factor()
        self.assertGreaterEqual(factor, 1.0)

    def test_icon_base_is_24 (self):
        self.assertEqual(_ICON_BASE, 24)

    def test_toolbar_icons_have_device_pixel_ratio (self):
        icons = _create_toolbar_icons()
        for name, icon in icons.items():
            self.assertFalse(icon.isNull(), f'{name} icon is null')
            # Icon pixmaps should be available at multiple sizes
            sizes = icon.availableSizes()
            self.assertGreater(len(sizes), 0,
                               f'{name} icon has no available sizes')


#----------------------------------------------------------------------
# Integration: MainWindow with all fixes
#----------------------------------------------------------------------
class TestMainWindowIntegration (unittest.TestCase):

    def setUp (self):
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        self.window = MainWindow()

    def test_new_tab_uses_settings_template (self):
        w = self.window
        w._action_new()
        tab = w.tab_manager.get_current()
        self.assertIsNotNone(tab)
        self.assertEqual(
            tab.editor_doc.toPlainText(),
            w.settings.template_text)

    def test_zoom_uses_settings_font_size (self):
        w = self.window
        w._action_new()
        tab = w.tab_manager.get_current()
        self.assertIsNotNone(tab)
        base = w.settings.editor_font_size
        w._action_zoom_in()
        self.assertEqual(tab.zoom_font_size, 1)
        zoom_size = max(6, base + 1)
        self.assertEqual(w.editor.font().pointSize(), zoom_size)

    def test_close_last_tab_enters_zero_state (self):
        w = self.window
        tab = TabData(file_path='/tmp/test.cpp', is_new=False,
                      encoding='UTF-8', content='hello',
                      dirty_callback=w._on_tab_dirty_changed)
        w.tab_manager.add_tab(tab)
        w.tabbar.addTab(tab.tab_name())
        w._switch_to_tab(0)
        w._handle_close_tab(0)
        self.assertEqual(w.tab_manager.current_index, -1)
        self.assertFalse(w.editor.isEnabled())

    def test_new_tab_enables_editor (self):
        w = self.window
        self.assertFalse(w.editor.isEnabled())
        w._action_new()
        self.assertTrue(w.editor.isEnabled())


if __name__ == '__main__':
    unittest.main()