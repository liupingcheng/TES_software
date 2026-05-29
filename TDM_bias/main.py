import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget,
                             QStatusBar, QTextEdit, QSplitter)
from PyQt5.QtCore import Qt
from tcp_client import TCPClient
from chip_widget import ChipControl
import datetime

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AFB Multi-Channel DDS Controller")
        self.resize(1200, 800)
        
        self.tcp = TCPClient()
        self.tcp.connected.connect(self.on_connected)
        self.tcp.disconnected.connect(self.on_disconnected)
        self.tcp.data_sent.connect(self.on_data_sent)
        self.tcp.data_received.connect(self.on_data_received)
        self.tcp.probe_finished.connect(self.on_probe_finished)
        
        self.init_ui()
        
    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # --- Top Bar: Connection ---
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("IP Address:"))
        self.txt_ip = QLineEdit("192.168.10.16")
        conn_layout.addWidget(self.txt_ip)
        
        conn_layout.addWidget(QLabel("Port:"))
        self.txt_port = QLineEdit("24")
        self.txt_port.setFixedWidth(60)
        conn_layout.addWidget(self.txt_port)

        conn_layout.addWidget(QLabel("Local IP:"))
        self.txt_local_ip = QLineEdit("192.168.10.100")
        self.txt_local_ip.setFixedWidth(140)
        conn_layout.addWidget(self.txt_local_ip)
        
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.btn_connect)

        self.btn_probe = QPushButton("Test Link")
        self.btn_probe.clicked.connect(self.run_probe)
        conn_layout.addWidget(self.btn_probe)
        
        conn_layout.addStretch()
        main_layout.addLayout(conn_layout)
        
        # --- Splitter for Content and Log ---
        splitter = QSplitter(Qt.Vertical)
        
        # --- Tabs for Chips ---
        self.tabs = QTabWidget()
        self.chip_widgets = []
        
        # Create 6 Tabs for 6 Chips (DAC0 - DAC5)
        for i in range(6):
            chip_ui = ChipControl(i)
            chip_ui.send_request.connect(self.send_packet)
            self.chip_widgets.append(chip_ui)
            self.tabs.addTab(chip_ui, f"DAC {i}")
            
        splitter.addWidget(self.tabs)
        
        # --- Log Window ---
        log_widget = QWidget()
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("Command Monitor:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        log_layout.addWidget(self.txt_log)
        log_widget.setLayout(log_layout)
        
        splitter.addWidget(log_widget)
        splitter.setSizes([600, 200]) # Initial ratio
        
        main_layout.addWidget(splitter)
        
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # --- Status Bar ---
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready. Not connected.")
        
    def log(self, msg):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{timestamp}] {msg}")
        
    def toggle_connection(self):
        if not self.tcp.is_connected:
            ip = self.txt_ip.text().strip()
            port = self.txt_port.text().strip()
            local_ip = self.txt_local_ip.text().strip()
            bind_desc = f" via {local_ip}" if local_ip else ""
            self.log(f"Connecting to {ip}:{port}{bind_desc}...")
            self.tcp.connect_to_server(ip, port, local_ip=local_ip)
        else:
            self.tcp.disconnect_from_server()
            self.on_disconnected("Disconnected by user")

    def run_probe(self):
        ip = self.txt_ip.text().strip()
        port = self.txt_port.text().strip()
        local_ip = self.txt_local_ip.text().strip()

        self.btn_probe.setEnabled(False)
        self.status.showMessage("Running TCP link probe...")
        bind_desc = f" via {local_ip}" if local_ip else ""
        self.log(f"Probing {ip}:{port}{bind_desc} for 5.0s...")
        self.tcp.probe_server(ip, port, hold_seconds=5.0, local_ip=local_ip)
            
    def on_connected(self):
        self.status.showMessage("Connected!")
        self.btn_connect.setText("Disconnect")
        self.log("TCP Connected.")
        
    def on_disconnected(self, msg):
        self.status.showMessage(f"Disconnected: {msg}")
        self.btn_connect.setText("Connect")
        self.log(f"TCP Disconnected: {msg}")
        
    def on_data_sent(self, length):
        self.status.showMessage(f"Sent {length} bytes", 2000)

    def on_data_received(self, length):
        self.status.showMessage(f"Received {length} bytes", 2000)
        self.log(f"RX: {length} bytes")

    def on_probe_finished(self, ok, msg):
        self.btn_probe.setEnabled(True)
        self.status.showMessage(msg, 5000)
        prefix = "Probe OK" if ok else "Probe Fail"
        self.log(f"{prefix}: {msg}")
        
    def send_packet(self, data, desc):
        if not self.tcp.is_connected:
            self.status.showMessage("Error: Not connected!")
            self.log("Error: Cannot send command, TCP not connected.")
            return
        
        hex_preview = data.hex().upper()
        # self.log(f"TX [{hex_preview}] - {desc}") 
        # Just log description and length to be cleaner
        self.log(f"TX: {desc} ({len(data)} bytes)")
        
        self.tcp.send_data(data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

