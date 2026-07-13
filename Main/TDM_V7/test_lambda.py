import sys
from PyQt5.QtCore import QObject, pyqtSignal, QCoreApplication

class Client(QObject):
    disconnected = pyqtSignal(str)
    
class Manager(QObject):
    board_disconnected = pyqtSignal(str, str)
    def __init__(self):
        super().__init__()
        self.c = Client()
        self.c.disconnected.connect(lambda err, b="bias1": self.board_disconnected.emit(b, err))

class App(QObject):
    def __init__(self):
        super().__init__()
        self.m = Manager()
        self.m.board_disconnected.connect(self.on_disc)
    def on_disc(self, b, err):
        print(f"DISC: {b} {err}")

app = QCoreApplication(sys.argv)
a = App()
a.m.c.disconnected.emit("timeout!")
