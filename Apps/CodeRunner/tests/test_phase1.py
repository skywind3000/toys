#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase1.py - Phase 1 automated tests for CodeRunner
#
# Created by skywind on 2026/05/05
# Last Modified: 2026/05/05 00:00:00
#
#======================================================================
import sys
import os
import unittest

# Force offscreen platform so tests run without display
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# Ensure single QApplication instance
_app = QApplication.instance()
if _app is None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    _app = QApplication(sys.argv)

# Add parent dir to path so we can import CodeRunner
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from CodeRunner import Settings, InputPanel, OutputPanel, MainWindow
from CodeRunner import _detect_monospace_font, _init_font_defaults
from CodeRunner import _create_toolbar_icons
from CodeRunner import _COLOR_NEW, _COLOR_SAVE, _COLOR_OPEN
from CodeRunner import _COLOR_RUN, _COLOR_TEST, _COLOR_STOP


#----------------------------------------------------------------------
# Settings defaults
#----------------------------------------------------------------------
class TestSettings (unittest.TestCase):

    def test_defaults (self):
        s = Settings()
        _init_font_defaults(s)
        self.assertEqual(s.compiler_path, 'g++')
        self.assertEqual(s.compiler_flags, '-std=c++14')
        self.assertEqual(s.env_vars, {})
        self.assertEqual(s.run_timeout, 10)
        self.assertEqual(s.compile_timeout, 20)
        # Font defaults are platform-dependent, must be non-empty after init
        self.assertTrue(len(s.editor_font_family) > 0)
        self.assertEqual(s.editor_font_size, 11)
        self.assertTrue(len(s.io_font_family) > 0)
        self.assertEqual(s.io_font_size, 11)
        self.assertTrue(s.bracket_completion)

    def test_template_content (self):
        s = Settings()
        self.assertIn('#include <iostream>', s.template_text)
        self.assertIn('int main()', s.template_text)
        self.assertIn('return 0;', s.template_text)
        # Template ends with newline
        self.assertTrue(s.template_text.endswith('\n'))

    def test_template_is_valid_cpp_skeleton (self):
        s = Settings()
        lines = s.template_text.strip().split('\n')
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], '#include <iostream>')
        self.assertEqual(lines[1], '#include <cstdio>')
        self.assertEqual(lines[2], 'using namespace std;')
        self.assertEqual(lines[3], 'int main() {')
        self.assertEqual(lines[4], '\treturn 0;')
        self.assertEqual(lines[5], '}')


#----------------------------------------------------------------------
# InputPanel
#----------------------------------------------------------------------
class TestInputPanel (unittest.TestCase):

    def test_basic_creation (self):
        panel = InputPanel()
        self.assertFalse(panel.isReadOnly())

    def test_tab_width_set (self):
        panel = InputPanel()
        # TabStopWidth should be > 0 (set to 4-char width)
        self.assertGreater(panel.tabStopWidth(), 0)


#----------------------------------------------------------------------
# OutputPanel
#----------------------------------------------------------------------
class TestOutputPanel (unittest.TestCase):

    def test_readonly (self):
        panel = OutputPanel()
        self.assertTrue(panel.isReadOnly())


#----------------------------------------------------------------------
# MainWindow layout
#----------------------------------------------------------------------
class TestMainWindow (unittest.TestCase):

    def setUp (self):
        self.window = MainWindow()

    def test_window_title (self):
        self.assertEqual(self.window.windowTitle(), 'CodeRunner')

    def test_window_size (self):
        # Resize should be 1000x650
        self.assertEqual(self.window.width(), 1000)
        self.assertEqual(self.window.height(), 650)

    def test_menubar_has_four_menus (self):
        menus = self.window.menuBar().actions()
        texts = [a.text() for a in menus]
        self.assertEqual(texts, ['File', 'Edit', 'Run', 'View'])

    def test_menu_file_exists (self):
        self.assertIsNotNone(self.window.menu_file)

    def test_menu_edit_exists (self):
        self.assertIsNotNone(self.window.menu_edit)

    def test_menu_run_exists (self):
        self.assertIsNotNone(self.window.menu_run)

    def test_menu_view_exists (self):
        self.assertIsNotNone(self.window.menu_view)

    def test_menu_file_has_items (self):
        # Phase 2: File menu is populated
        actions = self.window.menu_file.actions()
        self.assertGreater(len(actions), 0)

    def test_menu_edit_empty (self):
        self.assertEqual(len(self.window.menu_edit.actions()), 0)

    def test_menu_run_empty (self):
        self.assertEqual(len(self.window.menu_run.actions()), 0)

    def test_menu_view_has_zoom (self):
        # Phase 2: View menu has zoom actions
        actions = self.window.menu_view.actions()
        self.assertGreater(len(actions), 0)

    def test_toolbar_actions (self):
        # Check that all actions exist
        self.assertIsNotNone(self.window.act_new)
        self.assertIsNotNone(self.window.act_save)
        self.assertIsNotNone(self.window.act_open)
        self.assertIsNotNone(self.window.act_run)
        self.assertIsNotNone(self.window.act_test)
        self.assertIsNotNone(self.window.act_stop)
        self.assertIsNotNone(self.window.act_settings)

    def test_toolbar_actions_have_icons (self):
        # All toolbar actions should have icons
        for act in [self.window.act_new, self.window.act_save,
                    self.window.act_open, self.window.act_run,
                    self.window.act_test, self.window.act_stop,
                    self.window.act_settings]:
            self.assertFalse(act.icon().isNull(),
                            f'{act.text()} action has no icon')

    def test_toolbar_shortcuts (self):
        self.assertEqual(self.window.act_new.shortcut().toString(), 'Ctrl+N')
        self.assertEqual(self.window.act_save.shortcut().toString(), 'Ctrl+S')
        self.assertEqual(self.window.act_open.shortcut().toString(), 'Ctrl+O')
        self.assertEqual(self.window.act_run.shortcut().toString(), 'F5')
        self.assertEqual(self.window.act_test.shortcut().toString(), 'F9')
        self.assertEqual(self.window.act_stop.shortcut().toString(), 'F7')

    def test_toolbar_tooltips (self):
        self.assertEqual(self.window.act_new.toolTip(), 'New (Ctrl+N)')
        self.assertEqual(self.window.act_save.toolTip(), 'Save (Ctrl+S)')
        self.assertEqual(self.window.act_open.toolTip(), 'Open (Ctrl+O)')
        self.assertEqual(self.window.act_run.toolTip(), 'Run (F5)')
        self.assertEqual(self.window.act_test.toolTip(), 'Test (F9)')
        self.assertEqual(self.window.act_stop.toolTip(), 'Stop (F7)')

    def test_tabbar_exists (self):
        self.assertIsNotNone(self.window.tabbar)

    def test_tabbar_closable (self):
        self.assertTrue(self.window.tabbar.tabsClosable())

    def test_tabbar_movable (self):
        self.assertTrue(self.window.tabbar.isMovable())

    def test_tabbar_empty_on_start (self):
        self.assertEqual(self.window.tabbar.count(), 0)

    def test_zero_tab_state_editor_disabled (self):
        self.assertFalse(self.window.editor.isEnabled())

    def test_zero_tab_state_input_section_disabled (self):
        self.assertFalse(self.window.input_section.isEnabled())

    def test_zero_tab_state_output_section_disabled (self):
        self.assertFalse(self.window.output_section.isEnabled())

    def test_zero_tab_state_status_info_empty (self):
        self.assertEqual(self.window.status_info.text(), '')

    def test_zero_tab_state_placeholder_docs (self):
        # Editor should be using the empty placeholder document
        self.assertEqual(self.window.editor.document(),
                         self.window.empty_editor_doc)
        self.assertEqual(self.window.input_panel.document(),
                         self.window.empty_input_doc)
        self.assertEqual(self.window.output_panel.document(),
                         self.window.empty_output_doc)

    def test_splitters_exist (self):
        self.assertIsNotNone(self.window.main_splitter)
        self.assertIsNotNone(self.window.v_splitter)

    def test_horizontal_splitter_orientation (self):
        self.assertEqual(self.window.main_splitter.orientation(),
                         Qt.Horizontal)

    def test_vertical_splitter_orientation (self):
        self.assertEqual(self.window.v_splitter.orientation(),
                         Qt.Vertical)

    def test_splitter_children (self):
        # Main splitter: editor + v_splitter
        self.assertEqual(self.window.main_splitter.count(), 2)
        self.assertEqual(self.window.v_splitter.count(), 2)

    def test_v_splitter_children_are_io_sections (self):
        self.assertEqual(self.window.v_splitter.widget(0),
                         self.window.input_section)
        self.assertEqual(self.window.v_splitter.widget(1),
                         self.window.output_section)

    def test_input_section_label (self):
        label = self.window.input_section._section_label
        self.assertEqual(label.text(), 'INPUT')
        self.assertTrue(label.font().bold())

    def test_output_section_label (self):
        label = self.window.output_section._section_label
        self.assertEqual(label.text(), 'OUTPUT')
        self.assertTrue(label.font().bold())

    def test_statusbar_exists (self):
        self.assertIsNotNone(self.window.statusBar())

    def test_statusbar_has_message_and_info (self):
        self.assertIsNotNone(self.window.status_message)
        self.assertIsNotNone(self.window.status_info)

    def test_statusbar_message_alignment (self):
        self.assertEqual(self.window.status_message.alignment(),
                         Qt.AlignLeft)

    def test_statusbar_info_alignment (self):
        self.assertEqual(self.window.status_info.alignment(),
                         Qt.AlignRight)

    def test_exit_zero_tab_state_enables_panels (self):
        self.window._exit_zero_tab_state()
        self.assertTrue(self.window.editor.isEnabled())
        self.assertTrue(self.window.input_section.isEnabled())
        self.assertTrue(self.window.output_section.isEnabled())

    def test_enter_zero_tab_state_disables_panels (self):
        self.window._exit_zero_tab_state()
        self.window._enter_zero_tab_state()
        self.assertFalse(self.window.editor.isEnabled())
        self.assertFalse(self.window.input_section.isEnabled())
        self.assertFalse(self.window.output_section.isEnabled())
        self.assertEqual(self.window.status_info.text(), '')

    def test_zero_tab_state_switches_back_to_placeholder_docs (self):
        self.window._exit_zero_tab_state()
        self.window._enter_zero_tab_state()
        self.assertEqual(self.window.editor.document(),
                         self.window.empty_editor_doc)
        self.assertEqual(self.window.input_panel.document(),
                         self.window.empty_input_doc)
        self.assertEqual(self.window.output_panel.document(),
                         self.window.empty_output_doc)

    def test_settings_instance (self):
        self.assertIsInstance(self.window.settings, Settings)


#----------------------------------------------------------------------
# Font detection
#----------------------------------------------------------------------
class TestFontDetection (unittest.TestCase):

    def test_detect_returns_nonempty (self):
        font = _detect_monospace_font()
        self.assertTrue(len(font) > 0)

    def test_init_sets_font_defaults (self):
        s = Settings()
        _init_font_defaults(s)
        self.assertTrue(len(s.editor_font_family) > 0)
        self.assertTrue(len(s.io_font_family) > 0)
        self.assertEqual(s.editor_font_family, s.io_font_family)

    def test_priority_list_win32 (self):
        from CodeRunner import _MONOSPACE_PRIORITY
        self.assertIn('win32', _MONOSPACE_PRIORITY)
        self.assertIn('Consolas', _MONOSPACE_PRIORITY['win32'])

    def test_priority_list_darwin (self):
        from CodeRunner import _MONOSPACE_PRIORITY
        self.assertIn('darwin', _MONOSPACE_PRIORITY)
        self.assertIn('Menlo', _MONOSPACE_PRIORITY['darwin'])

    def test_linux_candidates (self):
        from CodeRunner import _LINUX_MONOSPACE
        self.assertIn('DejaVu Sans Mono', _LINUX_MONOSPACE)

    def test_fallback_is_monospace (self):
        font = _detect_monospace_font()
        self.assertTrue(font in ('Consolas', 'Menlo', 'DejaVu Sans Mono',
                                 'Courier New', 'SF Mono', 'Ubuntu Mono',
                                 'monospace'))


#----------------------------------------------------------------------
# Toolbar icons
#----------------------------------------------------------------------
class TestToolbarIcons (unittest.TestCase):

    def test_all_icons_created (self):
        icons = _create_toolbar_icons()
        expected = ['new', 'save', 'open', 'run', 'test', 'stop', 'settings']
        self.assertEqual(sorted(icons.keys()), sorted(expected))

    def test_no_icon_is_null (self):
        icons = _create_toolbar_icons()
        for name, icon in icons.items():
            self.assertFalse(icon.isNull(), f'{name} icon is null')

    def test_all_icons_are_generated (self):
        icons = _create_toolbar_icons()
        self.assertEqual(len(icons), 7)

    def test_icon_colors_defined (self):
        self.assertTrue(_COLOR_NEW.isValid())
        self.assertTrue(_COLOR_SAVE.isValid())
        self.assertTrue(_COLOR_OPEN.isValid())
        self.assertTrue(_COLOR_RUN.isValid())
        self.assertTrue(_COLOR_TEST.isValid())
        self.assertTrue(_COLOR_STOP.isValid())

    def test_icon_colors_are_distinct (self):
        colors = [_COLOR_NEW, _COLOR_SAVE, _COLOR_OPEN,
                  _COLOR_RUN, _COLOR_TEST, _COLOR_STOP]
        hex_colors = [c.name() for c in colors]
        self.assertEqual(len(set(hex_colors)), len(hex_colors),
                         'Some icon colors are not distinct')


#----------------------------------------------------------------------
# DPI attribute
#----------------------------------------------------------------------
class TestDPI (unittest.TestCase):

    def test_high_dpi_scaling_attribute (self):
        self.assertTrue(QApplication.testAttribute(Qt.AA_EnableHighDpiScaling))


if __name__ == '__main__':
    unittest.main()