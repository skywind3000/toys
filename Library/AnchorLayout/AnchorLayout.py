#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# AnchorLayout.py - csharp Anchor/Dock Layout
#
# Created by skywind on 2022/02/13
# Last Modified: 2022/02/13 23:36:39
#
#======================================================================
import sys

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QResizeEvent
from PyQt5.QtCore import Qt, QEvent, QRect, QSize


#----------------------------------------------------------------------
# AnchorLayout
#----------------------------------------------------------------------
class AnchorLayout (object):

    def __init__ (self, root:QWidget):
        self.root = root
        anchors = {'left':False, 'right':False, 'top':False, 'bottom':False}
        self.ANCHORS = anchors
        self.anchor_name = 'anchor'
        self.dock_name = 'dock'

    # initialize after child widgets are created
    def init (self):
        self.__geometry_store(self.root)
        return 0

    # update every QResizeEvent
    def update (self):
        self.__geometry_update(self.root)
        return 0

    # parse anchor string
    def __anchor_parse (self, anchor):
        if anchor is None:
            return None
        an = {k: False for k in self.ANCHORS}
        for n in anchor.lower().split(','):
            n = n.strip()
            if n: an[n] = True
        return an

    # check need recursion
    def __need_recursion (self, root:QWidget, store = True):
        if root:
            return True
        anchor = root.property(self.anchor_name)
        if anchor is not None:
            return True
        docking = root.property(self.dock_name)
        if docking is not None:
            return True
        return False

    # store geometry
    def __geometry_store (self, root:QWidget):
        geometry = root.geometry()
        if not geometry.isValid():
            return -1
        root.setProperty('__layout_origin', geometry)
        for widget in root.children():
            if not isinstance(widget, QWidget):
                continue
            if not self.__need_recursion(widget, True):
                continue
            self.__geometry_store(widget)
        return 0

    # fetch widget original geometry
    def __get_origin_geometry (self, widget:QWidget):
        origin = widget.property('__layout_origin')
        if origin is None:
            origin = widget.geometry()
            widget.setProperty('__layout_origin', origin)
        return origin

    # update geometry
    def __geometry_update (self, root:QWidget):
        if not isinstance(root, QWidget):
            return -1
        elif not root.size().isValid():
            return -2
        origin = self.__get_origin_geometry(root)
        client = root.geometry()
        dx = client.width() - origin.width()
        dy = client.height() - origin.height()
        avail = root.geometry()
        avail.moveTo(0, 0)
        for widget in root.children():
            if not isinstance(widget, QWidget):
                continue
            anchor = widget.property(self.anchor_name)
            dock = widget.property(self.dock_name)
            anchor = self.__anchor_parse(anchor)
            dock = dock and dock.strip().lower() or None
            if anchor is not None:
                if not dock:
                    self.__layout_anchor(widget, anchor, dx, dy)
            if dock:
                if client.isValid():
                    self.__layout_docking(widget, avail, dock)
            self.__geometry_update(widget)
        return 0

    # update geometry by "anchor" property
    def __layout_anchor (self, widget, anchor, dx, dy):
        rc = self.__get_origin_geometry(widget)
        if anchor['left']:
            if anchor['right']:
                rc.setWidth(rc.width() + dx)
        else:
            if anchor['right']:
                rc.moveTo(rc.left() + dx, rc.top())
            else:
                rc.moveTo(rc.left() + dx // 2, rc.top())
        if anchor['top']:
            if anchor['bottom']:
                rc.setHeight(rc.height() + dy)
        else:
            if anchor['bottom']:
                rc.moveTo(rc.left(), rc.top() + dy)
            else:
                rc.moveTo(rc.left(), rc.top() + dy // 2)
        widget.setGeometry(rc)
        return True

    # update frameGeometry by "docking" property
    def __layout_docking (self, widget:QWidget, client:QRect, dock):
        rc = widget.frameGeometry()
        if not rc.isValid():
            return False
        elif not client.isValid():
            return False
        if dock == 'left':
            rc.moveTo(client.x(), client.y())
            rc.setHeight(client.height())
            client.setLeft(client.left() + rc.width())
        elif dock == 'right':
            rc.moveTo(client.right() - rc.width(), client.y())
            rc.setHeight(client.height())
            client.setRight(client.right() - rc.width())
        elif dock == 'top':
            rc.moveTo(client.x(), client.y())
            rc.setWidth(client.width())
            client.setTop(client.top() + rc.height())
        elif dock == 'bottom':
            rc.moveTo(client.x(), client.height() - rc.height())
            rc.setWidth(client.width())
            client.setBottom(client.bottom() - rc.height())
        elif dock in ('fill', 'client'):
            rc.setRect(client.x(), client.y(), client.width(), client.height())
        else:
            return False
        self.__move_widget(widget, rc)
        return True

    # move widget by frameGeometry
    def __move_widget (self, widget:QWidget, rect:QRect):
        bound = widget.frameGeometry()
        client = widget.geometry()
        ox = client.x() - bound.x()
        oy = client.y() - bound.y()
        dx = bound.width() - client.width()
        dy = bound.height() - client.height()
        widget.setGeometry(rect.x() + ox, rect.y() + oy,
                rect.width() - dx, rect.height() - dy)
        return True


#----------------------------------------------------------------------
# testing suit
#----------------------------------------------------------------------
if __name__ == '__main__':
    def test_anchor():
        from PyQt5.QtWidgets import QApplication, QTextEdit, QLabel
        from PyQt5.QtWidgets import QPushButton
        class Form1 (QWidget):
            def __init__ (self, parent = None):
                super().__init__(parent)
                self.setWindowTitle('Anchor Demo')
                self.resize(400, 310)
                self.initUI()
                self.layout = AnchorLayout(self)
                self.layout.init()
            def initUI (self):
                self.label1 = QLabel('Enter Your Name:', self)
                self.label1.move(20, 20)
                self.text = QTextEdit('', self)
                self.text.move(20, 50)
                self.text.setGeometry(20, 50, 360, 200)
                self.text.setProperty('anchor', 'left,right,top,bottom')
                self.btn1 = QPushButton('OK', parent = self)
                self.btn2 = QPushButton('Cancel', parent = self)
                self.btn3 = QPushButton('Help', parent = self)
                self.btn1.move(382 - self.btn1.width(), 260)
                self.btn2.move(170, 260)
                self.btn3.move(60, 260)
                self.btn1.setProperty('anchor', 'right,bottom')
                self.btn2.setProperty('anchor', 'right,bottom')
                self.btn3.setProperty('anchor', 'bottom')
                return 0
            def resizeEvent (self, e: QResizeEvent):
                self.layout.update()
                return None
        app = QApplication([])
        form = Form1()
        form.show()
        app.exec_()
        return 0
    def test_docking():
        from PyQt5.QtWidgets import QApplication, QTextEdit, QLabel
        from PyQt5.QtWidgets import QPushButton, QGroupBox, QPlainTextEdit
        class Form1 (QWidget):
            def __init__ (self, parent = None):
                super().__init__(parent)
                self.setWindowTitle('Anchor Demo')
                self.resize(400, 310)
                self.layout = AnchorLayout(self)
                self.initUI()
                self.layout.init()
                self.layout.update()
            def initUI (self):
                self.layout.init()
                self.g1 = QGroupBox('Group 1', self)
                self.g1.resize(100, 50)
                self.g1.setProperty('dock', 'left')
                self.g2 = QGroupBox('Group 2', self)
                self.g2.resize(100, 80)
                self.g2.setProperty('dock', 'bottom')
                self.t1 = QPlainTextEdit('', self)
                self.t1.setProperty('dock', 'fill')
                self.layout.update()
                self.layout.init()
                self.b1 = QPushButton('OK', self.g2)
                self.b1.setObjectName('b1')
                self.b2 = QPushButton('Info', self.g2)
                self.b1.move(190, 20)
                self.b2.move(80, 20)
                self.b1.setProperty('anchor', 'right,bottom')
                self.b2.setProperty('anchor', 'left,bottom')
                self.b2.clicked.connect(self.on_click)
                return 0
            def resizeEvent (self, e: QResizeEvent):
                self.layout.update()
                # print('geometry', self.b1.geometry(), self.g2.size())
                return None
            def on_click (self):
                print('click me')
                print('b2 origin', self.g2.property('__layout_origin'), self.g2.geometry())
                return 0
        app = QApplication([])
        form = Form1()
        form.show()
        app.exec_()
        return 0
    test_anchor()
    # test_docking()


