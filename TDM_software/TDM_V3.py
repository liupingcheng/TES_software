#This is the the new version of the TDM software. PyQt5 is used for the GUI.
#The TDM software is used to control the TDM hardware. It will be used to control the TDM hardware and to collect data from the TDM hardware.
#written by: Pingcheng Liu, 2026-4
#V3增加打包

import sys
import time
import socket
import struct
from PyQt5.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLineEdit as _QLineEdit, QMainWindow, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
                             QTabWidget, QGroupBox, QComboBox as _QComboBox, QDoubleSpinBox as _QDoubleSpinBox, QCheckBox, QScrollArea, QSpinBox as _QSpinBox, QTableWidget, QFileDialog,
                             QMessageBox,QFrame)
# pyrefly: ignore [missing-import]
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# ================= 安全交互控件=================
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
        
        # ================= 1. 信号类型切换 =================
        ac_dc_group = QGroupBox("信号类型")
        ac_dc_layout = QHBoxLayout()
        self.signal_type = _QComboBox()
        self.signal_type.addItems(["直流", "交流"])
        ac_dc_layout.addWidget(QLabel("信号类型:"))
        ac_dc_layout.addWidget(self.signal_type)
        ac_dc_layout.addStretch()
        ac_dc_group.setLayout(ac_dc_layout)
        layout.addWidget(ac_dc_group)
        
        # ================= 2. 交流参数设置 =================
        self.ac_params_group = QGroupBox("交流信号参数")
        ac_layout = QGridLayout()
        
        ac_layout.addWidget(QLabel("波形类型:"), 0, 0)
        self.waveform_type = _QComboBox()
        self.waveform_type.addItems(["正弦波", "三角波", "方波"])
        ac_layout.addWidget(self.waveform_type, 0, 1)
        
        ac_layout.addWidget(QLabel("频率:"), 1, 0)
        self.frequency = _QDoubleSpinBox()
        self.frequency.setRange(0.1, 10000)
        self.frequency.setValue(1000)
        self.frequency.setSuffix(" Hz")
        ac_layout.addWidget(self.frequency, 1, 1)
        
        ac_layout.addWidget(QLabel("幅值:"), 2, 0)
        self.amplitude = _QDoubleSpinBox()
        self.amplitude.setRange(0, 1000)
        self.amplitude.setValue(10)
        self.amplitude.setSuffix(" μA")
        ac_layout.addWidget(self.amplitude, 2, 1)
        
        self.ac_params_group.setLayout(ac_layout)
        layout.addWidget(self.ac_params_group)
        
        # ================= 3. 直流参数设置 =================
        self.dc_params_group = QGroupBox("直流信号参数")
        dc_layout = QHBoxLayout()
        dc_layout.addWidget(QLabel("直流电流:"))
        self.dc_value = _QDoubleSpinBox()
        self.dc_value.setRange(-1000, 1000)
        self.dc_value.setValue(0)
        self.dc_value.setSuffix(" μA")
        dc_layout.addWidget(self.dc_value)
        dc_layout.addStretch()
        self.dc_params_group.setLayout(dc_layout)
        layout.addWidget(self.dc_params_group)
        
        # 必须先将上述基础组件设置为整个窗口的 Layout
        self.setLayout(layout)
        
        # ================= 4. 根据板卡ID动态加载底部矩阵 =================
        if self.board_id == 0:
            self.setup_board1_channels()
        elif self.board_id == 1:
            self.setup_board2_channels()
        else:
            self.setup_board3_channels()
            
        # 加上弹性空间，把上面的组件全都往上顶
        self.layout().addStretch()
        
        # ================= 5. 【极其关键】绑定事件并强制触发一次 =================
        self.signal_type.currentTextChanged.connect(self.on_signal_type_changed)
        # 这一句必须在所有 UI 都构建完毕之后执行，强制根据当前的文字（"直流"）进行一波显示/隐藏！
        self.on_signal_type_changed(self.signal_type.currentText())
        
    def on_signal_type_changed(self, signal_type):
        """信号类型切换时，动态显示/隐藏相关参数"""
        if signal_type == "交流":
            self.ac_params_group.show()
            self.dc_params_group.hide()
            
            # 如果是板卡1，且方波组已经成功创建，则显示它
            if self.board_id == 0 and hasattr(self, 'square_wave_group'):
                self.square_wave_group.show()
        else:
            # 直流模式下：隐藏交流参数，显示直流参数
            self.ac_params_group.hide()
            self.dc_params_group.show()
            
            # 如果是板卡1，隐藏方波组
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
        self.square_amplitude.setSuffix(" μA")
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
            value.setSuffix(" μA")
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
    
        # ========================== 板卡 2 ==========================
    def setup_board2_channels(self):
        """设置第二块板卡的通道控制 (紧凑型左右布局 + 分割线)"""
        main_h_layout = QHBoxLayout()
        
        # ================= 左侧模块: SA Ib & SA phix =================
        group1 = QGroupBox("SA Ib & SA phix控制 (16列)")
        layout1 = QGridLayout()
        layout1.setHorizontalSpacing(15) # 设置列与列之间的固定小间距
        
        self.sa_ib_master_switch = QCheckBox("SA Ib 总开关")
        self.sa_ib_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.sa_ib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_ib_switches])
        layout1.addWidget(self.sa_ib_master_switch, 0, 1, 1, 2)
        
        self.sa_phix_master_switch = QCheckBox("SA phix 总开关")
        self.sa_phix_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.sa_phix_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_phix_switches])
        # 注意：因为中间插了分割线，所以 phix 的位置往后挪了一列，到了第 4 列
        layout1.addWidget(self.sa_phix_master_switch, 0, 4, 1, 2)
        
        # 表头 (注意索引 3 留空给分割线)
        layout1.addWidget(QLabel("列"), 1, 0)
        layout1.addWidget(QLabel("SA Ib 开关"), 1, 1)
        layout1.addWidget(QLabel("SA Ib 输出值"), 1, 2)
        # 索引 3 是空的，用来放竖线
        layout1.addWidget(QLabel("SA phix 开关"), 1, 4)
        layout1.addWidget(QLabel("SA phix 输出值"), 1, 5)
        
        # 【画一条贯穿上下的竖线作为视觉隔离】
        vline = QFrame()            
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        vline.setStyleSheet("color: #CCCCCC;") # 淡淡的灰色
        # 把它放在第 1 行到第 17 行的第 3 列 (跨越17行，占用1列)
        layout1.addWidget(vline, 1, 3, 17, 1)
        
        self.sa_ib_switches, self.sa_ib_values = [], []
        self.sa_phix_switches, self.sa_phix_values = [], []
        
        for i in range(16):
            row = i + 2
            layout1.addWidget(QLabel(f" {i+1} "), row, 0)
            
            # --- Ib 部分 ---
            ib_switch = QCheckBox()
            self.sa_ib_switches.append(ib_switch)
            layout1.addWidget(ib_switch, row, 1)
            
            ib_value = QDoubleSpinBox()
            ib_value.setRange(-1000, 1000)
            ib_value.setSuffix(" μA")
            self.sa_ib_values.append(ib_value)
            layout1.addWidget(ib_value, row, 2)
            
            # --- phix 部分 ---
            phix_switch = QCheckBox()
            self.sa_phix_switches.append(phix_switch)
            layout1.addWidget(phix_switch, row, 4) # 放到第 4 列
            
            phix_value = QDoubleSpinBox()
            phix_value.setRange(-1000, 1000)
            phix_value.setSuffix(" μA")
            self.sa_phix_values.append(phix_value)
            layout1.addWidget(phix_value, row, 5) # 放到第 5 列
            
        # 【关键招式】：在最右侧（第 6 列）加一个弹簧，把所有控件狠狠往左挤！
        layout1.setColumnStretch(6, 1)
        
        group1.setLayout(layout1)
        main_h_layout.addWidget(group1, stretch=2) # 左侧组比较大，占 2 份宽度
        
        
        # ================= 右侧模块: Vb控制 =================
        group2 = QGroupBox("Vb控制 (16列)")
        layout2 = QGridLayout()
        layout2.setHorizontalSpacing(15)
        
        self.vb_master_switch = QCheckBox("Vb 总开关")
        self.vb_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.vb_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.vb_switches])
        layout2.addWidget(self.vb_master_switch, 0, 1, 1, 2)
        
        layout2.addWidget(QLabel("列"), 1, 0)
        layout2.addWidget(QLabel("开关"), 1, 1)
        layout2.addWidget(QLabel("输出值"), 1, 2)
        
        self.vb_switches, self.vb_values = [], []
        for i in range(16):
            row = i + 2
            layout2.addWidget(QLabel(f" {i+1} "), row, 0)
            
            switch = QCheckBox()
            self.vb_switches.append(switch)
            layout2.addWidget(switch, row, 1)
            
            value = QDoubleSpinBox()
            value.setRange(-10, 10)
            value.setSuffix(" V")
            self.vb_values.append(value)
            layout2.addWidget(value, row, 2)
            
        # 【关键招式】：在最右侧（第 3 列）加弹簧，把 Vb 也紧紧往左挤！
        layout2.setColumnStretch(3, 1)
        
        group2.setLayout(layout2)
        main_h_layout.addWidget(group2, stretch=1) # 右侧组较小，占 1 份宽度
        
        self.layout().addLayout(main_h_layout)
                
    # def setup_board2_channels(self):
    #     """设置第二块板卡的通道控制 (16行纵向排列)"""
    #     group1 = QGroupBox("SA Ib & SA phix控制 (16列)")
    #     layout1 = QGridLayout()
        
    #     # 总开关
    #     self.sa_ib_master_switch = QCheckBox("SA Ib 总开关")
    #     self.sa_ib_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
    #     self.sa_ib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_ib_switches])
    #     layout1.addWidget(self.sa_ib_master_switch, 0, 1, 1, 2)
        
    #     self.sa_phix_master_switch = QCheckBox("SA phix 总开关")
    #     self.sa_phix_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
    #     self.sa_phix_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_phix_switches])
    #     layout1.addWidget(self.sa_phix_master_switch, 0, 3, 1, 2)
        
    #     # 表头
    #     headers = ["列", "SA Ib开关", "SA Ib输出值", "SA phix开关", "SA phix输出值"]
    #     for col, text in enumerate(headers):
    #         layout1.addWidget(QLabel(text), 1, col)
        
    #     self.sa_ib_switches, self.sa_ib_values = [], []
    #     self.sa_phix_switches, self.sa_phix_values = [], []
        
    #     # 这里用的是纵向排列 (16行)
    #     for i in range(16):
    #         row = i + 2
    #         layout1.addWidget(QLabel(f"列{i+1}"), row, 0)
            
    #         # SA Ib
    #         ib_switch = QCheckBox()
    #         self.sa_ib_switches.append(ib_switch)
    #         layout1.addWidget(ib_switch, row, 1)
            
    #         ib_value = QDoubleSpinBox()
    #         ib_value.setRange(-1000, 1000)
    #         ib_value.setSuffix(" uA")
    #         self.sa_ib_values.append(ib_value)
    #         layout1.addWidget(ib_value, row, 2)
            
    #         # SA phix
    #         phix_switch = QCheckBox()
    #         self.sa_phix_switches.append(phix_switch)
    #         layout1.addWidget(phix_switch, row, 3)
            
    #         phix_value = QDoubleSpinBox()
    #         phix_value.setRange(-1000, 1000)
    #         phix_value.setSuffix(" uA")
    #         self.sa_phix_values.append(phix_value)
    #         layout1.addWidget(phix_value, row, 4)
            
    #     group1.setLayout(layout1)
    #     self.layout().addWidget(group1)
        
    #     # ----- Vb控制 -----
    #     group2 = QGroupBox("Vb控制 (16列)")
    #     layout2 = QGridLayout()
        
    #     self.vb_master_switch = QCheckBox("Vb 总开关")
    #     self.vb_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.vb_switches])
    #     layout2.addWidget(self.vb_master_switch, 0, 0, 1, 3)
        
    #     layout2.addWidget(QLabel("列"), 1, 0)
    #     layout2.addWidget(QLabel("开关"), 1, 1)
    #     layout2.addWidget(QLabel("输出值"), 1, 2)
        
    #     self.vb_switches, self.vb_values = [], []
    #     for i in range(16):
    #         row = i + 2
    #         layout2.addWidget(QLabel(f"列{i+1}"), row, 0)
            
    #         switch = QCheckBox()
    #         self.vb_switches.append(switch)
    #         layout2.addWidget(switch, row, 1)
            
    #         value = QDoubleSpinBox()
    #         value.setRange(-10, 10)
    #         value.setSuffix(" V")
    #         self.vb_values.append(value)
    #         layout2.addWidget(value, row, 2)
            
    #     group2.setLayout(layout2)
    #     self.layout().addWidget(group2)


    # ========================== 板卡 3 ==========================
    def setup_board3_channels(self):
        """设置第三块板卡的通道控制 (紧凑型布局 + 分割线)"""
        group = QGroupBox("IS I & IS phib控制 (16列)")
        layout = QGridLayout()
        layout.setHorizontalSpacing(15) # 设置列之间的固定紧凑间距
        
        # --- 总开关 ---
        self.is_i_master_switch = QCheckBox("IS I 总开关")
        self.is_i_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.is_i_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_i_switches])
        layout.addWidget(self.is_i_master_switch, 0, 1, 1, 2)
        
        self.is_phib_master_switch = QCheckBox("IS phib 总开关")
        self.is_phib_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.is_phib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_phib_switches])
        layout.addWidget(self.is_phib_master_switch, 0, 4, 1, 2) # 同样跳开第 3 列留给分割线
        
        # --- 表头 ---
        layout.addWidget(QLabel("列"), 1, 0)
        layout.addWidget(QLabel("IS I 开关"), 1, 1)
        layout.addWidget(QLabel("IS I 输出值"), 1, 2)
        # 第 3 列留空
        layout.addWidget(QLabel("IS phib 开关"), 1, 4)
        layout.addWidget(QLabel("IS phib 输出值"), 1, 5)
        
        # --- 画一根纵贯南北的灰色分割线 ---
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        vline.setStyleSheet("color: #CCCCCC;")
        layout.addWidget(vline, 1, 3, 17, 1) # 跨越17行
        
        self.is_i_switches, self.is_i_values = [], []
        self.is_phib_switches, self.is_phib_values = [], []
        
        # --- 16 路通道循环 ---
        for i in range(16):
            row = i + 2
            layout.addWidget(QLabel(f" {i+1} "), row, 0)
            
            # IS I 部分
            i_switch = QCheckBox()
            self.is_i_switches.append(i_switch)
            layout.addWidget(i_switch, row, 1)
            
            i_value = QDoubleSpinBox()
            i_value.setRange(-1000, 1000)
            i_value.setSuffix(" μA")
            self.is_i_values.append(i_value)
            layout.addWidget(i_value, row, 2)
            
            # IS phib 部分
            phib_switch = QCheckBox()
            self.is_phib_switches.append(phib_switch)
            layout.addWidget(phib_switch, row, 4)
            
            phib_value = QDoubleSpinBox()
            phib_value.setRange(-1000, 1000)
            phib_value.setSuffix(" μA")
            self.is_phib_values.append(phib_value)
            layout.addWidget(phib_value, row, 5)
            
        # 【关键招式】：在最右侧加一个隐形弹簧，把整个矩阵往左压紧！
        layout.setColumnStretch(6, 1)
        
        # 为了让它不过于铺满整个屏幕，我们在右侧再加一个空的水平弹簧外壳
        wrapper_layout = QHBoxLayout()
        group.setLayout(layout)
        wrapper_layout.addWidget(group)
        wrapper_layout.addStretch() # 这个弹簧防止 groupbox 被拉长
        
        self.layout().addLayout(wrapper_layout)
    # def setup_board3_channels(self):
    #     """设置第三块板卡的通道控制"""
    #     group = QGroupBox("IS I & IS phib控制 (16列)")
    #     layout = QGridLayout()
        
    #     # 总开关
    #     self.is_i_master_switch = QCheckBox("IS I 总开关")
    #     self.is_i_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_i_switches])
    #     layout.addWidget(self.is_i_master_switch, 0, 1, 1, 2)
        
    #     self.is_phib_master_switch = QCheckBox("IS phib 总开关")
    #     self.is_phib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_phib_switches])
    #     layout.addWidget(self.is_phib_master_switch, 0, 3, 1, 2)
        
    #     headers = ["列", "IS I开关", "IS I输出值", "IS phib开关", "IS phib输出值"]
    #     for col, text in enumerate(headers):
    #         layout.addWidget(QLabel(text), 1, col)
            
    #     self.is_i_switches, self.is_i_values = [], []
    #     self.is_phib_switches, self.is_phib_values = [], []
        
    #     for i in range(16):
    #         row = i + 2
    #         layout.addWidget(QLabel(f"列{i+1}"), row, 0)
            
    #         i_switch = QCheckBox()
    #         self.is_i_switches.append(i_switch)
    #         layout.addWidget(i_switch, row, 1)
            
    #         i_value = QDoubleSpinBox()
    #         i_value.setRange(-1000, 1000)
    #         i_value.setSuffix(" uA")
    #         self.is_i_values.append(i_value)
    #         layout.addWidget(i_value, row, 2)
            
    #         phib_switch = QCheckBox()
    #         self.is_phib_switches.append(phib_switch)
    #         layout.addWidget(phib_switch, row, 3)
            
    #         phib_value = QDoubleSpinBox()
    #         phib_value.setRange(-1000, 1000)
    #         phib_value.setSuffix(" uA")
    #         self.is_phib_values.append(phib_value)
    #         layout.addWidget(phib_value, row, 4)
            
    #     group.setLayout(layout)
    #     self.layout().addWidget(group)
        
    def generate_write_packets(self):
        """扫描当前面板参数，打包"""
        packets = []
        
        board_id = self.board_id + 1  # 板卡 ID 从 1 开始
        cmd = TDMProtocol.CMD_WRITE
        
        #交流直流设置
        if self.signal_type.currentText() == "交流":
            # 提取波形类型：0=正弦波, 1=三角波, 2=方波 (刚好对应下拉框的 Index)
            waveform_idx = self.waveform_type.currentIndex()
            packets.append(TDMProtocol.pack_frame(
                cmd, board_id, TDMProtocol.PARAM_WAVEFORM, 1, 0x00, 0x00, waveform_idx, is_float=False))
            
            freq = self.frequency.value()
            packets.append(TDMProtocol.pack_frame(
                cmd, board_id, TDMProtocol.PARAM_AC_FREQ, 1, 0x00, 0x00, freq, is_float=True))
                
            amp = self.amplitude.value()
            packets.append(TDMProtocol.pack_frame(
                cmd, board_id, TDMProtocol.PARAM_AC_AMP,  1, 0x00, 0x00, amp, is_float=True))
        else:
            dc_val = self.dc_value.value()
            packets.append(TDMProtocol.pack_frame(
                cmd, board_id, TDMProtocol.PARAM_DC_VALUE, 1, 0x00, 0x00, dc_val, is_float=True))        
      # 各板卡打包
        if self.board_id == 0:  
            # --- 偏置源板卡 1 (TES: 16列) ---
            for col in range(16):
                switch_on = 1 if self.tes_switches[col].isChecked() else 0
                voltage_val = self.tes_values[col].value()
                packets.append(TDMProtocol.pack_frame(
                    cmd, board_id, TDMProtocol.PARAM_TES_V, switch_on, 0x00, col, voltage_val, True))
                    
        elif self.board_id == 1:
            # --- 偏置源板卡 2 (SA Ib/phix, Vb: 16列) ---
            for col in range(16):
                # 1. SA Ib
                ib_on = 1 if self.sa_ib_switches[col].isChecked() else 0
                ib_val = self.sa_ib_values[col].value()
                packets.append(TDMProtocol.pack_frame(
                    cmd, board_id, TDMProtocol.PARAM_SA_IB, ib_on, 0x00, col, ib_val, True))
                
                # 2. SA phix
                phix_on = 1 if self.sa_phix_switches[col].isChecked() else 0
                phix_val = self.sa_phix_values[col].value()
                packets.append(TDMProtocol.pack_frame(
                    cmd, board_id, TDMProtocol.PARAM_SA_PHIX, phix_on, 0x00, col, phix_val, True))
                
                # 3. Vb
                vb_on = 1 if self.vb_switches[col].isChecked() else 0
                vb_val = self.vb_values[col].value()
                packets.append(TDMProtocol.pack_frame(
                    cmd, board_id, TDMProtocol.PARAM_VB, vb_on, 0x00, col, vb_val, True))

        elif self.board_id == 2:
            # --- 偏置源板卡 3 (IS I/phib: 16列) ---
            for col in range(16):
                # 1. IS I
                i_on = 1 if self.is_i_switches[col].isChecked() else 0
                i_val = self.is_i_values[col].value()
                packets.append(TDMProtocol.pack_frame(
                    cmd, board_id, TDMProtocol.PARAM_IS_I, i_on, 0x00, col, i_val, True))
                
                # 2. IS phib
                phib_on = 1 if self.is_phib_switches[col].isChecked() else 0
                phib_val = self.is_phib_values[col].value()
                packets.append(TDMProtocol.pack_frame(
                    cmd, board_id, TDMProtocol.PARAM_IS_PHIB, phib_on, 0x00, col, phib_val, True))
            
        return packets           

class ConnectThread(QThread):
    """
    后台连接线程：专门负责去尝试连接Socket，防止主界面卡死
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

            self.sock.sendall(self.command)
            
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
 
class TDMProtocol:
    '''16字节二进制通讯协议打包'''
    CMD_WRITE = 0x01
    
    #板卡ID映射
    BOARD_BIAS1 = 0x01
    BOARD_BIAS2 = 0x02
    BOARD_BIAS3 = 0x03
    BOARD_FPGA = 0x07 
    
    #PARAM_ID映射
    PARAM_ENABLE   = 0x01  # 通道开关 (0/1)
    PARAM_TES_V    = 0x02  # TES偏置电压
    PARAM_SA_IB    = 0x03  # SQUID 偏置电流 (μA)
    PARAM_SA_PHIX  = 0x04  # SQUID 磁通偏置 (μA)
    PARAM_VB       = 0x05  # VB 温度偏压
    PARAM_IS_I     = 0x06  # IS 偏置电流 (μA)
    PARAM_IS_PHIB  = 0x07  # IS 磁通偏置 (μA)
    PARAM_AC_FREQ  = 0x10  # 交流频率
    PARAM_AC_AMP   = 0x11  # 交流幅值
    PARAM_WAVEFORM = 0x12  # 波形类型 (0=正弦 1=方波 2=三角)
    PARAM_DC_VALUE = 0x13  # 直流幅值
    PARAM_SIG_TYPE = 0x14  # 信号类型 (0=直流, 1=交流)
    
    #打包
    @staticmethod
    def calc_crc16(data: bytes) -> int:
        """计算 CRC-16/CCITT False (多项式 0x1021，初始值 0xFFFF)"""
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
                crc &= 0xFFFF
        return crc
    
    @staticmethod
    def pack_frame(cmd_type, board_id, param_id, channel_state, row_id, col_id, value, is_float=True) -> bytes:
        # 0. 基础防御性检查：确保输入的 ID 在单字节范围内 (0~255)
        row_id = int(row_id) & 0xFF
        col_id = int(col_id) & 0xFF
        channel_state = int(channel_state) & 0x01  # 看通道前面开关状态
        board_id = int(board_id) & 0xFF
        cmd_type = int(cmd_type) & 0xFF
        param_id = int(param_id) & 0xFF
        
        if is_float:
            frame_head = struct.pack('>BBBBBBBBfBB', 
                                     0xAA, 0x55,        # 0~1: SYNC
                                     cmd_type,          # 2: CMD_TYPE
                                     board_id,          # 3: BOARD_ID
                                     param_id,          # 4: PARAM_ID
                                     channel_state,     # 5: CHANNEL_STATE
                                     row_id,            # 6: ROW_ID
                                     col_id,            # 7: COL_ID
                                     float(value),      # 9~12: VALUE
                                     0x00, 0x00)            # 13~14: RESERVED
        else:
            frame_head = struct.pack('>BBBBBBBBIBB', 
                                     0xAA, 0x55, 
                                     cmd_type, board_id, param_id, channel_state, row_id, col_id,
                                     int(value), 0x00, 0x00)
                                     
        crc_val = TDMProtocol.calc_crc16(frame_head[2:])    #CRC校验Byte 2 到 Byte 14
        final_frame = frame_head + struct.pack('>H', crc_val)
        
        return final_frame 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 【新增：网络相关的字典】
        self.active_sockets = {}    # 存放连上的 socket 对象
        self.connect_threads = {}   # 存放正在连接的后台线程，防止被 Python 垃圾回收
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("TES-SQUID TDM 上位机控制软件")
        self.setGeometry(100, 100, 1200, 800)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # ================= 1. 上半部分：选项卡控件 =================
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=4) # 占据 80% 高度
        
        # ================= 2. 下半部分：底座 (左日志 + 右状态) =================
        bottom_layout = QHBoxLayout()
        
        # --- 左侧：全局系统日志 ---
        log_group = QGroupBox("系统日志")
        log_layout = QVBoxLayout()
        self.connection_log = QTextEdit()
        self.connection_log.setReadOnly(True)
        self.connection_log.setMaximumHeight(200)
        self.connection_log.setStyleSheet("background-color: #F8F8F8; font-family: Consolas;")
        log_layout.addWidget(self.connection_log)
        log_group.setLayout(log_layout)
        
        bottom_layout.addWidget(log_group, stretch=3) # 日志较宽，占 3 份
        
        # --- 右侧：系统核心状态面板 ---
        status_group = QGroupBox("系统实时状态")
        status_layout = QGridLayout()
        status_layout.setVerticalSpacing(10) # 增加一点垂直行距，看起来更舒展
        
        # 定义初始状态，并准备一个字典存放标签对象的引用，方便以后动态修改
        status_items = [
            ("通讯状态", "未连接", "red"), ("数据读出", "关", "red"), 
            ("反馈控制", "关", "red"),     ("选通控制", "关", "red"),
            ("FPGA状态", "未知", "gray"),  ("温度监控", "正常", "green")
        ]
        
        self.sys_status_labels = {} # 字典：存着右侧的值标签
        
        for i, (key, val, color) in enumerate(status_items):
            row = i // 2
            col = (i % 2) * 2
            
            # 标题标签
            title_lbl = QLabel(f"{key}:")
            title_lbl.setFont(QFont("Arial", 9, QFont.Bold))
            status_layout.addWidget(title_lbl, row, col)
            
            # 值标签 (存入字典)
            val_lbl = QLabel(val)
            val_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
            status_layout.addWidget(val_lbl, row, col + 1)
            self.sys_status_labels[key] = val_lbl
            
        status_group.setLayout(status_layout)
        bottom_layout.addWidget(status_group, stretch=1) # 状态面板占 1 份
        
        main_layout.addLayout(bottom_layout, stretch=1) # 底座整体占据 20% 高度
        
        # ================= 3. 初始化选项卡 =================
        self.setup_connection_tab()
        self.setup_bias_control_tab()
        self.setup_ad_da_tab()
        self.setup_fpga_tab()

        
    def setup_connection_tab(self):
        widget = QWidget()  # Create a widget for the connection tab
        layout = QVBoxLayout() # Create a vertical layout for the connection tab
        
        connection_group = QGroupBox("Connection Settings")  # Create a group box for the connection settings
        connection_layout = QGridLayout()  # Create a vertical layout for the connection settings
        
        board_configs = [
            ('偏置源板卡 1', 'Bias1',        '192.168.1.11'),
            ('偏置源板卡 2', 'Bias2',        '192.168.1.12'),
            ('偏置源板卡 3', 'Bias3',        '192.168.1.13'),
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

        layout.addStretch() 
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
        self.write_bias_btn.clicked.connect(self.on_write_bias_clicked)
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
        """AD/DA控制选项卡 (双子标签页架构)"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        self.ad_da_sub_tabs = QTabWidget()
        self.ad_da_sub_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #C0C0C0; }
            QTabBar::tab { padding: 8px 15px; font-size: 13px; font-weight: bold; min-width: 100px; }
            QTabBar::tab:selected { background-color: #E8F0FE; color: #0055A4; }
        """)
        
        # ================= 子标签页 1：ADC & FB DAC (左右并排) =================
        ad_fb_scroll = QScrollArea()
        ad_fb_scroll.setWidgetResizable(True)
        ad_fb_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        ad_fb_widget = QWidget()
        ad_fb_layout = QHBoxLayout() # 横向布局，左右对分
        ad_fb_layout.setSpacing(20)  # 中间留一点空隙
        
        # 左侧：ADC
        adc_container = QWidget()
        adc_layout = QVBoxLayout()
        adc_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_adc_control(adc_layout)
        adc_layout.addStretch() # 把内容往上顶
        adc_container.setLayout(adc_layout)
        ad_fb_layout.addWidget(adc_container, stretch=1) # 占比 1
        
        # 右侧：FB DAC
        fb_container = QWidget()
        fb_layout = QVBoxLayout()
        fb_layout.setContentsMargins(0, 0, 0, 0)
        self.setup_fb_dac_control(fb_layout)
        fb_layout.addStretch()
        fb_container.setLayout(fb_layout)
        ad_fb_layout.addWidget(fb_container, stretch=1) # 占比 1，绝对均分
        
        ad_fb_widget.setLayout(ad_fb_layout)
        ad_fb_scroll.setWidget(ad_fb_widget)
        self.ad_da_sub_tabs.addTab(ad_fb_scroll, "ADC FB DAC控制")
        
        # ================= 子标签页 2：选通 DAC 板 =================
        gate_scroll = QScrollArea()
        gate_scroll.setWidgetResizable(True)
        gate_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        gate_widget = QWidget()
        gate_layout = QVBoxLayout()
        self.setup_gate_dac_control(gate_layout)
        gate_layout.addStretch()
        gate_widget.setLayout(gate_layout)
        gate_scroll.setWidget(gate_widget)
        self.ad_da_sub_tabs.addTab(gate_scroll, "选通 DAC 控制")
        
        layout.addWidget(self.ad_da_sub_tabs)
        
        # --- 底部公共控制按钮 ---
        button_layout = QHBoxLayout()
        self.read_ad_da_btn = QPushButton("读取参数")
        self.write_ad_da_btn = QPushButton("写入参数")
        self.save_ad_da_btn = QPushButton("保存配置")
        button_layout.addWidget(self.read_ad_da_btn)
        button_layout.addWidget(self.write_ad_da_btn)
        button_layout.addWidget(self.save_ad_da_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        widget.setLayout(layout)
        self.tabs.addTab(widget, "AD/DA控制")

    def setup_fpga_tab(self):
        """FPGA数据汇总选项卡 (顶部双拼布局 + 底部大表格)"""
        widget = QWidget()
        main_layout = QVBoxLayout()
        
        # ================= 顶部：横向双拼布局 =================
        top_h_layout = QHBoxLayout()
        
        # --- 左侧：FPGA 主控制开关 (紧凑纵向排列) ---
        control_group = QGroupBox("FPGA主控制")
        control_layout = QVBoxLayout()
        control_layout.setSpacing(15) # 适当的垂直间距
        
        self.data_read_switch = QCheckBox("数据读出开关")
        self.data_read_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.data_read_switch.stateChanged.connect(self.on_data_read_changed)
        control_layout.addWidget(self.data_read_switch)
        
        self.fb_control_switch = QCheckBox("反馈控制开关")
        self.fb_control_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.fb_control_switch.stateChanged.connect(self.on_fb_control_changed)
        control_layout.addWidget(self.fb_control_switch)
        
        self.gate_control_switch = QCheckBox("选通控制开关")
        self.gate_control_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.gate_control_switch.stateChanged.connect(self.on_gate_control_changed)
        control_layout.addWidget(self.gate_control_switch)
        
        control_layout.addStretch() # 把这三个开关狠狠顶在上面
        control_group.setLayout(control_layout)
        top_h_layout.addWidget(control_group, stretch=1) # 左侧比较窄，占 1 份
        
# --- 右侧：数据存储设置 ---
        storage_group = QGroupBox("数据存储设置与日志")
        storage_layout = QVBoxLayout()
        
        # 第一行：路径选择
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("存储路径:"))
        self.storage_path = _QLineEdit()
        self.storage_path.setPlaceholderText("请选择数据存储路径...")
        self.storage_path.setReadOnly(True)
        path_layout.addWidget(self.storage_path, stretch=1)
        self.browse_path_btn = QPushButton("浏览...")
        self.browse_path_btn.clicked.connect(self.browse_storage_path)
        path_layout.addWidget(self.browse_path_btn)
        storage_layout.addLayout(path_layout)
        
        # 第二行：格式、前缀、自动保存间隔
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("格式:"))
        self.storage_format = _QComboBox()
        self.storage_format.addItems(["二进制(.bin)", "数据(.dat)"])
        format_layout.addWidget(self.storage_format)
        
        format_layout.addSpacing(10)
        format_layout.addWidget(QLabel("前缀:"))
        self.file_prefix = _QLineEdit("TDM_data")
        self.file_prefix.setMaximumWidth(100)
        format_layout.addWidget(self.file_prefix)
        
        format_layout.addSpacing(10)
        format_layout.addWidget(QLabel("分卷间隔:"))
        self.save_interval = _QSpinBox()
        self.save_interval.setRange(1, 86400) # 1秒 到 24小时
        self.save_interval.setValue(60)       # 默认 60 秒切一个文件
        self.save_interval.setSuffix(" 秒")
        self.save_interval.setMinimumWidth(80)
        format_layout.addWidget(self.save_interval)
        format_layout.addStretch()
        storage_layout.addLayout(format_layout)
        
        # 第三行：控制按钮
        btn_layout = QHBoxLayout()
        self.start_storage_btn = QPushButton("开始存储")
        # 预留槽函数连接，稍后我们会写具体的存储逻辑
        # self.start_storage_btn.clicked.connect(self.start_data_storage)
        btn_layout.addWidget(self.start_storage_btn)
        
        self.stop_storage_btn = QPushButton("停止存储")
        self.stop_storage_btn.setEnabled(False)
        # self.stop_storage_btn.clicked.connect(self.stop_data_storage)
        btn_layout.addWidget(self.stop_storage_btn)
        btn_layout.addStretch()
        storage_layout.addLayout(btn_layout)
        
        # # 第四行：专属数据日志框
        # self.data_log = QTextEdit()
        # self.data_log.setReadOnly(True)
        # # 用蓝色背景，把它和底部的全局灰色日志区分开
        # self.data_log.setStyleSheet("background-color: #F0F8FF; font-family: Consolas;") 
        # storage_layout.addWidget(self.data_log)
        
        storage_group.setLayout(storage_layout)
        top_h_layout.addWidget(storage_group, stretch=3) # 占 3 份宽度
        
        main_layout.addLayout(top_h_layout)
        
        # ================= 下半部分：PID 参数控制区 (20行16列) =================
        pid_group = QGroupBox("PID参数控制 (20行 × 16列)")
        pid_main_layout = QVBoxLayout()
        
        pid_param_layout = QHBoxLayout()
        self.pid_master_switch = QCheckBox("PID参数 总开关")
        self.pid_master_switch.setFont(QFont("Arial", 10, QFont.Bold))
        self.pid_master_switch.stateChanged.connect(self.toggle_all_pid)
        pid_param_layout.addWidget(self.pid_master_switch)
        
        pid_param_layout.addSpacing(30)
        
        pid_param_layout.addWidget(QLabel("P系数(HEX):"))
        self.pid_p_value = _QLineEdit("0x100")
        self.pid_p_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_p_value)
        
        pid_param_layout.addWidget(QLabel("I系数(HEX):"))
        self.pid_i_value = _QLineEdit("0x1")
        self.pid_i_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_i_value)
        
        pid_param_layout.addWidget(QLabel("D系数(HEX):"))
        self.pid_d_value = _QLineEdit("0x0")
        self.pid_d_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_d_value)
        
        pid_param_layout.addWidget(QLabel("缩放因子(HEX):"))
        self.pid_scale_value = _QLineEdit("0xD")
        self.pid_scale_value.setMaximumWidth(80)
        pid_param_layout.addWidget(self.pid_scale_value)
        
        pid_param_layout.addStretch()
        pid_main_layout.addLayout(pid_param_layout)
        
        self.pid_table = QTableWidget()
        self.pid_table.setRowCount(20)
        self.pid_table.setColumnCount(16)
        
        row_headers = [f" {i+1} " for i in range(20)]
        col_headers = [f" {i+1} " for i in range(16)]
        self.pid_table.setVerticalHeaderLabels(row_headers)
        self.pid_table.setHorizontalHeaderLabels(col_headers)
        
        self.pid_switches, self.pid_values = [], []
        
        for row in range(20):
            row_switches, row_values = [], []
            for col in range(16):
                cell_widget = QWidget()
                cell_layout = QVBoxLayout()
                cell_layout.setContentsMargins(5, 2, 5, 2)
                
                switch = QCheckBox()
                row_switches.append(switch)
                cell_layout.addWidget(switch, alignment=Qt.AlignCenter) # 开关居中
                
                value = _QDoubleSpinBox()
                value.setRange(-10, 10)
                value.setDecimals(3)
                row_values.append(value)
                cell_layout.addWidget(value)
                
                cell_widget.setLayout(cell_layout)
                self.pid_table.setCellWidget(row, col, cell_widget)
            
            self.pid_switches.append(row_switches)
            self.pid_values.append(row_values)
        
        self.pid_table.horizontalHeader().setDefaultSectionSize(70)
        self.pid_table.verticalHeader().setDefaultSectionSize(65)
        
        pid_main_layout.addWidget(self.pid_table)
        pid_group.setLayout(pid_main_layout)
        # main_layout.addWidget(pid_group)
        main_layout.addWidget(pid_group, stretch=1) 
        widget.setLayout(main_layout)
        self.tabs.addTab(widget, "FPGA数据汇总")

    def on_data_read_changed(self, state):
        if state == 2:
            self.sys_status_labels["数据读出"].setText("开")
            self.sys_status_labels["数据读出"].setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
            # 【修改】：采用极其硬核的等宽日志风格
            self.connection_log.append("数据读出: [ ON ]")
        else:
            self.sys_status_labels["数据读出"].setText("关")
            self.sys_status_labels["数据读出"].setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
            # 【修改】
            self.connection_log.append("数据读出: [ OFF ]")

    def on_fb_control_changed(self, state):
        if state == 2:
            self.sys_status_labels["反馈控制"].setText("开")
            self.sys_status_labels["反馈控制"].setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
            self.connection_log.append("反馈控制: [ ON ]")
        else:
            self.sys_status_labels["反馈控制"].setText("关")
            self.sys_status_labels["反馈控制"].setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
            self.connection_log.append("反馈控制: [ OFF ]")
            
    def on_gate_control_changed(self, state):
        if state == 2:
            self.sys_status_labels["选通控制"].setText("开")
            self.sys_status_labels["选通控制"].setStyleSheet("color: green; font-weight: bold; font-size: 13px;")
            self.connection_log.append("选通控制: [ ON ]")
        else:
            self.sys_status_labels["选通控制"].setText("关")
            self.sys_status_labels["选通控制"].setStyleSheet("color: red; font-weight: bold; font-size: 13px;")
            self.connection_log.append("选通控制: [ OFF ]")
            
    def toggle_all_pid(self, state):
        checked = (state == 2)
        # 二维数组的遍历
        for row in range(20):
            for col in range(16):
                self.pid_switches[row][col].setChecked(checked)

    def setup_fb_dac_control(self, parent_layout):
        """FB DAC控制 (紧凑排版 + 呼吸空间)"""
        group = QGroupBox("FB DAC控制 (16列)")
        layout = QGridLayout()
        layout.setHorizontalSpacing(10)
        
        # --- 总开关 ---
        self.fb_dac_master_switch = QCheckBox("DAC 总开关")
        self.fb_dac_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.fb_dac_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.fb_dac_switches])
        layout.addWidget(self.fb_dac_master_switch, 0, 1, 1, 2)
        
        self.fb_dac_offset_master_switch = QCheckBox("DAC offset 总开关")
        self.fb_dac_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.fb_dac_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.fb_dac_offset_switches])
        layout.addWidget(self.fb_dac_offset_master_switch, 0, 4, 1, 2)
        
        # --- 表头 ---
        layout.addWidget(QLabel("列"), 1, 0)
        layout.addWidget(QLabel("DAC开关"), 1, 1)
        layout.addWidget(QLabel("DAC输出值"), 1, 2)
        layout.addWidget(QLabel("offset开关"), 1, 4)
        layout.addWidget(QLabel("offset值"), 1, 5)
        
        self.fb_dac_switches, self.fb_dac_values = [], []
        self.fb_dac_offset_switches, self.fb_dac_offset_values = [], []
        
        for i in range(16):
            row = i + 2
            layout.addWidget(QLabel(f" {i+1} "), row, 0)
            
            # DAC 部分
            dac_switch = QCheckBox()
            self.fb_dac_switches.append(dac_switch)
            layout.addWidget(dac_switch, row, 1)
            
            dac_value = QDoubleSpinBox()
            dac_value.setRange(-10, 10)
            dac_value.setSuffix(" V")
            dac_value.setDecimals(3)
            self.fb_dac_values.append(dac_value)
            layout.addWidget(dac_value, row, 2)
            
            # Offset 部分
            offset_switch = QCheckBox()
            self.fb_dac_offset_switches.append(offset_switch)
            layout.addWidget(offset_switch, row, 4)
            
            offset_value = QDoubleSpinBox()
            offset_value.setRange(-10, 10)
            offset_value.setSuffix(" V")
            offset_value.setDecimals(3)
            self.fb_dac_offset_values.append(offset_value)
            layout.addWidget(offset_value, row, 5)
            
        # 同样的排版魔法
        layout.setColumnStretch(3, 1) 
        layout.setColumnStretch(6, 2)
        
        group.setLayout(layout)
        parent_layout.addWidget(group)
        
    def setup_adc_control(self, parent_layout):
        """ADC读出控制 (极致紧凑 + 竖线隔离 + 居左防拉伸)"""
        group = QGroupBox("ADC读出控制 (16列)")
        layout = QGridLayout()
        layout.setHorizontalSpacing(15)
        
        self.adc_master_switch = QCheckBox("ADC 总开关")
        self.adc_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.adc_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_switches])
        layout.addWidget(self.adc_master_switch, 0, 1, 1, 2)
        
        self.adc_offset_master_switch = QCheckBox("offset 总开关")
        self.adc_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.adc_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_offset_switches])
        layout.addWidget(self.adc_offset_master_switch, 0, 4, 1, 2)
        
        layout.addWidget(QLabel("列"), 1, 0)
        layout.addWidget(QLabel("ADC 开关"), 1, 1)
        layout.addWidget(QLabel("ADC 输出值"), 1, 2)
        layout.addWidget(QLabel("offset 开关"), 1, 4)
        layout.addWidget(QLabel("offset 值"), 1, 5)
        
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet("color: #CCCCCC;")
        layout.addWidget(vline, 1, 3, 17, 1)
        
        self.adc_switches, self.adc_values = [], []
        self.adc_offset_switches, self.adc_offset_values = [], []
        
        for i in range(16):
            row = i + 2
            layout.addWidget(QLabel(f" {i+1} "), row, 0)
            
            s1 = QCheckBox()
            self.adc_switches.append(s1)
            layout.addWidget(s1, row, 1)
            
            v1 = _QDoubleSpinBox()
            v1.setRange(-10, 10)
            v1.setSuffix(" V")
            v1.setDecimals(3)
            self.adc_values.append(v1)
            layout.addWidget(v1, row, 2)
            
            s2 = QCheckBox()
            self.adc_offset_switches.append(s2)
            layout.addWidget(s2, row, 4)
            
            v2 = _QDoubleSpinBox()
            v2.setRange(-10, 10)
            v2.setSuffix(" V")
            v2.setDecimals(3)
            self.adc_offset_values.append(v2)
            layout.addWidget(v2, row, 5)
            
        layout.setColumnStretch(6, 1) # 右侧压紧弹簧
        group.setLayout(layout)
        parent_layout.addWidget(group)

    # def setup_adc_control(self, parent_layout):
    #     """ADC读出控制 (左侧部分)"""
    #     group = QGroupBox("ADC读出控制 (16列)")
    #     layout = QGridLayout()
        
    #     # 总开关
    #     self.adc_master_switch = QCheckBox("ADC 总开关")
    #     self.adc_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
    #     self.adc_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_switches])
    #     layout.addWidget(self.adc_master_switch, 0, 1, 1, 2)
        
    #     self.adc_offset_master_switch = QCheckBox("ADC offset 总开关")
    #     self.adc_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
    #     self.adc_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_offset_switches])
    #     layout.addWidget(self.adc_offset_master_switch, 0, 3, 1, 2)
        
    #     # 表头
    #     headers = ["列", "ADC开关", "ADC输出值", "offset开关", "offset值"]
    #     for col, text in enumerate(headers):
    #         layout.addWidget(QLabel(text), 1, col)
            
    #     self.adc_switches, self.adc_values = [], []
    #     self.adc_offset_switches, self.adc_offset_values = [], []
        
    #     # 16路通道
    #     for i in range(16):
    #         row = i + 2
    #         layout.addWidget(QLabel(f"列{i+1}"), row, 0)
            
    #         # ADC
    #         adc_switch = QCheckBox()
    #         self.adc_switches.append(adc_switch)
    #         layout.addWidget(adc_switch, row, 1)
            
    #         adc_value = QDoubleSpinBox()
    #         adc_value.setRange(-10, 10)
    #         adc_value.setSuffix(" V")
    #         adc_value.setDecimals(3) # 设置保留3位小数
    #         self.adc_values.append(adc_value)
    #         layout.addWidget(adc_value, row, 2)
            
    #         # Offset
    #         offset_switch = QCheckBox()
    #         self.adc_offset_switches.append(offset_switch)
    #         layout.addWidget(offset_switch, row, 3)
            
    #         offset_value = QDoubleSpinBox()
    #         offset_value.setRange(-10, 10)
    #         offset_value.setSuffix(" V")
    #         offset_value.setDecimals(3)
    #         self.adc_offset_values.append(offset_value)
    #         layout.addWidget(offset_value, row, 4)
            
    #     group.setLayout(layout)
    #     parent_layout.addWidget(group)

    
    def setup_gate_dac_control(self, parent_layout):
        """选通DAC控制 (20行矩阵, 极致紧凑 + 竖线隔离 + 居左防拉伸)"""
        # --- 1. 顶部的参数设置区 ---
        param_group = QGroupBox("20行选通全局参数设定")
        param_layout = QGridLayout()
        param_layout.setHorizontalSpacing(20)
        
        param_layout.addWidget(QLabel("波形类型:"), 0, 0)
        self.gate_waveform = _QComboBox()
        self.gate_waveform.addItems(["某一行DC", "三角波", "方波", "正弦波"])
        param_layout.addWidget(self.gate_waveform, 0, 1)
        
        param_layout.addWidget(QLabel("频率:"), 0, 2)
        self.gate_frequency = _QDoubleSpinBox()
        self.gate_frequency.setRange(0.1, 100000)
        self.gate_frequency.setValue(1000)
        self.gate_frequency.setSuffix(" Hz")
        param_layout.addWidget(self.gate_frequency, 0, 3)
        
        param_layout.addWidget(QLabel("幅值(HEX):"), 1, 0)
        self.gate_amplitude = _QLineEdit("0xFFFF")
        param_layout.addWidget(self.gate_amplitude, 1, 1)
        
        param_layout.addWidget(QLabel("选通开始延迟:"), 1, 2)
        self.gate_start_delay = _QSpinBox()
        self.gate_start_delay.setRange(0, 10000)
        self.gate_start_delay.setValue(0)
        self.gate_start_delay.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_delay, 1, 3)
        
        param_layout.addWidget(QLabel("选通开始稳态:"), 2, 0)
        self.gate_start_steady = _QSpinBox()
        self.gate_start_steady.setRange(0, 10000)
        self.gate_start_steady.setValue(100)
        self.gate_start_steady.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_steady, 2, 1)
        
        param_layout.addWidget(QLabel("选通结束稳态:"), 2, 2)
        self.gate_end_steady = _QSpinBox()
        self.gate_end_steady.setRange(0, 10000)
        self.gate_end_steady.setValue(100)
        self.gate_end_steady.setSuffix(" ns")
        param_layout.addWidget(self.gate_end_steady, 2, 3)
        
        param_layout.setColumnStretch(4, 1) # 把参数区也往左压紧
        param_group.setLayout(param_layout)
        
        # --- 2. 20行的矩阵控制区 ---
        matrix_group = QGroupBox("20行通道控制")
        dac_layout = QGridLayout()
        dac_layout.setHorizontalSpacing(15)
        
        self.gate_dac_master_switch = QCheckBox("DAC 总开关")
        self.gate_dac_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.gate_dac_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.gate_dac_switches])
        dac_layout.addWidget(self.gate_dac_master_switch, 0, 1, 1, 2)
        
        self.gate_dac_offset_master_switch = QCheckBox("offset 总开关")
        self.gate_dac_offset_master_switch.setFont(QFont("Arial", 9, QFont.Bold))
        self.gate_dac_offset_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.gate_dac_offset_switches])
        dac_layout.addWidget(self.gate_dac_offset_master_switch, 0, 4, 1, 2)
        
        # 优化表头，去掉“行”字
        dac_layout.addWidget(QLabel("行"), 1, 0)
        dac_layout.addWidget(QLabel("DAC 开关"), 1, 1)
        dac_layout.addWidget(QLabel("DAC 输出值"), 1, 2)
        dac_layout.addWidget(QLabel("offset 开关"), 1, 4)
        dac_layout.addWidget(QLabel("offset 值"), 1, 5)
        
        # 画贯穿 20 行的垂直分割线
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setStyleSheet("color: #CCCCCC;")
        dac_layout.addWidget(vline, 1, 3, 21, 1) # 跨越21行 (20数据+1表头)
        
        self.gate_dac_switches, self.gate_dac_values = [], []
        self.gate_dac_offset_switches, self.gate_dac_offset_values = [], []
        
        for i in range(20):
            row = i + 2
            dac_layout.addWidget(QLabel(f" {i+1} "), row, 0) # 去掉行字，更极简
            
            s1 = QCheckBox()
            self.gate_dac_switches.append(s1)
            dac_layout.addWidget(s1, row, 1)
            
            v1 = _QDoubleSpinBox()
            v1.setRange(-10, 10)
            v1.setSuffix(" V")
            v1.setDecimals(3)
            self.gate_dac_values.append(v1)
            dac_layout.addWidget(v1, row, 2)
            
            s2 = QCheckBox()
            self.gate_dac_offset_switches.append(s2)
            dac_layout.addWidget(s2, row, 4)
            
            v2 = _QDoubleSpinBox()
            v2.setRange(-10, 10)
            v2.setSuffix(" V")
            v2.setDecimals(3)
            self.gate_dac_offset_values.append(v2)
            dac_layout.addWidget(v2, row, 5)
            
        dac_layout.setColumnStretch(6, 1)
        matrix_group.setLayout(dac_layout)
        
        # --- 组装选通 DAC 页面 ---
        wrapper = QHBoxLayout()
        # 把两块包在一个垂直布局里，再整体靠左
        left_vbox = QVBoxLayout()
        left_vbox.addWidget(param_group)
        left_vbox.addWidget(matrix_group)
        wrapper.addLayout(left_vbox)
        wrapper.addStretch()
        
        parent_layout.addLayout(wrapper)
        
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
        # command = self.test_cmd_input.text() # 原来的字符串发送不用了
        
        if board_type not in self.active_sockets:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 错误: {board_type} 尚未连接！")
            return
            
        sock = self.active_sockets[board_type]
        
        # =================【模拟生成二进制指令】=================
        # 假设我们要发送：向 Bias1 (0x01) 的 行0xFF(广播) 列0x05 发送电压 -1.25V
        # 查表得知：CMD_WRITE=0x01, VOLTAGE=0x02
        test_frame = TDMProtocol.pack_frame(
            cmd_type=0x01, 
            board_id=0x01, 
            param_id=0x02, 
            channel_state=1,
            row_id=0xFF, 
            col_id=0x05, 
            value=-1.25, 
            is_float=True
        )
        
        # 为了能在界面上直观看到底层真实发出的 16进制 是什么，我们把它转成字符串打印在日志里
        hex_str = ' '.join([f'{b:02X}' for b in test_frame])
        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] -> 发送给 {board_type}:")
        self.connection_log.append(f"HEX: {hex_str}")
        # ========================================================

        self.test_send_btn.setEnabled(False)
        self.test_send_btn.setText("等待回复...")
        
        if not hasattr(self, 'comm_threads'):
            self.comm_threads = {}
            
        # 注意这里把原来的 command 改成了 test_frame，并在 SendCommandThread 里记得去掉 .encode()
        # 因为我们现在发的就是真正的 bytes 二进制了！
        thread = SendCommandThread(board_type, sock, test_frame) 
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
        """浏览并选择存储路径"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择数据存储目录",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if directory:
            self.storage_path.setText(directory)
            # 【修改】：打入专属数据日志
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 存储路径已更新: {directory}")

                
    def on_write_bias_clicked(self):
        """写入参数按钮的槽函数"""
        #获取当前选中的板卡索引
        current_index = self.bias_sub_tabs.currentIndex()
        current_board_widget = self.bias_boards[current_index]
        #socket
        board_type = f"Bias{current_index+1}"
        if board_type not in self.active_sockets:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 错误: {board_type} 尚未连接！")
            QMessageBox.warning(self, "警告", f"尚未连接 {board_type} 板卡！")
            return         
        sock = self.active_sockets[board_type]
        
        try:
            packets = current_board_widget.generate_write_packets()
            for pkt in packets:
                sock.sendall(pkt)
                
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 已向 {board_type} 发送写入指令 ({len(packets)} 条)")           
        except Exception as e:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 写入失败: {str(e)}")

            
            
        



def main():
        app = QApplication(sys.argv)
        app.setStyle('Fusion')  
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()

