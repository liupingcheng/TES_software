from PyQt5.QtWidgets import QWidget, QGridLayout, QGroupBox
from PyQt5.QtCore import pyqtSignal
from channel_widget import ChannelControl
from protocol import ProtocolEncoder

class ChipControl(QWidget):
    # Signal: (bytes_data, description_str)
    send_request = pyqtSignal(bytes, str)
    
    def __init__(self, chip_id, parent=None):
        super().__init__(parent)
        self.chip_id = chip_id
        self.init_ui()
        
    def init_ui(self):
        layout = QGridLayout()
        
        # Create 8 channel widgets in a 2x4 grid
        for i in range(8):
            ch_widget = ChannelControl(i)
            ch_widget.send_clicked.connect(self.on_channel_send)
            # Row = i // 4, Col = i % 4
            layout.addWidget(ch_widget, i // 4, i % 4)
            
        self.group = QGroupBox(f"DAC {self.chip_id}")
        self.group.setLayout(layout)
        
        main_layout = QGridLayout()
        main_layout.addWidget(self.group)
        self.setLayout(main_layout)
        
    def on_channel_send(self, ch_idx, wtype, freq, amp_norm, offset_mA):
        # Generate packets
        data = ProtocolEncoder.commands_for_channel_config(
            self.chip_id, ch_idx, wtype, freq, amp_norm, offset_mA
        )
        
        # Create description string for logging
        desc = (f"DAC{self.chip_id}-Ch{ch_idx}: Set Type={wtype}, "
                f"Freq={freq:.1f}Hz, Amp={amp_norm:.3f}, Offset={offset_mA:.3f}mA")
        
        self.send_request.emit(data, desc)

