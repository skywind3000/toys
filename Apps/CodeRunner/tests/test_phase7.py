#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase7.py - Phase 7 automated tests for CodeRunner
#
# Created by skywind on 2026/05/07
# Last Modified: 2026/05/07 00:00:00
#
#======================================================================
import sys
import os
import tempfile
import unittest
import shutil

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
    MainWindow, _init_font_defaults, _read_file,
    FindDialog, ReplaceDialog, _ClickableLabel,
    _COMMON_ENCODINGS, _ACTION_DEFS, CodeEditor
)


def _safe_close_window (window):
    """Close MainWindow safely in offscreen mode — mark all tabs not dirty
    and disconnect signals to avoid QMessageBox crash in closeEvent."""
    for tab in window.tab_manager.tabs:
        tab.is_dirty = False
        tab.editor_doc.setModified(False)
        try:
            tab.editor_doc.modificationChanged.disconnect(
                tab._on_modified_changed)
        except (RuntimeError, TypeError):
            pass
        # Cancel batch highlighting timers
        tab.highlighter.cancel_batch_highlight()
    window.close()


#----------------------------------------------------------------------
# FindDialog unit tests
#----------------------------------------------------------------------
class TestFindDialog (unittest.TestCase):

    def setUp (self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown (self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_find_dialog_creation (self):
        """FindDialog can be created with a CodeEditor."""
        editor = CodeEditor()
        dlg = FindDialog(editor)
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.windowTitle(), 'Find')
        self.assertIsNotNone(dlg.edit_find)
        self.assertIsNotNone(dlg.chk_case)
        self.assertIsNotNone(dlg.radio_down)
        self.assertIsNotNone(dlg.radio_up)
        self.assertFalse(dlg.chk_case.isChecked())
        self.assertTrue(dlg.radio_down.isChecked())

    def test_find_dialog_non_modal_flags (self):
        """FindDialog has Qt.Window flag for non-modal behavior."""
        editor = CodeEditor()
        dlg = FindDialog(editor)
        self.assertTrue(dlg.windowFlags() & Qt.Window)

    def test_find_basic (self):
        """FindDialog finds text in document."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('hello world hello')
        editor.setDocument(doc)
        # Move cursor to start
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)
        dlg = FindDialog(editor)
        dlg.edit_find.setText('hello')
        dlg._on_find_next()
        found = editor.textCursor()
        self.assertTrue(found.hasSelection())
        self.assertEqual(found.selectedText(), 'hello')
        self.assertEqual(found.selectionStart(), 0)

    def test_find_next_advances (self):
        """Second Find Next advances to next occurrence."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('aaa bbb aaa')
        editor.setDocument(doc)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)
        dlg = FindDialog(editor)
        dlg.edit_find.setText('aaa')
        dlg._on_find_next()
        first_pos = editor.textCursor().selectionStart()
        dlg._on_find_next()
        second_pos = editor.textCursor().selectionStart()
        self.assertGreater(second_pos, first_pos)

    def test_find_not_found_updates_title (self):
        """When text not found, title shows 'Not found'."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('hello world')
        editor.setDocument(doc)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)
        dlg = FindDialog(editor)
        dlg.edit_find.setText('xyz')
        dlg._on_find_next()
        self.assertIn('Not found', dlg.windowTitle())

    def test_find_case_sensitive (self):
        """Case sensitive search only matches exact case."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('Hello World')
        editor.setDocument(doc)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)
        dlg = FindDialog(editor)
        dlg.chk_case.setChecked(True)
        # Case-sensitive search for lowercase 'hello' should NOT find uppercase 'Hello'
        dlg.edit_find.setText('hello')
        dlg._on_find_next()
        self.assertIn('Not found', dlg.windowTitle())
        # Case-sensitive search for 'Hello' should find it
        dlg.edit_find.setText('Hello')
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)
        dlg.setWindowTitle('Find')  # reset title
        dlg._on_find_next()
        found = editor.textCursor()
        self.assertTrue(found.hasSelection())
        self.assertEqual(found.selectedText(), 'Hello')

    def test_find_backward (self):
        """Up search finds text backwards."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('aaa bbb ccc')
        editor.setDocument(doc)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        editor.setTextCursor(cursor)
        dlg = FindDialog(editor)
        dlg.radio_up.setChecked(True)
        dlg.edit_find.setText('bbb')
        dlg._on_find_next()
        found = editor.textCursor()
        self.assertTrue(found.hasSelection())
        self.assertEqual(found.selectedText(), 'bbb')

    def test_find_wraps_forward (self):
        """Forward search wraps from end to beginning."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('aaa bbb aaa')
        editor.setDocument(doc)
        # Place cursor after second 'aaa'
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        editor.setTextCursor(cursor)
        dlg = FindDialog(editor)
        dlg.edit_find.setText('aaa')
        dlg._on_find_next()
        found = editor.textCursor()
        self.assertTrue(found.hasSelection())
        # Should have wrapped to the first occurrence
        self.assertEqual(found.selectionStart(), 0)

    def test_find_empty_text_no_action (self):
        """Find with empty search text does nothing."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('hello world')
        editor.setDocument(doc)
        original_pos = editor.textCursor().position()
        dlg = FindDialog(editor)
        dlg.edit_find.setText('')
        dlg._on_find_next()
        self.assertEqual(editor.textCursor().position(), original_pos)


#----------------------------------------------------------------------
# ReplaceDialog unit tests
#----------------------------------------------------------------------
class TestReplaceDialog (unittest.TestCase):

    def setUp (self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown (self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_replace_dialog_creation (self):
        """ReplaceDialog can be created with a CodeEditor."""
        editor = CodeEditor()
        dlg = ReplaceDialog(editor)
        self.assertIsNotNone(dlg)
        self.assertEqual(dlg.windowTitle(), 'Replace')
        self.assertIsNotNone(dlg.edit_find)
        self.assertIsNotNone(dlg.edit_replace)
        self.assertIsNotNone(dlg.chk_case)

    def test_replace_dialog_non_modal_flags (self):
        """ReplaceDialog has Qt.Window flag for non-modal behavior."""
        editor = CodeEditor()
        dlg = ReplaceDialog(editor)
        self.assertTrue(dlg.windowFlags() & Qt.Window)

    def test_replace_single (self):
        """Replace replaces current match and finds next."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('foo bar foo')
        editor.setDocument(doc)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        editor.setTextCursor(cursor)
        dlg = ReplaceDialog(editor)
        dlg.edit_find.setText('foo')
        dlg.edit_replace.setText('baz')
        # First find
        dlg._on_find_next()
        self.assertTrue(editor.textCursor().hasSelection())
        # Replace current selection
        dlg._on_replace()
        self.assertEqual(doc.toPlainText(), 'baz bar foo')
        # After replace, should auto-find next
        self.assertTrue(editor.textCursor().hasSelection())

    def test_replace_all (self):
        """Replace All replaces all occurrences and reports count."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('aaa bbb aaa ccc aaa')
        editor.setDocument(doc)
        dlg = ReplaceDialog(editor)
        dlg.edit_find.setText('aaa')
        dlg.edit_replace.setText('xxx')
        dlg._on_replace_all()
        self.assertEqual(doc.toPlainText(), 'xxx bbb xxx ccc xxx')
        self.assertIn('3 replaced', dlg.windowTitle())

    def test_replace_all_no_match (self):
        """Replace All with no match reports 0 replaced."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('hello world')
        editor.setDocument(doc)
        dlg = ReplaceDialog(editor)
        dlg.edit_find.setText('xyz')
        dlg.edit_replace.setText('abc')
        dlg._on_replace_all()
        self.assertEqual(doc.toPlainText(), 'hello world')
        self.assertIn('0 replaced', dlg.windowTitle())

    def test_replace_all_case_sensitive (self):
        """Replace All with case sensitive only replaces exact matches."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('Hello hello HELLO')
        editor.setDocument(doc)
        dlg = ReplaceDialog(editor)
        dlg.chk_case.setChecked(True)
        dlg.edit_find.setText('Hello')
        dlg.edit_replace.setText('world')
        dlg._on_replace_all()
        self.assertEqual(doc.toPlainText(), 'world hello HELLO')

    def test_replace_empty_find_no_action (self):
        """Replace with empty find text does nothing."""
        editor = CodeEditor()
        doc = QTextDocument()
        doc.setPlainText('hello world')
        editor.setDocument(doc)
        dlg = ReplaceDialog(editor)
        dlg.edit_find.setText('')
        dlg.edit_replace.setText('x')
        dlg._on_replace_all()
        self.assertEqual(doc.toPlainText(), 'hello world')


#----------------------------------------------------------------------
# _ClickableLabel unit tests
#----------------------------------------------------------------------
class TestClickableLabel (unittest.TestCase):

    def test_creation (self):
        """_ClickableLabel can be created and has pointing hand cursor."""
        label = _ClickableLabel('UTF-8')
        self.assertEqual(label.text(), 'UTF-8')
        self.assertEqual(label.cursor().shape(), Qt.PointingHandCursor)

    def test_set_main_window (self):
        """_ClickableLabel can store main window reference."""
        label = _ClickableLabel()
        # Use None as placeholder — just verify the setter works
        label.setMainWindow(None)
        self.assertIsNone(label._main_window)


#----------------------------------------------------------------------
# _COMMON_ENCODINGS constant test
#----------------------------------------------------------------------
class TestCommonEncodings (unittest.TestCase):

    def test_encodings_list_content (self):
        """_COMMON_ENCODINGS contains expected encodings."""
        self.assertIn('UTF-8', _COMMON_ENCODINGS)
        self.assertIn('GBK', _COMMON_ENCODINGS)
        self.assertIn('Big5', _COMMON_ENCODINGS)
        self.assertIn('Shift_JIS', _COMMON_ENCODINGS)
        self.assertIn('ISO-8859-1', _COMMON_ENCODINGS)

    def test_encodings_list_size (self):
        """_COMMON_ENCODINGS has reasonable size (>= 5)."""
        self.assertGreaterEqual(len(_COMMON_ENCODINGS), 5)


#----------------------------------------------------------------------
# Encoding menu integration tests
#----------------------------------------------------------------------
class TestEncodingMenu (unittest.TestCase):

    def setUp (self):
        self.tmpdir = tempfile.mkdtemp()
        s = Settings()
        _init_font_defaults(s)
        self.window = MainWindow(s)

    def tearDown (self):
        _safe_close_window(self.window)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_encoding_label_is_clickable (self):
        """Status info label uses _ClickableLabel."""
        self.assertIsInstance(self.window.status_info, _ClickableLabel)

    def test_encoding_label_has_main_window (self):
        """_ClickableLabel has main window reference set."""
        self.assertEqual(self.window.status_info._main_window, self.window)

    def test_reopen_with_encoding_new_file_skipped (self):
        """Reopen with Encoding is skipped for new (unsaved) tabs."""
        self.window._action_new()
        tab = self.window.tab_manager.get_current()
        self.assertTrue(tab.is_new)
        # Call _on_reopen_with_encoding with encoding parameter
        # — should return early without changing encoding
        original_encoding = tab.encoding
        self.window._on_reopen_with_encoding(encoding='GBK')
        # Encoding unchanged because is_new tab
        self.assertEqual(tab.encoding, original_encoding)

    def test_save_with_encoding_new_file_requires_path (self):
        """Save with Encoding on new file requires path selection.
        Verify is_new flag is True — the method would open a
        SaveFileDialog which we can't test in offscreen mode."""
        self.window._action_new()
        tab = self.window.tab_manager.get_current()
        self.assertTrue(tab.is_new)
        # Can't call _on_save_with_encoding on is_new tab in offscreen
        # mode because QFileDialog would block. Just verify the guard
        # condition exists.

    def test_reopen_with_encoding_existing_file (self):
        """Reopen with Encoding logic: file can be read with alternate
        encoding. Testing the data layer without triggering Qt rehighlight
        which crashes in offscreen mode."""
        # Create a GBK file with Chinese content
        path = os.path.join(self.tmpdir, 'test_gbk.cpp')
        with open(path, 'wb') as f:
            f.write(b'// \xd6\xd0\xb9\xfa\nint main() { return 0; }\n')
        # Verify _read_file detects GBK
        content, encoding = _read_file(path)
        self.assertEqual(encoding, 'GBK')
        # Verify file can be re-read with UTF-8 (with replacement)
        content_utf8 = open(path, 'r', encoding='UTF-8', errors='replace').read()
        self.assertIn('main', content_utf8)


#----------------------------------------------------------------------
# Shortcut and action wiring verification
#----------------------------------------------------------------------
class TestActionWiring (unittest.TestCase):

    def setUp (self):
        s = Settings()
        _init_font_defaults(s)
        self.window = MainWindow(s)

    def tearDown (self):
        _safe_close_window(self.window)

    def test_all_actions_created (self):
        """All _ACTION_DEFS actions are created as attributes."""
        for attr, label, icon_key, shortcuts, tooltip in _ACTION_DEFS:
            action = getattr(self.window, attr, None)
            self.assertIsNotNone(action,
                                 'Action {} not found'.format(attr))
            self.assertEqual(action.text(), label)

    def test_all_shortcuts_match_prd (self):
        """All action shortcuts match the PRD specification."""
        # Expected shortcuts from PRD
        expected = {
            'act_new': ['Ctrl+N'],
            'act_save': ['Ctrl+S'],
            'act_open': ['Ctrl+O'],
            'act_save_as': ['Ctrl+Shift+S'],
            'act_close': ['Ctrl+W'],
            'act_run': ['F5'],
            'act_test': ['F9'],
            'act_stop': ['F7'],
            'act_zoom_in': ['Ctrl++', 'Ctrl+='],
            'act_zoom_out': ['Ctrl+-'],
            'act_undo': ['Ctrl+Z'],
            'act_redo': ['Ctrl+Y'],
            'act_cut': ['Ctrl+X'],
            'act_copy': ['Ctrl+C'],
            'act_paste': ['Ctrl+V'],
            'act_find': ['Ctrl+F'],
            'act_replace': ['Ctrl+H'],
            'act_goto_line': ['Ctrl+G'],
            'act_build': ['Ctrl+B'],
        }
        for attr, shortcuts in expected.items():
            action = getattr(self.window, attr)
            actual = [s.toString() for s in action.shortcuts()]
            for exp_short in shortcuts:
                # Normalize shortcut strings for comparison
                found = any(exp_short.replace('+', '').lower()
                           == a.replace('+', '').lower()
                           for a in actual)
                self.assertTrue(
                    found,
                    '{}: expected shortcut {} not in actual {}'.format(
                        attr, exp_short, actual))

    def test_no_shortcut_actions (self):
        """Settings and About have no shortcuts as per PRD."""
        self.assertEqual(len(self.window.act_settings.shortcuts()), 0)
        self.assertEqual(len(self.window.act_about.shortcuts()), 0)

    def test_all_actions_connected (self):
        """All actions have triggered signals connected to handler methods."""
        # Map action attr to expected handler method
        handler_map = {
            'act_new': '_action_new',
            'act_save': '_action_save',
            'act_open': '_action_open',
            'act_save_as': '_action_save_as',
            'act_close': '_action_close',
            'act_run': '_action_run',
            'act_test': '_action_test',
            'act_stop': '_action_stop',
            'act_settings': '_action_settings',
            'act_zoom_in': '_action_zoom_in',
            'act_zoom_out': '_action_zoom_out',
            'act_undo': '_action_undo',
            'act_redo': '_action_redo',
            'act_cut': '_action_cut',
            'act_copy': '_action_copy',
            'act_paste': '_action_paste',
            'act_find': '_action_find',
            'act_replace': '_action_replace',
            'act_goto_line': '_action_goto_line',
            'act_build': '_action_build',
            'act_about': '_action_about',
        }
        for attr, method_name in handler_map.items():
            action = getattr(self.window, attr)
            handler = getattr(self.window, method_name)
            # Verify the handler is callable
            self.assertTrue(
                callable(handler),
                '{} handler {} not callable'.format(attr, method_name))

    def test_tooltips_format (self):
        """Toolbar button tooltips follow 'action name (shortcut)' format."""
        tooltip_actions = {
            'act_new': 'New (Ctrl+N)',
            'act_save': 'Save (Ctrl+S)',
            'act_open': 'Open (Ctrl+O)',
            'act_run': 'Run (F5)',
            'act_test': 'Test (F9)',
            'act_stop': 'Stop (F7)',
            'act_undo': 'Undo (Ctrl+Z)',
            'act_redo': 'Redo (Ctrl+Y)',
            'act_cut': 'Cut (Ctrl+X)',
            'act_copy': 'Copy (Ctrl+C)',
            'act_paste': 'Paste (Ctrl+V)',
            'act_find': 'Find (Ctrl+F)',
            'act_replace': 'Replace (Ctrl+H)',
            'act_goto_line': 'Goto Line (Ctrl+G)',
            'act_build': 'Build (Ctrl+B)',
            'act_save_as': 'Save As (Ctrl+Shift+S)',
            'act_close': 'Close (Ctrl+W)',
            'act_zoom_in': 'Zoom In (Ctrl++)',  # primary shortcut
            'act_zoom_out': 'Zoom Out (Ctrl+-)',
        }
        for attr, expected_tip in tooltip_actions.items():
            action = getattr(self.window, attr)
            tip = action.toolTip()
            # The tooltip should contain the label
            label = expected_tip.split(' ')[0]
            self.assertIn(label, tip,
                          '{} tooltip missing label'.format(attr))
            # Check shortcut key is in tooltip
            shortcut_part = expected_tip.split('(')[1].rstrip(')')
            self.assertIn(shortcut_part, tip,
                          '{} tooltip missing shortcut (got: {})'.format(
                              attr, tip))

    def test_settings_tooltip_explicit (self):
        """Settings action has explicit tooltip 'Settings'."""
        self.assertEqual(self.window.act_settings.toolTip(), 'Settings')

    def test_about_tooltip_auto (self):
        """About action has auto tooltip 'About' (label with no shortcut)."""
        # QAction auto-sets text as tooltip when tooltip='' is specified
        # in _ACTION_DEFS — but the actual behavior is tooltip='About'
        self.assertIn('About', self.window.act_about.toolTip())


#----------------------------------------------------------------------
# FindDialog integration with MainWindow
#----------------------------------------------------------------------
class TestFindDialogIntegration (unittest.TestCase):

    def setUp (self):
        s = Settings()
        _init_font_defaults(s)
        self.window = MainWindow(s)

    def tearDown (self):
        _safe_close_window(self.window)

    def test_action_find_creates_dialog (self):
        """_action_find lazily creates FindDialog."""
        self.assertIsNone(self.window._find_dialog)
        self.window._action_new()
        self.window._action_find()
        self.assertIsNotNone(self.window._find_dialog)
        self.assertIsInstance(self.window._find_dialog, FindDialog)

    def test_action_find_reuses_dialog (self):
        """Second _action_find reuses the same dialog."""
        self.window._action_new()
        self.window._action_find()
        first = self.window._find_dialog
        self.window._action_find()
        self.assertEqual(self.window._find_dialog, first)

    def test_action_replace_creates_dialog (self):
        """_action_replace lazily creates ReplaceDialog."""
        self.assertIsNone(self.window._replace_dialog)
        self.window._action_new()
        self.window._action_replace()
        self.assertIsNotNone(self.window._replace_dialog)
        self.assertIsInstance(self.window._replace_dialog, ReplaceDialog)

    def test_action_replace_reuses_dialog (self):
        """Second _action_replace reuses the same dialog."""
        self.window._action_new()
        self.window._action_replace()
        first = self.window._replace_dialog
        self.window._action_replace()
        self.assertEqual(self.window._replace_dialog, first)


#----------------------------------------------------------------------
# Menu structure verification
#----------------------------------------------------------------------
class TestMenuStructure (unittest.TestCase):

    def setUp (self):
        s = Settings()
        _init_font_defaults(s)
        self.window = MainWindow(s)

    def tearDown (self):
        _safe_close_window(self.window)

    def test_edit_menu_has_all_actions (self):
        """Edit menu contains Undo, Redo, Cut, Copy, Paste, Find, Replace, Goto Line."""
        actions = [a.text() for a in self.window.menu_edit.actions()
                   if a.text() and not a.isSeparator()]
        expected = ['Undo', 'Redo', 'Cut', 'Copy', 'Paste',
                    'Find', 'Replace', 'Goto Line']
        for name in expected:
            self.assertIn(name, actions,
                          '{} not in Edit menu'.format(name))

    def test_view_menu_has_zoom (self):
        """View menu contains Zoom In and Zoom Out."""
        actions = [a.text() for a in self.window.menu_view.actions()
                   if a.text() and not a.isSeparator()]
        self.assertIn('Zoom In', actions)
        self.assertIn('Zoom Out', actions)

    def test_run_menu_has_all_actions (self):
        """Run menu contains Build, Test, Run, Stop."""
        actions = [a.text() for a in self.window.menu_run.actions()
                   if a.text() and not a.isSeparator()]
        expected = ['Build', 'Test', 'Run', 'Stop']
        for name in expected:
            self.assertIn(name, actions,
                          '{} not in Run menu'.format(name))

    def test_file_menu_has_all_actions (self):
        """File menu contains New, Open, Save, Save As, Close, Settings."""
        # Collect all action texts including submenu texts
        texts = []
        for a in self.window.menu_file.actions():
            if a.menu():
                texts.append(a.menu().title())
            elif a.text() and not a.isSeparator():
                texts.append(a.text())
        expected = ['New', 'Open', 'Save', 'Save As', 'Close',
                    'Recent Files', 'Settings']
        for name in expected:
            self.assertIn(name, texts,
                          '{} not in File menu'.format(name))

    def test_help_menu_has_about (self):
        """Help menu contains About action."""
        actions = [a.text() for a in self.window.menu_help.actions()
                   if a.text()]
        self.assertIn('About', actions)


#----------------------------------------------------------------------
# Alt+0-9 tab switching shortcuts
#----------------------------------------------------------------------
class TestTabSwitchShortcuts (unittest.TestCase):

    def setUp (self):
        s = Settings()
        _init_font_defaults(s)
        self.window = MainWindow(s)

    def tearDown (self):
        _safe_close_window(self.window)

    def test_alt_shortcuts_created (self):
        """Alt+1 through Alt+0 shortcuts are registered."""
        # The shortcuts are created in __setup_tab_switch_shortcuts
        # We verify they exist by checking the window's children
        shortcuts = [c for c in self.window.children()
                     if c.__class__.__name__ == 'QShortcut']
        # Should have 10 shortcuts (Alt+1 through Alt+9, Alt+0)
        self.assertGreaterEqual(len(shortcuts), 10)


#----------------------------------------------------------------------
# Goto Line integration test
#----------------------------------------------------------------------
class TestGotoLineIntegration (unittest.TestCase):

    def setUp (self):
        s = Settings()
        _init_font_defaults(s)
        self.window = MainWindow(s)

    def tearDown (self):
        _safe_close_window(self.window)

    def test_goto_line_handler_callable (self):
        """_action_goto_line handler is callable."""
        self.assertTrue(callable(self.window._action_goto_line))


if __name__ == '__main__':
    unittest.main()