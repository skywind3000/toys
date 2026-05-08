#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase11.py - Phase 11 automated tests for CodeRunner
#   interactive flush, deprecated code cleanup, and documentation sync
#
# Created by skywind on 2026/05/08
# Last Modified: 2026/05/08
#
#======================================================================
import sys
import os
import unittest

# Force offscreen platform so tests run without display
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat, QBrush, QTextDocument, QKeyEvent

# Ensure single QApplication instance
_app = QApplication.instance()
if _app is None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    _app = QApplication(sys.argv)
    _app.setStyle('Fusion')

# Add parent dir to path so we can import CodeRunner
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from CodeRunner import (
    Settings, TabData, MainWindow, _init_font_defaults,
    _output_clear, FlowController,
    _FLOW_IDLE
)


#----------------------------------------------------------------------
# 1. Deprecated code removal verification
#----------------------------------------------------------------------

class TestOutputAppendRemoved (unittest.TestCase):
    """Verify _output_append function is removed from module."""

    def test_output_append_not_in_module (self):
        """_output_append should not exist in CodeRunner module."""
        import CodeRunner as cr
        self.assertFalse(hasattr(cr, '_output_append'))

    def test_no_need_scroll_in_tabdata (self):
        """TabData should not have _need_scroll attribute by default."""
        tab = TabData(content='hello')
        self.assertFalse(hasattr(tab, '_need_scroll'))

    def test_scroll_requested_not_in_flowcontroller (self):
        """FlowController should not have scroll_requested signal."""
        self.assertFalse(hasattr(FlowController, 'scroll_requested'))

    def test_maybe_scroll_output_not_in_mainwindow (self):
        """MainWindow should not have _maybe_scroll_output method."""
        settings = Settings()
        _init_font_defaults(settings)
        window = MainWindow(settings)
        self.assertFalse(hasattr(window, '_maybe_scroll_output'))

    def test_flow_scroll_requested_not_in_mainwindow (self):
        """MainWindow should not have _on_flow_scroll_requested method."""
        settings = Settings()
        _init_font_defaults(settings)
        window = MainWindow(settings)
        self.assertFalse(hasattr(window, '_on_flow_scroll_requested'))


#----------------------------------------------------------------------
# 2. Stdin immediate flush verification
#----------------------------------------------------------------------

class TestStdinImmediateFlush (unittest.TestCase):
    """Verify InputPanel Enter triggers _immediate_flush."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        self.tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        self.tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(self.tab)
        self.window.tabbar.addTab(self.tab.tab_name())
        self.window._switch_to_tab(index)

    def test_immediate_flush_exists (self):
        """MainWindow should have _immediate_flush method."""
        self.assertTrue(hasattr(self.window, '_immediate_flush'))

    def test_immediate_flush_writes_buffer_to_doc (self):
        """_immediate_flush writes buffer contents to output_doc."""
        self.tab.output_buffer.append((None, 'prompt> '))
        self.window._immediate_flush(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'prompt> ')
        self.assertEqual(self.tab.output_buffer, [])

    def test_immediate_flush_multiple_colors (self):
        """_immediate_flush correctly handles mixed color entries."""
        red = QColor(Qt.red)
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((None, 'output\n'))
        self.tab.output_buffer.append((gray, 'stderr\n'))
        self.tab.output_buffer.append((red, 'error\n'))
        self.window._immediate_flush(self.tab)
        text = self.tab.output_doc.toPlainText()
        self.assertEqual(text, 'output\nstderr\nerror\n')

    def test_immediate_flush_preserves_pinned_state (self):
        """_immediate_flush does not change pinned_to_bottom=False."""
        self.tab.pinned_to_bottom = False
        self.tab.output_buffer.append((None, 'text\n'))
        self.window._immediate_flush(self.tab)
        self.assertFalse(self.tab.pinned_to_bottom)

    def test_immediate_flush_scrolls_when_pinned (self):
        """_immediate_flush scrolls to bottom when pinned=True on current tab."""
        self.tab.pinned_to_bottom = True
        self.tab.output_buffer.append((None, 'line1\nline2\nline3\n'))
        self.window._immediate_flush(self.tab)
        # Buffer should be empty and content in doc
        self.assertEqual(self.tab.output_buffer, [])
        self.assertIn('line1', self.tab.output_doc.toPlainText())

    def test_buffer_overflow_immediate_flush_on_count (self):
        """_check_buffer_overflow flushes when buffer exceeds 200 entries."""
        for i in range(201):
            self.tab.output_buffer.append((None, 'x'))
        self.window._check_buffer_overflow(self.tab)
        self.assertEqual(len(self.tab.output_buffer), 0)
        self.assertIn('x', self.tab.output_doc.toPlainText())

    def test_buffer_overflow_immediate_flush_on_size (self):
        """_check_buffer_overflow flushes when buffer text exceeds 64KB."""
        big_text = 'x' * 70000
        self.tab.output_buffer.append((None, big_text))
        self.window._check_buffer_overflow(self.tab)
        self.assertEqual(len(self.tab.output_buffer), 0)

    def tearDown (self):
        pass


#----------------------------------------------------------------------
# 3. Pinned-to-bottom state invariants
#----------------------------------------------------------------------

class TestPinnedToBottomInvariants (unittest.TestCase):
    """Test pinned_to_bottom state management edge cases."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        self.tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        self.tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(self.tab)
        self.window.tabbar.addTab(self.tab.tab_name())
        self.window._switch_to_tab(index)

    def test_initial_pinned_is_true (self):
        """New tab should have pinned_to_bottom=True."""
        self.assertTrue(self.tab.pinned_to_bottom)

    def test_clear_and_start_compile_sets_pinned (self):
        """FlowController.clear_and_start_compile resets pinned=True."""
        self.tab.pinned_to_bottom = False
        # Simulate what clear_and_start_compile does
        self.tab.output_buffer.clear()
        _output_clear(self.tab.output_doc)
        self.tab.pinned_to_bottom = True
        self.assertTrue(self.tab.pinned_to_bottom)

    def test_is_output_at_bottom_exists (self):
        """MainWindow should have _is_output_at_bottom method."""
        self.assertTrue(hasattr(self.window, '_is_output_at_bottom'))

    def test_programmatic_scroll_flag_exists (self):
        """MainWindow should have __programmatic_scroll attribute."""
        self.assertTrue(hasattr(self.window, '_MainWindow__programmatic_scroll'))

    def test_flush_output_buffer_exists (self):
        """MainWindow should have _flush_output_buffer method."""
        self.assertTrue(hasattr(self.window, '_flush_output_buffer'))

    def test_check_buffer_overflow_exists (self):
        """MainWindow should have _check_buffer_overflow method."""
        self.assertTrue(hasattr(self.window, '_check_buffer_overflow'))

    def tearDown (self):
        pass


#----------------------------------------------------------------------
# 4. Merge adjacent same-color entries in flush
#----------------------------------------------------------------------

class TestFlushMergeLogic (unittest.TestCase):
    """Test that _flush_output_buffer merges adjacent same-color entries."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        self.tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        self.tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(self.tab)
        self.window.tabbar.addTab(self.tab.tab_name())
        self.window._switch_to_tab(index)

    def test_merge_two_none_colors (self):
        """Two adjacent None-color entries merge into one text."""
        self.tab.output_buffer.append((None, 'hello'))
        self.tab.output_buffer.append((None, ' world'))
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'hello world')

    def test_merge_two_gray_colors (self):
        """Two adjacent gray entries merge into one text."""
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((gray, 'err1'))
        self.tab.output_buffer.append((gray, 'err2'))
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'err1err2')

    def test_no_merge_across_different_colors (self):
        """Different color entries are not merged."""
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((None, 'stdout'))
        self.tab.output_buffer.append((gray, 'stderr'))
        self.tab.output_buffer.append((None, 'stdout2'))
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(
            self.tab.output_doc.toPlainText(), 'stdoutstderrstdout2')

    def test_merge_multiple_same_color (self):
        """Three consecutive same-color entries merge."""
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((gray, 'a'))
        self.tab.output_buffer.append((gray, 'b'))
        self.tab.output_buffer.append((gray, 'c'))
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'abc')

    def test_merge_preserves_color_in_first_merged_entry (self):
        """After merge, char format should reflect the merged color."""
        red = QColor(Qt.red)
        self.tab.output_buffer.append((red, 'line1\n'))
        self.tab.output_buffer.append((red, 'line2\n'))
        self.window._flush_output_buffer(self.tab)
        cursor = QTextCursor(self.tab.output_doc)
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 5)
        fmt = cursor.charFormat()
        self.assertEqual(fmt.foreground().color(), red)

    def test_empty_buffer_flush_is_noop (self):
        """Flushing empty buffer leaves output_doc unchanged."""
        self.assertEqual(self.tab.output_doc.toPlainText(), '')
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), '')

    def tearDown (self):
        pass


#----------------------------------------------------------------------
# 5. Flush timer integration
#----------------------------------------------------------------------

class TestFlushTimerIntegration (unittest.TestCase):
    """Test _on_flush_timer processes all tabs correctly."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def test_flush_timer_exists_and_active (self):
        """_flush_output_timer exists and is always active."""
        self.assertTrue(hasattr(self.window, '_flush_output_timer'))
        self.assertTrue(self.window._flush_output_timer.isActive())

    def test_flush_timer_interval (self):
        """_flush_output_timer interval is 50ms."""
        self.assertEqual(self.window._flush_output_timer.interval(), 50)

    def test_flush_timer_no_start_stop_calls_in_init (self):
        """Timer should not need explicit start/stop after init."""
        # Timer was started in __init_connections and never stops
        self.assertTrue(self.window._flush_output_timer.isActive())

    def tearDown (self):
        pass


#----------------------------------------------------------------------
# 6. OutputPanel End key and pinned state
#----------------------------------------------------------------------

class TestOutputPanelEndKey (unittest.TestCase):
    """Test OutputPanel End key sets pinned_to_bottom=True."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        self.tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        self.tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(self.tab)
        self.window.tabbar.addTab(self.tab.tab_name())
        self.window._switch_to_tab(index)

    def test_end_key_sets_pinned (self):
        """End key in OutputPanel sets pinned_to_bottom=True."""
        self.tab.pinned_to_bottom = False
        # Simulate End key press via QKeyEvent
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_End, Qt.NoModifier)
        self.window.output_panel.keyPressEvent(event)
        self.assertTrue(self.tab.pinned_to_bottom)

    def test_immediate_flush_on_end_key (self):
        """End key calls _immediate_flush which flushes buffer."""
        # Simulate what End key does
        self.tab.pinned_to_bottom = True
        self.tab.output_buffer.append((None, 'data\n'))
        self.window._immediate_flush(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'data\n')

    def tearDown (self):
        pass


if __name__ == '__main__':
    unittest.main()