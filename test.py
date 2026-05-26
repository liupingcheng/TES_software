import sys
import json
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, 
                             QGroupBox, QLabel, QComboBox, QLineEdit, QPushButton, QCheckBox, 
                             QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QTextEdit,
                             QGridLayout, QSplitter, QFrame, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor
import socket
import threading
import time

from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QStackedWidget, QFormLayout
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

class BiasBoardWidget(QWidget):
    """独立的偏置源板卡控件 (优化版)"""
    def __init__(self, board_id, parent=None):
        super().__init__(parent)
        self.board_id = board_id
        self.init_ui()
        
    def init_ui(self):
        # 整体的主布局，仍然是从上到下
        main_layout = QVBoxLayout()
        # 去除一些不必要的边缘留白，让界面紧凑一点
        main_layout.setContentsMargins(10, 10, 10, 10) 
        
        # 1. 醒目的板卡标题 (加个背景色或下划线效果更好，这里简单居中加粗)
        title_label = QLabel(f"=== 偏置源板卡 {self.board_id + 1} ===")
        title_label.setFont(QFont("Arial", 14, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)  # 标题居中
        main_layout.addWidget(title_label)
        
        # 2. 全局信号设置区 (横向排列)
        global_group = QGroupBox("全局信号参数设定")
        global_layout = QHBoxLayout()
        
        # 2.1 信号类型选择 (放在左边)
        type_layout = QFormLayout()
        self.signal_type = QComboBox()
        self.signal_type.addItems(["直流", "交流"])
        self.signal_type.setMinimumWidth(100)
        type_layout.addRow("信号类型:", self.signal_type)
        global_layout.addLayout(type_layout)
        
        # 加一条竖线作为分隔符 (视觉美化)
        from PyQt5.QtWidgets import QFrame
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        global_layout.addWidget(line)
        
        # 2.2 具体的参数设置区 (用 StackedWidget 叠加，不浪费空间)
        self.params_stack = QStackedWidget()
        
        # ---- 第一页：直流参数面板 ----
        self.dc_page = QWidget()
        dc_layout = QHBoxLayout()
        dc_layout.setContentsMargins(0, 0, 0, 0)
        
        dc_form = QFormLayout()
        self.dc_value = QDoubleSpinBox()
        self.dc_value.setRange(-1000, 1000)
        self.dc_value.setValue(0)
        self.dc_value.setSuffix(" uA")
        self.dc_value.setMinimumWidth(120)
        dc_form.addRow("直流输出值:", self.dc_value)
        
        dc_layout.addLayout(dc_form)
        dc_layout.addStretch() # 靠左对齐
        self.dc_page.setLayout(dc_layout)
        self.params_stack.addWidget(self.dc_page)
        
        # ---- 第二页：交流参数面板 ----
        self.ac_page = QWidget()
        ac_layout = QHBoxLayout()
        ac_layout.setContentsMargins(0, 0, 0, 0)
        
        ac_form1 = QFormLayout()
        self.waveform_type = QComboBox()
        self.waveform_type.addItems(["正弦波", "三角波", "方波"])
        ac_form1.addRow("波形类型:", self.waveform_type)
        
        ac_form2 = QFormLayout()
        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.1, 10000)
        self.frequency.setValue(1000)
        self.frequency.setSuffix(" Hz")
        ac_form2.addRow("频率:", self.frequency)
        
        ac_form3 = QFormLayout()
        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(0, 1000)
        self.amplitude.setValue(10)
        self.amplitude.setSuffix(" uA")
        ac_form3.addRow("幅值:", self.amplitude)
        
        ac_layout.addLayout(ac_form1)
        ac_layout.addLayout(ac_form2)
        ac_layout.addLayout(ac_form3)
        ac_layout.addStretch() # 靠左对齐
        self.ac_page.setLayout(ac_layout)
        self.params_stack.addWidget(self.ac_page)
        
        global_layout.addWidget(self.params_stack)
        # 给右边加个弹簧，不让控件被无限拉长
        global_layout.setStretch(2, 1) 
        
        global_group.setLayout(global_layout)
        main_layout.addWidget(global_group)
        
        # (预留：这里之后放 16 路通道的矩阵)
        self.channel_layout_placeholder = QVBoxLayout()
        main_layout.addLayout(self.channel_layout_placeholder)
        
        main_layout.addStretch() # 把上面内容紧紧顶上去
        self.setLayout(main_layout)
        
        # 3. 绑定信号
        self.signal_type.currentTextChanged.connect(self.on_signal_type_changed)
        
    def on_signal_type_changed(self, signal_type):
        """利用 QStackedWidget 切换页面"""
        if signal_type == "直流":
            self.params_stack.setCurrentIndex(0) # 0 是 DC_page
        else:
            self.params_stack.setCurrentIndex(1) # 1 是 AC_page

class CommunicationManager:
    """通讯管理类"""
    def __init__(self):
        self.sockets = {}
        self.connected_boards = {}
        self.board_ips = {
            'bias1': '192.168.1.11',
            'bias2': '192.168.1.12', 
            'bias3': '192.168.1.13',
            'ADC_readout': '192.168.1.14',
            'FB_DAC': '192.168.1.15',
            'gate_DAC': '192.168.1.16',
            'fpga': '192.168.1.10'
        }
        
    def connect_to_board(self, board_type):
        """连接到指定板卡"""
        try:
            # 如果已经连接，先断开
            if board_type in self.sockets:
                self.disconnect_board(board_type)
                
            ip = self.board_ips[board_type]
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # 设置2秒超时
            sock.connect((ip, 5000))
            self.sockets[board_type] = sock
            self.connected_boards[board_type] = True
            return True
        except Exception as e:
            print(f"连接{board_type}失败: {e}")
            self.connected_boards[board_type] = False
            return False
    
    def disconnect_board(self, board_type):
        """断开指定板卡连接"""
        try:
            if board_type in self.sockets:
                self.sockets[board_type].close()
                del self.sockets[board_type]
            self.connected_boards[board_type] = False
            return True
        except Exception as e:
            print(f"断开{board_type}失败: {e}")
            return False
    
    def is_connected(self, board_type):
        """检查板卡是否已连接"""
        return self.connected_boards.get(board_type, False)
            
    def send_command(self, board_type, command):
        """发送命令到指定板卡"""
        if board_type in self.sockets:
            try:
                self.sockets[board_type].send(command.encode())
                response = self.sockets[board_type].recv(1024)
                return response.decode()
            except Exception as e:
                print(f"发送命令到{board_type}失败: {e}")
                return None
        return None
    
    def disconnect_all(self):
        """断开所有连接"""
        for board_type in list(self.sockets.keys()):
            self.disconnect_board(board_type)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.comm_manager = CommunicationManager()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("机箱上位机控制软件")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建主选项卡
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        
        # 创建各个选项卡
        self.setup_connection_tab()
        self.setup_bias_control_tab()
        self.setup_ad_da_tab()
        self.setup_fpga_tab()
        self.setup_monitor_tab()
        
        # 初始化：默认禁用AD/DA控制，必须通过FPGA开关启用
        self.enable_adc_control(False)
        self.enable_fb_dac_control(False)
        self.enable_gate_dac_control(False)
        
    def setup_connection_tab(self):
        """板卡连接选项卡"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 板卡IP地址配置
        connection_group = QGroupBox("板卡IP地址配置")
        connection_layout = QGridLayout()
        
        # 板卡配置列表
        board_configs = [
            ('偏置源板卡1', 'bias1', '192.168.1.11'),
            ('偏置源板卡2', 'bias2', '192.168.1.12'),
            ('偏置源板卡3', 'bias3', '192.168.1.13'),
            ('ADC读出板', 'ADC_readout', '192.168.1.14'),
            ('FB DAC板', 'FB_DAC', '192.168.1.15'),
            ('选通DAC板', 'gate_DAC', '192.168.1.16'),
            ('FPGA汇总板', 'fpga', '192.168.1.10'),
        ]
        
        # 存储控件引用
        self.board_ip_edits = {}
        self.board_connect_btns = {}
        self.board_status_labels = {}
        
        # 创建每个板卡的控件行
        for i, (name, board_type, default_ip) in enumerate(board_configs):
            # 板卡名称
            name_label = QLabel(name)
            connection_layout.addWidget(name_label, i, 0)
            
            # IP地址输入框
            ip_edit = QLineEdit(default_ip)
            ip_edit.setMinimumWidth(150)
            self.board_ip_edits[board_type] = ip_edit
            connection_layout.addWidget(ip_edit, i, 1)
            
            # 连接按钮
            connect_btn = QPushButton("连接")
            connect_btn.setMinimumWidth(80)
            connect_btn.clicked.connect(lambda checked, bt=board_type: self.connect_single_board(bt))
            self.board_connect_btns[board_type] = connect_btn
            connection_layout.addWidget(connect_btn, i, 2)
            
            # 状态标签
            status_label = QLabel("未连接")
            status_label.setStyleSheet("color: red; font-weight: bold;")
            status_label.setMinimumWidth(80)
            self.board_status_labels[board_type] = status_label
            connection_layout.addWidget(status_label, i, 3)
        
        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)
        
        # 批量操作按钮
        button_layout = QHBoxLayout()
        
        self.connect_all_btn = QPushButton("连接所有板卡")
        self.connect_all_btn.setMinimumHeight(40)
        self.connect_all_btn.clicked.connect(self.connect_all_boards)
        button_layout.addWidget(self.connect_all_btn)
        
        self.disconnect_all_btn = QPushButton("断开所有连接")
        self.disconnect_all_btn.setMinimumHeight(40)
        self.disconnect_all_btn.clicked.connect(self.disconnect_all_boards)
        button_layout.addWidget(self.disconnect_all_btn)
        
        layout.addLayout(button_layout)
        
        # 连接日志
        log_group = QGroupBox("连接日志")
        log_layout = QVBoxLayout()
        self.connection_log = QTextEdit()
        self.connection_log.setMaximumHeight(150)
        self.connection_log.setReadOnly(True)
        log_layout.addWidget(self.connection_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        self.tabs.addTab(widget, "板卡连接")
        
    def setup_bias_control_tab(self):
        """偏置源控制选项卡"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 偏置源板卡选择
        board_select_group = QGroupBox("偏置源板卡选择")
        board_layout = QHBoxLayout()
        board_layout.addWidget(QLabel("当前板卡:"))
        self.bias_board_selector = QComboBox()
        self.bias_board_selector.addItems(["偏置源板卡1", "偏置源板卡2", "偏置源板卡3"])
        self.bias_board_selector.currentIndexChanged.connect(self.switch_bias_board)
        board_layout.addWidget(self.bias_board_selector)
        board_layout.addStretch()
        board_select_group.setLayout(board_layout)
        layout.addWidget(board_select_group)
        
        # 偏置源板卡控件堆叠
        self.bias_stack = QWidget()
        stack_layout = QVBoxLayout()
        self.bias_boards = []
        
        for i in range(3):
            board_widget = BiasBoardWidget(i)
            self.bias_boards.append(board_widget)
            stack_layout.addWidget(board_widget)
            
        self.bias_stack.setLayout(stack_layout)
        layout.addWidget(self.bias_stack)
        
        # 控制按钮
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
        
        # 默认显示第一块板卡
        self.switch_bias_board(0)
        
    def setup_ad_da_tab(self):
        """AD/DA控制选项卡"""
        widget = QWidget()
        main_layout = QVBoxLayout()
        
        # 创建滚动区域
        scroll = QWidget()
        scroll_layout = QVBoxLayout()
        
        # 第一行：ADC读出控制和FB DAC控制横向排列
        top_row_layout = QHBoxLayout()
        
        # ADC读出控制（左侧）
        adc_container = QWidget()
        adc_layout = QVBoxLayout()
        adc_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_adc_control(adc_layout)
        adc_container.setLayout(adc_layout)
        top_row_layout.addWidget(adc_container)
        
        # FB DAC控制（右侧）
        fb_dac_container = QWidget()
        fb_dac_layout = QVBoxLayout()
        fb_dac_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_fb_dac_control(fb_dac_layout)
        fb_dac_container.setLayout(fb_dac_layout)
        top_row_layout.addWidget(fb_dac_container)
        
        scroll_layout.addLayout(top_row_layout)
        
        # 第二行：选通DAC控制
        self.setup_gate_dac_control(scroll_layout)
        
        scroll_layout.addStretch()
        scroll.setLayout(scroll_layout)
        main_layout.addWidget(scroll)
        
        widget.setLayout(main_layout)
        self.tabs.addTab(widget, "AD/DA控制")
    
    def setup_adc_control(self, parent_layout):
        """ADC读出控制"""
        group = QGroupBox("ADC读出控制 (16列)")
        layout = QGridLayout()
        
        # ADC信号总开关
        self.adc_master_switch = QCheckBox("ADC信号 总开关")
        self.adc_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.adc_master_switch.stateChanged.connect(self.toggle_all_adc)
        layout.addWidget(self.adc_master_switch, 0, 1, 1, 2)
        
        # ADC offset总开关
        self.adc_offset_master_switch = QCheckBox("ADC offset 总开关")
        self.adc_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.adc_offset_master_switch.stateChanged.connect(self.toggle_all_adc_offset)
        layout.addWidget(self.adc_offset_master_switch, 0, 3, 1, 2)
        
        # 表头
        layout.addWidget(QLabel("列"), 1, 0)
        layout.addWidget(QLabel("ADC开关"), 1, 1)
        layout.addWidget(QLabel("ADC输出值"), 1, 2)
        layout.addWidget(QLabel("offset开关"), 1, 3)
        layout.addWidget(QLabel("offset值"), 1, 4)
        
        self.adc_switches = []
        self.adc_values = []
        self.adc_offset_switches = []
        self.adc_offset_values = []
        
        for i in range(16):
            # 列标签
            layout.addWidget(QLabel(f"列{i+1}"), i+2, 0)
            
            # ADC开关
            adc_switch = QCheckBox()
            self.adc_switches.append(adc_switch)
            layout.addWidget(adc_switch, i+2, 1)
            
            # ADC输出值
            adc_value = QDoubleSpinBox()
            adc_value.setRange(-10, 10)
            adc_value.setValue(0)
            adc_value.setSuffix(" V")
            adc_value.setDecimals(3)
            self.adc_values.append(adc_value)
            layout.addWidget(adc_value, i+2, 2)
            
            # ADC offset开关
            offset_switch = QCheckBox()
            self.adc_offset_switches.append(offset_switch)
            layout.addWidget(offset_switch, i+2, 3)
            
            # ADC offset值
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setValue(0)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.adc_offset_values.append(offset_value)
            layout.addWidget(offset_value, i+2, 4)
        
        group.setLayout(layout)
        parent_layout.addWidget(group)
    
    def setup_fb_dac_control(self, parent_layout):
        """FB DAC控制"""
        group = QGroupBox("FB DAC控制 (16列)")
        layout = QGridLayout()
        
        # DAC信号总开关
        self.fb_dac_master_switch = QCheckBox("DAC信号 总开关")
        self.fb_dac_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.fb_dac_master_switch.stateChanged.connect(self.toggle_all_fb_dac)
        layout.addWidget(self.fb_dac_master_switch, 0, 1, 1, 2)
        
        # DAC offset总开关
        self.fb_dac_offset_master_switch = QCheckBox("DAC offset 总开关")
        self.fb_dac_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.fb_dac_offset_master_switch.stateChanged.connect(self.toggle_all_fb_dac_offset)
        layout.addWidget(self.fb_dac_offset_master_switch, 0, 3, 1, 2)
        
        # 表头
        layout.addWidget(QLabel("列"), 1, 0)
        layout.addWidget(QLabel("DAC开关"), 1, 1)
        layout.addWidget(QLabel("DAC输出值"), 1, 2)
        layout.addWidget(QLabel("offset开关"), 1, 3)
        layout.addWidget(QLabel("offset值"), 1, 4)
        
        self.fb_dac_switches = []
        self.fb_dac_values = []
        self.fb_dac_offset_switches = []
        self.fb_dac_offset_values = []
        
        for i in range(16):
            # 列标签
            layout.addWidget(QLabel(f"列{i+1}"), i+2, 0)
            
            # DAC开关
            dac_switch = QCheckBox()
            self.fb_dac_switches.append(dac_switch)
            layout.addWidget(dac_switch, i+2, 1)
            
            # DAC输出值
            dac_value = QDoubleSpinBox()
            dac_value.setRange(-10, 10)
            dac_value.setValue(0)
            dac_value.setSuffix(" V")
            dac_value.setDecimals(3)
            self.fb_dac_values.append(dac_value)
            layout.addWidget(dac_value, i+2, 2)
            
            # DAC offset开关
            offset_switch = QCheckBox()
            self.fb_dac_offset_switches.append(offset_switch)
            layout.addWidget(offset_switch, i+2, 3)
            
            # DAC offset值
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setValue(0)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.fb_dac_offset_values.append(offset_value)
            layout.addWidget(offset_value, i+2, 4)
        
        group.setLayout(layout)
        parent_layout.addWidget(group)
    
    def setup_gate_dac_control(self, parent_layout):
        """选通DAC控制"""
        group = QGroupBox("选通DAC控制 (20行)")
        main_layout = QVBoxLayout()
        
        # 20行选通参数设定
        param_group = QGroupBox("20行选通参数设定")
        param_layout = QGridLayout()
        
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
        
        param_layout.addWidget(QLabel("幅值:"), 1, 0)
        self.gate_amplitude = QLineEdit("0xFFFF")
        param_layout.addWidget(self.gate_amplitude, 1, 1)
        
        param_layout.addWidget(QLabel("选通开始延迟时间:"), 1, 2)
        self.gate_start_delay = QSpinBox()
        self.gate_start_delay.setRange(0, 10000)
        self.gate_start_delay.setValue(0)
        self.gate_start_delay.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_delay, 1, 3)
        
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
        
        # 20行DAC控制
        dac_layout = QGridLayout()
        
        # DAC信号总开关
        self.gate_dac_master_switch = QCheckBox("20行DAC 总开关")
        self.gate_dac_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.gate_dac_master_switch.stateChanged.connect(self.toggle_all_gate_dac)
        dac_layout.addWidget(self.gate_dac_master_switch, 0, 1, 1, 2)
        
        # DAC offset总开关
        self.gate_dac_offset_master_switch = QCheckBox("20行offset 总开关")
        self.gate_dac_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.gate_dac_offset_master_switch.stateChanged.connect(self.toggle_all_gate_dac_offset)
        dac_layout.addWidget(self.gate_dac_offset_master_switch, 0, 3, 1, 2)
        
        # 表头
        dac_layout.addWidget(QLabel("行"), 1, 0)
        dac_layout.addWidget(QLabel("DAC开关"), 1, 1)
        dac_layout.addWidget(QLabel("DAC输出值"), 1, 2)
        dac_layout.addWidget(QLabel("offset开关"), 1, 3)
        dac_layout.addWidget(QLabel("offset值"), 1, 4)
        
        self.gate_dac_switches = []
        self.gate_dac_values = []
        self.gate_dac_offset_switches = []
        self.gate_dac_offset_values = []
        
        for i in range(20):
            # 行标签
            dac_layout.addWidget(QLabel(f"行{i+1}"), i+2, 0)
            
            # DAC开关
            dac_switch = QCheckBox()
            self.gate_dac_switches.append(dac_switch)
            dac_layout.addWidget(dac_switch, i+2, 1)
            
            # DAC输出值
            dac_value = QDoubleSpinBox()
            dac_value.setRange(-10, 10)
            dac_value.setValue(0)
            dac_value.setSuffix(" V")
            dac_value.setDecimals(3)
            self.gate_dac_values.append(dac_value)
            dac_layout.addWidget(dac_value, i+2, 2)
            
            # DAC offset开关
            offset_switch = QCheckBox()
            self.gate_dac_offset_switches.append(offset_switch)
            dac_layout.addWidget(offset_switch, i+2, 3)
            
            # DAC offset值
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setValue(0)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.gate_dac_offset_values.append(offset_value)
            dac_layout.addWidget(offset_value, i+2, 4)
        
        main_layout.addLayout(dac_layout)
        group.setLayout(main_layout)
        parent_layout.addWidget(group)
    
    # 总开关切换函数
    def toggle_all_adc(self, state):
        """切换所有ADC通道"""
        checked = (state == 2)
        for switch in self.adc_switches:
            switch.setChecked(checked)
    
    def toggle_all_adc_offset(self, state):
        """切换所有ADC offset通道"""
        checked = (state == 2)
        for switch in self.adc_offset_switches:
            switch.setChecked(checked)
    
    def toggle_all_fb_dac(self, state):
        """切换所有FB DAC通道"""
        checked = (state == 2)
        for switch in self.fb_dac_switches:
            switch.setChecked(checked)
    
    def toggle_all_fb_dac_offset(self, state):
        """切换所有FB DAC offset通道"""
        checked = (state == 2)
        for switch in self.fb_dac_offset_switches:
            switch.setChecked(checked)
    
    def toggle_all_gate_dac(self, state):
        """切换所有选通DAC通道"""
        checked = (state == 2)
        for switch in self.gate_dac_switches:
            switch.setChecked(checked)
    
    def toggle_all_gate_dac_offset(self, state):
        """切换所有选通DAC offset通道"""
        checked = (state == 2)
        for switch in self.gate_dac_offset_switches:
            switch.setChecked(checked)
        
    def setup_fpga_tab(self):
        """FPGA数据汇总选项卡"""
        widget = QWidget()
        main_layout = QVBoxLayout()
        
        # 主控制区
        control_group = QGroupBox("FPGA主控制")
        control_layout = QHBoxLayout()
        
        # 数据读出开关
        data_read_layout = QVBoxLayout()
        self.data_read_switch = QCheckBox("数据读出开关")
        self.data_read_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.data_read_switch.stateChanged.connect(self.on_data_read_changed)
        data_read_layout.addWidget(self.data_read_switch)
        self.data_read_indicator = QLabel("●")
        self.data_read_indicator.setAlignment(Qt.AlignCenter)
        self.data_read_indicator.setStyleSheet("color: red; font-size: 24px;")
        data_read_layout.addWidget(self.data_read_indicator)
        data_read_layout.addWidget(QLabel("数据读出状态"))
        control_layout.addLayout(data_read_layout)

        # 反馈控制开关
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
        
        # 选通控制开关
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
        
        # PID参数控制区 (20行16列)
        pid_group = QGroupBox("PID参数控制 (20行 × 16列)")
        pid_main_layout = QVBoxLayout()
        
        # PID总开关
        pid_master_layout = QHBoxLayout()
        self.pid_master_switch = QCheckBox("PID参数 总开关")
        self.pid_master_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.pid_master_switch.stateChanged.connect(self.toggle_all_pid)
        pid_master_layout.addWidget(self.pid_master_switch)
        pid_master_layout.addStretch()
        pid_main_layout.addLayout(pid_master_layout)
        
        # PID参数设置
        pid_param_layout = QHBoxLayout()
        pid_param_layout.addWidget(QLabel("P系数:"))
        self.pid_p_value = QLineEdit("0x100")
        self.pid_p_value.setMaximumWidth(100)
        pid_param_layout.addWidget(self.pid_p_value)
        
        pid_param_layout.addWidget(QLabel("I系数:"))
        self.pid_i_value = QLineEdit("0x1")
        self.pid_i_value.setMaximumWidth(100)
        pid_param_layout.addWidget(self.pid_i_value)
        
        pid_param_layout.addWidget(QLabel("D系数:"))
        self.pid_d_value = QLineEdit("0x0")
        self.pid_d_value.setMaximumWidth(100)
        pid_param_layout.addWidget(self.pid_d_value)
        
        pid_param_layout.addWidget(QLabel("缩放因子:"))
        self.pid_scale_value = QLineEdit("0xD")
        self.pid_scale_value.setMaximumWidth(100)
        pid_param_layout.addWidget(self.pid_scale_value)
        
        pid_param_layout.addStretch()
        pid_main_layout.addLayout(pid_param_layout)
        
        # PID开关矩阵 (20行16列) - 使用表格显示
        pid_table_layout = QVBoxLayout()
        
        self.pid_table = QTableWidget()
        self.pid_table.setRowCount(20)
        self.pid_table.setColumnCount(16)
        
        # 设置表头
        row_headers = [f"行{i+1}" for i in range(20)]
        col_headers = [f"列{i+1}" for i in range(16)]
        self.pid_table.setVerticalHeaderLabels(row_headers)
        self.pid_table.setHorizontalHeaderLabels(col_headers)
        
        # 创建PID开关和数值
        self.pid_switches = []
        self.pid_values = []
        
        for row in range(20):
            row_switches = []
            row_values = []
            for col in range(16):
                # 创建单元格组件
                cell_widget = QWidget()
                cell_layout = QVBoxLayout()
                cell_layout.setContentsMargins(2, 2, 2, 2)
                
                # 开关
                switch = QCheckBox()
                row_switches.append(switch)
                cell_layout.addWidget(switch)
                
                # 数值
                value = QDoubleSpinBox()
                value.setRange(-10, 10)
                value.setValue(0)
                value.setDecimals(3)
                value.setMaximumHeight(25)
                row_values.append(value)
                cell_layout.addWidget(value)
                
                cell_widget.setLayout(cell_layout)
                self.pid_table.setCellWidget(row, col, cell_widget)
            
            self.pid_switches.append(row_switches)
            self.pid_values.append(row_values)
        
        # 设置表格大小
        self.pid_table.setMaximumHeight(400)
        self.pid_table.horizontalHeader().setDefaultSectionSize(80)
        self.pid_table.verticalHeader().setDefaultSectionSize(60)
        
        pid_table_layout.addWidget(self.pid_table)
        pid_main_layout.addLayout(pid_table_layout)
        
        pid_group.setLayout(pid_main_layout)
        main_layout.addWidget(pid_group)
        
        # 文件存储功能区
        storage_group = QGroupBox("数据存储设置")
        storage_layout = QVBoxLayout()
        
        # 存储路径设置
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("存储路径:"))
        self.storage_path = QLineEdit()
        self.storage_path.setPlaceholderText("请选择数据存储路径...")
        self.storage_path.setReadOnly(True)
        self.storage_path.setMinimumWidth(300)
        path_layout.addWidget(self.storage_path)
        
        self.browse_path_btn = QPushButton("浏览...")
        self.browse_path_btn.setMaximumWidth(80)
        self.browse_path_btn.clicked.connect(self.browse_storage_path)
        path_layout.addWidget(self.browse_path_btn)
        path_layout.addStretch()
        storage_layout.addLayout(path_layout)
        
        # 存储格式和控制
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("存储格式:"))
        self.storage_format = QComboBox()
        self.storage_format.addItems(["二进制(.bin)", "二进制(.dat)"])
        self.storage_format.setMaximumWidth(150)
        format_layout.addWidget(self.storage_format)
        
        format_layout.addSpacing(20)
        
        # 文件名前缀
        format_layout.addWidget(QLabel("文件名前缀:"))
        self.file_prefix = QLineEdit("fpga_data")
        self.file_prefix.setMaximumWidth(150)
        format_layout.addWidget(self.file_prefix)
        
        format_layout.addSpacing(20)
        
        # 存储控制按钮
        self.start_storage_btn = QPushButton("开始存储")
        self.start_storage_btn.setMaximumWidth(100)
        self.start_storage_btn.clicked.connect(self.start_data_storage)
        format_layout.addWidget(self.start_storage_btn)
        
        self.stop_storage_btn = QPushButton("停止存储")
        self.stop_storage_btn.setMaximumWidth(100)
        self.stop_storage_btn.setEnabled(False)
        self.stop_storage_btn.clicked.connect(self.stop_data_storage)
        format_layout.addWidget(self.stop_storage_btn)
        
        # 存储状态指示
        self.storage_status_label = QLabel("状态: 未存储")
        self.storage_status_label.setStyleSheet("color: gray; font-weight: bold;")
        format_layout.addWidget(self.storage_status_label)
        
        format_layout.addStretch()
        storage_layout.addLayout(format_layout)
        
        # 存储信息显示
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
        
        # 初始化存储相关变量
        self.is_storing = False
        self.current_storage_file = None
        self.stored_size = 0
        
        # 数据监控区域
        monitor_group = QGroupBox("实时数据监控")
        monitor_layout = QVBoxLayout()
        self.data_monitor = QTextEdit()
        self.data_monitor.setMaximumHeight(150)
        monitor_layout.addWidget(self.data_monitor)
        monitor_group.setLayout(monitor_layout)
        main_layout.addWidget(monitor_group)
        
        main_layout.addStretch()
        widget.setLayout(main_layout)
        self.tabs.addTab(widget, "FPGA数据汇总")

    def on_data_read_changed(self, state):
        """数据读出开关改变"""
        if state == 2:  # 开启
            self.data_read_indicator.setStyleSheet("color: green; font-size: 24px;")
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 数据读出已开启")
            # 启用ADC读出控制
            self.enable_adc_control(True)
        else:  # 关闭
            self.data_read_indicator.setStyleSheet("color: red; font-size: 24px;")
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 数据读出已关闭")
            # 禁用ADC读出控制
            self.enable_adc_control(False)    
    def on_fb_control_changed(self, state):
        """反馈控制开关改变"""
        if state == 2:  # 开启
            self.fb_control_indicator.setStyleSheet("color: green; font-size: 24px;")
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 反馈控制已开启")
            # 启用FB DAC控制
            self.enable_fb_dac_control(True)
        else:  # 关闭
            self.fb_control_indicator.setStyleSheet("color: red; font-size: 24px;")
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 反馈控制已关闭")
            # 禁用FB DAC控制
            self.enable_fb_dac_control(False)
    
    def on_gate_control_changed(self, state):
        """选通控制开关改变"""
        if state == 2:  # 开启
            self.gate_control_indicator.setStyleSheet("color: green; font-size: 24px;")
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 选通控制已开启")
            # 启用选通DAC控制
            self.enable_gate_dac_control(True)
        else:  # 关闭
            self.gate_control_indicator.setStyleSheet("color: red; font-size: 24px;")
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 选通控制已关闭")
            # 禁用选通DAC控制
            self.enable_gate_dac_control(False)
    
    def toggle_all_pid(self, state):
        """切换所有PID开关"""
        checked = (state == 2)
        for row in range(20):
            for col in range(16):
                self.pid_switches[row][col].setChecked(checked)
    
    def browse_storage_path(self):
        """浏览并选择存储路径"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择数据存储目录",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if directory:
            self.storage_path.setText(directory)
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 存储路径已设置: {directory}")
    
    def start_data_storage(self):
        """开始数据存储"""
        # 检查存储路径是否已设置
        if not self.storage_path.text():
            QMessageBox.warning(self, "警告", "请先选择存储路径！")
            return
        
        # 检查数据读出是否已开启
        if not self.data_read_switch.isChecked():
            QMessageBox.warning(self, "警告", "请先开启数据读出开关！")
            return
        
        # 生成文件名
        import os
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = self.file_prefix.text() or "fpga_data"
        
        # 根据选择的格式确定文件扩展名
        format_text = self.storage_format.currentText()
        if ".bin" in format_text:
            extension = ".bin"
        else:
            extension = ".dat"
        
        filename = f"{prefix}_{timestamp}{extension}"
        filepath = os.path.join(self.storage_path.text(), filename)
        
        try:
            # 创建文件（二进制写入模式）
            self.current_storage_file = open(filepath, 'wb')
            self.is_storing = True
            self.stored_size = 0
            
            # 更新UI状态
            self.start_storage_btn.setEnabled(False)
            self.stop_storage_btn.setEnabled(True)
            self.storage_status_label.setText("状态: 正在存储")
            self.storage_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.current_file_label.setText(filename)
            self.storage_size_label.setText("0 KB")
            
            self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 开始存储数据到: {filename}")
            
            # TODO: 这里应该启动实际的数据采集和存储线程
            # 示例：启动定时器模拟数据写入
            if not hasattr(self, 'storage_timer'):
                self.storage_timer = QTimer()
                self.storage_timer.timeout.connect(self.write_data_to_file)
            self.storage_timer.start(100)  # 每100ms写入一次数据
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建存储文件失败: {str(e)}")
            if self.current_storage_file:
                self.current_storage_file.close()
                self.current_storage_file = None
    
    def stop_data_storage(self):
        """停止数据存储"""
        if self.is_storing and self.current_storage_file:
            try:
                # 停止数据写入定时器
                if hasattr(self, 'storage_timer'):
                    self.storage_timer.stop()
                
                # 关闭文件
                self.current_storage_file.close()
                self.current_storage_file = None
                self.is_storing = False
                
                # 更新UI状态
                self.start_storage_btn.setEnabled(True)
                self.stop_storage_btn.setEnabled(False)
                self.storage_status_label.setText("状态: 已停止")
                self.storage_status_label.setStyleSheet("color: gray; font-weight: bold;")
                
                self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 数据存储已停止，总大小: {self.stored_size / 1024:.2f} KB")
                
            except Exception as e:
                QMessageBox.critical(self, "错误", f"停止存储时出错: {str(e)}")
    
    def write_data_to_file(self):
        """写入数据到文件（示例方法）"""
        if self.is_storing and self.current_storage_file:
            try:
                # 这里是示例代码，实际应该从FPGA读取数据
                # 模拟写入一些二进制数据
                import struct
                import random
                
                # 示例：写入16个通道的数据（每个通道4字节浮点数）
                data = struct.pack('16f', *[random.random() * 100 for _ in range(16)])
                self.current_storage_file.write(data)
                self.current_storage_file.flush()
                
                # 更新存储大小
                self.stored_size += len(data)
                size_kb = self.stored_size / 1024
                if size_kb < 1024:
                    self.storage_size_label.setText(f"{size_kb:.2f} KB")
                else:
                    self.storage_size_label.setText(f"{size_kb / 1024:.2f} MB")
                
            except Exception as e:
                self.data_monitor.append(f"[{time.strftime('%H:%M:%S')}] 数据写入错误: {str(e)}")
                self.stop_data_storage()
    
    def enable_fb_dac_control(self, enabled):
        """启用/禁用FB DAC控制"""
        self.fb_dac_master_switch.setEnabled(enabled)
        self.fb_dac_offset_master_switch.setEnabled(enabled)
        for switch in self.fb_dac_switches:
            switch.setEnabled(enabled)
        for switch in self.fb_dac_offset_switches:
            switch.setEnabled(enabled)
        for value in self.fb_dac_values:
            value.setEnabled(enabled)
        for value in self.fb_dac_offset_values:
            value.setEnabled(enabled)
    
    def enable_gate_dac_control(self, enabled):
        """启用/禁用选通DAC控制"""
        self.gate_dac_master_switch.setEnabled(enabled)
        self.gate_dac_offset_master_switch.setEnabled(enabled)
        self.gate_waveform.setEnabled(enabled)
        self.gate_frequency.setEnabled(enabled)
        self.gate_amplitude.setEnabled(enabled)
        self.gate_start_delay.setEnabled(enabled)
        self.gate_start_steady.setEnabled(enabled)
        self.gate_end_steady.setEnabled(enabled)
        for switch in self.gate_dac_switches:
            switch.setEnabled(enabled)
        for switch in self.gate_dac_offset_switches:
            switch.setEnabled(enabled)
        for value in self.gate_dac_values:
            value.setEnabled(enabled)
        for value in self.gate_dac_offset_values:
            value.setEnabled(enabled)
    
    def enable_adc_control(self, enabled):
        """启用/禁用ADC读出控制"""
        self.adc_master_switch.setEnabled(enabled)
        self.adc_offset_master_switch.setEnabled(enabled)
        for switch in self.adc_switches:
            switch.setEnabled(enabled)
        for switch in self.adc_offset_switches:
            switch.setEnabled(enabled)
        for value in self.adc_values:
            value.setEnabled(enabled)
        for value in self.adc_offset_values:
            value.setEnabled(enabled)
        
    def setup_monitor_tab(self):
        """系统监控选项卡"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 系统状态显示
        status_group = QGroupBox("系统状态")
        status_layout = QGridLayout()
        
        status_labels = [
            ("通讯状态", "正常"), ("数据读出", "关"), 
            ("反馈控制", "关"), ("选通控制", "关"),
            ("FPGA状态", "正常"), ("温度监控", "正常")
        ]
        
        for i, (label, value) in enumerate(status_labels):
            status_layout.addWidget(QLabel(f"{label}:"), i//2, (i%2)*2)
            value_label = QLabel(value)
            value_label.setStyleSheet("color: green; font-weight: bold;")
            status_layout.addWidget(value_label, i//2, (i%2)*2 + 1)
            
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # 日志显示
        log_group = QGroupBox("系统日志")
        log_layout = QVBoxLayout()
        self.system_log = QTextEdit()
        log_layout.addWidget(self.system_log)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        widget.setLayout(layout)
        self.tabs.addTab(widget, "系统监控")
        
    def connect_single_board(self, board_type):
        """连接单个板卡"""
        # 获取IP地址
        ip_address = self.board_ip_edits[board_type].text()
        self.comm_manager.board_ips[board_type] = ip_address
        
        # 判断当前是连接还是断开
        if self.comm_manager.is_connected(board_type):
            # 断开连接
            if self.comm_manager.disconnect_board(board_type):
                self.update_board_status(board_type, False)
                self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 已断开连接")
        else:
            # 建立连接
            if self.comm_manager.connect_to_board(board_type):
                self.update_board_status(board_type, True)
                self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接成功 ({ip_address})")
            else:
                self.update_board_status(board_type, False)
                self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接失败 ({ip_address})")
    
    def update_board_status(self, board_type, connected):
        """更新板卡连接状态显示"""
        if connected:
            self.board_status_labels[board_type].setText("连接")
            self.board_status_labels[board_type].setStyleSheet("color: green; font-weight: bold;")
            self.board_connect_btns[board_type].setText("断开")
        else:
            self.board_status_labels[board_type].setText("未连接")
            self.board_status_labels[board_type].setStyleSheet("color: red; font-weight: bold;")
            self.board_connect_btns[board_type].setText("连接")
    
    def connect_all_boards(self):
        """连接所有板卡"""
        self.connection_log.append(f"\n[{time.strftime('%H:%M:%S')}] 开始连接所有板卡...")
        success_count = 0
        fail_count = 0
        
        for board_type in self.board_ip_edits.keys():
            ip_address = self.board_ip_edits[board_type].text()
            self.comm_manager.board_ips[board_type] = ip_address
            
            if self.comm_manager.connect_to_board(board_type):
                self.update_board_status(board_type, True)
                self.connection_log.append(f"  ✓ {board_type} 连接成功")
                success_count += 1
            else:
                self.update_board_status(board_type, False)
                self.connection_log.append(f"  ✗ {board_type} 连接失败")
                fail_count += 1
        
        self.connection_log.append(f"连接完成: 成功 {success_count} 个, 失败 {fail_count} 个\n")
    
    def disconnect_all_boards(self):
        """断开所有板卡连接"""
        self.connection_log.append(f"\n[{time.strftime('%H:%M:%S')}] 开始断开所有连接...")
        self.comm_manager.disconnect_all()
        
        for board_type in self.board_ip_edits.keys():
            self.update_board_status(board_type, False)
        
        self.connection_log.append(f"所有连接已断开\n")
            
    def switch_bias_board(self, index):
        """切换偏置源板卡显示"""
        for i, board in enumerate(self.bias_boards):
            board.setVisible(i == index)

def main():
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()