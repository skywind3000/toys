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

    def resizeEvent (self, e):
        self.layout.update()
        return None

app = QApplication([])

form = Form1()
form.show()

app.exec_()

