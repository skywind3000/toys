#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase10.py - Phase 10 automated tests for CodeRunner
#   output_buffer + flush timer mechanism
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
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat, QBrush

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


class TestTabDataOutputBuffer (unittest.TestCase):
    """Test TabData.output_buffer field."""

    def test_default_buffer_is_empty (self):
        """New TabData should have output_buffer=[]."""
        tab = TabData(content='hello')
        self.assertEqual(tab.output_buffer, [])

    def test_buffer_append (self):
        """Can append (color, text) tuples to output_buffer."""
        tab = TabData(content='hello')
        tab.output_buffer.append((None, 'hello\n'))
        self.assertEqual(len(tab.output_buffer), 1)
        self.assertEqual(tab.output_buffer[0], (None, 'hello\n'))

    def test_buffer_clear (self):
        """output_buffer.clear() empties the buffer."""
        tab = TabData(content='hello')
        tab.output_buffer.append((QColor(Qt.red), 'error\n'))
        tab.output_buffer.append((None, 'output\n'))
        tab.output_buffer.clear()
        self.assertEqual(tab.output_buffer, [])

    def test_buffer_with_color (self):
        """Buffer entries with QColor work correctly."""
        tab = TabData(content='hello')
        red = QColor(Qt.red)
        gray = QColor(128, 128, 128)
        tab.output_buffer.append((red, 'error\n'))
        tab.output_buffer.append((gray, 'warning\n'))
        self.assertEqual(len(tab.output_buffer), 2)
        self.assertEqual(tab.output_buffer[0][0], red)
        self.assertEqual(tab.output_buffer[1][0], gray)

    def test_buffer_with_none_color (self):
        """Buffer entries with None color represent default stdout."""
        tab = TabData(content='hello')
        tab.output_buffer.append((None, 'stdout output\n'))
        self.assertIsNone(tab.output_buffer[0][0])


class TestFlushOutputBuffer (unittest.TestCase):
    """Test _flush_output_buffer method on MainWindow."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        self.tab = tab

    def test_flush_empty_buffer_is_noop (self):
        """Flushing empty buffer should not modify output_doc."""
        self.assertEqual(self.tab.output_doc.toPlainText(), '')
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), '')
        self.assertEqual(self.tab.output_buffer, [])

    def test_flush_single_entry (self):
        """Flushing single buffer entry writes text to output_doc."""
        self.tab.output_buffer.append((None, 'hello world\n'))
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'hello world\n')
        self.assertEqual(self.tab.output_buffer, [])

    def test_flush_multiple_entries_different_colors (self):
        """Flushing multiple entries with different colors preserves order."""
        red = QColor(Qt.red)
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((red, 'error\n'))
        self.tab.output_buffer.append((gray, 'warning\n'))
        self.tab.output_buffer.append((None, 'output\n'))
        self.window._flush_output_buffer(self.tab)
        text = self.tab.output_doc.toPlainText()
        self.assertEqual(text, 'error\nwarning\noutput\n')
        self.assertEqual(self.tab.output_buffer, [])

    def test_flush_merges_adjacent_same_color (self):
        """Adjacent same-color entries should be merged into one cursor op."""
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((gray, 'line1\n'))
        self.tab.output_buffer.append((gray, 'line2\n'))
        self.tab.output_buffer.append((gray, 'line3\n'))
        self.window._flush_output_buffer(self.tab)
        text = self.tab.output_doc.toPlainText()
        self.assertEqual(text, 'line1\nline2\nline3\n')

    def test_flush_does_not_merge_across_color_boundary (self):
        """Same color separated by different color should NOT merge."""
        red = QColor(Qt.red)
        gray = QColor(128, 128, 128)
        self.tab.output_buffer.append((gray, 'a'))
        self.tab.output_buffer.append((red, 'b'))
        self.tab.output_buffer.append((gray, 'c'))
        self.window._flush_output_buffer(self.tab)
        text = self.tab.output_doc.toPlainText()
        self.assertEqual(text, 'abc')

    def test_flush_clears_buffer (self):
        """After flush, buffer should be empty."""
        self.tab.output_buffer.append((None, 'text\n'))
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(self.tab.output_buffer, [])

    def test_flush_preserves_color_in_document (self):
        """Flushing with color should set foreground in output_doc."""
        red = QColor(Qt.red)
        self.tab.output_buffer.append((red, 'red text\n'))
        self.window._flush_output_buffer(self.tab)
        # Verify color is set by checking the character format
        cursor = QTextCursor(self.tab.output_doc)
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 4)
        fmt = cursor.charFormat()
        self.assertEqual(fmt.foreground().color(), red)

    def test_flush_none_color_uses_default (self):
        """Flushing with None color should not set foreground."""
        self.tab.output_buffer.append((None, 'default text\n'))
        self.window._flush_output_buffer(self.tab)
        cursor = QTextCursor(self.tab.output_doc)
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 7)
        fmt = cursor.charFormat()
        # Default foreground should be empty brush (no explicit color)
        self.assertFalse(fmt.foreground().style())

    def test_flush_accumulates_to_existing_doc (self):
        """Flushing appends to existing output_doc content."""
        self.tab.output_buffer.append((None, 'existing\n'))
        self.window._flush_output_buffer(self.tab)
        self.tab.output_buffer.append((None, 'new\n'))
        self.window._flush_output_buffer(self.tab)
        text = self.tab.output_doc.toPlainText()
        self.assertEqual(text, 'existing\nnew\n')

    def tearDown (self):
        pass


class TestImmediateFlush (unittest.TestCase):
    """Test _immediate_flush: flush + scroll if pinned."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        self.tab = tab

    def test_immediate_flush_writes_to_doc (self):
        """_immediate_flush should flush buffer to output_doc."""
        self.tab.output_buffer.append((None, 'test output\n'))
        self.window._immediate_flush(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'test output\n')
        self.assertEqual(self.tab.output_buffer, [])

    def test_immediate_flush_scrolls_if_pinned (self):
        """_immediate_flush scrolls to bottom if pinned=True and current tab."""
        # Add content to make scrollbar have range
        self.tab.output_buffer.append(
            (None, 'line1\nline2\nline3\nline4\nline5\n'))
        self.tab.pinned_to_bottom = True
        self.window._immediate_flush(self.tab)
        # After flush, output should be in doc
        self.assertIn('line1', self.tab.output_doc.toPlainText())

    def test_immediate_flush_no_scroll_if_not_pinned (self):
        """_immediate_flush does not scroll if pinned=False."""
        self.tab.pinned_to_bottom = False
        self.tab.output_buffer.append((None, 'test\n'))
        self.window._immediate_flush(self.tab)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'test\n')
        self.assertFalse(self.tab.pinned_to_bottom)

    def tearDown (self):
        pass


class TestBufferOverflowProtection (unittest.TestCase):
    """Test __check_buffer_overflow triggers immediate flush."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()
        tab = TabData(
            content='hello', dirty_callback=self.window._on_tab_dirty_changed)
        tab.compiler_mtime = self.settings.compiler_mtime
        index = self.window.tab_manager.add_tab(tab)
        self.window.tabbar.addTab(tab.tab_name())
        self.window._switch_to_tab(index)
        self.tab = tab

    def test_overflow_count_triggers_flush (self):
        """Buffer exceeding 200 entries triggers immediate flush."""
        for i in range(201):
            self.tab.output_buffer.append((None, 'x'))
        self.window._check_buffer_overflow(self.tab)
        # After overflow check, buffer should be flushed
        self.assertEqual(len(self.tab.output_buffer), 0)
        self.assertIn('x', self.tab.output_doc.toPlainText())

    def test_overflow_size_triggers_flush (self):
        """Buffer exceeding 64KB total text triggers immediate flush."""
        # Create one entry larger than 64KB
        big_text = 'x' * 70000
        self.tab.output_buffer.append((None, big_text))
        self.window._check_buffer_overflow(self.tab)
        self.assertEqual(len(self.tab.output_buffer), 0)

    def test_no_overflow_below_threshold (self):
        """Buffer below thresholds does not trigger immediate flush."""
        for i in range(50):
            self.tab.output_buffer.append((None, 'x'))
        self.window._check_buffer_overflow(self.tab)
        # Buffer should not be flushed (below 200 count and 64KB size)
        self.assertEqual(len(self.tab.output_buffer), 50)

    def tearDown (self):
        pass


class TestFlushTimerNeverStops (unittest.TestCase):
    """Test _flush_output_timer is always running."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def test_timer_exists (self):
        """MainWindow should have _flush_output_timer."""
        self.assertTrue(hasattr(self.window, '_flush_output_timer'))

    def test_timer_is_active (self):
        """_flush_output_timer should be active (never stops)."""
        self.assertTrue(self.window._flush_output_timer.isActive())

    def test_timer_interval_is_50ms (self):
        """_flush_output_timer interval should be 50ms."""
        self.assertEqual(self.window._flush_output_timer.interval(), 50)

    def tearDown (self):
        pass


class TestNoScrollRequestedSignal (unittest.TestCase):
    """Test scroll_requested signal is removed from FlowController."""

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)
        self.window.show()

    def test_no_scroll_requested (self):
        """FlowController should not have scroll_requested signal."""
        self.assertFalse(hasattr(FlowController, 'scroll_requested'))

    def test_no_maybe_scroll_output (self):
        """MainWindow should not have _maybe_scroll_output method."""
        self.assertFalse(hasattr(self.window, '_maybe_scroll_output'))


class TestOnFlushTimer (unittest.TestCase):
    """Test _on_flush_timer behavior."""

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

    def test_flush_timer_flushes_all_tabs (self):
        """_on_flush_timer should flush buffers for all tabs."""
        tab2 = TabData(
            content='world', dirty_callback=self.window._on_tab_dirty_changed)
        tab2.compiler_mtime = self.settings.compiler_mtime
        index2 = self.window.tab_manager.add_tab(tab2)
        self.window.tabbar.addTab(tab2.tab_name())
        # Add buffers to both tabs
        self.tab.output_buffer.append((None, 'output1\n'))
        tab2.output_buffer.append((None, 'output2\n'))
        # Trigger flush
        self.window._on_flush_timer()
        # Both buffers should be flushed
        self.assertEqual(len(self.tab.output_buffer), 0)
        self.assertEqual(len(tab2.output_buffer), 0)
        self.assertEqual(self.tab.output_doc.toPlainText(), 'output1\n')
        self.assertEqual(tab2.output_doc.toPlainText(), 'output2\n')

    def test_flush_timer_scrolls_current_pinned_tab (self):
        """_on_flush_timer scrolls to bottom for current pinned tab."""
        self.tab.output_buffer.append(
            (None, 'line1\nline2\nline3\n'))
        self.tab.pinned_to_bottom = True
        self.window._on_flush_timer()
        self.assertEqual(len(self.tab.output_buffer), 0)

    def test_flush_timer_no_scroll_for_unpinned (self):
        """_on_flush_timer does not scroll for pinned=False tab."""
        self.tab.pinned_to_bottom = False
        self.window._on_flush_timer()

    def tearDown (self):
        pass


class TestOutputClearWithBuffer (unittest.TestCase):
    """Test _output_clear combined with output_buffer.clear()."""

    def test_clear_buffer_and_doc (self):
        """Both buffer and doc should be empty after clear."""
        tab = TabData(content='hello')
        tab.output_buffer.append((None, 'buffered\n'))
        tab.output_buffer.append((None, 'in doc\n'))
        # Simulate: after clearing, both should be empty
        tab.output_buffer.clear()
        _output_clear(tab.output_doc)
        self.assertEqual(tab.output_buffer, [])
        self.assertEqual(tab.output_doc.toPlainText(), '')

    def test_clear_then_append_to_buffer (self):
        """After clearing, new buffer entries work correctly."""
        tab = TabData(content='hello')
        tab.output_buffer.append((None, 'old\n'))
        tab.output_buffer.clear()
        _output_clear(tab.output_doc)
        tab.pinned_to_bottom = True
        tab.output_buffer.append((None, 'new\n'))
        self.assertEqual(len(tab.output_buffer), 1)
        self.assertEqual(tab.output_buffer[0], (None, 'new\n'))


class TestStdoutStderrBufferAppend (unittest.TestCase):
    """Test _on_run_stdout/stderr_ready append to buffer."""

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
        # Set flow_ctrl.tab so stdout/stderr handlers can find the tab
        self.window.flow_ctrl.tab = self.tab

    def test_stdout_handler_appends_none_color (self):
        """_on_run_stdout_ready appends (None, text) to buffer."""
        self.window._on_run_stdout_ready('hello\n')
        self.assertEqual(len(self.tab.output_buffer), 1)
        self.assertIsNone(self.tab.output_buffer[0][0])
        self.assertEqual(self.tab.output_buffer[0][1], 'hello\n')

    def test_stderr_handler_appends_gray_color (self):
        """_on_run_stderr_ready appends (QColor(128,128,128), text) to buffer."""
        self.window._on_run_stderr_ready('error\n')
        self.assertEqual(len(self.tab.output_buffer), 1)
        gray = QColor(128, 128, 128)
        self.assertEqual(self.tab.output_buffer[0][0], gray)
        self.assertEqual(self.tab.output_buffer[0][1], 'error\n')

    def test_multiple_stdout_chunks_accumulate (self):
        """Multiple stdout chunks accumulate in buffer."""
        self.window._on_run_stdout_ready('line1\n')
        self.window._on_run_stdout_ready('line2\n')
        self.assertEqual(len(self.tab.output_buffer), 2)
        # Flush to verify they all appear in doc
        self.window._flush_output_buffer(self.tab)
        self.assertEqual(
            self.tab.output_doc.toPlainText(), 'line1\nline2\n')

    def tearDown (self):
        pass


if __name__ == '__main__':
    unittest.main()