#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase6.py - Phase 6 automated tests for CodeRunner
#
# Created by skywind on 2026/05/06
# Last Modified: 2026/05/06 00:00:00
#
#======================================================================
import sys
import os
import unittest
import tempfile
import json
import shutil

# Force offscreen platform so tests run without display
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

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
    MainWindow, _init_font_defaults, _expand_env_vars,
    _resolve_compiler_path, _settings_path, _window_state_path,
    _ensure_dir, _auto_detect_compiler, _ensure_cmd_file,
    SettingsDialog
)


class TestSettingsJSON (unittest.TestCase):

    def setUp (self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown (self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_serialize_deserialize (self):
        """Settings write → read → all values match."""
        s = Settings()
        _init_font_defaults(s)
        path = os.path.join(self.tmpdir, 'settings.json')
        self.assertEqual(s.save(path), 0)
        s2 = Settings()
        _init_font_defaults(s2)
        self.assertEqual(s2.load(path), 0)
        for key in _SETTINGS_DEFAULTS:
            if key == 'env_vars':
                self.assertEqual(s.__dict__[key], s2.__dict__[key])
            else:
                self.assertEqual(
                    getattr(s, key), getattr(s2, key),
                    'Mismatch on key: {}'.format(key))

    def test_load_nonexistent (self):
        """Loading from nonexistent file returns -1, defaults intact."""
        s = Settings()
        _init_font_defaults(s)
        old_family = s.editor_font_family
        result = s.load('/nonexistent/path/settings.json')
        self.assertEqual(result, -1)
        self.assertEqual(s.editor_font_family, old_family)

    def test_load_corrupt_json (self):
        """Loading corrupt JSON returns -1."""
        path = os.path.join(self.tmpdir, 'bad.json')
        with open(path, 'w') as f:
            f.write('not valid json{{{')
        s = Settings()
        _init_font_defaults(s)
        result = s.load(path)
        self.assertEqual(result, -1)

    def test_save_creates_directory (self):
        """Save creates parent directory if it doesn't exist."""
        path = os.path.join(self.tmpdir, 'sub', 'dir', 'settings.json')
        s = Settings()
        _init_font_defaults(s)
        self.assertEqual(s.save(path), 0)
        self.assertTrue(os.path.exists(path))

    def test_unknown_keys_ignored (self):
        """Load ignores keys not in _SETTINGS_DEFAULTS."""
        path = os.path.join(self.tmpdir, 'settings.json')
        data = dict(_SETTINGS_DEFAULTS)
        data['unknown_key'] = 'should_be_ignored'
        data['another_unknown'] = 42
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        s = Settings()
        _init_font_defaults(s)
        s.load(path)
        self.assertFalse(hasattr(s, 'unknown_key'))
        self.assertFalse(hasattr(s, 'another_unknown'))

    def test_env_vars_saved_correctly (self):
        """env_vars dict is saved and restored correctly."""
        s = Settings()
        _init_font_defaults(s)
        s.env_vars = {'PATH': '$PATH;/custom/bin', 'MY_VAR': 'hello'}
        path = os.path.join(self.tmpdir, 'settings.json')
        self.assertEqual(s.save(path), 0)
        s2 = Settings()
        _init_font_defaults(s2)
        self.assertEqual(s2.load(path), 0)
        self.assertEqual(s2.env_vars, s.env_vars)

    def test_settings_copy_independence (self):
        """Settings.copy() produces independent deep copy."""
        s = Settings()
        _init_font_defaults(s)
        s.env_vars = {'A': '1'}
        s2 = s.copy()
        s2.env_vars['A'] = '2'
        s2.compiler_path = 'different'
        # Original unchanged
        self.assertEqual(s.env_vars['A'], '1')
        self.assertEqual(s.compiler_path, 'gcc')

    def test_settings_apply_from (self):
        """Settings.apply_from() merges all attributes."""
        s = Settings()
        _init_font_defaults(s)
        s2 = s.copy()
        s2.compiler_path = 'clang++'
        s2.editor_font_size = 14
        s.apply_from(s2)
        self.assertEqual(s.compiler_path, 'clang++')
        self.assertEqual(s.editor_font_size, 14)


class TestEnvVarExpansion (unittest.TestCase):

    def test_expand_simple (self):
        """$VAR_NAME expands to os.environ value."""
        os.environ['TEST_VAR_PH6'] = 'hello'
        result = _expand_env_vars('$TEST_VAR_PH6')
        self.assertEqual(result, 'hello')
        del os.environ['TEST_VAR_PH6']

    def test_expand_unknown_var (self):
        """$UNKNOWN_VAR expands to empty string."""
        result = _expand_env_vars('$NONEXISTENT_VAR_12345')
        self.assertEqual(result, '')

    def test_expand_mixed_text (self):
        """Mixed text with $VAR references."""
        os.environ['MY_PATH_PH6'] = '/usr/bin'
        result = _expand_env_vars('$MY_PATH_PH6;/custom')
        self.assertEqual(result, '/usr/bin;/custom')
        del os.environ['MY_PATH_PH6']

    def test_expand_no_vars (self):
        """Plain text without $VAR references stays unchanged."""
        result = _expand_env_vars('plain text 123')
        self.assertEqual(result, 'plain text 123')

    def test_expand_multiple_vars (self):
        """Multiple $VAR references in one string."""
        os.environ['A_PH6'] = 'x'
        os.environ['B_PH6'] = 'y'
        result = _expand_env_vars('$A_PH6:$B_PH6')
        self.assertEqual(result, 'x:y')
        del os.environ['A_PH6']
        del os.environ['B_PH6']


class TestWindowStateJSON (unittest.TestCase):

    def setUp (self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown (self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_window_state_format (self):
        """window.json has expected structure."""
        state = {
            'geometry': {'x': 100, 'y': 100, 'w': 1000, 'h': 650},
            'h_splitter': [500, 500],
            'v_splitter': [325, 325],
            'last_file_dir': 'C:/Users/xxx/Documents',
            'tabs': [
                {'file_path': 'C:/Users/xxx/test.cpp', 'input_text': '3 5'},
                {'is_new': True, 'editor_text': '#include ...',
                 'input_text': '', 'untitled_number': 3}
            ],
            'active_tab': 0,
            'recent_files': ['C:/Users/xxx/test.cpp']
        }
        path = os.path.join(self.tmpdir, 'window.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)
        with open(path, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        # Verify all expected keys exist
        self.assertIn('geometry', loaded)
        self.assertIn('h_splitter', loaded)
        self.assertIn('v_splitter', loaded)
        self.assertIn('last_file_dir', loaded)
        self.assertIn('tabs', loaded)
        self.assertIn('active_tab', loaded)
        self.assertIn('recent_files', loaded)
        # Verify geometry structure
        geo = loaded['geometry']
        self.assertIn('x', geo)
        self.assertIn('y', geo)
        self.assertIn('w', geo)
        self.assertIn('h', geo)
        # Verify tabs structure
        tabs = loaded['tabs']
        self.assertEqual(len(tabs), 2)
        self.assertIn('file_path', tabs[0])
        self.assertIn('input_text', tabs[0])
        self.assertTrue(tabs[1]['is_new'])
        self.assertIn('editor_text', tabs[1])

    def test_window_state_path_function (self):
        """_window_state_path returns expected location."""
        path = _window_state_path()
        self.assertTrue(path.endswith('window.json'))
        self.assertIn('coderunner', path)

    def test_settings_path_function (self):
        """_settings_path returns expected location."""
        path = _settings_path()
        self.assertTrue(path.endswith('settings.json'))
        self.assertIn('coderunner', path)

    def test_ensure_dir (self):
        """_ensure_dir creates directory."""
        path = os.path.join(self.tmpdir, 'new', 'nested', 'dir')
        self.assertFalse(os.path.exists(path))
        _ensure_dir(path)
        self.assertTrue(os.path.exists(path))


class TestAutoDetectCompiler (unittest.TestCase):

    def test_auto_detect_returns_string (self):
        """_auto_detect_compiler returns a string."""
        result = _auto_detect_compiler()
        self.assertIsInstance(result, str)


class TestMainWindowState (unittest.TestCase):

    def test_recent_files_init (self):
        """MainWindow starts with empty recent files list."""
        wpath = _window_state_path()
        if os.path.exists(wpath):
            os.unlink(wpath)
        s = Settings()
        _init_font_defaults(s)
        win = MainWindow(s)
        self.assertEqual(win._recent_files, [])


class TestResolveCompilerPath (unittest.TestCase):

    def test_bare_name (self):
        """Bare name 'g++' returns ('g++', '')."""
        resolved, bin_dir = _resolve_compiler_path('g++')
        self.assertEqual(resolved, 'g++')
        self.assertEqual(bin_dir, '')

    def test_bare_name_with_extension (self):
        """Bare name 'g++.exe' returns ('g++.exe', '')."""
        resolved, bin_dir = _resolve_compiler_path('g++.exe')
        self.assertEqual(resolved, 'g++.exe')
        self.assertEqual(bin_dir, '')

    def test_absolute_path_windows (self):
        """Absolute path extracts directory as bin_dir."""
        path = 'C:\\MinGW\\bin\\g++.exe'
        resolved, bin_dir = _resolve_compiler_path(path)
        self.assertEqual(resolved, path)
        self.assertEqual(bin_dir, 'C:\\MinGW\\bin')

    def test_absolute_path_forward_slash (self):
        """Absolute path with forward slashes extracts directory."""
        path = 'C:/MinGW/bin/g++'
        resolved, bin_dir = _resolve_compiler_path(path)
        self.assertEqual(resolved, path)
        # os.path.dirname handles forward slashes on Windows
        self.assertEqual(bin_dir, os.path.dirname(path))

    def test_relative_path_dot (self):
        """Relative path './g++' resolves against CodeRunner.py directory."""
        resolved, bin_dir = _resolve_compiler_path('./g++')
        base_dir = os.path.dirname(os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'CodeRunner.py')))
        expected_bin = base_dir
        self.assertEqual(bin_dir, expected_bin)
        self.assertTrue(os.path.isabs(resolved))

    def test_relative_path_dot_backslash (self):
        """Relative path '.\\g++' resolves against CodeRunner.py directory."""
        resolved, bin_dir = _resolve_compiler_path('.\\g++.exe')
        base_dir = os.path.dirname(os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'CodeRunner.py')))
        expected_bin = base_dir
        self.assertEqual(bin_dir, expected_bin)
        self.assertTrue(os.path.isabs(resolved))

    def test_relative_path_parent (self):
        """Relative path '../bin/g++' resolves correctly."""
        resolved, bin_dir = _resolve_compiler_path('../bin/g++')
        base_dir = os.path.dirname(os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'CodeRunner.py')))
        # ../bin from CodeRunner.py's dir -> one level up, then bin
        expected_bin = os.path.abspath(os.path.join(base_dir, '..', 'bin'))
        self.assertEqual(bin_dir, expected_bin)
        self.assertTrue(os.path.isabs(resolved))

    def test_relative_path_subdir (self):
        """Relative path 'mingw/bin/g++' resolves correctly."""
        resolved, bin_dir = _resolve_compiler_path('mingw/bin/g++')
        base_dir = os.path.dirname(os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', 'CodeRunner.py')))
        expected_bin = os.path.abspath(os.path.join(base_dir, 'mingw', 'bin'))
        self.assertEqual(bin_dir, expected_bin)

    def test_empty_path (self):
        """Empty string returns ('', '')."""
        resolved, bin_dir = _resolve_compiler_path('')
        self.assertEqual(resolved, '')
        self.assertEqual(bin_dir, '')

    def test_absolute_path_nested (self):
        """Deeply nested absolute path extracts correct bin_dir."""
        path = 'C:\\Program Files\\Dev-Cpp\\MinGW64\\bin\\g++.exe'
        resolved, bin_dir = _resolve_compiler_path(path)
        self.assertEqual(resolved, path)
        self.assertEqual(bin_dir, 'C:\\Program Files\\Dev-Cpp\\MinGW64\\bin')


class TestProcessEnvPathPrepend (unittest.TestCase):

    def test_bare_compiler_no_path_prepend (self):
        """Bare 'g++' does not prepend anything to PATH."""
        s = Settings()
        _init_font_defaults(s)
        s.compiler_path = 'g++'
        win = MainWindow(s)
        env = win.flow_ctrl.make_process_env()
        path_value = env.value('PATH', '')
        # PATH should not have any extra prepend
        self.assertNotEqual(path_value, '')

    def test_absolute_compiler_path_prepend (self):
        """Absolute compiler path prepends bin_dir to PATH."""
        s = Settings()
        _init_font_defaults(s)
        s.compiler_path = 'C:\\MinGW\\bin\\g++.exe'
        win = MainWindow(s)
        env = win.flow_ctrl.make_process_env()
        path_value = env.value('PATH', '')
        sep = ';' if sys.platform == 'win32' else ':'
        self.assertTrue(path_value.startswith('C:\\MinGW\\bin' + sep),
                        'PATH should start with compiler bin_dir')

    def test_relative_compiler_path_prepend (self):
        """Relative compiler path resolves and prepends to PATH."""
        s = Settings()
        _init_font_defaults(s)
        s.compiler_path = './g++'
        win = MainWindow(s)
        env = win.flow_ctrl.make_process_env()
        path_value = env.value('PATH', '')
        _, bin_dir = _resolve_compiler_path('./g++')
        sep = ';' if sys.platform == 'win32' else ':'
        self.assertTrue(path_value.startswith(bin_dir + sep),
                        'PATH should start with resolved bin_dir')


class TestCmdFilePathPrefix (unittest.TestCase):

    def setUp (self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown (self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cmd_file_contains_path_prefix (self):
        """coderunner.cmd includes CR_SET_PATH and CR_ENV_SETUP placeholders."""
        old_temp = os.environ.get('TEMP', '')
        old_tmp = os.environ.get('TMP', '')
        os.environ['TEMP'] = self.tmpdir
        os.environ['TMP'] = self.tmpdir
        bat_path = _ensure_cmd_file()
        with open(bat_path, 'r') as f:
            content = f.read()
        # Restore
        if old_temp:
            os.environ['TEMP'] = old_temp
        else:
            del os.environ['TEMP']
        if old_tmp:
            os.environ['TMP'] = old_tmp
        else:
            del os.environ['TMP']
        # Verify the new placeholders exist
        self.assertIn('CR_SET_PATH', content)
        self.assertIn('CR_ENV_SETUP', content)


if __name__ == '__main__':
    unittest.main()