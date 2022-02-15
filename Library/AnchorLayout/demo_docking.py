import sys
import AnchorLayout

from PyQt5.QtWidgets import *

class Form1 (QWidget):
    def __init__ (self, parent = None):
        super().__init__(parent)
        self.setWindowTitle('Anchor Demo')
        self.resize(400, 310)
        self.layout = AnchorLayout.AnchorLayout(self)
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

    def resizeEvent (self, e):
        self.layout.update()
        return None
    
    def on_click (self):
        print('click me')
        print('b2 origin', self.g2.property('__layout_origin'), self.g2.geometry())
        return 0

app = QApplication([])

form = Form1()
form.show()

app.exec_()

