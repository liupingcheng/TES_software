from PyQt5.QtWidgets import QWidget, QGridLayout, QGroupBox
from PyQt5.QtCore import pyqtSignal
from channel_widget import ChannelControl
from bias_protocol import ProtocolEncoder

class ChipControl(QWidget):
    # 发送请求信号: (字节数据, 描述字符串)
    send_request = pyqtSignal(bytes, str)
    
    def __init__(self, chip_id, parent=None):
        super().__init__(parent)
        self.chip_id = chip_id
        self.init_ui()
        
    def init_ui(self):
        layout = QGridLayout()
        self.channel_widgets = []
        
        # 创建 8 个通道控制组件 (2行4列)
        for i in range(8):
            ch_widget = ChannelControl(self.chip_id, i)
            ch_widget.send_clicked.connect(self.on_channel_send)
            layout.addWidget(ch_widget, i // 4, i % 4)
            self.channel_widgets.append(ch_widget)
            
        self.setLayout(layout)
        
    def get_config(self):
        config = {}
        for i, ch_widget in enumerate(self.channel_widgets):
            config[f"ch_{i}"] = ch_widget.get_config()
        return config
        
    def set_config(self, config):
        for i, ch_widget in enumerate(self.channel_widgets):
            key = f"ch_{i}"
            if key in config:
                ch_widget.set_config(config[key])
        
    def on_channel_send(self, ch_idx, wtype, freq, amp_norm, offset_mA):
        # 生成协议数据包
        data = ProtocolEncoder.commands_for_channel_config(
            self.chip_id, ch_idx, wtype, freq, amp_norm, offset_mA
        )
        
        # 生成日志描述信息
        desc = (f"DAC{self.chip_id}-Ch{ch_idx}: Type={wtype}, "
                f"Freq={freq:.1f}Hz, Amp={amp_norm:.3f}, Offset={offset_mA:.3f}mA")
        
        self.send_request.emit(data, desc)

