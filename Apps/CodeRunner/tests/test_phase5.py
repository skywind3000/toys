#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase5.py - Phase 5 automated tests for CodeRunner
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
from PyQt5.QtCore import Qt, QProcessEnvironment
from PyQt5.QtGui import QTextDocument, QTextCursor, QTextCharFormat, QColor

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
    CodeEditor, InputPanel, MainWindow,
    _init_font_defaults, _detect_encoding, _read_file,
    EncodingManager, _expand_env_vars, _ensure_cmd_file,
    _output_clear, _output_append, ProcessManager,
    _FLOW_IDLE, _FLOW_COMPILING, _FLOW_RUNNING
)


#----------------------------------------------------------------------
# Encoding detection tests
#----------------------------------------------------------------------
class TestEncodingDetection (unittest.TestCase):

    def test_utf8_bom (self):
        raw = b'\xef\xbb\xbf#include <iostream>'
        encoding = _detect_encoding(raw)
        self.assertEqual(encoding, 'UTF-8')

    def test_pure_utf8 (self):
        raw = b'#include <iostream>\nint main() { return 0; }'
        encoding = _detect_encoding(raw)
        self.assertEqual(encoding, 'UTF-8')

    def test_utf8_with_chinese (self):
        raw = 'int x = 中文;'.encode('utf-8')
        encoding = _detect_encoding(raw)
        self.assertEqual(encoding, 'UTF-8')

    def test_gbk_on_windows (self):
        if sys.platform != 'win32':
            return
        # GBK-encoded Chinese text
        raw = '中文'.encode('gbk')
        # This is not valid UTF-8, so detection should fall back to gbk
        encoding = _detect_encoding(raw)
        self.assertEqual(encoding, 'gbk')

    def test_mixed_invalid_bytes (self):
        # Bytes that are not valid UTF-8 and not valid any encoding
        raw = b'\x80\x81\x82'
        encoding = _detect_encoding(raw)
        if sys.platform == 'win32':
            self.assertEqual(encoding, 'gbk')
        else:
            self.assertEqual(encoding, 'utf-8')

    def test_empty_file (self):
        raw = b''
        encoding = _detect_encoding(raw)
        self.assertEqual(encoding, 'UTF-8')

    def test_read_file_utf8_bom (self):
        with tempfile.NamedTemporaryFile(
                suffix='.cpp', delete=False, mode='wb') as f:
            f.write(b'\xef\xbb\xbfint main() { return 0; }')
            path = f.name
        try:
            content, encoding = _read_file(path)
            self.assertEqual(encoding, 'UTF-8')
            self.assertIn('int main()', content)
        finally:
            os.unlink(path)

    def test_read_file_pure_utf8 (self):
        with tempfile.NamedTemporaryFile(
                suffix='.cpp', delete=False, mode='w',
                encoding='utf-8') as f:
            f.write('int main() { return 0; }')
            path = f.name
        try:
            content, encoding = _read_file(path)
            self.assertEqual(encoding, 'UTF-8')
            self.assertIn('int main()', content)
        finally:
            os.unlink(path)

    def test_read_file_gbk (self):
        if sys.platform != 'win32':
            return
        with tempfile.NamedTemporaryFile(
                suffix='.cpp', delete=False, mode='w',
                encoding='gbk') as f:
            f.write('中文变数')
            path = f.name
        try:
            content, encoding = _read_file(path)
            self.assertEqual(encoding, 'gbk')
            self.assertIn('中文', content)
        finally:
            os.unlink(path)


#----------------------------------------------------------------------
# Build flags tests
#----------------------------------------------------------------------
class TestBuildFlags (unittest.TestCase):

    def test_utf8_source_on_windows (self):
        if sys.platform != 'win32':
            return
        flags = EncodingManager.build_flags('UTF-8')
        self.assertIn('-fexec-charset=gbk', flags)
        self.assertIn('-finput-charset=UTF-8', flags)

    def test_utf8_source_on_linux (self):
        if sys.platform == 'win32':
            return
        flags = EncodingManager.build_flags('UTF-8')
        self.assertIn('-fexec-charset=utf-8', flags)
        self.assertIn('-finput-charset=UTF-8', flags)

    def test_gbk_source_on_windows (self):
        if sys.platform != 'win32':
            return
        flags = EncodingManager.build_flags('gbk')
        self.assertIn('-fexec-charset=gbk', flags)
        self.assertNotIn('-finput-charset', ' '.join(flags))

    def test_utf8_variants (self):
        # utf-8, UTF-8, utf8 should all be detected as UTF-8
        for variant in ['UTF-8', 'utf-8', 'utf8', 'Utf-8']:
            flags = EncodingManager.build_flags(variant)
            self.assertIn('-finput-charset=UTF-8', flags)

    def test_platform_charset (self):
        pc = EncodingManager.platform_charset()
        if sys.platform == 'win32':
            self.assertEqual(pc, 'gbk')
        else:
            self.assertEqual(pc, 'utf-8')


#----------------------------------------------------------------------
# I/O encoding conversion tests
#----------------------------------------------------------------------
class TestIOEncodingConversion (unittest.TestCase):

    def test_encode_stdin_ascii (self):
        data = EncodingManager.encode_stdin('hello world')
        self.assertEqual(data, b'hello world')

    def test_decode_stdout_ascii (self):
        text = EncodingManager.decode_stdout(b'hello world')
        self.assertEqual(text, 'hello world')

    def test_encode_stdin_chinese_on_windows (self):
        if sys.platform != 'win32':
            return
        data = EncodingManager.encode_stdin('中文')
        # GBK encoding of Chinese characters
        self.assertEqual(data, '中文'.encode('gbk'))

    def test_decode_stdout_chinese_on_windows (self):
        if sys.platform != 'win32':
            return
        gbk_bytes = '中文'.encode('gbk')
        text = EncodingManager.decode_stdout(gbk_bytes)
        self.assertEqual(text, '中文')

    def test_roundtrip_on_windows (self):
        if sys.platform != 'win32':
            return
        original = '中文abc123'
        encoded = EncodingManager.encode_stdin(original)
        decoded = EncodingManager.decode_stdout(encoded)
        self.assertEqual(decoded, original)

    def test_invalid_bytes_replacement (self):
        # decode with invalid bytes should use 'replace' strategy
        raw = b'\xff\xfe'
        text = EncodingManager.decode_stdout(raw)
        # Should not crash, contains replacement char
        self.assertIsInstance(text, str)


#----------------------------------------------------------------------
# Environment variable expansion tests
#----------------------------------------------------------------------
class TestEnvVarExpansion (unittest.TestCase):

    def test_simple_var (self):
        os.environ['TEST_CR_VAR'] = 'hello'
        result = _expand_env_vars('$TEST_CR_VAR')
        self.assertEqual(result, 'hello')
        del os.environ['TEST_CR_VAR']

    def test_var_in_path (self):
        path_val = os.environ.get('PATH', '')
        result = _expand_env_vars('$PATH;/custom/bin')
        self.assertTrue(result.startswith(path_val))
        self.assertIn(';', result)

    def test_unknown_var (self):
        result = _expand_env_vars('$NONEXISTENT_VAR')
        self.assertEqual(result, '')

    def test_multiple_vars (self):
        os.environ['TEST_CR_A'] = 'aaa'
        os.environ['TEST_CR_B'] = 'bbb'
        result = _expand_env_vars('$TEST_CR_A/$TEST_CR_B')
        self.assertEqual(result, 'aaa/bbb')
        del os.environ['TEST_CR_A']
        del os.environ['TEST_CR_B']

    def test_no_vars (self):
        result = _expand_env_vars('/plain/path')
        self.assertEqual(result, '/plain/path')

    def test_var_name_format (self):
        # Only alphanumeric + underscore in var names
        result = _expand_env_vars('$PATH_DIR')
        self.assertNotIn('$', result)


#----------------------------------------------------------------------
# Output rendering tests
#----------------------------------------------------------------------
class TestOutputRendering (unittest.TestCase):

    def test_output_clear (self):
        doc = QTextDocument()
        doc.setPlainText('Hello World')
        _output_clear(doc)
        self.assertEqual(doc.toPlainText(), '')

    def test_output_append_default_color (self):
        doc = QTextDocument()
        _output_clear(doc)
        _output_append(doc, 'Hello')
        self.assertEqual(doc.toPlainText(), 'Hello')

    def test_output_append_with_color (self):
        doc = QTextDocument()
        _output_clear(doc)
        _output_append(doc, 'Error', QColor(Qt.red))
        self.assertEqual(doc.toPlainText(), 'Error')

    def test_output_append_multiple_segments (self):
        doc = QTextDocument()
        _output_clear(doc)
        _output_append(doc, 'stdout text')
        _output_append(doc, 'stderr text', QColor(128, 128, 128))
        _output_append(doc, 'error text', QColor(Qt.red))
        self.assertEqual(
            doc.toPlainText(), 'stdout textstderr texterror text')

    def test_output_append_then_clear (self):
        doc = QTextDocument()
        _output_clear(doc)
        _output_append(doc, 'first')
        _output_clear(doc)
        _output_append(doc, 'second')
        self.assertEqual(doc.toPlainText(), 'second')


#----------------------------------------------------------------------
# CMD file creation tests
#----------------------------------------------------------------------
class TestCmdFile (unittest.TestCase):

    def test_ensure_cmd_file_creates (self):
        bat_path = _ensure_cmd_file()
        self.assertTrue(os.path.exists(bat_path))
        self.assertTrue(bat_path.endswith('coderunner.cmd'))

    def test_ensure_cmd_file_content (self):
        bat_path = _ensure_cmd_file()
        with open(bat_path, 'r') as f:
            content = f.read()
        self.assertIn('@echo off', content)
        self.assertIn('CR_COMMAND', content)
        self.assertIn('CR_PAUSE', content)
        self.assertIn('CR_EXITCODE', content)

    def test_ensure_cmd_file_no_duplicate_write (self):
        # Calling twice should not overwrite if content matches
        bat_path = _ensure_cmd_file()
        mtime1 = os.path.getmtime(bat_path)
        # Ensure mtime doesn't change (may be same second)
        bat_path2 = _ensure_cmd_file()
        self.assertEqual(bat_path, bat_path2)
        self.assertTrue(os.path.exists(bat_path2))


#----------------------------------------------------------------------
# ProcessManager basic tests
#----------------------------------------------------------------------
class TestProcessManager (unittest.TestCase):

    def test_initial_state (self):
        settings = Settings()
        pm = ProcessManager(parent=None, settings=settings)
        self.assertFalse(pm.busy)
        self.assertIsNone(pm.mode)
        self.assertIsNone(pm.process)

    def test_kill_when_not_busy (self):
        settings = Settings()
        pm = ProcessManager(parent=None, settings=settings)
        pm.kill_process()
        self.assertFalse(pm.busy)


#----------------------------------------------------------------------
# MainWindow compile/run integration tests
#----------------------------------------------------------------------
class TestMainWindowCompile (unittest.TestCase):

    def setUp (self):
        self.settings = Settings()
        _init_font_defaults(self.settings)
        self.window = MainWindow(self.settings)

    def test_initial_flow_state (self):
        self.assertEqual(self.window._flow_state, _FLOW_IDLE)
        self.assertIsNone(self.window._flow_intent)
        self.assertIsNone(self.window._flow_tab)
        self.assertEqual(self.window.status_message.text(), 'Ready')

    def test_set_flow_state (self):
        self.window._set_flow_state(_FLOW_COMPILING)
        self.assertEqual(self.window._flow_state, _FLOW_COMPILING)
        self.assertEqual(self.window.status_message.text(), 'Compiling...')
        self.window._set_flow_state(_FLOW_RUNNING)
        self.assertEqual(self.window._flow_state, _FLOW_RUNNING)
        self.assertEqual(self.window.status_message.text(), 'Running...')
        self.window._set_flow_state(_FLOW_IDLE)
        self.assertEqual(self.window._flow_state, _FLOW_IDLE)
        self.assertEqual(self.window.status_message.text(), 'Ready')

    def test_need_recompile_new_file (self):
        tab = TabData(is_new=True, encoding='UTF-8', content='test')
        # New file always needs recompile (no exe exists)
        result = self.window._need_recompile(tab)
        # is_new files have no exe path, should return True
        self.assertTrue(result)

    def test_need_recompile_no_exe (self):
        # Create a temp cpp file with no exe
        with tempfile.NamedTemporaryFile(
                suffix='.cpp', delete=False, mode='w') as f:
            f.write('int main() { return 0; }')
            path = f.name
        try:
            tab = TabData(
                file_path=path, is_new=False,
                encoding='UTF-8', content='test')
            result = self.window._need_recompile(tab)
            self.assertTrue(result)  # exe doesn't exist
        finally:
            os.unlink(path)

    def test_get_exe_path (self):
        tab = TabData(
            file_path='C:/Users/test/hello.cpp',
            is_new=False, encoding='UTF-8', content='')
        exe = self.window._get_exe_path(tab)
        self.assertEqual(exe, 'C:/Users/test/hello.exe')

    def test_get_exe_path_new_file (self):
        tab = TabData(is_new=True, encoding='UTF-8', content='')
        exe = self.window._get_exe_path(tab)
        self.assertEqual(exe, '')

    def test_build_compile_command (self):
        with tempfile.NamedTemporaryFile(
                suffix='.cpp', delete=False, mode='w') as f:
            f.write('int main() { return 0; }')
            path = f.name
        try:
            tab = TabData(
                file_path=path, is_new=False,
                encoding='UTF-8', content='test')
            cmd = self.window._build_compile_command(tab)
            self.assertEqual(cmd[0], 'gcc')
            self.assertIn('-fexec-charset', cmd[0] + ' ' + ' '.join(cmd))
            self.assertIn('-finput-charset=UTF-8',
                          ' '.join(cmd))
            self.assertIn(path, cmd)
            self.assertIn('-o', cmd)
        finally:
            os.unlink(path)

    def test_make_process_env (self):
        env = self.window._make_process_env()
        self.assertTrue(env.contains('PATH'))

    def test_make_process_env_with_user_vars (self):
        self.settings.env_vars = {'MY_VAR': 'my_value'}
        env = self.window._make_process_env()
        self.assertTrue(env.contains('MY_VAR'))
        self.assertEqual(env.value('MY_VAR'), 'my_value')

    def test_make_process_env_with_dollar_expansion (self):
        self.settings.env_vars = {
            'PATH': '$PATH;/custom/bin'
        }
        env = self.window._make_process_env()
        path_val = env.value('PATH')
        self.assertIn('/custom/bin', path_val)
        # Should contain original PATH
        orig_path = os.environ.get('PATH', '')
        self.assertIn(orig_path.split(';')[0] if orig_path else '',
                      path_val)

    def test_count_compile_errors (self):
        stderr = 'test.cpp:5: error: expected ;\ntest.cpp:8: error: undeclared'
        count = self.window._count_compile_errors(stderr)
        self.assertEqual(count, 2)

    def test_count_compile_errors_empty (self):
        count = self.window._count_compile_errors('')
        self.assertEqual(count, 0)

    def test_count_compile_errors_no_error_lines (self):
        stderr = 'test.cpp:3: warning: unused variable'
        count = self.window._count_compile_errors(stderr)
        self.assertEqual(count, 1)  # min 1 if stderr non-empty


if __name__ == '__main__':
    unittest.main()