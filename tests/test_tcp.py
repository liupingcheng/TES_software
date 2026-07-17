import sys
import threading
import time
from pathlib import Path

from PyQt5.QtCore import QCoreApplication


V8_DIRECTORY = Path(__file__).resolve().parents[1] / "TDM_V8"
sys.path.insert(0, str(V8_DIRECTORY))

from tcp_client import TCPClient

app = QCoreApplication(sys.argv)
client = TCPClient()

def on_conn():
    print("CONNECTED")
    app.quit()

def on_disc(msg):
    print("DISCONNECTED:", msg)
    app.quit()

client.connected.connect(on_conn)
client.disconnected.connect(on_disc)

def run():
    print("Attempting connection...")
    client.connect_to_server("192.0.2.1", 5000)  # 无效的IP地址 (测试用)

threading.Thread(target=run).start()
app.exec_()
