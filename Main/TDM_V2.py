#This is the the new version of the TDM software. PyQt5 is used for the GUI.
#The TDM software is used to control the TDM hardware. It will be used to control the TDM hardware and to collect data from the TDM hardware.
#written by: Pingcheng Liu, 2026-4

import sys
import time
import socket
from PyQt5.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLineEdit as _QLineEdit, QMainWindow, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
                             QTabWidget, QGroupBox, QComboBox as _QComboBox, QDoubleSpinBox as _QDoubleSpinBox, QCheckBox, QScrollArea, QSpinBox as _QSpinBox, QTableWidget, QFileDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# ================= 安全交互控件=================
#尽量保证参数安全
from PyQt5.QtCore import Qt # 确保导入了 Qt，用来识别回车键和ESC键

# 1. 下拉框：只屏蔽滚轮误触
class QComboBox(_QComboBox):
    def wheelEvent(self, event):
        event.ignore()

# 2. 文本框：防点错恢复机制
class QLineEdit(_QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_text = ""
        self._is_editing = False

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._original_text = self.text() # 获得焦点时，记下修改前的文本
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event) # 先让原生控件处理回车
            self._original_text = self.text() # 更新原始值为新文本
            self.clearFocus() # 丢掉焦点（这会触发下面的 focusOutEvent）
        elif event.key() == Qt.Key_Escape:
            self.setText(self._original_text) # 按ESC直接恢复原样
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._is_editing:
            self.setText(self._original_text) # 失去焦点时，强制恢复为记录的值
            self.setStyleSheet("") # 恢复白底
            self._is_editing = False
        super().focusOutEvent(event)

# 3. 浮点数字框：防点错恢复机制
class QDoubleSpinBox(_QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setKeyboardTracking(False) 
        self._original_value = self.value()
        self._is_editing = False

    def wheelEvent(self, event):
        event.ignore()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._original_value = self.value() # 记下修改前的值
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            super().keyPressEvent(event) # 让控件提交新值
            self._original_value = self.value() # 覆盖记录
            self.clearFocus()
        elif event.key() == Qt.Key_Escape:
            self.setValue(self._original_value)
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._is_editing:
            # 如果是按回车触发的失去焦点，_original_value 是新值，反正就是必须回车确认才会更新 _original_value
            # 如果是鼠标点到别的地方，_original_value 是老值
            self.setValue(self._original_value) 
            self.setStyleSheet("")
            self._is_editing = False
        super().focusOutEvent(event)

# 4. 整数数字框：防点错恢复机制
class QSpinBox(_QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setKeyboardTracking(False)
        self._original_value = self.value()
        self._is_editing = False

    def wheelEvent(self, event):
        event.ignore()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._original_value = self.value()
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")

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
        if self._is_editing:
            self.setValue(self._original_value)
            self.setStyleSheet("")
            self._is_editing = False
        super().focusOutEvent(event)
# ==========================================================

class BiasBoardWidget(QWidget):
    """独立的偏置源板卡控件"""
    def __init__(self, board_id, parent=None):
        super().__init__(parent)
        self.board_id = board_id
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        # title_label = QLabel(f"偏置源板卡 {self.board_id + 1}")
        # title_label.setFont(QFont("Arial", 12, QFont.Bold))
        # layout.addWidget(title_label)
        
        #直流交流切换下拉框
        ac_dc_group = QGroupBox("信号类型")
        ac_dc_layout = QHBoxLayout()
        self.signal_type = QComboBox()
        self.signal_type.addItems(["直流", "交流"])
        ac_dc_layout.addWidget(QLabel("信号类型"))
        ac_dc_layout.addWidget(self.signal_type)
        ac_dc_layout.addStretch()
        ac_dc_group.setLayout(ac_dc_layout)
        layout.addWidget(ac_dc_group)
        
        #交流参数设置
        self.ac_params_group = QGroupBox("交流信号参数")
        ac_layout = QGridLayout()
        
        ac_layout.addWidget(QLabel("波形类型："), 0, 0)
        self.waveform_type = QComboBox()
        self.waveform_type.addItems(["正弦波", "方波", "三角波"])
        ac_layout.addWidget(self.waveform_type, 0, 1)
        
        ac_layout.addWidget(QLabel("频率 (Hz)："), 1, 0)
        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.1, 10000)
#        self.frequency.setValue(1000)
        ac_layout.addWidget(self.frequency, 1, 1)
        
        ac_layout.addWidget(QLabel("幅值 (μA)："), 2, 0)
        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(0, 1000)
        self.amplitude.setValue(100)
        ac_layout.addWidget(self.amplitude, 2, 1)
        
        self.ac_params_group.setLayout(ac_layout)
        layout.addWidget(self.ac_params_group)
        
        #DC参数设置
        self.dc_params_group = QGroupBox("直流信号参数")
        dc_layout = QHBoxLayout()
        dc_layout.addWidget(QLabel("电流 (μA)："))
        self.dc_value = QDoubleSpinBox()
        self.dc_value.setRange(-1000, 1000)
        self.dc_value.setValue(0)
        dc_layout.addWidget(self.dc_value)
        dc_layout.addStretch()
        self.dc_params_group.setLayout(dc_layout)
        layout.addWidget(self.dc_params_group)
        
        #根据选择的信号类型显示对应的参数设置
        self.signal_type.currentTextChanged.connect(self.on_signal_type_changed)
        if self.board_id == 0:
            self.setup_board1_channels()  # 第一块板卡
        elif self.board_id == 1:
            self.setup_board2_channels()
            pass  
        elif self.board_id == 2:
            self.setup_board3_channels()
            pass
            
        layout.addStretch()
        
        
    def on_signal_type_changed(self, signal_type):
        """信号类型切换时，动态显示/隐藏相关参数"""
        if signal_type == "交流":
            self.ac_params_group.show()
            self.dc_params_group.hide()
            # 【新增】：如果是板卡1，且方波组已经创建，则显示它
            if self.board_id == 0 and hasattr(self, 'square_wave_group'):
                self.square_wave_group.show()
        else:
            self.ac_params_group.hide()
            self.dc_params_group.show()
            # 【新增】：如果是板卡1，隐藏方波组
            if self.board_id == 0 and hasattr(self, 'square_wave_group'):
                self.square_wave_group.hide()
    def setup_board1_channels(self):
        """设置第一块板卡 (Board 0) 的通道控制"""
        # ================= 1. TES 信号控制区 =================
        group = QGroupBox("TES信号控制 (16列)")
        layout = QGridLayout()
        
        self.tes_master_switch = QCheckBox("TES 总开关")
        self.tes_master_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.tes_master_switch.stateChanged.connect(self.toggle_all_tes)
        layout.addWidget(self.tes_master_switch, 0, 0, 1, 8)
        
        self.tes_switches = []
        self.tes_values = []
        for i in range(16):
            switch = QCheckBox(f"列{i+1}")
            self.tes_switches.append(switch)
            row = i // 4 + 1
            col = (i % 4) * 2
            layout.addWidget(switch, row, col)
            
            value = QDoubleSpinBox()
            value.setRange(-10, 10)
            value.setSuffix(" V")
            self.tes_values.append(value)
            layout.addWidget(value, row, col + 1)
        group.setLayout(layout)
        self.layout().addWidget(group)
        
        # ================= 2. 独立方波信号控制区 =================
        self.square_wave_group = QGroupBox("独立方波信号控制 (16列)")
        sq_layout = QGridLayout()
        
        # 顶部方波参数
        sq_layout.addWidget(QLabel("方波幅值:"), 0, 0)
        self.square_amplitude = QDoubleSpinBox()
        self.square_amplitude.setRange(0, 1000)
        self.square_amplitude.setValue(5)
        self.square_amplitude.setSuffix(" uA")
        sq_layout.addWidget(self.square_amplitude, 0, 1)
        
        sq_layout.addWidget(QLabel("方波频率:"), 0, 2)
        self.square_frequency = QDoubleSpinBox()
        self.square_frequency.setRange(0.1, 10000)
        self.square_frequency.setValue(100)
        self.square_frequency.setSuffix(" Hz")
        sq_layout.addWidget(self.square_frequency, 0, 3)
        
        # 方波总开关
        self.square_master_switch = QCheckBox("方波信号 总开关")
        self.square_master_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.square_master_switch.stateChanged.connect(self.toggle_all_square)
        sq_layout.addWidget(self.square_master_switch, 1, 0, 1, 8)
        
        self.square_switches = []
        self.square_values = []
        for i in range(16):
            switch = QCheckBox(f"列{i+1}")
            self.square_switches.append(switch)
            row = i // 4 + 2  # 从第2行开始（0行是参数，1行是总开关）
            col = (i % 4) * 2
            sq_layout.addWidget(switch, row, col)
            
            value = QDoubleSpinBox()
            value.setRange(-1000, 1000)
            value.setSuffix(" uA")
            self.square_values.append(value)
            sq_layout.addWidget(value, row, col + 1)
            
        self.square_wave_group.setLayout(sq_layout)
        self.layout().addWidget(self.square_wave_group)
        
        # 初始时根据下拉框状态决定是否显示
        self.on_signal_type_changed(self.signal_type.currentText())

    def toggle_all_tes(self, state):
        checked = (state == 2)
        for switch in self.tes_switches:
            switch.setChecked(checked)
            
    def toggle_all_square(self, state):
        """联动方法：方波总开关"""
        checked = (state == 2)
        for switch in self.square_switches:
            switch.setChecked(checked)
        
    def toggle_all_tes(self, state):
        checked = (state == 2)  # Checked 的值是 2
        #根据总开关的状态切换所有TES开关的状态
        for switch in self.tes_switches:
            switch.setChecked(checked)
    
        # ========================== 板卡 2 ==========================
    def setup_board2_channels(self):
        """设置第二块板卡的通道控制 (16行纵向排列)"""
        group1 = QGroupBox("SA Ib & SA phix控制 (16列)")
        layout1 = QGridLayout()
        
        # 总开关
        self.sa_ib_master_switch = QCheckBox("SA Ib 总开关")
        self.sa_ib_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.sa_ib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_ib_switches])
        layout1.addWidget(self.sa_ib_master_switch, 0, 1, 1, 2)
        
        self.sa_phix_master_switch = QCheckBox("SA phix 总开关")
        self.sa_phix_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.sa_phix_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_phix_switches])
        layout1.addWidget(self.sa_phix_master_switch, 0, 3, 1, 2)
        
        # 表头
        headers = ["列", "SA Ib开关", "SA Ib输出值", "SA phix开关", "SA phix输出值"]
        for col, text in enumerate(headers):
            layout1.addWidget(QLabel(text), 1, col)
        
        self.sa_ib_switches, self.sa_ib_values = [], []
        self.sa_phix_switches, self.sa_phix_values = [], []
        
        # 这里用的是纵向排列 (16行)
        for i in range(16):
            row = i + 2
            layout1.addWidget(QLabel(f"列{i+1}"), row, 0)
            
            # SA Ib
            ib_switch = QCheckBox()
            self.sa_ib_switches.append(ib_switch)
            layout1.addWidget(ib_switch, row, 1)
            
            ib_value = QDoubleSpinBox()
            ib_value.setRange(-1000, 1000)
            ib_value.setSuffix(" uA")
            self.sa_ib_values.append(ib_value)
            layout1.addWidget(ib_value, row, 2)
            
            # SA phix
            phix_switch = QCheckBox()
            self.sa_phix_switches.append(phix_switch)
            layout1.addWidget(phix_switch, row, 3)
            
            phix_value = QDoubleSpinBox()
            phix_value.setRange(-1000, 1000)
            phix_value.setSuffix(" uA")
            self.sa_phix_values.append(phix_value)
            layout1.addWidget(phix_value, row, 4)
            
        group1.setLayout(layout1)
        self.layout().addWidget(group1)
        
        # ----- Vb控制 -----
        group2 = QGroupBox("Vb控制 (16列)")
        layout2 = QGridLayout()
        
        self.vb_master_switch = QCheckBox("Vb 总开关")
        self.vb_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.vb_switches])
        layout2.addWidget(self.vb_master_switch, 0, 0, 1, 3)
        
        layout2.addWidget(QLabel("列"), 1, 0)
        layout2.addWidget(QLabel("开关"), 1, 1)
        layout2.addWidget(QLabel("输出值"), 1, 2)
        
        self.vb_switches, self.vb_values = [], []
        for i in range(16):
            row = i + 2
            layout2.addWidget(QLabel(f"列{i+1}"), row, 0)
            
            switch = QCheckBox()
            self.vb_switches.append(switch)
            layout2.addWidget(switch, row, 1)
            
            value = QDoubleSpinBox()
            value.setRange(-10, 10)
            value.setSuffix(" V")
            self.vb_values.append(value)
            layout2.addWidget(value, row, 2)
            
        group2.setLayout(layout2)
        self.layout().addWidget(group2)


    # ========================== 板卡 3 ==========================
    def setup_board3_channels(self):
        """设置第三块板卡的通道控制"""
        group = QGroupBox("IS I & IS phib控制 (16列)")
        layout = QGridLayout()
        
        # 总开关
        self.is_i_master_switch = QCheckBox("IS I 总开关")
        self.is_i_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_i_switches])
        layout.addWidget(self.is_i_master_switch, 0, 1, 1, 2)
        
        self.is_phib_master_switch = QCheckBox("IS phib 总开关")
        self.is_phib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_phib_switches])
        layout.addWidget(self.is_phib_master_switch, 0, 3, 1, 2)
        
        headers = ["列", "IS I开关", "IS I输出值", "IS phib开关", "IS phib输出值"]
        for col, text in enumerate(headers):
            layout.addWidget(QLabel(text), 1, col)
            
        self.is_i_switches, self.is_i_values = [], []
        self.is_phib_switches, self.is_phib_values = [], []
        
        for i in range(16):
            row = i + 2
            layout.addWidget(QLabel(f"列{i+1}"), row, 0)
            
            i_switch = QCheckBox()
            self.is_i_switches.append(i_switch)
            layout.addWidget(i_switch, row, 1)
            
            i_value = QDoubleSpinBox()
            i_value.setRange(-1000, 1000)
            i_value.setSuffix(" uA")
            self.is_i_values.append(i_value)
            layout.addWidget(i_value, row, 2)
            
            phib_switch = QCheckBox()
            self.is_phib_switches.append(phib_switch)
            layout.addWidget(phib_switch, row, 3)
            
            phib_value = QDoubleSpinBox()
            phib_value.setRange(-1000, 1000)
            phib_value.setSuffix(" uA")
            self.is_phib_values.append(phib_value)
            layout.addWidget(phib_value, row, 4)
            
        group.setLayout(layout)
        self.layout().addWidget(group)           

class ConnectThread(QThread):
    """
    后台连接线程：专门负责去尝试连接 Socket，防止主界面卡死
    """
    # 定义一个信号：当连接结束时，把结果发射出去
    # 参数类型：(板卡类型(字符串), 是否成功(布尔值), 附带信息或Socket对象)
    finished_signal = pyqtSignal(str, bool, object)

    def __init__(self, board_type, ip, port=5000):
        super().__init__()
        self.board_type = board_type
        self.ip = ip
        self.port = port

    def run(self):
        """线程启动时会自动执行这里的代码"""
        try:
            # 创建 TCP Socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)  # 强制 2 秒超时，连不上就报错，不死等
            
            # 尝试连接（这一步非常耗时，但因为它在后台，所以主界面不会卡）
            sock.connect((self.ip, self.port))
            
            self.finished_signal.emit(self.board_type, True, sock)
            
        except Exception as e:
            # 如果发生错误（超时、拒接等），发射失败信号和错误信息
            self.finished_signal.emit(self.board_type, False, str(e))
            
class SendCommandThread(QThread):
    """
    后台通讯线程：专门负责发送指令并等待板卡回复，防止主界面在等待回复时卡死
    """
    # 信号：板卡类型, 是否成功, 收到回复的内容(或错误信息)
    response_signal = pyqtSignal(str, bool, str)

    def __init__(self, board_type, sock, command):
        super().__init__()
        self.board_type = board_type
        self.sock = sock
        self.command = command

    def run(self):
        try:
            # 1. 发送数据 (encode将字符串转为字节流发送)
            # 在工业协议中，通常会在末尾加一个换行符 \n 或 \r\n，这里先用普通的
            self.sock.sendall(self.command.encode('utf-8'))
            
            # 2. 准备接收回复 (最多接收 1024 字节)
            # 注意：如果板卡没回复，这里会一直等，直到触发我们之前设置的 2秒超时
            response_bytes = self.sock.recv(1024)
            
            if response_bytes:
                # 收到数据，解码并发送成功信号
                response_str = response_bytes.decode('utf-8', errors='ignore').strip()
                self.response_signal.emit(self.board_type, True, response_str)
            else:
                self.response_signal.emit(self.board_type, False, "板卡断开了连接 (收到空字节)")
                
        except socket.timeout:
            self.response_signal.emit(self.board_type, False, "等待回复超时")
        except Exception as e:
            self.response_signal.emit(self.board_type, False, f"通讯异常: {str(e)}")            
            

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 【新增：网络相关的字典】
        self.active_sockets = {}    # 存放连上的 socket 对象
        self.connect_threads = {}   # 存放正在连接的后台线程，防止被 Python 垃圾回收
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("TDM Software V1.0")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create a central widget and set it as the central widget of the main window
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # Create tabs
        self.setup_connection_tab()
        self.setup_bias_control_tab()
        self.setup_ad_da_tab()
        self.setup_fpga_tab()
        self.setup_monitor_tab()
        
    def setup_connection_tab(self):
        widget = QWidget()  # Create a widget for the connection tab
        layout = QVBoxLayout() # Create a vertical layout for the connection tab
        
        connection_group = QGroupBox("Connection Settings")  # Create a group box for the connection settings
        connection_layout = QGridLayout()  # Create a vertical layout for the connection settings
        
        board_configs = [
            ('偏置源板卡 1', 'bias1',        '192.168.1.11'),
            ('偏置源板卡 2', 'bias2',        '192.168.1.12'),
            ('偏置源板卡 3', 'bias3',        '192.168.1.13'),
            ('ADC 读出板',   'ADC_readout',  '192.168.1.14'),
            ('FB DAC 板',    'FB_DAC',       '192.168.1.15'),
            ('选通 DAC 板',  'gate_DAC',     '192.168.1.16'),
            ('FPGA 汇总板',  'fpga',         '192.168.1.10'),
        ]
        
        #准备空字典来存储输入框
        self.board_ip_edits = {}
        self.board_connection_btns = {}
        self.board_status_labels= {}
        
        widget.setLayout(layout)  # Set the layout for the connection tab
        self.tabs.addTab(widget, "板卡控制")  # Add the connection tab to the tab widget
        
        # 循环生成每一行的控件
        for i,(name, board_type, default_ip) in enumerate(board_configs): 
            # first column: board name label
            connection_layout.addWidget(QLabel(name), i, 0) 
            
            # second column: IP address input box
            ip_edit = QLineEdit(default_ip) 
            ip_edit.setMinimumWidth(150) # set minimum width for better appearance
            self.board_ip_edits[board_type] = ip_edit # store the input box in the dictionary for later use
            connection_layout.addWidget(ip_edit, i, 1)
            
            # third column: connection button
            connect_btn = QPushButton("连接")
            connect_btn.setMaximumWidth(80) # set maximum width for better appearance

            # 信号与槽连接
            connect_btn.clicked.connect(lambda checked, bt=board_type: self.connect_single_board(bt))
            self.board_connection_btns[board_type] = connect_btn # store the button in the dictionary for later use
            connection_layout.addWidget(connect_btn, i, 2)
            
            # fourth column: connection status label
            status_label = QLabel("未连接")
            status_label.setStyleSheet("color: red; font-weight: bold;") # set text color to red for "not connected" status   
            status_label.setMidLineWidth(80) # set a fixed width for better appearance
            self.board_status_labels[board_type] = status_label # store the label in the dictionary for later use
            connection_layout.addWidget(status_label, i, 3)
            
        connection_group.setLayout(connection_layout) # Set the layout for the connection group box
        layout.addWidget(connection_group) # Add the connection group box to the main layout of the

        #批量操作的按钮
        button_layout = QHBoxLayout() # 横向布局
        
        self.connect_all_btn = QPushButton("连接所有板卡")
        self.connect_all_btn.setMinimumHeight(40)
        #绑定点击事件到函数
        self.connect_all_btn.clicked.connect(self.connect_all_boards)
        button_layout.addWidget(self.connect_all_btn)
        
        button_layout.setSpacing(60)
        
        self.disconnect_all_btn = QPushButton("断开所有连接")
        self.disconnect_all_btn.setMinimumHeight(40)
        #绑定点击事件到断开按钮
        self.disconnect_all_btn.clicked.connect(self.disconnect_all_boards)
        button_layout.addWidget(self.disconnect_all_btn)
        
        layout.addLayout(button_layout)
        
        #日志显示区域
        layout.addStretch()
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout()
        self.connection_log = QTextEdit()
        self.connection_log.setMaximumHeight(150)
        self.connection_log.setReadOnly(True) # 日志框设为只读
        log_layout.addWidget(self.connection_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
               # =================【新增：通讯测试区】=================
        test_group = QGroupBox("底层通讯测试 (Debug)")
        test_layout = QHBoxLayout()
        
        test_layout.addWidget(QLabel("选择板卡:"))
        self.test_board_selector = _QComboBox() # 用我们安全重写的下拉框
        # 把板卡代号加进去
        self.test_board_selector.addItems(['bias1', 'bias2', 'bias3', 'ADC_readout', 'FB_DAC', 'gate_DAC', 'fpga'])
        test_layout.addWidget(self.test_board_selector)
        
        test_layout.addWidget(QLabel("测试指令:"))
        self.test_cmd_input = _QLineEdit("*IDN?") # 很多仪器默认查身分的指令是 *IDN?
        test_layout.addWidget(self.test_cmd_input)
        
        self.test_send_btn = QPushButton("发送并等待回复")
        self.test_send_btn.clicked.connect(self.on_test_send_clicked)
        test_layout.addWidget(self.test_send_btn)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        # ====================================================

        layout.addStretch() # 原来的代码
        widget.setLayout(layout)
        self.tabs.addTab(widget, "板卡连接")
        
    def setup_bias_control_tab(self):
        """偏置源控制选项卡 (采用子标签页方案)"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # ================= 1. 创建子标签页控件 =================
        self.bias_sub_tabs = QTabWidget()
        # 优化标签页样式：加粗、加大字号、设置最小宽度防截断
        self.bias_sub_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #C0C0C0; }
            QTabBar::tab { 
                padding: 8px 15px; 
                font-size: 13px; 
                font-weight: bold; 
                min-width: 100px; 
            }
            QTabBar::tab:selected {
                background-color: #E8F0FE; /* 选中的标签变亮蓝色，更好看 */
                color: #0055A4;
            }
        """)
        
        # ================= 2. 将三块板卡加入子标签页 =================
        # 原来需要我们自己手动创建堆叠布局，现在全部交给 sub_tabs 自动管理
        self.bias_boards = []
        for i in range(3):
            # 创建带滚动条的外壳（防止通道太多撑爆屏幕）
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setStyleSheet("QScrollArea { border: none; }")
            
            # 实例化我们写好的板卡界面
            board_widget = BiasBoardWidget(board_id=i)
            self.bias_boards.append(board_widget)
            
            # 把板卡装进滚动条
            scroll_area.setWidget(board_widget)
            
            # 把滚动条作为一个全新的标签页，加入到 sub_tabs 中
            self.bias_sub_tabs.addTab(scroll_area, f"偏置源板卡 {i+1}")
            
        layout.addWidget(self.bias_sub_tabs)
        
        # ================= 3. 底部公共操作按钮 =================
        # 这些按钮放在子标签页的外面，意味着不管切到哪个板卡，都能点这几个按钮
        button_layout = QHBoxLayout()
        self.read_bias_btn = QPushButton("读取参数")
        self.write_bias_btn = QPushButton("写入参数")
        self.save_bias_btn = QPushButton("保存配置")
        
        button_layout.addWidget(self.read_bias_btn)
        button_layout.addWidget(self.write_bias_btn)
        button_layout.addWidget(self.save_bias_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        widget.setLayout(layout)
        self.tabs.addTab(widget, "偏置源控制")
   
    # def setup_bias_control_tab(self):
    #     widget = QWidget()  
    #     layout = QVBoxLayout()
        
    #     #板卡选择下拉框
    #     board_select_group = QGroupBox("偏置源板卡")
    #     board_layout = QHBoxLayout()
    #     board_layout.addWidget(QLabel("当前板卡："))
    #     self.bias_board_selector = QComboBox()
    #     self.bias_board_selector.addItems(["偏置源板卡 1", "偏置源板卡 2", "偏置源板卡 3"])
    #     #绑定选择事件
    #     self.bias_board_selector.currentIndexChanged.connect(self.switch_bias_board)
    #     board_layout.addWidget(self.bias_board_selector)
    #     board_layout.addStretch()
    #     board_select_group.setLayout(board_layout)
    #     layout.addWidget(board_select_group)
        
        
        
    #     #三块偏置源板卡的独立控件
    #     # self.bias_stack = QWidget()
    #     # stack_layout = QVBoxLayout()
    #     # stack_layout.setContentsMargins(0,0,0,0) # 去掉内部边距
    #     # self.bias_board = []    
    #     # for i in range(3):
    #     #     bias_widget = BiasBoardWidget(board_id=i)
    #     #     self.bias_board.append(bias_widget)
    #     #     stack_layout.addWidget(bias_widget)
    #     # self.bias_stack.setLayout(stack_layout)
    #     # layout.addWidget(self.bias_stack)
        
    #     # 新 创建滚动区域
    #     scroll_area = QScrollArea()
    #     scroll_area.setWidgetResizable(True) # 允许内部控件随窗口拉伸
    #     scroll_area.setStyleSheet("QScrollArea { border: none; }") # 去掉难看的自带边框
        
    #     self.bias_stack = QWidget()
    #     stack_layout = QVBoxLayout()
    #     stack_layout.setContentsMargins(0, 0, 0, 0)
        
    #     self.bias_board = []
    #     for i in range(3):
    #         board_widget = BiasBoardWidget(board_id=i)
    #         self.bias_board.append(board_widget)
    #         stack_layout.addWidget(board_widget)
            
    #     self.bias_stack.setLayout(stack_layout)
        
    #     # 把底板装进滚动条，再把滚动条装进主布局
    #     scroll_area.setWidget(self.bias_stack)
    #     layout.addWidget(scroll_area)
        
    #     #底部的控制按钮
    #     button_layout = QHBoxLayout()
    #     self.read_bias_btn = QPushButton("读取参数")
    #     self.write_bias_btn = QPushButton("写入参数")
    #     self.save_bias_btn = QPushButton("保存配置")
    #     button_layout.addWidget(self.read_bias_btn)
    #     button_layout.addWidget(self.write_bias_btn)
    #     button_layout.addWidget(self.save_bias_btn)
    #     button_layout.addStretch()
    #     layout.addLayout(button_layout)
        
    #     widget.setLayout(layout)
    #     self.tabs.addTab(widget, "偏置源控制")  
        
    #     #默认显示第一块板卡的控件
    #     self.switch_bias_board(0)
    
        # def switch_bias_board(self, index):
    #     #只显示当前选中的板卡界面，隐藏其他板卡界面
    #     for i, board in enumerate(self.bias_board):
    #         # setVisible(True) 则显示，False 则隐藏
    #         board.setVisible(i == index) 
        
    def setup_ad_da_tab(self):
        """AD/DA控制选项卡的主体框架"""
        widget = QWidget()
        main_layout = QVBoxLayout()
        
        # === 核心修复：创建真正的滚动区域 ===
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True) # 允许内部的控件随窗口拉伸
        
        # 创建一个“超大号底板”来承载所有控件，把它塞进滚动区域里
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout()
        
        # 第一行：ADC读出控制(左) 和 FB DAC控制(右) 横向排列
        top_row_layout = QHBoxLayout()
        
        # --- 左侧：ADC ---
        adc_container = QWidget()
        adc_layout = QVBoxLayout()
        adc_layout.setContentsMargins(0, 0, 0, 0) # 去除边缘留白
        self.setup_adc_control(adc_layout) # 把布局传给专门的函数去填充
        adc_container.setLayout(adc_layout)
        top_row_layout.addWidget(adc_container)
        
        # --- 右侧：FB DAC ---
        fb_dac_container = QWidget()
        fb_dac_layout = QVBoxLayout()
        fb_dac_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_fb_dac_control(fb_dac_layout)
        fb_dac_container.setLayout(fb_dac_layout)
        top_row_layout.addWidget(fb_dac_container)
        
        scroll_layout.addLayout(top_row_layout)
        self.setup_gate_dac_control(scroll_layout)
        
        scroll_content.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_content)
        
        main_layout.addWidget(scroll_area)
        widget.setLayout(main_layout)
        self.tabs.addTab(widget, "AD/DA控制")

    def setup_fpga_tab(self):
        """FPGA数据汇总选项卡"""
        widget = QWidget()
        main_layout = QVBoxLayout()
        
        # ================= 1. FPGA 主控制区 (带状态指示灯) =================
        control_group = QGroupBox("FPGA主控制")
        control_layout = QHBoxLayout()
        
        # --- 数据读出开关 ---
        data_read_layout = QVBoxLayout()
        self.data_read_switch = QCheckBox("数据读出开关")
        self.data_read_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.data_read_switch.stateChanged.connect(self.on_data_read_changed)
        data_read_layout.addWidget(self.data_read_switch)
        
        # 画一个圆点当指示灯
        self.data_read_indicator = QLabel("●")
        self.data_read_indicator.setAlignment(Qt.AlignCenter)
        self.data_read_indicator.setStyleSheet("color: red; font-size: 24px;") # 默认红色
        data_read_layout.addWidget(self.data_read_indicator)
        data_read_layout.addWidget(QLabel("数据读出状态"))
        control_layout.addLayout(data_read_layout)

        # --- 反馈控制开关 ---
        fb_control_layout = QVBoxLayout()
        self.fb_control_switch = QCheckBox("反馈控制开关")
        self.fb_control_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.fb_control_switch.stateChanged.connect(self.on_fb_control_changed)
        fb_control_layout.addWidget(self.fb_control_switch)
        
        self.fb_control_indicator = QLabel("●")
        self.fb_control_indicator.setAlignment(Qt.AlignCenter)
        self.fb_control_indicator.setStyleSheet("color: red; font-size: 24px;")
        fb_control_layout.addWidget(self.fb_control_indicator)
        fb_control_layout.addWidget(QLabel("反馈控制状态"))
        control_layout.addLayout(fb_control_layout)
        
        # --- 选通控制开关 ---
        gate_control_layout = QVBoxLayout()
        self.gate_control_switch = QCheckBox("选通控制开关")
        self.gate_control_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.gate_control_switch.stateChanged.connect(self.on_gate_control_changed)
        gate_control_layout.addWidget(self.gate_control_switch)
        
        self.gate_control_indicator = QLabel("●")
        self.gate_control_indicator.setAlignment(Qt.AlignCenter)
        self.gate_control_indicator.setStyleSheet("color: red; font-size: 24px;")
        gate_control_layout.addWidget(self.gate_control_indicator)
        gate_control_layout.addWidget(QLabel("选通控制状态"))
        control_layout.addLayout(gate_control_layout)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # ================= 2. PID 参数控制区 (20行16列) =================
        pid_group = QGroupBox("PID参数控制 (20行 × 16列)")
        pid_main_layout = QVBoxLayout()
        
        # --- 顶部：PID参数设置 ---
        pid_param_layout = QHBoxLayout()
        self.pid_master_switch = QCheckBox("PID参数 总开关")
        self.pid_master_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.pid_master_switch.stateChanged.connect(self.toggle_all_pid)
        pid_param_layout.addWidget(self.pid_master_switch)
        
        # (加点间距)
        pid_param_layout.addSpacing(30) 
        
        pid_param_layout.addWidget(QLabel("P系数:"))
        self.pid_p_value = QLineEdit("0x100")
        self.pid_p_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_p_value)
        
        pid_param_layout.addWidget(QLabel("I系数:"))
        self.pid_i_value = QLineEdit("0x1")
        self.pid_i_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_i_value)
        
        pid_param_layout.addWidget(QLabel("D系数:"))
        self.pid_d_value = QLineEdit("0x0")
        self.pid_d_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_d_value)
        
        pid_param_layout.addWidget(QLabel("缩放因子:"))
        self.pid_scale_value = QLineEdit("0xD")
        self.pid_scale_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_scale_value)
        
        pid_param_layout.addStretch()
        pid_main_layout.addLayout(pid_param_layout)
        
        # --- 底部：超级大表格 QTableWidget ---
        self.pid_table = QTableWidget()
        self.pid_table.setRowCount(20) # 设置20行
        self.pid_table.setColumnCount(16) # 设置16列
        
        # 设置表头
        row_headers = [f"行{i+1}" for i in range(20)]
        col_headers = [f"列{i+1}" for i in range(16)]
        self.pid_table.setVerticalHeaderLabels(row_headers)
        self.pid_table.setHorizontalHeaderLabels(col_headers)
        
        # 准备一个二维列表来存放所有的开关和数值框
        self.pid_switches = []
        self.pid_values = []
        
        # 嵌套循环生成 320 个单元格
        for row in range(20):
            row_switches = []
            row_values = []
            for col in range(16):
                # 创建一个小底板，把开关和数字框纵向排在一起
                cell_widget = QWidget()
                cell_layout = QVBoxLayout()
                cell_layout.setContentsMargins(2, 2, 2, 2)
                
                switch = QCheckBox()
                row_switches.append(switch)
                cell_layout.addWidget(switch)
                
                value = QDoubleSpinBox()
                value.setRange(-10, 10)
                value.setDecimals(3)
                row_values.append(value)
                cell_layout.addWidget(value)
                
                cell_widget.setLayout(cell_layout)
                
                # 【核心】：把做好的小部件塞进表格的特定单元格里
                self.pid_table.setCellWidget(row, col, cell_widget)
            
            self.pid_switches.append(row_switches)
            self.pid_values.append(row_values)
        
        # 调整一下单元格的默认大小，让它看起来更顺眼
        self.pid_table.horizontalHeader().setDefaultSectionSize(70)
        self.pid_table.verticalHeader().setDefaultSectionSize(65)
        
        pid_main_layout.addWidget(self.pid_table)
        pid_group.setLayout(pid_main_layout)
        main_layout.addWidget(pid_group)
        
        # ================= 3. 数据存储设置区 =================
        storage_group = QGroupBox("数据存储设置")
        storage_layout = QVBoxLayout()
        
        # --- 第一行：存储路径 ---
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("存储路径:"))
        self.storage_path = QLineEdit()
        self.storage_path.setPlaceholderText("请选择数据存储路径...") # 占位提示词
        self.storage_path.setReadOnly(True) # 不允许手动乱敲，只能通过浏览按钮选
        self.storage_path.setMinimumWidth(300)
        path_layout.addWidget(self.storage_path)
        
        self.browse_path_btn = QPushButton("浏览...")
        self.browse_path_btn.setMaximumWidth(80)
        self.browse_path_btn.clicked.connect(self.browse_storage_path) # 绑定浏览文件夹弹窗
        path_layout.addWidget(self.browse_path_btn)
        path_layout.addStretch()
        storage_layout.addLayout(path_layout)
        
        # --- 第二行：存储格式和控制 ---
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("存储格式:"))
        self.storage_format = QComboBox()
        self.storage_format.addItems(["二进制(.bin)", "二进制(.dat)"])
        format_layout.addWidget(self.storage_format)
        
        format_layout.addSpacing(20)
        format_layout.addWidget(QLabel("文件名前缀:"))
        self.file_prefix = QLineEdit("fpga_data")
        self.file_prefix.setMaximumWidth(150)
        format_layout.addWidget(self.file_prefix)
        
        format_layout.addSpacing(20)
        self.start_storage_btn = QPushButton("开始存储")
        format_layout.addWidget(self.start_storage_btn)
        
        self.stop_storage_btn = QPushButton("停止存储")
        self.stop_storage_btn.setEnabled(False) # 还没开始存，所以“停止”按钮默认置灰
        format_layout.addWidget(self.stop_storage_btn)
        
        self.storage_status_label = QLabel("状态: 未存储")
        self.storage_status_label.setStyleSheet("color: gray; font-weight: bold;")
        format_layout.addWidget(self.storage_status_label)
        format_layout.addStretch()
        storage_layout.addLayout(format_layout)
        
        # --- 第三行：存储信息显示 ---
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("当前文件:"))
        self.current_file_label = QLabel("无")
        self.current_file_label.setStyleSheet("color: blue;")
        info_layout.addWidget(self.current_file_label)
        
        info_layout.addSpacing(20)
        info_layout.addWidget(QLabel("已存储大小:"))
        self.storage_size_label = QLabel("0 KB")
        self.storage_size_label.setStyleSheet("color: green;")
        info_layout.addWidget(self.storage_size_label)
        info_layout.addStretch()
        storage_layout.addLayout(info_layout)
        
        storage_group.setLayout(storage_layout)
        main_layout.addWidget(storage_group)
        
        # ================= 4. 实时数据监控文本框 =================
        monitor_group = QGroupBox("实时数据监控")
        monitor_layout = QVBoxLayout()
        self.data_monitor = QTextEdit()
        self.data_monitor.setMaximumHeight(150)
        self.data_monitor.setReadOnly(True)
        monitor_layout.addWidget(self.data_monitor)
        monitor_group.setLayout(monitor_layout)
        main_layout.addWidget(monitor_group)
        
        widget.setLayout(main_layout)
        self.tabs.addTab(widget, "FPGA数据汇总")

    # ================= 槽函数：开关控制灯泡变色 =================
    def on_data_read_changed(self, state):
        if state == 2:
            self.data_read_indicator.setStyleSheet("color: green; font-size: 24px;")
        else:
            self.data_read_indicator.setStyleSheet("color: red; font-size: 24px;")

    def on_fb_control_changed(self, state):
        if state == 2:
            self.fb_control_indicator.setStyleSheet("color: green; font-size: 24px;")
        else:
            self.fb_control_indicator.setStyleSheet("color: red; font-size: 24px;")
            
    def on_gate_control_changed(self, state):
        if state == 2:
            self.gate_control_indicator.setStyleSheet("color: green; font-size: 24px;")
        else:
            self.gate_control_indicator.setStyleSheet("color: red; font-size: 24px;")
            
    def toggle_all_pid(self, state):
        checked = (state == 2)
        # 二维数组的遍历
        for row in range(20):
            for col in range(16):
                self.pid_switches[row][col].setChecked(checked)
    
    def setup_adc_control(self, parent_layout):
        """ADC读出控制 (左侧部分)"""
        group = QGroupBox("ADC读出控制 (16列)")
        layout = QGridLayout()
        
        # 总开关
        self.adc_master_switch = QCheckBox("ADC 总开关")
        self.adc_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.adc_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_switches])
        layout.addWidget(self.adc_master_switch, 0, 1, 1, 2)
        
        self.adc_offset_master_switch = QCheckBox("ADC offset 总开关")
        self.adc_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.adc_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_offset_switches])
        layout.addWidget(self.adc_offset_master_switch, 0, 3, 1, 2)
        
        # 表头
        headers = ["列", "ADC开关", "ADC输出值", "offset开关", "offset值"]
        for col, text in enumerate(headers):
            layout.addWidget(QLabel(text), 1, col)
            
        self.adc_switches, self.adc_values = [], []
        self.adc_offset_switches, self.adc_offset_values = [], []
        
        # 16路通道
        for i in range(16):
            row = i + 2
            layout.addWidget(QLabel(f"列{i+1}"), row, 0)
            
            # ADC
            adc_switch = QCheckBox()
            self.adc_switches.append(adc_switch)
            layout.addWidget(adc_switch, row, 1)
            
            adc_value = QDoubleSpinBox()
            adc_value.setRange(-10, 10)
            adc_value.setSuffix(" V")
            adc_value.setDecimals(3) # 设置保留3位小数
            self.adc_values.append(adc_value)
            layout.addWidget(adc_value, row, 2)
            
            # Offset
            offset_switch = QCheckBox()
            self.adc_offset_switches.append(offset_switch)
            layout.addWidget(offset_switch, row, 3)
            
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.adc_offset_values.append(offset_value)
            layout.addWidget(offset_value, row, 4)
            
        group.setLayout(layout)
        parent_layout.addWidget(group)

    def setup_fb_dac_control(self, parent_layout):
        """FB DAC控制 (右侧部分) - 结构与ADC几乎一样"""
        group = QGroupBox("FB DAC控制 (16列)")
        layout = QGridLayout()
        
        self.fb_dac_master_switch = QCheckBox("DAC 总开关")
        self.fb_dac_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.fb_dac_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.fb_dac_switches])
        layout.addWidget(self.fb_dac_master_switch, 0, 1, 1, 2)
        
        self.fb_dac_offset_master_switch = QCheckBox("DAC offset 总开关")
        self.fb_dac_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.fb_dac_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.fb_dac_offset_switches])
        layout.addWidget(self.fb_dac_offset_master_switch, 0, 3, 1, 2)
        
        headers = ["列", "DAC开关", "DAC输出值", "offset开关", "offset值"]
        for col, text in enumerate(headers):
            layout.addWidget(QLabel(text), 1, col)
            
        self.fb_dac_switches, self.fb_dac_values = [], []
        self.fb_dac_offset_switches, self.fb_dac_offset_values = [], []
        
        for i in range(16):
            row = i + 2
            layout.addWidget(QLabel(f"列{i+1}"), row, 0)
            
            dac_switch = QCheckBox()
            self.fb_dac_switches.append(dac_switch)
            layout.addWidget(dac_switch, row, 1)
            
            dac_value = QDoubleSpinBox()
            dac_value.setRange(-10, 10)
            dac_value.setSuffix(" V")
            dac_value.setDecimals(3)
            self.fb_dac_values.append(dac_value)
            layout.addWidget(dac_value, row, 2)
            
            offset_switch = QCheckBox()
            self.fb_dac_offset_switches.append(offset_switch)
            layout.addWidget(offset_switch, row, 3)
            
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.fb_dac_offset_values.append(offset_value)
            layout.addWidget(offset_value, row, 4)
            
        group.setLayout(layout)
        parent_layout.addWidget(group)
    
    def setup_gate_dac_control(self, parent_layout):
        """选通DAC控制 (下半部分)"""
        group = QGroupBox("选通DAC控制 (20行)")
        main_layout = QVBoxLayout()
        
        # ================= 1. 20行选通参数设定 =================
        param_group = QGroupBox("20行选通参数设定")
        param_layout = QGridLayout()
        
        # 第0行参数
        param_layout.addWidget(QLabel("波形类型:"), 0, 0)
        self.gate_waveform = QComboBox()
        self.gate_waveform.addItems(["某一行DC", "三角波", "方波", "正弦波"])
        param_layout.addWidget(self.gate_waveform, 0, 1)
        
        param_layout.addWidget(QLabel("频率:"), 0, 2)
        self.gate_frequency = QDoubleSpinBox()
        self.gate_frequency.setRange(0.1, 100000)
        self.gate_frequency.setValue(1000)
        self.gate_frequency.setSuffix(" Hz")
        param_layout.addWidget(self.gate_frequency, 0, 3)
        
        # 第1行参数
        param_layout.addWidget(QLabel("幅值:"), 1, 0)
        # 注意这里：原代码因为要输入 16进制，所以用了 QLineEdit 文本框
        self.gate_amplitude = QLineEdit("0xFFFF") 
        param_layout.addWidget(self.gate_amplitude, 1, 1)
        
        param_layout.addWidget(QLabel("选通开始延迟时间:"), 1, 2)
        # 这里用的是 QSpinBox (整数输入框)
        self.gate_start_delay = QSpinBox()
        self.gate_start_delay.setRange(0, 10000)
        self.gate_start_delay.setValue(0)
        self.gate_start_delay.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_delay, 1, 3)
        
        # 第2行参数
        param_layout.addWidget(QLabel("选通开始稳态时间:"), 2, 0)
        self.gate_start_steady = QSpinBox()
        self.gate_start_steady.setRange(0, 10000)
        self.gate_start_steady.setValue(100)
        self.gate_start_steady.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_steady, 2, 1)
        
        param_layout.addWidget(QLabel("选通结束稳态时间:"), 2, 2)
        self.gate_end_steady = QSpinBox()
        self.gate_end_steady.setRange(0, 10000)
        self.gate_end_steady.setValue(100)
        self.gate_end_steady.setSuffix(" ns")
        param_layout.addWidget(self.gate_end_steady, 2, 3)
        
        param_group.setLayout(param_layout)
        main_layout.addWidget(param_group)
        
        # ================= 2. 20行DAC控制矩阵 =================
        dac_layout = QGridLayout()
        
        # 总开关
        self.gate_dac_master_switch = QCheckBox("20行DAC 总开关")
        self.gate_dac_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.gate_dac_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.gate_dac_switches])
        dac_layout.addWidget(self.gate_dac_master_switch, 0, 1, 1, 2)
        
        self.gate_dac_offset_master_switch = QCheckBox("20行offset 总开关")
        self.gate_dac_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.gate_dac_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.gate_dac_offset_switches])
        dac_layout.addWidget(self.gate_dac_offset_master_switch, 0, 3, 1, 2)
        
        # 表头
        headers = ["行", "DAC开关", "DAC输出值", "offset开关", "offset值"]
        for col, text in enumerate(headers):
            dac_layout.addWidget(QLabel(text), 1, col)
            
        self.gate_dac_switches, self.gate_dac_values = [], []
        self.gate_dac_offset_switches, self.gate_dac_offset_values = [], []
        
        # 【注意】这里是 20 行，不是 16 行了
        for i in range(20):
            row = i + 2
            dac_layout.addWidget(QLabel(f"行{i+1}"), row, 0)
            
            dac_switch = QCheckBox()
            self.gate_dac_switches.append(dac_switch)
            dac_layout.addWidget(dac_switch, row, 1)
            
            dac_value = QDoubleSpinBox()
            dac_value.setRange(-10, 10)
            dac_value.setSuffix(" V")
            dac_value.setDecimals(3)
            self.gate_dac_values.append(dac_value)
            dac_layout.addWidget(dac_value, row, 2)
            
            offset_switch = QCheckBox()
            self.gate_dac_offset_switches.append(offset_switch)
            dac_layout.addWidget(offset_switch, row, 3)
            
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.gate_dac_offset_values.append(offset_value)
            dac_layout.addWidget(offset_value, row, 4)
            
        main_layout.addLayout(dac_layout)
        group.setLayout(main_layout)
        parent_layout.addWidget(group)
            
        
    def connect_single_board(self, board_type):
        """处理单个板卡的连接/断开点击"""
        current_text = self.board_connection_btns[board_type].text()
        
        # 状态 1：明确要求【连接】
        if current_text == "连接":
            ip = self.board_ip_edits[board_type].text()
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 正在后台尝试连接 ({ip})...")
            
            self.board_status_labels[board_type].setText("连接中...")
            self.board_status_labels[board_type].setStyleSheet("color: orange; font-weight: bold;")
            self.board_connection_btns[board_type].setEnabled(False)
            
            thread = ConnectThread(board_type, ip)
            thread.finished_signal.connect(self.on_connect_finished)
            self.connect_threads[board_type] = thread
            thread.start()
            
        # 状态 2：明确要求【断开】
        elif current_text == "断开":
            if board_type in self.active_sockets:
                try:
                    self.active_sockets[board_type].close()
                except:
                    pass
                del self.active_sockets[board_type]
                
            self.board_status_labels[board_type].setText("未连接")
            self.board_status_labels[board_type].setStyleSheet("color: red; font-weight: bold;")
            self.board_connection_btns[board_type].setText("连接")
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接已断开")
            
        # 状态 3：如果是 "连接中..." 等其他状态，直接无视（防狂点）
        else:
            pass 

    def connect_all_boards(self):
        """一键连接所有板卡 (严格判断状态)"""
        self.connection_log.append(f"\n[{time.strftime('%H:%M:%S')}] 开始尝试连接未连的板卡...")
        for board_type in self.board_ip_edits.keys():
            # 只有明确处于“连接”待机状态的按钮，才去触发
            if self.board_connection_btns[board_type].text() == "连接":
                self.connect_single_board(board_type)

    def disconnect_all_boards(self):
        """一键断开所有板卡 (严格判断状态)"""
        self.connection_log.append(f"\n[{time.strftime('%H:%M:%S')}] 开始断开已连的板卡...")
        for board_type in self.board_ip_edits.keys():
            # 只有明确处于“断开”待机状态的按钮，才去触发
            if self.board_connection_btns[board_type].text() == "断开":
                self.connect_single_board(board_type)

    def on_connect_finished(self, board_type, success, result):
        """后台工人汇报结果的槽函数"""
        # 恢复按钮的点击能力
        self.board_connection_btns[board_type].setEnabled(True)
        
        if success:
            # 成功,result 里面装的是那个做好的 socket 对象
            self.active_sockets[board_type] = result
            
            self.board_status_labels[board_type].setText("已连接")
            self.board_status_labels[board_type].setStyleSheet("color: green; font-weight: bold;")
            self.board_connection_btns[board_type].setText("断开")
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接成功！")
        else:
            # 失败,result 里面装的是错误原因的字符串
            self.board_status_labels[board_type].setText("未连接")
            self.board_status_labels[board_type].setStyleSheet("color: red; font-weight: bold;")
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接失败: {result}")
            
    def on_test_send_clicked(self):
        """点击测试发送按钮"""
        board_type = self.test_board_selector.currentText()
        command = self.test_cmd_input.text()
        
        # 1. 检查有没有连上
        if board_type not in self.active_sockets:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 错误: {board_type} 尚未连接！")
            return
            
        sock = self.active_sockets[board_type]
        
        # 2. 记录日志并禁用按钮防连点
        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] -> 发送给 {board_type}: {command}")
        self.test_send_btn.setEnabled(False)
        self.test_send_btn.setText("等待回复...")
        
        # 3. 开启后台通讯线程
        # 为了防止线程被垃圾回收，我们需要像之前一样把它存进字典
        if not hasattr(self, 'comm_threads'):
            self.comm_threads = {}
            
        thread = SendCommandThread(board_type, sock, command)
        thread.response_signal.connect(self.on_test_response_received)
        self.comm_threads[board_type] = thread
        thread.start()

    def on_test_response_received(self, board_type, success, message):
        """后台通讯线程结束后的回调"""
        # 恢复按钮
        self.test_send_btn.setEnabled(True)
        self.test_send_btn.setText("发送并等待回复")
        
        if success:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] <- 收到 {board_type} 回复: {message}")
        else:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] ❌ {board_type} 通讯失败: {message}")
            # 如果断开了，还可以顺手在界面上做清理，把灯变成红色（这里先省略）
    
    def browse_storage_path(self):
        """打开系统原生的文件夹选择弹窗"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择数据存储目录",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        # 如果用户选了路径（没点取消），就把路径填进文本框
        if directory:
            self.storage_path.setText(directory)
            import time
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 存储路径已设置: {directory}")

    def setup_monitor_tab(self):
        """第五个选项卡：系统监控"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # --- 系统状态显示 (网格布局) ---
        status_group = QGroupBox("系统状态")
        status_layout = QGridLayout()
        
        # 用数据驱动的方式快速生成 6 个状态标签
        status_labels = [
            ("通讯状态", "正常"), ("数据读出", "关"), 
            ("反馈控制", "关"), ("选通控制", "关"),
            ("FPGA状态", "正常"), ("温度监控", "正常")
        ]
        
        for i, (label_name, value) in enumerate(status_labels):
            # 同样运用巧妙的数学计算，把一维列表排成 2列 的矩阵
            row = i // 2
            col = (i % 2) * 2
            status_layout.addWidget(QLabel(f"{label_name}:"), row, col)
            
            value_label = QLabel(value)
            value_label.setStyleSheet("color: green; font-weight: bold;")
            status_layout.addWidget(value_label, row, col + 1)
            
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # --- 全局系统日志 ---
        log_group = QGroupBox("系统日志")
        log_layout = QVBoxLayout()
        self.system_log = QTextEdit()
        self.system_log.setReadOnly(True)
        log_layout.addWidget(self.system_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        widget.setLayout(layout)
        self.tabs.addTab(widget, "系统监控")        
            
            
        
            
            
        



def main():
        app = QApplication(sys.argv)
        app.setStyle('Fusion')  
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()

