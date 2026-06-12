from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QComboBox as _QComboBox, QDoubleSpinBox as _QDoubleSpinBox, 
                             QGroupBox, QPushButton, QFormLayout)
from PyQt5.QtCore import pyqtSignal, Qt

class SafeComboBox(_QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class SafeDoubleSpinBox(_QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setKeyboardTracking(False) 
        self._original_value = self.value()
        self._is_editing = False

    def wheelEvent(self, event):
        event.ignore()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._original_value = self.value()
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event)
            self._original_value = self.value()
            self.clearFocus()
        elif event.key() == Qt.Key_Escape:
            self.setValue(self._original_value)
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.setStyleSheet("")
        if self._is_editing:
            self.setValue(self._original_value)
            self._is_editing = False
        super().focusOutEvent(event)


class ChannelControl(QWidget):
    # "Set" 按钮按下时触发信号
    # 参数: (通道索引, 波形类型, 频率, 归一化幅值, 偏置电流)
    send_clicked = pyqtSignal(int, int, float, float, float)
    
    def __init__(self, chip_id, ch_idx, parent=None):
        super().__init__(parent)
        self.chip_id = chip_id
        self.ch_idx = ch_idx
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.group = QGroupBox(f"DAC {self.chip_id} - Ch {self.ch_idx}")
        self.group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                margin-top: 1.5ex;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                color: #555555;
            }
        """)
        
        form_layout = QFormLayout()
        
        # 波形类型
        self.combo_type = SafeComboBox()
        self.combo_type.addItems(["Sine", "Square", "Triangle", "DC"])
        form_layout.addRow("Type:", self.combo_type)
        
        # 频率 (Hz)
        self.spin_freq = SafeDoubleSpinBox()
        self.spin_freq.setRange(0, 10_000_000) # 0 to 10MHz
        self.spin_freq.setSuffix(" Hz")
        self.spin_freq.setDecimals(2)
        self.spin_freq.setValue(1000.0)
        form_layout.addRow("Freq:", self.spin_freq)
        
        # 幅值 (归一化 0.0 - 1.0)
        self.spin_amp = SafeDoubleSpinBox()
        self.spin_amp.setRange(0.0, 1.0)
        self.spin_amp.setSingleStep(0.01)
        self.spin_amp.setDecimals(3)
        self.spin_amp.setValue(0.5)
        form_layout.addRow("Amp (0-1):", self.spin_amp)
        
        # 偏置电流 (0.0 - 20.0 mA)
        self.spin_offset = SafeDoubleSpinBox()
        self.spin_offset.setRange(0.0, 20.0)
        self.spin_offset.setSuffix(" mA")
        self.spin_offset.setDecimals(3)
        self.spin_offset.setValue(0.0)
        form_layout.addRow("Offset (0-20):", self.spin_offset)
        
        # 设置按钮
        self.btn_send = QPushButton("Set")
        self.btn_send.clicked.connect(self.on_send)
        form_layout.addRow("", self.btn_send)
        
        self.group.setLayout(form_layout)
        layout.addWidget(self.group)
        self.setLayout(layout)
        
        # 默认使用正弦波
        self.combo_type.setCurrentIndex(0)
        
    def get_config(self):
        return {
            "type": self.combo_type.currentIndex(),
            "freq": self.spin_freq.value(),
            "amp": self.spin_amp.value(),
            "offset": self.spin_offset.value()
        }
        
    def set_config(self, config):
        if "type" in config: self.combo_type.setCurrentIndex(config["type"])
        if "freq" in config: self.spin_freq.setValue(config["freq"])
        if "amp" in config: self.spin_amp.setValue(config["amp"])
        if "offset" in config: self.spin_offset.setValue(config["offset"])

    def on_send(self):
        self.send_clicked.emit(
            self.ch_idx,
            self.combo_type.currentIndex(),
            self.spin_freq.value(),
            self.spin_amp.value(),
            self.spin_offset.value()
        )
