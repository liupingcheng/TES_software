import sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QTabWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from chip_widget import ChipControl
import datetime


class SafeLineEdit(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_value = self.text()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._original_value = self.text()
        self.setStyleSheet("background-color: #FFFF99;")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event)
            self._original_value = self.text()
            self.setStyleSheet("")
            self.clearFocus()
        elif event.key() == Qt.Key_Escape:
            self.setText(self._original_value)
            self.setStyleSheet("")
            self.clearFocus()
        else:
            super().keyPressEvent(event)
            
    def focusOutEvent(self, event):
        self.setText(self._original_value)
        self.setStyleSheet("")
        super().focusOutEvent(event)

class TDMBiasWidget(QWidget):
    # 与主窗口同步的信号
    sync_params_signal = pyqtSignal(str, str, str, str)
    connect_clicked_signal = pyqtSignal(str)
    probe_clicked_signal = pyqtSignal(str)
    send_data_signal = pyqtSignal(str, bytes)
    log_signal = pyqtSignal(str)
    
    def __init__(self, board_type, board_name="Bias Board", default_ip="", default_port="24", default_local_ip="", parent=None):
        super().__init__(parent)
        self.board_type = board_type
        self.board_name = board_name
        self.default_ip = default_ip
        self.default_port = default_port
        self.default_local_ip = default_local_ip
        self.is_connected = False  # 由父组件管理连接状态
        
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout()
        
        # 顶部连接栏
        conn_layout = QHBoxLayout()
        conn_layout.addStretch()
        
        # 板卡名称标签 (用作状态指示)
        short_name = self.board_name.split('-')[-1] if '-' in self.board_name else self.board_name
        self.lbl_board_name = QLabel(f" {short_name} ")
        self.lbl_board_name.setStyleSheet("""
            QLabel {
                background-color: #7F8C8D;
                color: #ECF0F1;
                font-size: 13px;
                padding: 4px 12px;
                border-radius: 4px;
                margin-right: 15px;
            }
        """)
        conn_layout.addWidget(self.lbl_board_name)
        
        conn_layout.addWidget(QLabel("IP Address:"))
        self.txt_ip = SafeLineEdit(self.default_ip)
        self.txt_ip.returnPressed.connect(self.on_params_changed)
        conn_layout.addWidget(self.txt_ip)
        
        conn_layout.addWidget(QLabel("Port:"))
        self.txt_port = SafeLineEdit(self.default_port)
        self.txt_port.setFixedWidth(60)
        self.txt_port.returnPressed.connect(self.on_params_changed)
        conn_layout.addWidget(self.txt_port)

        conn_layout.addWidget(QLabel("Local IP:"))
        self.txt_local_ip = SafeLineEdit(self.default_local_ip)
        self.txt_local_ip.setFixedWidth(140)
        self.txt_local_ip.returnPressed.connect(self.on_params_changed)
        conn_layout.addWidget(self.txt_local_ip)
        
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.on_connect_clicked)
        conn_layout.addWidget(self.btn_connect)

        self.btn_probe = QPushButton("Test Link")
        self.btn_probe.clicked.connect(self.on_probe_clicked)
        conn_layout.addWidget(self.btn_probe)
        
        conn_layout.addStretch()
        main_layout.addLayout(conn_layout)
        
        # 芯片控制标签页
        self.tabs = QTabWidget()
        
        # 安全地强制彻底关闭底层截断，修复 Windows 环境下超短标签的 Bug
        self.tabs.setElideMode(Qt.ElideNone)
        self.chip_widgets = []
        
        # 创建 6 个 DAC 芯片控制页
        for i in range(6):
            chip_ui = ChipControl(i)
            chip_ui.send_request.connect(self.send_packet)
            self.chip_widgets.append(chip_ui)
            self.tabs.addTab(chip_ui, f"DAC {i}")
            
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)
        
    def on_params_changed(self):
        ip = self.txt_ip.text().strip()
        port = self.txt_port.text().strip()
        local_ip = self.txt_local_ip.text().strip()
        self.sync_params_signal.emit(self.board_type, ip, port, local_ip)
        
    def set_connection_params(self, ip, port, local_ip):
        # 阻止信号发射，避免死循环同步
        self.txt_ip.blockSignals(True)
        self.txt_port.blockSignals(True)
        self.txt_local_ip.blockSignals(True)
        
        self.txt_ip.setText(ip)
        self.txt_port.setText(port)
        self.txt_local_ip.setText(local_ip)
        
        self.txt_ip.blockSignals(False)
        self.txt_port.blockSignals(False)
        self.txt_local_ip.blockSignals(False)

    def on_connect_clicked(self):
        self.connect_clicked_signal.emit(self.board_type)

    def on_probe_clicked(self):
        self.probe_clicked_signal.emit(self.board_type)
        
    def update_connection_state(self, is_connected):
        self.is_connected = is_connected
        if is_connected:
            self.btn_connect.setText("Disconnect")
            self.set_badge_state("connected")
        else:
            self.btn_connect.setText("Connect")
            self.set_badge_state("disconnected")

    def set_badge_state(self, state):
        colors = {
            "disconnected": "#7F8C8D",
            "connecting": "orange",
            "connected": "#2ecc71"
        }
        color = colors.get(state, "#7F8C8D")
        self.lbl_board_name.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: #ECF0F1;
                font-size: 13px;
                padding: 4px 12px;
                border-radius: 4px;
                margin-right: 15px;
            }}
        """)

    def log(self, msg):
        self.log_signal.emit(f"[{self.board_name}] {msg}")

    def send_packet(self, data, desc):
        if not self.is_connected:
            self.log("发送失败: TCP 未连接")
            return
        
        self.log(f"TX: {desc} ({len(data)} bytes)")
        self.send_data_signal.emit(self.board_type, data)

    def get_board_config(self):
        config = {
            "type": "bias_board",
            # "board_ip": self.default_ip,
            "board_ip": self.txt_ip.text().strip(),
            "dacs": {}
        }
        for idx in range(len(self.chip_widgets)):
            config["dacs"][f"dac_{idx}"] = self.chip_widgets[idx].get_config()
        return config
        
    def set_board_config(self, data):
        if data.get("type") != "bias_board":
            return False, "参数类型不匹配 (期望 bias_board)"
            
        dacs_cfg = data.get("dacs", {})
        for idx in range(len(self.chip_widgets)):
            dac_key = f"dac_{idx}"
            if dac_key in dacs_cfg:
                self.chip_widgets[idx].set_config(dacs_cfg[dac_key])
        return True, "读取成功"
