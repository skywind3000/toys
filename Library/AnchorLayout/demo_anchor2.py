import sys
import AnchorLayout

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QEvent, QRect, QSize


class Form1 (QWidget):
    def __init__ (self, parent = None):
        super().__init__(parent)
        self.setWindowTitle('Anchor Demo')
        self.resize(400, 310)
        self.initUI()
        self.layout = AnchorLayout.AnchorLayout(self)
        self.layout.init()

    def initUI (self):
        self.label1 = QLabel('Name:', self)
        self.label1.move(20, 20)
        self.text1 = QLineEdit('Name', self)
        self.text1.move(70, 16)
        self.text1.setGeometry(70, 14, 310, self.text1.height())
        self.text1.setProperty('anchor', 'left,top,right')
        self.box = QGroupBox("Dialog 1", self)
        self.box.move(20, 50)
        self.box.setGeometry(20, 50, 360, 200)
        self.box.setProperty('anchor', 'left,right,top,bottom')
        self.b1 = QPushButton('LeftTop', self.box)
        self.b2 = QPushButton('RightTop', self.box)
        self.b3 = QPushButton('LeftBottom', self.box)
        self.b4 = QPushButton('RightBottom', self.box)
        self.b1.move(10, 20)
        self.b2.move(250, 20)
        self.b3.move(10, 160)
        self.b4.move(250, 160)
        self.b1.setProperty('anchor', 'left,top')
        self.b2.setProperty('anchor', 'right,top')
        self.b3.setProperty('anchor', 'left,bottom')
        self.b4.setProperty('anchor', 'right,bottom')
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

    def resizeEvent (self, e):
        self.layout.update()
        return None

app = QApplication([])

form = Form1()
form.show()

app.exec_()

