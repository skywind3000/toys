#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# test_phase4.py - Phase 4 automated tests for CodeRunner
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
from PyQt5.QtGui import (
    QTextDocument, QTextCursor, QTextCharFormat, QFont, QColor
)

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
    CodeEditor, InputPanel, MainWindow, CppHighlighter,
    _init_font_defaults, _detect_encoding, _read_file
)


#----------------------------------------------------------------------
# Encoding detection
#----------------------------------------------------------------------
class TestEncodingDetection (unittest.TestCase):

    def test_utf8_bom_detected (self):
        raw = b'\xef\xbb\xbf#include <iostream>'
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_pure_utf8_detected (self):
        raw = '#include <iostream>\n'.encode('utf-8')
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_utf8_with_chinese (self):
        raw = '// \xe4\xb8\xad\xe6\x96\x87\n'.encode('utf-8')
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_gbk_detected_when_not_utf8 (self):
        raw = b'\xd6\xd0\xce\xc4'
        if sys.platform == 'win32':
            self.assertEqual(_detect_encoding(raw), 'gbk')
        else:
            self.assertEqual(_detect_encoding(raw), 'utf-8')

    def test_empty_file_is_utf8 (self):
        raw = b''
        self.assertEqual(_detect_encoding(raw), 'UTF-8')

    def test_mixed_invalid_bytes (self):
        raw = b'hello \xff world'
        if sys.platform == 'win32':
            self.assertEqual(_detect_encoding(raw), 'gbk')
        else:
            self.assertEqual(_detect_encoding(raw), 'utf-8')


#----------------------------------------------------------------------
# Compile flags generation
#----------------------------------------------------------------------
class TestCompileFlags (unittest.TestCase):

    def test_utf8_source_flags (self):
        flags = self._build_flags('UTF-8')
        if sys.platform == 'win32':
            self.assertIn('-fexec-charset=gbk', flags)
        else:
            self.assertIn('-fexec-charset=utf-8', flags)
        self.assertIn('-finput-charset=UTF-8', flags)

    def test_gbk_source_flags (self):
        flags = self._build_flags('gbk')
        if sys.platform == 'win32':
            self.assertIn('-fexec-charset=gbk', flags)
        else:
            self.assertIn('-fexec-charset=utf-8', flags)
        self.assertNotIn('-finput-charset', flags)

    def test_utf8_lowercase (self):
        flags = self._build_flags('utf-8')
        self.assertIn('-finput-charset=UTF-8', flags)

    def _build_flags (self, source_encoding):
        flags = []
        platform_charset = 'gbk' if sys.platform == 'win32' else 'utf-8'
        flags.append('-fexec-charset={}'.format(platform_charset))
        if source_encoding.lower().replace('-', '') == 'utf8':
            flags.append('-finput-charset=UTF-8')
        return flags


#----------------------------------------------------------------------
# CppHighlighter rules
#----------------------------------------------------------------------
class TestCppHighlighter (unittest.TestCase):

    def _get_highlight_formats (self, doc, hl, block_number=0):
        """Extract highlight format ranges from block layout."""
        hl.rehighlight()
        block = doc.findBlockByNumber(block_number)
        return block.layout().additionalFormats()

    def test_keyword_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('int main() {}')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0 and f.length == 3:
                fg = f.format.foreground().color()
                self.assertEqual(fg.red(), 0)
                self.assertEqual(fg.blue(), 255)
                self.assertEqual(f.format.fontWeight(), QFont.Normal)
                return
        self.fail('No keyword format found at position 0')

    def test_preprocessor_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('#include <iostream>')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                # VC++ style: preprocessor is blue (0,0,255)
                self.assertEqual(fg.red(), 0)
                self.assertEqual(fg.blue(), 255)
                return
        self.fail('No preprocessor format found')

    def test_string_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('"hello world"')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.red(), 163)
                self.assertEqual(fg.green(), 21)
                return
        self.fail('No string format found')

    def test_single_line_comment (self):
        doc = QTextDocument()
        doc.setPlainText('// this is a comment')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                # VC++ style: comments are green (0,128,0)
                self.assertEqual(fg.green(), 128)
                return
        self.fail('No comment format found')

    def test_number_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('42')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.blue(), 128)
                return
        self.fail('No number format found')

    def test_keyword_priority_over_number (self):
        doc = QTextDocument()
        doc.setPlainText('return 0')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        found_kw = found_num = False
        for f in fmts:
            if f.start == 0 and f.length == 6:
                fg = f.format.foreground().color()
                self.assertEqual(fg.blue(), 255)
                found_kw = True
            if f.start == 7:
                fg = f.format.foreground().color()
                self.assertEqual(fg.blue(), 128)
                found_num = True
        self.assertTrue(found_kw, 'keyword not found')
        self.assertTrue(found_num, 'number not found')

    def test_multiline_comment_across_blocks (self):
        doc = QTextDocument()
        doc.setPlainText('/* start\nmiddle\nend */')
        hl = CppHighlighter(doc)
        hl.rehighlight()
        block0 = doc.findBlockByNumber(0)
        fmts0 = block0.layout().additionalFormats()
        self.assertTrue(len(fmts0) > 0)
        fg0 = fmts0[0].format.foreground().color()
        # VC++ style: comments are green (0,128,0)
        self.assertEqual(fg0.green(), 128)

    def test_char_literal_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText("'x'")
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.red(), 163)
                return
        self.fail('No char literal format found')

    def test_symbol_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('x = 42;')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 2 and f.length == 1:
                fg = f.format.foreground().color()
                # VC++ style: symbols are teal (0,128,128)
                self.assertEqual(fg.green(), 128)
                self.assertEqual(fg.blue(), 128)
                return
        self.fail('No symbol format found for =')

    def test_semicolon_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText(';')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.green(), 128)
                self.assertEqual(fg.blue(), 128)
                return
        self.fail('No symbol format found for ;')

    def test_hex_number_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('0xFF')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0 and f.length == 4:
                fg = f.format.foreground().color()
                self.assertEqual(fg.blue(), 128)
                return
        self.fail('No hex number format found')

    def test_binary_number_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('0b1010')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.blue(), 128)
                return
        self.fail('No binary number format found')

    def test_arrow_operator_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('p->x')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        for f in fmts:
            if f.start == 1 and f.length == 2:
                fg = f.format.foreground().color()
                # VC++ style: symbols are teal (0,128,128)
                self.assertEqual(fg.green(), 128)
                self.assertEqual(fg.blue(), 128)
                return
        self.fail('No symbol format found for ->')

    def test_keyword_inside_string_not_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('"int x"')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        # The entire string including "int" should be string-colored
        # (dark red 163,21,21), NOT keyword blue
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.red(), 163)
                self.assertEqual(fg.green(), 21)
                return
        self.fail('No string format found for keyword inside string')

    def test_keyword_inside_comment_not_highlighted (self):
        doc = QTextDocument()
        doc.setPlainText('// return 0')
        hl = CppHighlighter(doc)
        fmts = self._get_highlight_formats(doc, hl)
        # The entire comment should be comment-colored (green 0,128,0),
        # NOT keyword blue
        for f in fmts:
            if f.start == 0:
                fg = f.format.foreground().color()
                self.assertEqual(fg.green(), 128)
                return
        self.fail('No comment format found for keyword inside comment')


#----------------------------------------------------------------------
# Bracket completion
#----------------------------------------------------------------------
class TestBracketCompletion (unittest.TestCase):

    def setUp (self):
        self.editor = CodeEditor()
        self.editor.set_bracket_completion(True)
        self.editor.show()

    def test_bracket_open_paren (self):
        doc = QTextDocument()
        self.editor.setDocument(doc)
        self.editor._handle_bracket_open('(')
        text = self.editor.document().toPlainText()
        self.assertEqual(text, '()')

    def test_bracket_open_brace (self):
        doc = QTextDocument()
        self.editor.setDocument(doc)
        self.editor._handle_bracket_open('{')
        text = self.editor.document().toPlainText()
        self.assertEqual(text, '{}')

    def test_bracket_open_bracket (self):
        doc = QTextDocument()
        self.editor.setDocument(doc)
        self.editor._handle_bracket_open('[')
        text = self.editor.document().toPlainText()
        self.assertEqual(text, '[]')

    def test_bracket_open_double_quote (self):
        doc = QTextDocument()
        self.editor.setDocument(doc)
        self.editor._handle_bracket_open('"')
        text = self.editor.document().toPlainText()
        self.assertEqual(text, '""')

    def test_bracket_open_single_quote (self):
        doc = QTextDocument()
        self.editor.setDocument(doc)
        self.editor._handle_bracket_open("'")
        text = self.editor.document().toPlainText()
        self.assertEqual(text, "''")

    def test_bracket_close_skip (self):
        doc = QTextDocument()
        doc.setPlainText('()')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(1)
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_bracket_close(')')
        self.assertTrue(result)
        self.assertEqual(self.editor.textCursor().position(), 2)

    def test_bracket_close_no_skip (self):
        doc = QTextDocument()
        doc.setPlainText('a')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(0)
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_bracket_close(')')
        self.assertFalse(result)

    def test_bracket_completion_disabled (self):
        self.editor.set_bracket_completion(False)
        self.assertFalse(self.editor._bracket_completion_enabled)


#----------------------------------------------------------------------
# Smart backspace (batch-delete spaces at indent boundary)
#----------------------------------------------------------------------
class TestSmartBackspace (unittest.TestCase):

    def setUp (self):
        self.editor = CodeEditor()
        self.editor.indent_size = 4
        self.editor.show()

    def test_batch_delete_at_indent_boundary (self):
        doc = QTextDocument()
        doc.setPlainText('        int x;')  # 8 spaces
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(8)  # col=8, 8%4==0, all spaces left
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_backspace()
        self.assertTrue(result)
        text = self.editor.document().toPlainText()
        self.assertEqual(text, '    int x;')  # 4 spaces left

    def test_batch_delete_multiple_levels (self):
        doc = QTextDocument()
        doc.setPlainText('            return 0;')  # 12 spaces
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(12)  # col=12, 12%4==0
        self.editor.setTextCursor(cursor)
        self.editor._handle_backspace()
        text = self.editor.document().toPlainText()
        self.assertEqual(text, '        return 0;')  # 8 spaces

    def test_no_batch_at_non_boundary (self):
        doc = QTextDocument()
        doc.setPlainText('   int x;')  # 3 spaces (not at boundary)
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(3)  # col=3, 3%4!=0
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_backspace()
        self.assertFalse(result)

    def test_no_batch_with_non_space_prefix (self):
        doc = QTextDocument()
        doc.setPlainText('abc     int x;')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(8)  # col=8, 8%4==0, but prefix 'abc     ' not all spaces
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_backspace()
        self.assertFalse(result)

    def test_no_batch_with_tab_in_prefix (self):
        doc = QTextDocument()
        doc.setPlainText('\t    int x;')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(5)  # prefix contains tab
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_backspace()
        self.assertFalse(result)

    def test_no_batch_at_col_zero (self):
        doc = QTextDocument()
        doc.setPlainText('    int x;')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(0)  # col=0, nothing to delete
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_backspace()
        self.assertFalse(result)

    def test_batch_delete_with_selection_does_not_trigger (self):
        doc = QTextDocument()
        doc.setPlainText('        int x;')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(4)
        cursor.setPosition(8, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        result = self.editor._handle_backspace()
        self.assertFalse(result)


#----------------------------------------------------------------------
# Overwrite mode
#----------------------------------------------------------------------
class TestOverwriteMode (unittest.TestCase):

    def setUp (self):
        self.editor = CodeEditor()
        self.editor.show()

    def test_initial_mode_is_insert (self):
        self.assertFalse(self.editor.overwrite_mode)

    def test_toggle_overwrite_mode (self):
        self.editor.overwrite_mode = True
        self.assertTrue(self.editor.overwrite_mode)
        self.editor.overwrite_mode = False
        self.assertFalse(self.editor.overwrite_mode)

    def test_overwrite_char (self):
        doc = QTextDocument()
        doc.setPlainText('abc')
        self.editor.setDocument(doc)
        self.editor.overwrite_mode = True
        cursor = self.editor.textCursor()
        cursor.setPosition(0)
        self.editor.setTextCursor(cursor)
        cursor.beginEditBlock()
        if not cursor.atBlockEnd():
            cursor.deleteChar()
        cursor.insertText('x')
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        text = self.editor.document().toPlainText()
        self.assertEqual(text, 'xbc')

    def test_overwrite_at_end_of_line (self):
        doc = QTextDocument()
        doc.setPlainText('ab')
        self.editor.setDocument(doc)
        self.editor.overwrite_mode = True
        cursor = self.editor.textCursor()
        cursor.setPosition(2)
        self.editor.setTextCursor(cursor)
        cursor.beginEditBlock()
        if not cursor.atBlockEnd():
            cursor.deleteChar()
        cursor.insertText('x')
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        text = self.editor.document().toPlainText()
        self.assertEqual(text, 'abx')


#----------------------------------------------------------------------
# Auto indent
#----------------------------------------------------------------------
class TestAutoIndent (unittest.TestCase):

    def setUp (self):
        self.editor = CodeEditor()
        self.editor.show()

    def test_extract_indent_spaces (self):
        indent = self.editor._CodeEditor__extract_indent('    int x;')
        self.assertEqual(indent, '    ')

    def test_extract_indent_tabs (self):
        indent = self.editor._CodeEditor__extract_indent('\tint x;')
        self.assertEqual(indent, '\t')

    def test_extract_indent_empty (self):
        indent = self.editor._CodeEditor__extract_indent('int x;')
        self.assertEqual(indent, '')

    def test_extract_indent_mixed (self):
        indent = self.editor._CodeEditor__extract_indent('  \t  int x;')
        self.assertEqual(indent, '  \t  ')

    def test_enter_preserves_indent (self):
        doc = QTextDocument()
        doc.setPlainText('    int x')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.editor.setTextCursor(cursor)
        self.editor._handle_enter_key()
        text = self.editor.document().toPlainText()
        lines = text.split('\n')
        self.assertTrue(lines[1].startswith('    '))
        self.assertEqual(lines[1].strip(), '')

    def test_enter_after_brace_adds_indent (self):
        self.editor.indent_style = 'space'
        self.editor.indent_size = 4
        doc = QTextDocument()
        doc.setPlainText('    {')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.editor.setTextCursor(cursor)
        self.editor._handle_enter_key()
        text = self.editor.document().toPlainText()
        lines = text.split('\n')
        self.assertTrue(lines[1].startswith('        '))

    def test_enter_after_brace_with_closing_tab (self):
        doc = QTextDocument()
        doc.setPlainText('{}')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(1)
        self.editor.setTextCursor(cursor)
        self.editor._handle_enter_key()
        text = self.editor.document().toPlainText()
        lines = text.split('\n')
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], '{')
        self.assertEqual(lines[1], '\t')
        self.assertEqual(lines[2], '}')

    def test_enter_after_brace_with_closing_space (self):
        self.editor.indent_style = 'space'
        self.editor.indent_size = 4
        doc = QTextDocument()
        doc.setPlainText('{}')
        self.editor.setDocument(doc)
        cursor = self.editor.textCursor()
        cursor.setPosition(1)
        self.editor.setTextCursor(cursor)
        self.editor._handle_enter_key()
        text = self.editor.document().toPlainText()
        lines = text.split('\n')
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], '{')
        self.assertEqual(lines[1], '    ')
        self.assertEqual(lines[2], '}')


#----------------------------------------------------------------------
# TabData highlighter attachment
#----------------------------------------------------------------------
class TestHighlighterAttachment (unittest.TestCase):

    def test_tabdata_has_highlighter (self):
        tab = TabData(is_new=True, content='int main() {}')
        self.assertIsNotNone(tab.highlighter)
        self.assertIsInstance(tab.highlighter, CppHighlighter)

    def test_highlighter_attached_to_editor_doc (self):
        tab = TabData(is_new=True, content='int main() {}')
        self.assertIs(tab.highlighter.document(), tab.editor_doc)

    def test_highlighter_reformats_on_content (self):
        tab = TabData(is_new=True, content='int x = 42;')
        tab.highlighter.rehighlight()
        block = tab.editor_doc.firstBlock()
        fmts = block.layout().additionalFormats()
        self.assertTrue(len(fmts) > 0)
        fg = fmts[0].format.foreground().color()
        self.assertEqual(fg.blue(), 255)


#----------------------------------------------------------------------
# IO encoding conversion
#----------------------------------------------------------------------
class TestIOEncodingConversion (unittest.TestCase):

    def test_platform_charset (self):
        charset = 'gbk' if sys.platform == 'win32' else 'utf-8'
        text = 'hello'
        encoded = text.encode(charset)
        decoded = encoded.decode(charset)
        self.assertEqual(decoded, text)

    def test_chinese_roundtrip_gbk (self):
        if sys.platform != 'win32':
            return
        text = '中文'  # 中文
        encoded = text.encode('gbk')
        decoded = encoded.decode('gbk')
        self.assertEqual(decoded, text)

    def test_chinese_roundtrip_utf8 (self):
        text = '中文'
        encoded = text.encode('utf-8')
        decoded = encoded.decode('utf-8')
        self.assertEqual(decoded, text)


#----------------------------------------------------------------------
# Environment variable expansion
#----------------------------------------------------------------------
class TestEnvVarExpansion (unittest.TestCase):

    def test_simple_var_expansion (self):
        env = {'PATH': '$PATH;/custom/bin'}
        old_path = os.environ.get('PATH', '')
        expanded = env['PATH'].replace('$PATH', old_path)
        self.assertIn(old_path, expanded)
        self.assertIn('/custom/bin', expanded)

    def test_no_var_syntax (self):
        env = {'HOME': '/home/user'}
        self.assertEqual(env['HOME'], '/home/user')


if __name__ == '__main__':
    unittest.main()