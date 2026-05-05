#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Benchmark: verify deferred + batch highlighting performance

import sys
import time

from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit
from PyQt5.QtGui import (QTextDocument, QSyntaxHighlighter,
                          QTextCharFormat, QBrush, QColor, QFont,
                          QTextCursor)
from PyQt5.QtCore import Qt, QRegularExpression, QTimer

_CPP_KEYWORDS = (
    'alignas|alignof|asm|auto|bool|break|case|catch|char|char8_t|char16_t|char32_t|'
    'class|compl|concept|const|consteval|constexpr|const_cast|continue|co_await|'
    'co_return|co_yield|decltype|default|delete|do|double|dynamic_cast|else|enum|'
    'explicit|export|extern|false|float|for|friend|goto|if|inline|int|long|mutable|'
    'namespace|new|noexcept|not|not_eq|nullptr|operator|or|or_eq|private|protected|'
    'public|register|reinterpret_cast|requires|return|short|signed|sizeof|static|'
    'static_assert|static_cast|struct|switch|template|this|thread_local|throw|true|'
    'try|typedef|typeid|typename|union|unsigned|using|virtual|void|volatile|while|'
    'xor|xor_eq|size_t|int8_t|int16_t|int32_t|int64_t|uint8_t|uint16_t|uint32_t|'
    'uint64_t|intptr_t|uintptr_t|ptrdiff_t'
)

_CPP_PREPROCESSOR = (
    'include|define|ifdef|ifndef|endif|if|elif|else|pragma|error|warning|'
    'defined|line|undef'
)

class CppHighlighter (QSyntaxHighlighter):

    def __init__ (self, parent=None, deferred=False):
        super().__init__(parent)
        self._rules = []
        self._deferred = deferred
        self._batch_block_number = 0
        self._batch_timer = None
        self._batch_editor = None
        self.__init_rules()

    def __init_rules (self):
        fmt_comment_single = QTextCharFormat()
        fmt_comment_single.setForeground(QBrush(QColor(0, 128, 0)))
        self._rules.append((
            QRegularExpression(r'//[^\n]*'), fmt_comment_single))
        fmt_string = QTextCharFormat()
        fmt_string.setForeground(QBrush(QColor(163, 21, 21)))
        self._rules.append((
            QRegularExpression(r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"'), fmt_string))
        fmt_char = QTextCharFormat()
        fmt_char.setForeground(QBrush(QColor(163, 21, 21)))
        self._rules.append((
            QRegularExpression(r"'[^'\\\n]*(?:\\.[^'\\\n]*)*'"), fmt_char))
        fmt_keyword = QTextCharFormat()
        fmt_keyword.setForeground(QBrush(QColor(0, 0, 255)))
        self._rules.append((
            QRegularExpression(r'\b(' + _CPP_KEYWORDS + r')\b'), fmt_keyword))
        fmt_preproc = QTextCharFormat()
        fmt_preproc.setForeground(QBrush(QColor(0, 0, 255)))
        self._rules.append((
            QRegularExpression(r'^#\s*(' + _CPP_PREPROCESSOR + r')\b'), fmt_preproc))
        fmt_number = QTextCharFormat()
        fmt_number.setForeground(QBrush(QColor(0, 0, 128)))
        self._rules.append((
            QRegularExpression(
                r'\b(0[xX][0-9a-fA-F]+[uUlL]*'
                r'|0[bB][01]+[uUlL]*'
                r'|[0-9]+(\.[0-9]*)?([eE][+-]?[0-9]+)?[fFlLuU]*'
                r')\b'), fmt_number))
        fmt_symbol = QTextCharFormat()
        fmt_symbol.setForeground(QBrush(QColor(0, 128, 128)))
        self._rules.append((
            QRegularExpression(
                r'(::|->|\.\*|->\*|<<=|>>=|<<|>>'
                r'|==|!=|<=|>=|&&|\|\|'
                r'|\+=|-=|\*=|/=|%=|&=|\|=|\^='
                r'|\+\+|--|\.\.\.'
                r'|[+\-*/%&|^~!=<>?:;,]'
                r')'), fmt_symbol))
        fmt_comment_multi = QTextCharFormat()
        fmt_comment_multi.setForeground(QBrush(QColor(0, 128, 0)))
        self._multi_start = QRegularExpression(r'/\*')
        self._multi_end = QRegularExpression(r'\*/')
        self._multi_fmt = fmt_comment_multi

    def highlightBlock (self, text):
        if self._deferred:
            self.__track_multiline_state(text)
            return
        for regex, fmt in self._rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart()
                length = match.capturedLength()
                self.__format_if_free(start, length, fmt)
        self.__highlight_multiline_comments(text)

    def __format_if_free (self, start, length, fmt):
        existing = self.format(start)
        fg = existing.foreground()
        if not fg.style() or fg.color() == QColor():
            self.setFormat(start, length, fmt)

    def __highlight_multiline_comments (self, text):
        start_state = self.previousBlockState()
        start_idx = 0
        if start_state != 1:
            match = self._multi_start.match(text)
            if match.hasMatch():
                start_idx = match.capturedStart()
            else:
                self.setCurrentBlockState(0)
                return
        end_match = self._multi_end.match(text, start_idx)
        if end_match.hasMatch():
            end_idx = end_match.capturedEnd()
            self.setFormat(start_idx, end_idx - start_idx, self._multi_fmt)
            self.setCurrentBlockState(0)
            next_start = self._multi_start.match(text, end_idx)
            if next_start.hasMatch():
                ns = next_start.capturedStart()
                next_end = self._multi_end.match(text, ns)
                if next_end.hasMatch():
                    ne = next_end.capturedEnd()
                    self.setFormat(ns, ne - ns, self._multi_fmt)
                else:
                    self.setFormat(ns, len(text) - ns, self._multi_fmt)
                    self.setCurrentBlockState(1)
        else:
            self.setFormat(start_idx, len(text) - start_idx, self._multi_fmt)
            self.setCurrentBlockState(1)

    def __track_multiline_state (self, text):
        start_state = self.previousBlockState()
        start_idx = 0
        if start_state != 1:
            match = self._multi_start.match(text)
            if match.hasMatch():
                start_idx = match.capturedStart()
            else:
                self.setCurrentBlockState(0)
                return
        end_match = self._multi_end.match(text, start_idx)
        if end_match.hasMatch():
            self.setCurrentBlockState(0)
            next_start = self._multi_start.match(text, end_match.capturedEnd())
            if next_start.hasMatch():
                next_end = self._multi_end.match(
                    text, next_start.capturedStart())
                if not next_end.hasMatch():
                    self.setCurrentBlockState(1)
        else:
            self.setCurrentBlockState(1)

    def start_batch_highlight (self, editor_widget, batch_size=100):
        if self._batch_timer is not None:
            self._batch_timer.stop()
            self._batch_timer = None
        self._deferred = False
        self._batch_block_number = 0
        self._batch_editor = editor_widget
        self._batch_size = batch_size
        self.__process_highlight_batch()

    def __process_highlight_batch (self):
        doc = self.document()
        block = doc.findBlockByNumber(self._batch_block_number)
        editor = self._batch_editor
        if not editor or not block.isValid():
            self._batch_timer = None
            self._batch_editor = None
            return
        count = 0
        editor.setUpdatesEnabled(False)
        while block.isValid() and count < self._batch_size:
            self.rehighlightBlock(block)
            block = block.next()
            count += 1
        editor.setUpdatesEnabled(True)
        if block.isValid():
            self._batch_block_number += count
            self._batch_timer = QTimer.singleShot(
                0, self.__process_highlight_batch)
        else:
            self._batch_timer = None
            self._batch_editor = None


class BenchWindow (QMainWindow):

    def __init__ (self):
        super().__init__()
        self.resize(1000, 650)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        font = QFont('Consolas', 11)
        self.editor.setFont(font)
        self.setCentralWidget(self.editor)
        self._phase = 0
        self._start_time = 0

    def run_old_bench (self):
        """Old approach: highlighter with full rehighlight at once."""
        file_path = r'e:\lab\workshop\system\inetbase.c'
        with open(file_path, 'rb') as f:
            raw = f.read()
        try:
            content = raw.decode('utf-8', 'strict')
        except UnicodeDecodeError:
            content = raw.decode('gbk', 'replace')

        print('\n=== OLD approach (full rehighlight) ===')
        self._start_time = time.time()

        doc = QTextDocument()
        doc.setDefaultFont(self.editor.font())
        doc.setPlainText(content)

        hl = CppHighlighter(doc)  # non-deferred

        self.editor.setUpdatesEnabled(False)
        self.editor.setDocument(doc)
        self.editor.setUpdatesEnabled(True)

        # Wait for layout+paint to complete (includes queued rehighlight)
        def done():
            total = time.time() - self._start_time
            print('Total time (old): {:.3f}s'.format(total))
            self._phase = 1
            # Clear editor for next test
            self.editor.setDocument(QTextDocument())
            QTimer.singleShot(500, self.run_new_bench)

        QTimer.singleShot(3000, done)

    def run_new_bench (self):
        """New approach: deferred + batch highlighting."""
        file_path = r'e:\lab\workshop\system\inetbase.c'
        with open(file_path, 'rb') as f:
            raw = f.read()
        try:
            content = raw.decode('utf-8', 'strict')
        except UnicodeDecodeError:
            content = raw.decode('gbk', 'replace')

        print('\n=== NEW approach (deferred + batch via timer) ===')
        self._start_time = time.time()

        doc = QTextDocument()
        doc.setDefaultFont(self.editor.font())
        doc.setPlainText(content)

        # Create highlighter in deferred mode (queued rehighlight will
        # process all blocks minimally at next event loop iteration)
        hl = CppHighlighter(doc, deferred=True)

        # Switch to tab (setDocument with deferred highlighter)
        self.editor.setUpdatesEnabled(False)
        self.editor.setDocument(doc)
        self.editor.setUpdatesEnabled(True)
        doc_visible_time = time.time()
        print('setDocument (no format spans): {:.3f}s'.format(
            doc_visible_time - self._start_time))

        # CRITICAL: use QTimer.singleShot(0) so the queued rehighlight
        # (from the constructor) is processed in deferred mode FIRST
        self._hl = hl
        QTimer.singleShot(0, self._start_batch)

    def _start_batch (self):
        hl = self._hl
        batch_start_time = time.time()
        print('Queued rehighlight done, batch starts at: {:.3f}s from start'.format(
            batch_start_time - self._start_time))
        hl.start_batch_highlight(self.editor, batch_size=100)

        def check_done():
            if hl._batch_timer is not None:
                QTimer.singleShot(500, check_done)
                return
            total = time.time() - self._start_time
            display_time = batch_start_time - self._start_time
            print('Document visible at: {:.3f}s (vs ~10s old)'.format(
                display_time))
            print('Total (including background highlight): {:.3f}s'.format(total))
            print('UI was responsive for {:.3f}s before first batch'.format(
                display_time))
            QApplication.instance().quit()

        QTimer.singleShot(200, check_done)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = BenchWindow()
    win.show()
    QTimer.singleShot(500, win.run_old_bench)
    app.exec_()


if __name__ == '__main__':
    main()