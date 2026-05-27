from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox, QGroupBox, QPushButton
from PyQt5.QtCore import pyqtSignal

class ChannelControl(QWidget):
    # Signal emitted when "Send" is clicked
    # Args: (ch_idx, wtype, freq, amp_norm, offset_mA)
    send_clicked = pyqtSignal(int, int, float, float, float)
    
    def __init__(self, ch_idx, parent=None):
        super().__init__(parent)
        self.ch_idx = ch_idx
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        self.group = QGroupBox(f"Ch {self.ch_idx}")
        form_layout = QVBoxLayout()
        
        # Waveform Type
        self.combo_type = QComboBox()
        self.combo_type.addItems(["Sine", "Square", "Triangle", "DC"])
        form_layout.addWidget(QLabel("Type:"))
        form_layout.addWidget(self.combo_type)
        
        # Frequency (Hz)
        self.spin_freq = QDoubleSpinBox()
        self.spin_freq.setRange(0, 10_000_000) # 0 to 10MHz
        self.spin_freq.setSuffix(" Hz")
        self.spin_freq.setDecimals(2)
        self.spin_freq.setValue(1000.0)
        form_layout.addWidget(QLabel("Freq:"))
        form_layout.addWidget(self.spin_freq)
        
        # Amplitude (Normalized 0.0 - 1.0)
        self.spin_amp = QDoubleSpinBox()
        self.spin_amp.setRange(0.0, 1.0)
        self.spin_amp.setSingleStep(0.01)
        self.spin_amp.setDecimals(3)
        self.spin_amp.setValue(0.5)
        form_layout.addWidget(QLabel("Amp (0.0-1.0):"))
        form_layout.addWidget(self.spin_amp)
        
        # Offset (0.0 - 20.0 mA)
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(0.0, 20.0)
        self.spin_offset.setSuffix(" mA")
        self.spin_offset.setDecimals(3)
        self.spin_offset.setValue(0.0)
        form_layout.addWidget(QLabel("Offset (0-20mA):"))
        form_layout.addWidget(self.spin_offset)
        
        # Send Button
        self.btn_send = QPushButton("Set")
        self.btn_send.clicked.connect(self.on_send)
        form_layout.addWidget(self.btn_send)
        
        self.group.setLayout(form_layout)
        layout.addWidget(self.group)
        self.setLayout(layout)
        
    def on_send(self):
        self.send_clicked.emit(
            self.ch_idx,
            self.combo_type.currentIndex(),
            self.spin_freq.value(),
            self.spin_amp.value(),
            self.spin_offset.value()
        )

