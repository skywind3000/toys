#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# CodeEditor.py - Code Editor Widget with Editing Extensions
#
# Created by skywind on 2026/05/07
# Last Modified: 2026/05/07 22:00:00
#
#======================================================================
import sys, os

from PyQt5.QtWidgets import (
    QTextEdit, QWidget, QAction, QMenu
)
from PyQt5.QtCore import (
    Qt, QSize, QRect, pyqtSignal
)
from PyQt5.QtGui import (
    QPainter, QColor, QBrush, QTextCursor, QTextCharFormat,
    QKeySequence
)


#----------------------------------------------------------------------
# FileDragMixin — ignore URL drag-drop, pass text drag-drop through
#----------------------------------------------------------------------
class FileDragMixin:
    """Mixin that ignores URL drag-drop while passing text drag-drop
    to the QTextEdit default behavior. Useful when the parent window
    handles file drops separately."""

    def dragEnterEvent (self, event):
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent (self, event):
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dragMoveEvent(event)

    def dropEvent (self, event):
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dropEvent(event)


#----------------------------------------------------------------------
# LineNumberArea — left margin widget that paints line numbers
#----------------------------------------------------------------------
class LineNumberArea (QWidget):

    def __init__ (self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent (self, event):
        self.editor._paint_line_numbers(event)

    def sizeHint (self):
        return QSize(self.editor._line_number_width(), 0)


#----------------------------------------------------------------------
# CodeEditor (uses QTextEdit for setDocument compatibility)
#----------------------------------------------------------------------
class CodeEditor (FileDragMixin, QTextEdit):

    overwriteModeChanged = pyqtSignal(bool)

    _LINE_NUM_COLOR = QColor(120, 120, 120)
    _LINE_NUM_BG = QColor(235, 235, 235)

    _BRACKET_OPEN = {'(': ')', '{': '}', '[': ']', '"': '"', "'": "'"}
    _BRACKET_CLOSE = {')': '(', '}': '{', ']': '['}
    _CURRENT_LINE_COLOR = QColor(245, 245, 220)
    _BRACKET_MATCH_COLOR = QColor(180, 220, 255)

    _EDIT_ACTION_DEFS = [
        # (attr_name, label, shortcut, method_name)
        ('act_comment', 'Comment/Uncomment', 'Ctrl+/', '_handle_comment_uncomment'),
        ('act_indent', 'Indent', 'Ctrl+]', '_handle_indent_selection'),
        ('act_unindent', 'Unindent', 'Ctrl+[', '_handle_unindent_selection'),
        ('act_duplicate', 'Duplicate Line', 'Ctrl+D', '_handle_duplicate_line'),
        ('act_delete_line', 'Delete Line', 'Ctrl+Shift+K', '_handle_delete_line'),
        ('act_move_up', 'Move Line Up', 'Alt+Up', '_handle_move_line_up'),
        ('act_move_down', 'Move Line Down', 'Alt+Down', '_handle_move_line_down'),
    ]

    def __init__ (self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.indent_style = 'tab'
        self.indent_size = 4
        self._update_tab_width()
        self.line_number_area = LineNumberArea(self)
        self.overwrite_mode = False
        self._bracket_completion_enabled = True
        self._highlighter = None
        self._edit_actions = None
        self.document().blockCountChanged.connect(
            self._update_line_number_area_width)
        self.verticalScrollBar().valueChanged.connect(
            self.line_number_area.update)
        self._update_line_number_area_width()
        self.cursorPositionChanged.connect(self._update_extra_selections)

    #----- Edit Actions -----

    def createEditActions (self):
        """Create the 7 edit extension actions (comment, indent, etc).
        Call this once after construction. Actions are stored in
        self._edit_actions dict keyed by attr_name."""
        self._edit_actions = {}
        for attr, label, shortcut, method_name in self._EDIT_ACTION_DEFS:
            action = QAction(label, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.setToolTip('{} ({})'.format(label, shortcut))
            handler = getattr(self, method_name)
            action.triggered.connect(handler)
            setattr(self, attr, action)
            self._edit_actions[attr] = action

    def editActions (self) -> dict:
        """Return dict of edit extension actions {attr_name: QAction}."""
        if self._edit_actions is None:
            self.createEditActions()
        return self._edit_actions

    #----- Highlighter Injection -----

    def setHighlighter (self, highlighter):
        """Inject a syntax highlighter for bracket context detection.
        Used by _is_bracket_in_comment_or_string to check whether a
        bracket is inside a comment or string literal."""
        self._highlighter = highlighter

    #----- Tab Width & Line Numbers -----

    def _update_tab_width (self):
        # Tab width = indent_size characters. IMPORTANT: tab width (pixels)
        # depends on the current font's char width. Whenever font/size changes
        # (SettingsDialog, zoom), must call updateFontMetrics() to
        # recalculate tab width and sync document.setDefaultFont().
        self.setTabStopWidth(
            self.fontMetrics().horizontalAdvance('x') * self.indent_size)

    def _line_number_width (self) -> int:
        digits = 1
        count = max(1, self.document().blockCount())
        while count >= 10:
            count //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def _update_line_number_area_width (self):
        # Use isHidden() instead of isVisible() — isVisible() returns False
        # when parent window hasn't been shown yet (during __init__),
        # causing viewport margins to stay 0 after session restore.
        shown = not self.line_number_area.isHidden()
        width = self._line_number_width() if shown else 0
        margins = self.viewportMargins()
        self.setViewportMargins(
            width, margins.top(), margins.right(), margins.bottom())
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), width, cr.height()))
        self.line_number_area.update()

    def setDocument (self, doc):
        old_doc = self.document()
        if old_doc:
            try:
                old_doc.blockCountChanged.disconnect(
                    self._update_line_number_area_width)
            except (RuntimeError, TypeError):
                pass
        # Sync document's defaultFont to editor widget font, so that
        # tab stops and layout use the same font metrics. Without this,
        # the document uses its own defaultFont (often system default)
        # while setTabStopWidth is calculated from the editor font,
        # causing mismatch (e.g. 4-char tab appearing as 5 chars).
        doc.setDefaultFont(self.font())
        super().setDocument(doc)
        doc.blockCountChanged.connect(
            self._update_line_number_area_width)
        self._update_line_number_area_width()

    def resizeEvent (self, event):
        super().resizeEvent(event)
        self._update_line_number_area_width()

    def updateFontMetrics (self):
        """Refresh tab width, line number area, and document font."""
        self._update_tab_width()
        self._update_line_number_area_width()
        # Keep document's default font in sync with widget font
        # so layout and tab stops use the correct metrics
        doc = self.document()
        if doc:
            doc.setDefaultFont(self.font())

    def setFontSize (self, point_size:int):
        """Set font point size and refresh metrics."""
        font = self.font()
        font.setPointSize(point_size)
        self.setFont(font)
        self.updateFontMetrics()

    def _estimate_first_visible_block (self) -> int:
        """Estimate first visible block number from scroll position
        and average block height. Avoids iterating from block 0 for
        large documents."""
        scroll_y = self.verticalScrollBar().value()
        if scroll_y <= 0:
            return 0
        layout = self.document().documentLayout()
        total_h = layout.documentSize().height()
        count = max(1, self.document().blockCount())
        avg = total_h / count
        if avg <= 0:
            return 0
        est = int(scroll_y / avg)
        return max(0, est - 5)

    def _paint_line_numbers (self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), self._LINE_NUM_BG)
        scroll_y = self.verticalScrollBar().value()
        start_num = self._estimate_first_visible_block()
        block = self.document().findBlockByNumber(start_num)
        while block.isValid():
            layout = self.document().documentLayout()
            block_rect = layout.blockBoundingRect(block)
            y = block_rect.y() - scroll_y
            height = block_rect.height()
            if y > event.rect().bottom():
                break
            if y + height >= event.rect().top():
                painter.setPen(self._LINE_NUM_COLOR)
                painter.drawText(
                    0, int(y), self._line_number_width() - 3,
                    int(height),
                    Qt.AlignRight | Qt.AlignVCenter,
                    str(block.blockNumber() + 1))
            block = block.next()
        painter.end()

    #----- Key Event Handling -----

    def keyPressEvent (self, event):
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Insert key toggles overwrite mode
        if key == Qt.Key_Insert:
            self.overwrite_mode = not self.overwrite_mode
            self._notify_overwrite_changed()
            return

        # Ctrl+/ — Comment/Uncomment
        if key == Qt.Key_Slash and modifiers == Qt.ControlModifier:
            self._handle_comment_uncomment()
            return

        # Ctrl+D — Duplicate line
        if key == Qt.Key_D and modifiers == Qt.ControlModifier:
            self._handle_duplicate_line()
            return

        # Ctrl+Shift+K — Delete line
        if key == Qt.Key_K and modifiers == (Qt.ControlModifier | Qt.ShiftModifier):
            self._handle_delete_line()
            return

        # Alt+Up/Alt+Down — Move line
        if key == Qt.Key_Up and modifiers == Qt.AltModifier:
            self._handle_move_line_up()
            return
        if key == Qt.Key_Down and modifiers == Qt.AltModifier:
            self._handle_move_line_down()
            return

        # Tab — indent selection or insert tab
        if key == Qt.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                self._handle_indent_selection()
            else:
                cursor.insertText('\t')
            return

        # Shift+Tab — unindent selection or current line
        if key == Qt.Key_Backtab:
            self._handle_unindent_selection()
            return

        # Enter key — auto indent
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._handle_enter_key()
            return

        # Backspace — smart space deletion and bracket deletion
        if key == Qt.Key_Backspace:
            if self._handle_backspace():
                return
            super().keyPressEvent(event)
            return

        # Bracket completion (extended: #include < and /* */)
        if text and self._bracket_completion_enabled:
            if text == '<':
                if self._handle_include_angle():
                    return
            if text == '*':
                if self._handle_star_for_comment_open():
                    return
            if text == '/':
                if self._handle_slash_for_comment():
                    return
            if text in self._BRACKET_OPEN:
                if self._handle_bracket_open(text):
                    return
                # In comment/string context, fall through to default input
            if text in self._BRACKET_CLOSE:
                if self._handle_bracket_close(text):
                    return

        # Overwrite mode: normal character input
        if text and self.overwrite_mode and key != Qt.Key_Backspace:
            cursor = self.textCursor()
            if not cursor.hasSelection():
                cursor.beginEditBlock()
                if not cursor.atBlockEnd():
                    cursor.deleteChar()
                cursor.insertText(text)
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    #----- Comment/Uncomment -----

    def _handle_comment_uncomment (self):
        """Toggle // comment on current line or selected lines."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            # If selection ends at start of a block, don't include that block
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block

        # Check if ALL lines are already commented
        all_commented = True
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            text = block.text()
            stripped = text.lstrip()
            # Empty/whitespace-only lines are not considered "commented"
            if not stripped:
                all_commented = False
                break
            if not stripped.startswith('//'):
                all_commented = False
                break
            block = block.next()

        cursor.beginEditBlock()
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            text = block.text()
            cursor_pos = block.position()
            if all_commented:
                # Remove // and all spaces immediately after it
                stripped_len = len(text) - len(text.lstrip())
                comment_start = stripped_len
                if text[comment_start:comment_start + 2] == '//':
                    remove_end = comment_start + 2
                    while remove_end < len(text) and text[remove_end] == ' ':
                        remove_end += 1
                    c = QTextCursor(doc)
                    c.setPosition(cursor_pos + comment_start)
                    c.setPosition(cursor_pos + remove_end,
                                  QTextCursor.KeepAnchor)
                    c.removeSelectedText()
            else:
                # Add "// " before first non-whitespace
                stripped_len = len(text) - len(text.lstrip())
                if stripped_len == len(text):
                    # Whitespace-only line — add // at start
                    c = QTextCursor(doc)
                    c.setPosition(cursor_pos)
                    c.insertText('// ')
                else:
                    c = QTextCursor(doc)
                    c.setPosition(cursor_pos + stripped_len)
                    c.insertText('// ')
            block = block.next()
        cursor.endEditBlock()

    #----- Indent/Unindent -----

    def _handle_indent_selection (self):
        """Indent current line or all selected lines by one level."""
        doc = self.document()
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        if has_selection:
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        indent_char = '\t' if self.indent_style == 'tab' else \
            ' ' * self.indent_size
        start_num = start_block.blockNumber()
        end_num = end_block.blockNumber()
        if not has_selection:
            cursor_col = cursor.position() - cursor.block().position()
        cursor.beginEditBlock()
        for i in range(start_num, end_num + 1):
            block = doc.findBlockByNumber(i)
            c = QTextCursor(doc)
            c.setPosition(block.position())
            c.insertText(indent_char)
        cursor.endEditBlock()
        if has_selection:
            # Linewise: anchor at block start, position at end of block
            # range, so repeated indent/unindent never drifts
            new_start = doc.findBlockByNumber(start_num).position()
            new_end_block = doc.findBlockByNumber(end_num)
            new_end = new_end_block.position() + new_end_block.length()
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_start)
            new_cursor.setPosition(new_end, QTextCursor.KeepAnchor)
            self.setTextCursor(new_cursor)
        else:
            new_block = doc.findBlockByNumber(start_num)
            new_pos = new_block.position() + cursor_col + len(indent_char)
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_pos)
            self.setTextCursor(new_cursor)

    def _handle_unindent_selection (self):
        """Unindent current line or all selected lines by one level."""
        doc = self.document()
        cursor = self.textCursor()
        has_selection = cursor.hasSelection()
        if has_selection:
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        start_num = start_block.blockNumber()
        end_num = end_block.blockNumber()
        if not has_selection:
            cursor_col = cursor.position() - cursor.block().position()
        removed_per_line = []
        for i in range(start_num, end_num + 1):
            block = doc.findBlockByNumber(i)
            text = block.text()
            remove_len = 0
            if text.startswith('\t'):
                remove_len = 1
            elif text.startswith(' ' * self.indent_size):
                remove_len = self.indent_size
            elif text.startswith(' '):
                count = 0
                for ch in text:
                    if ch == ' ' and count < self.indent_size:
                        count += 1
                    else:
                        break
                remove_len = count
            removed_per_line.append(remove_len)
        cursor.beginEditBlock()
        for i in range(start_num, end_num + 1):
            block = doc.findBlockByNumber(i)
            remove_len = removed_per_line[i - start_num]
            if remove_len > 0:
                c = QTextCursor(doc)
                c.setPosition(block.position())
                c.setPosition(
                    block.position() + remove_len,
                    QTextCursor.KeepAnchor)
                c.removeSelectedText()
        cursor.endEditBlock()
        if has_selection:
            # Linewise: anchor at block start, position at end of block
            # range, so repeated indent/unindent never drifts
            new_start = doc.findBlockByNumber(start_num).position()
            new_end_block = doc.findBlockByNumber(end_num)
            new_end = new_end_block.position() + new_end_block.length()
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_start)
            new_cursor.setPosition(new_end, QTextCursor.KeepAnchor)
            self.setTextCursor(new_cursor)
        else:
            removed = removed_per_line[0]
            new_block = doc.findBlockByNumber(start_num)
            new_col = max(0, cursor_col - removed)
            new_pos = new_block.position() + new_col
            new_cursor = QTextCursor(doc)
            new_cursor.setPosition(new_pos)
            self.setTextCursor(new_cursor)

    #----- Line Operations -----

    def _handle_duplicate_line (self):
        """Duplicate current line or selected lines below."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            text = cursor.selectedText()
            # QTextCursor.selectedText uses   as paragraph separator
            text = text.replace(' ', '\n')
            end_pos = cursor.selectionEnd()
            c = QTextCursor(doc)
            c.setPosition(end_pos)
            c.insertText('\n' + text)
        else:
            block = cursor.block()
            text = block.text()
            # block.length includes the trailing newline char
            c = QTextCursor(doc)
            c.setPosition(block.position() + block.length() - 1)
            c.insertText('\n' + text)

    def _handle_delete_line (self):
        """Delete current line or selected lines."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            # Include end block even if selection ends at block start
            last_pos = end_block.position() + end_block.length()
            c = QTextCursor(doc)
            c.setPosition(start_block.position())
            c.setPosition(last_pos, QTextCursor.KeepAnchor)
            c.removeSelectedText()
        else:
            block = cursor.block()
            c = QTextCursor(doc)
            c.setPosition(block.position())
            next_block = block.next()
            if next_block.isValid():
                c.setPosition(
                    next_block.position(), QTextCursor.KeepAnchor)
            else:
                # Last line — delete to end of document
                c.setPosition(
                    block.position() + block.length(),
                    QTextCursor.KeepAnchor)
            c.removeSelectedText()

    def _handle_move_line_up (self):
        """Move current line or selected lines up."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        prev_block = start_block.previous()
        if not prev_block.isValid():
            return
        # Swap prev_block with the range [start_block..end_block]
        cursor.beginEditBlock()
        # Collect text of blocks to move
        move_lines = []
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            move_lines.append(block.text())
            block = block.next()
        swap_line = prev_block.text()
        # Delete the moved range
        c = QTextCursor(doc)
        c.setPosition(start_block.position())
        last_block = end_block
        next_after = last_block.next()
        if next_after.isValid():
            c.setPosition(next_after.position(), QTextCursor.KeepAnchor)
        else:
            c.setPosition(
                last_block.position() + last_block.length(),
                QTextCursor.KeepAnchor)
        c.removeSelectedText()
        # Delete the swap line
        c2 = QTextCursor(doc)
        c2.setPosition(prev_block.position())
        next_prev = prev_block.next()
        if next_prev.isValid():
            c2.setPosition(next_prev.position(), QTextCursor.KeepAnchor)
        else:
            c2.setPosition(
                prev_block.position() + prev_block.length(),
                QTextCursor.KeepAnchor)
        c2.removeSelectedText()
        # Insert move_lines then swap_line at original prev position
        c3 = QTextCursor(doc)
        c3.setPosition(prev_block.position())
        c3.insertText('\n'.join(move_lines) + '\n' + swap_line)
        cursor.endEditBlock()
        # Restore cursor/selection in moved range
        new_start_pos = prev_block.position()
        new_end_pos = new_start_pos + len('\n'.join(move_lines))
        restore = QTextCursor(doc)
        restore.setPosition(new_start_pos)
        restore.setPosition(new_end_pos, QTextCursor.KeepAnchor)
        self.setTextCursor(restore)

    def _handle_move_line_down (self):
        """Move current line or selected lines down."""
        cursor = self.textCursor()
        doc = self.document()
        if cursor.hasSelection():
            start_block = doc.findBlock(cursor.selectionStart())
            end_block = doc.findBlock(cursor.selectionEnd())
            if cursor.selectionEnd() == end_block.position():
                end_block = end_block.previous()
        else:
            start_block = cursor.block()
            end_block = start_block
        next_block = end_block.next()
        if not next_block.isValid():
            return
        # Swap the range [start_block..end_block] with next_block
        cursor.beginEditBlock()
        move_lines = []
        block = start_block
        while block.isValid() and block.blockNumber() <= end_block.blockNumber():
            move_lines.append(block.text())
            block = block.next()
        swap_line = next_block.text()
        # Delete the moved range
        c = QTextCursor(doc)
        c.setPosition(start_block.position())
        next_after_range = end_block.next().next()
        if next_after_range.isValid():
            c.setPosition(
                next_after_range.position(), QTextCursor.KeepAnchor)
        else:
            # The next_block is last, so delete to end of next_block
            c.setPosition(
                next_block.position() + next_block.length(),
                QTextCursor.KeepAnchor)
        c.removeSelectedText()
        # Insert swap_line then move_lines at original start position
        c2 = QTextCursor(doc)
        c2.setPosition(start_block.position())
        c2.insertText(swap_line + '\n' + '\n'.join(move_lines))
        cursor.endEditBlock()
        # Restore cursor/selection in moved range (now shifted down)
        new_start_pos = start_block.position() + len(swap_line) + 1
        new_end_pos = new_start_pos + len('\n'.join(move_lines))
        restore = QTextCursor(doc)
        restore.setPosition(new_start_pos)
        restore.setPosition(new_end_pos, QTextCursor.KeepAnchor)
        self.setTextCursor(restore)

    #----- Bracket Completion -----

    def _handle_include_angle (self) -> bool:
        """Auto-complete #include < with >. Only if line starts with #include."""
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text().lstrip()
        if text.startswith('#include'):
            cursor.beginEditBlock()
            cursor.insertText('<>')
            cursor.movePosition(QTextCursor.Left)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
            return True
        return False

    def _handle_slash_for_comment (self) -> bool:
        """Skip over */ when typing / and right side has / from auto-close.
        After /* auto-completes */, the closing */ is to the right.
        When user types * then / (closing */), the / on the right is
        the auto-completed one — skip over it."""
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        # */ skip: we just typed /, left char is *, right char is /
        if pos < doc.characterCount() and doc.characterAt(pos) == '/':
            if pos > 0 and doc.characterAt(pos - 1) == '*':
                cursor.movePosition(QTextCursor.Right)
                self.setTextCursor(cursor)
                return True
        return False

    def _handle_star_for_comment_open (self) -> bool:
        """Auto-complete /* with */. When user types * and left char is /.
        Only triggers if not inside an already-auto-completed /* */ pair."""
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        # Left char must be /
        if pos < 1 or doc.characterAt(pos - 1) != '/':
            return False
        # Don't trigger if right side is already ' */' (we're closing)
        remaining = doc.characterCount() - pos
        if remaining >= 3:
            right3 = ''
            for i in range(3):
                right3 += doc.characterAt(pos + i)
            if right3 == ' */':
                return False
        cursor.beginEditBlock()
        cursor.insertText(' */')
        # Move cursor between /* and */
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, 3)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def contextMenuEvent (self, event):
        """Custom right-click context menu for CodeEditor."""
        menu = QMenu(self)
        # Standard edit actions from QTextEdit
        menu.addAction(self.act_undo if hasattr(self, 'act_undo')
                       else self._create_standard_action('Undo', self.undo))
        menu.addAction(self.act_redo if hasattr(self, 'act_redo')
                       else self._create_standard_action('Redo', self.redo))
        menu.addSeparator()
        menu.addAction(self.act_cut if hasattr(self, 'act_cut')
                       else self._create_standard_action('Cut', self.cut))
        menu.addAction(self.act_copy if hasattr(self, 'act_copy')
                       else self._create_standard_action('Copy', self.copy))
        menu.addAction(self.act_paste if hasattr(self, 'act_paste')
                       else self._create_standard_action('Paste', self.paste))
        menu.addSeparator()
        # Edit extension actions from createEditActions()
        actions = self.editActions()
        menu.addAction(actions['act_comment'])
        menu.addAction(actions['act_indent'])
        menu.addAction(actions['act_unindent'])
        menu.addAction(actions['act_duplicate'])
        menu.addAction(actions['act_delete_line'])
        menu.exec_(event.globalPos())

    def _create_standard_action (self, label, handler):
        """Create a simple QAction for standard edit operations
        (undo/redo/cut/copy/paste) when not injected from outside."""
        action = QAction(label, self)
        action.triggered.connect(handler)
        return action

    def set_bracket_completion (self, enabled:bool):
        self._bracket_completion_enabled = enabled

    def _handle_bracket_open (self, text:str) -> bool:
        """Handle bracket/quote auto-completion. Returns True if handled,
        False if in comment/string context (should use default input)."""
        cursor = self.textCursor()
        # Skip auto-completion inside comments or string literals
        pos = cursor.position()
        if self._is_bracket_in_comment_or_string(pos):
            return False
        # For quotes: if cursor is inside a matching pair, skip over
        if text in ('"', "'"):
            doc = self.document()
            if pos < doc.characterCount():
                char_after = doc.characterAt(pos)
                if char_after == text:
                    cursor.movePosition(QTextCursor.Right)
                    self.setTextCursor(cursor)
                    return True
        # Insert open + close, place cursor between
        close = self._BRACKET_OPEN[text]
        cursor.beginEditBlock()
        cursor.insertText(text + close)
        cursor.movePosition(QTextCursor.Left)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True

    def _handle_bracket_close (self, text:str) -> bool:
        cursor = self.textCursor()
        pos = cursor.position()
        doc = self.document()
        if pos < doc.characterCount():
            char_after = doc.characterAt(pos)
            if char_after == text:
                cursor.movePosition(QTextCursor.Right)
                self.setTextCursor(cursor)
                return True
        return False

    def _handle_backspace (self) -> bool:
        """Handle backspace: batch-delete spaces at indent boundaries,
        or delete paired brackets."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False
        col = cursor.columnNumber()
        if col > 0 and col % self.indent_size == 0:
            line_text = cursor.block().text()
            prefix = line_text[:col]
            if prefix and all(ch == ' ' for ch in prefix):
                # All spaces to the left, at indent boundary —
                # delete indent_size spaces at once
                cursor.beginEditBlock()
                for _i in range(self.indent_size):
                    cursor.deletePreviousChar()
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True
        # Bracket pair deletion
        if self._bracket_completion_enabled:
            pos = cursor.position()
            doc = self.document()
            if 0 < pos < doc.characterCount():
                char_before = doc.characterAt(pos - 1)
                char_after = doc.characterAt(pos)
                if char_before in self._BRACKET_OPEN:
                    expected_close = self._BRACKET_OPEN[char_before]
                    if char_after == expected_close:
                        cursor.beginEditBlock()
                        cursor.deleteChar()
                        cursor.deletePreviousChar()
                        cursor.endEditBlock()
                        self.setTextCursor(cursor)
                        return True
        return False

    def _handle_enter_key (self):
        cursor = self.textCursor()
        block = cursor.block()
        line_text = block.text()
        indent = self.__extract_indent(line_text)
        pos = cursor.position()
        doc = self.document()
        char_before = ''
        char_after = ''
        if pos > 0:
            char_before = doc.characterAt(pos - 1)
        if pos < doc.characterCount():
            char_after = doc.characterAt(pos)

        extra_indent = ''
        if char_before == '{':
            if self.indent_style == 'tab':
                extra_indent = '\t'
            else:
                extra_indent = ' ' * self.indent_size

        new_indent = indent + extra_indent
        if char_before == '{' and char_after == '}':
            cursor.beginEditBlock()
            cursor.insertText('\n' + new_indent + '\n' + indent)
            cursor.endEditBlock()
            new_pos = pos + 1 + len(new_indent)
            cursor.setPosition(new_pos)
            self.setTextCursor(cursor)
        else:
            cursor.beginEditBlock()
            cursor.insertText('\n' + new_indent)
            cursor.endEditBlock()
            self.setTextCursor(cursor)

    def __extract_indent (self, line:str) -> str:
        result = []
        for ch in line:
            if ch in (' ', '\t'):
                result.append(ch)
            else:
                break
        return ''.join(result)

    #----- Extra Selections (Current Line + Bracket Match) -----

    def _update_extra_selections (self):
        """Update current line highlight and bracket match highlight."""
        if not self.isEnabled():
            self.setExtraSelections([])
            return
        selections = []
        # Current line highlight
        cursor = self.textCursor()
        line_sel = QTextEdit.ExtraSelection()
        line_sel.format.setBackground(QBrush(self._CURRENT_LINE_COLOR))
        line_sel.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        line_sel.cursor = cursor
        line_sel.cursor.movePosition(QTextCursor.StartOfLine)
        selections.append(line_sel)
        # Bracket match highlight
        match_sel = self._find_bracket_match_selections()
        if match_sel:
            selections.extend(match_sel)
        self.setExtraSelections(selections)

    def _find_bracket_match_selections (self):
        """Find matching bracket and return ExtraSelections for both."""
        cursor = self.textCursor()
        doc = self.document()
        pos = cursor.position()
        # Check char at cursor and char before cursor
        chars_to_check = []
        if pos < doc.characterCount():
            chars_to_check.append((pos, doc.characterAt(pos)))
        if pos > 0:
            chars_to_check.append((pos - 1, doc.characterAt(pos - 1)))
        brackets = '(){}[]'
        for check_pos, ch in chars_to_check:
            if ch not in brackets:
                continue
            match_pos = self._find_matching_bracket(check_pos, ch)
            if match_pos < 0:
                continue
            if self._is_bracket_in_comment_or_string(check_pos):
                continue
            selections = []
            for bp in (check_pos, match_pos):
                sel = QTextEdit.ExtraSelection()
                sel.format.setBackground(QBrush(self._BRACKET_MATCH_COLOR))
                c = QTextCursor(doc)
                c.setPosition(bp)
                c.setPosition(bp + 1, QTextCursor.KeepAnchor)
                sel.cursor = c
                selections.append(sel)
            return selections
        return None

    def _find_matching_bracket (self, pos:int, ch:str) -> int:
        """Find matching bracket position. Returns -1 if not found."""
        doc = self.document()
        if ch in self._BRACKET_OPEN:
            # Search forward
            target = self._BRACKET_OPEN[ch]
            depth = 1
            p = pos + 1
            while p < doc.characterCount():
                c = doc.characterAt(p)
                if c == ch:
                    depth += 1
                elif c == target:
                    depth -= 1
                    if depth == 0:
                        return p
                p += 1
        elif ch in self._BRACKET_CLOSE:
            # Search backward
            target = self._BRACKET_CLOSE[ch]
            depth = 1
            p = pos - 1
            while p >= 0:
                c = doc.characterAt(p)
                if c == ch:
                    depth += 1
                elif c == target:
                    depth -= 1
                    if depth == 0:
                        return p
                p -= 1
        return -1

    def _is_bracket_in_comment_or_string (self, pos:int) -> bool:
        """Check if position is inside a comment or string literal."""
        block = self.document().findBlock(pos)
        if not block.isValid():
            return False
        block_pos = block.position()
        text = block.text()
        local_pos = pos - block_pos
        if local_pos < 0 or local_pos >= len(text):
            return False
        # Check injected highlighter format at this position
        highlighter = self._highlighter
        if highlighter and not highlighter._deferred:
            fmt = highlighter.format(local_pos)
            fg = fmt.foreground()
            if fg.style() and fg.color() != QColor():
                # Colored by highlighter = inside comment/string/char
                return True
        # In deferred mode or no highlighter: check block state for
        # multi-line comment and do a quick text-based check
        if block.previous().userState() == 1 or block.userState() == 1:
            return True
        # Quick regex check for strings and comments around local_pos
        # Check if local_pos is inside a quoted string
        in_string = False
        i = 0
        while i < local_pos:
            if text[i] == '"':
                in_string = not in_string
                # Skip escaped chars
                while in_string and i + 1 < len(text) and text[i + 1] == '\\':
                    i += 2
            elif text[i] == "'" and not in_string:
                # Character literal: skip until closing '
                end = text.find("'", i + 1)
                if end >= 0 and end < local_pos:
                    i = end + 1
                else:
                    return True
            i += 1
        if in_string:
            return True
        # Check single-line comment
        comment_pos = text.find('//')
        if comment_pos >= 0 and comment_pos <= local_pos:
            # Make sure it's not inside a string
            in_str = False
            for j in range(comment_pos):
                if text[j] == '"':
                    in_str = not in_str
            if not in_str:
                return True
        return False

    #----- Overwrite Mode -----

    def _notify_overwrite_changed (self):
        """Update cursor shape and emit overwriteModeChanged signal."""
        if self.overwrite_mode:
            self.setCursorWidth(self.fontMetrics().horizontalAdvance('x'))
        else:
            self.setCursorWidth(1)
        self.overwriteModeChanged.emit(self.overwrite_mode)