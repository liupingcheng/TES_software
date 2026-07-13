#V6 整合子豪的bias界面连接控制逻辑

import sys
import time
import socket
import struct
import ipaddress
from PyQt5.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLineEdit as _QLineEdit, QMainWindow, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
                             QTabWidget, QGroupBox, QComboBox as _QComboBox, QDoubleSpinBox as _QDoubleSpinBox, QCheckBox, QScrollArea, QSpinBox as _QSpinBox, QTableWidget, QFileDialog,
                             QMessageBox, QFrame, QTableWidgetItem, QAbstractItemView, QHeaderView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent
from PyQt5.QtGui import QFont, QBrush, QColor

from tcp_manager import TCPManager
from protocol import TDMProtocol
from tdm_bias_widget import TDMBiasWidget

# ================= 安全交互控件=================
# 1. 下拉框：只屏蔽滚轮误触
class QComboBox(_QComboBox):
    def wheelEvent(self, event):
        event.ignore()

class ColoredHeaderView(QHeaderView):
    """可单独设置每个表头 section 颜色的表头。"""
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._default_color = QColor("#F0F0F0")
        self._section_colors = {}
        self.setSectionsClickable(True)

    def set_section_color(self, section, color):
        self._section_colors[section] = QColor(color)
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        if not rect.isValid():
            return
        painter.save()
        bg_color = self._section_colors.get(logicalIndex, self._default_color)
        painter.fillRect(rect, bg_color)
        painter.setPen(QColor("#CCCCCC"))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        text = self.model().headerData(logicalIndex, self.orientation(), Qt.DisplayRole)
        painter.setPen(QColor("#202124"))
        painter.drawText(rect, Qt.AlignCenter, "" if text is None else str(text))
        painter.restore()

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

class PIDCellWidget(QFrame):
    """
    智能 PID 单元格卡片：
    - 单击：发送预选中信号 (浅红色)
    - 双击：立即切换启用状态，并解除预选
    - 颜色判定：如果不等于全局参数，才显示蓝色
    """
    single_clicked = pyqtSignal(int, int)

    def __init__(self, row, col, parent=None):
        super().__init__(parent)
        self.row = row
        self.col = col
        self.is_enabled = False
        self.is_custom = False
        self.is_selected = False

        self.setFrameShape(QFrame.StyledPanel)
        
        layout = QGridLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        self.p_edit = QLineEdit("0x100")
        self.i_edit = QLineEdit("0x1")
        self.d_edit = QLineEdit("0x0")
        self.s_edit = QLineEdit("0xD")
        
        for ed in [self.p_edit, self.i_edit, self.d_edit, self.s_edit]:
            ed.setMaximumWidth(40)
            ed.setAlignment(Qt.AlignCenter)
            ed.installEventFilter(self)
            # 用户修改完毕后，进行比对校验
            ed.editingFinished.connect(self.on_edit_finished)
            
        lbl_p = QLabel("P:")
        lbl_i = QLabel("I:")
        lbl_d = QLabel("D:")
        lbl_s = QLabel("S:")
            
        
        layout.addWidget(lbl_p, 0, 0); layout.addWidget(self.p_edit, 0, 1)
        layout.addWidget(lbl_i, 0, 2); layout.addWidget(self.i_edit, 0, 3)
        layout.addWidget(lbl_d, 1, 0); layout.addWidget(self.d_edit, 1, 1)
        layout.addWidget(lbl_s, 1, 2); layout.addWidget(self.s_edit, 1, 3)
        
        self.update_color()

    def eventFilter(self, watched, event):
        if watched in [self.p_edit, self.i_edit, self.d_edit, self.s_edit] and event.type() == QEvent.MouseButtonPress:
            main_win = self.window()
            if hasattr(main_win, 'on_pid_cell_input_clicked'):
                main_win.on_pid_cell_input_clicked(self.row, self.col)
        return super().eventFilter(watched, event)

    def on_edit_finished(self):
        """用户编辑完毕后，自动对比全局参数，并按当前预选范围批量同步。"""
        self.is_enabled = True # 用户手动改参数，默认意图就是开启
        main_win = self.window()
        if hasattr(main_win, 'update_pid_cell_custom_flag'):
            main_win.update_pid_cell_custom_flag(self)
        if hasattr(main_win, 'apply_pid_bulk_edit_from_cell'):
            main_win.apply_pid_bulk_edit_from_cell(self.row, self.col)
        self.update_color()

    def set_enabled(self, state):
        self.is_enabled = state
        self.update_color()
        
    def set_selected(self, state):
        self.is_selected = state
        self.update_color()

    def set_pid_values(self, p_text, i_text, d_text, s_text):
        for editor, value in [(self.p_edit, p_text), (self.i_edit, i_text), (self.d_edit, d_text), (self.s_edit, s_text)]:
            editor.blockSignals(True)
            editor.setText(value)
            editor.blockSignals(False)

    def mousePressEvent(self, event):
        self.single_clicked.emit(self.row, self.col)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.is_enabled = not self.is_enabled
        if hasattr(self.window(), 'clear_pid_selection'):
            self.window().clear_pid_selection()
        self.update_color()
        super().mouseDoubleClickEvent(event)

    def update_color(self):
        """颜色优先级：红色预选 > 灰色禁用 > 蓝色独立 > 绿色跟随"""
        if self.is_selected:
            bg_color = "#FFCDD2" # 浅红预选
            border = "2px solid red"
        else:
            border = "1px solid #AAA"
            if not self.is_enabled:
                bg_color = "#E0E0E0" # 灰色未启用
            elif self.is_custom:
                bg_color = "#BBDEFB" # 蓝色独立设置
            else:
                bg_color = "#C8E6C9" # 绿色已启用
                
        self.setStyleSheet(f"PIDCellWidget {{ background-color: {bg_color}; border-radius: 4px; border: {border}; }}")
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
        self.signal_type = QComboBox()
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
        self.waveform_type = QComboBox()
        self.waveform_type.addItems(["正弦波", "三角波", "方波"])
        ac_layout.addWidget(self.waveform_type, 0, 1)
        
        ac_layout.addWidget(QLabel("频率:"), 1, 0)
        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.1, 10000)
        self.frequency.setValue(1000)
        self.frequency.setSuffix(" Hz")
        ac_layout.addWidget(self.frequency, 1, 1)
        
        ac_layout.addWidget(QLabel("幅值:"), 2, 0)
        self.amplitude = QDoubleSpinBox()
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
        self.dc_value = QDoubleSpinBox()
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
        self.sa_ib_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.sa_ib_switches])
        layout1.addWidget(self.sa_ib_master_switch, 0, 1, 1, 2)
        
        self.sa_phix_master_switch = QCheckBox("SA phix 总开关")
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
                
    def setup_board3_channels(self):
        """设置第三块板卡的通道控制 (紧凑型布局 + 分割线)"""
        group = QGroupBox("IS I & IS phib控制 (16列)")
        layout = QGridLayout()
        layout.setHorizontalSpacing(15) # 设置列之间的固定紧凑间距
        
        # --- 总开关 ---
        self.is_i_master_switch = QCheckBox("IS I 总开关")
        self.is_i_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.is_i_switches])
        layout.addWidget(self.is_i_master_switch, 0, 1, 1, 2)
        
        self.is_phib_master_switch = QCheckBox("IS phib 总开关")
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



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 【新增：网络连接管理器】
        self.tcp_manager = TCPManager()
        self.tcp_manager.board_connected.connect(self.on_board_connected)
        self.tcp_manager.board_disconnected.connect(self.on_board_disconnected)
        self.tcp_manager.board_data_received.connect(self.on_board_data_received)
        self.tcp_manager.board_probe_finished.connect(self.on_board_probe_finished)
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("TES-SQUID TDM 上位机控制软件")
        self.setGeometry(100, 100, 1200, 800)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # ================= 1. 上半部分：选项卡控件 =================
        self.tabs = QTabWidget()
        
        # 使用纯 Python 方式安全地放大主标签字体，相对缩放避免破坏 Mac 原生字体度量
        main_tab_font = self.tabs.tabBar().font()
        current_size = main_tab_font.pointSize()
        # 如果获取不到确切字号(某些系统返回-1)，给个默认基准值
        if current_size <= 0:
            current_size = 12
        main_tab_font.setPointSize(current_size + 2)
        self.tabs.tabBar().setFont(main_tab_font)
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
            status_layout.addWidget(title_lbl, row, col)
            
            # 值标签 (存入字典)
            val_lbl = QLabel(val)
            val_lbl.setStyleSheet(f"color: {color}; font-size: 13px;")
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
        widget = QWidget()  # 创建连接配置页
        layout = QVBoxLayout() # 创建连接配置页垂直布局
        
        connection_group = QGroupBox("Connection Settings")  # 创建连接配置组
        connection_layout = QGridLayout()  # 创建连接配置组垂直布局
        
        board_configs = [
            ('偏置源板卡1-TES Bias', 'Bias1',        '192.168.1.11'),
            ('偏置源板卡2-IS Bias', 'Bias2',        '192.168.1.12'),
            ('偏置源板卡3-SA Bias', 'Bias3',        '192.168.1.13'),
            ('ADC 读出板',   'ADC_readout',  '192.168.1.14'),
            ('FB DAC 板',    'FB_DAC',       '192.168.1.15'),
            ('选通 DAC 板',  'gate_DAC',     '192.168.1.16'),
            ('FPGA 汇总板',  'fpga',         '192.168.1.10'),
        ]
        
        #准备空字典来存储输入框
        self.board_ip_edits = {}
        self.board_port_edits = {}
        self.board_local_ip_edits = {}
        self.board_connection_btns = {}
        self.board_name_labels = {}
        
        widget.setLayout(layout)  # 设置连接配置页布局
        self.tabs.addTab(widget, "板卡控制")  # 添加连接配置页到选项卡
        
        # 循环生成每一行的控件
        for i,(name, board_type, default_ip) in enumerate(board_configs): 
            # 第1列：板卡名称标签（用作状态指示）
            name_label = QLabel(f" {name} ")
            name_label.setStyleSheet("background-color: #7F8C8D; color: white; padding: 4px; border-radius: 4px;")
            name_label.setAlignment(Qt.AlignCenter)
            self.board_name_labels[board_type] = name_label
            connection_layout.addWidget(name_label, i, 0) 
            
            # 第2列：IP 地址输入框
            ip_edit = QLineEdit(default_ip) 
            ip_edit.setMinimumWidth(120) 
            self.board_ip_edits[board_type] = ip_edit 
            connection_layout.addWidget(ip_edit, i, 1)
            
            # 第3列：端口输入框
            port_edit = QLineEdit("24")
            port_edit.setMaximumWidth(60)
            self.board_port_edits[board_type] = port_edit
            connection_layout.addWidget(QLabel("Port:"), i, 2)
            connection_layout.addWidget(port_edit, i, 3)

            # 第4列：本地 IP 输入框
            local_ip_edit = QLineEdit("")
            local_ip_edit.setMinimumWidth(120)
            self.board_local_ip_edits[board_type] = local_ip_edit
            connection_layout.addWidget(QLabel("Local IP:"), i, 4)
            connection_layout.addWidget(local_ip_edit, i, 5)

            # 第5列：连接按钮
            connect_btn = QPushButton("Connect")
            connect_btn.setMaximumWidth(80) 

            # 信号与槽连接
            connect_btn.clicked.connect(lambda checked, bt=board_type: self.connect_single_board(bt))
            self.board_connection_btns[board_type] = connect_btn 
            connection_layout.addWidget(connect_btn, i, 6)
            
            # 第6列：探测按钮
            probe_btn = QPushButton("Test Link")
            probe_btn.setMaximumWidth(80)
            probe_btn.clicked.connect(lambda checked, bt=board_type: self.probe_single_board(bt))
            connection_layout.addWidget(probe_btn, i, 7)
            
        connection_group.setLayout(connection_layout) # 设置连接配置组布局
        layout.addWidget(connection_group) # 将连接配置组添加到主布局

        #批量操作的按钮
        button_layout = QHBoxLayout() # 横向布局
        
        self.connect_all_btn = QPushButton("Connect All")
        self.connect_all_btn.setMinimumHeight(40)
        #绑定点击事件到函数
        self.connect_all_btn.clicked.connect(self.connect_all_boards)
        button_layout.addWidget(self.connect_all_btn)
        
        button_layout.setSpacing(60)
        
        self.disconnect_all_btn = QPushButton("Disconnect All")
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
        self.bias_sub_tabs.setStyleSheet("""
            QTabWidget::tab-bar { alignment: center; }
            QTabWidget::pane { border: none; border-top: 1px solid #D0D0D0; margin-top: 5px; }
            QTabBar::tab {
                background: #FFFFFF;
                border: 1px solid #C0C0C0;
                padding: 6px 20px;
                color: #333333;
                font-size: 13px;
                }
            QTabBar::tab:first { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
            QTabBar::tab:last { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
            QTabBar::tab:!first { margin-left: -1px; }
            QTabBar::tab:selected {
                background: #007AFF;
                color: white;
                border-color: #007AFF;
            }
        """)
        
        # ================= 2. 将三块板卡加入子标签页 =================
        self.bias_boards = []
        
        bias_board_configs = [
            (0, "Bias1", "偏置源板卡1-TES Bias", "192.168.1.11"),
            (1, "Bias2", "偏置源板卡2-IS Bias", "192.168.1.12"),
            (2, "Bias3", "偏置源板卡3-SA Bias", "192.168.1.13")
        ]
        
        for i, board_type, tab_name, default_ip in bias_board_configs:
            # 实例化新的板卡界面
            board_widget = TDMBiasWidget(board_type=board_type, board_name=tab_name, default_ip=default_ip)
            
            # 绑定信号以与主窗口同步
            board_widget.sync_params_signal.connect(self.on_bias_sync_params)
            board_widget.connect_clicked_signal.connect(self.connect_single_board)
            board_widget.probe_clicked_signal.connect(self.probe_single_board)
            board_widget.send_data_signal.connect(self.tcp_manager.send_data)
            board_widget.log_signal.connect(self.log_from_bias)
            
            # 反向同步：当主标签页切换时更新 board_widget
            ip_edit = self.board_ip_edits[board_type]
            port_edit = self.board_port_edits[board_type]
            local_ip_edit = self.board_local_ip_edits[board_type]
            
            ip_edit.textChanged.connect(lambda txt, bw=board_widget: bw.set_connection_params(txt, bw.txt_port.text(), bw.txt_local_ip.text()))
            port_edit.textChanged.connect(lambda txt, bw=board_widget: bw.set_connection_params(bw.txt_ip.text(), txt, bw.txt_local_ip.text()))
            local_ip_edit.textChanged.connect(lambda txt, bw=board_widget: bw.set_connection_params(bw.txt_ip.text(), bw.txt_port.text(), txt))
            
            self.bias_boards.append(board_widget)
            
            self.bias_sub_tabs.addTab(board_widget, f"   {tab_name}   ")
            
        layout.addWidget(self.bias_sub_tabs)
        
        # ================= 3. 底部公共操作按钮 =================
        # 原有的读写保存按钮对于 TDM bias 可能不再需要，因为 TDM bias 界面每个 channel 有自己的 send 按钮。
        # 如果需要保留，可以在这里添加。目前暂时隐藏或移除，以完全采用 TDM bias 的操作逻辑。
        # layout.addLayout(button_layout)
        
        widget.setLayout(layout)
        self.tabs.addTab(widget, "偏置源控制")
   
    def setup_ad_da_tab(self):
        """AD/DA控制选项卡 (双子标签页架构)"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        self.ad_da_sub_tabs = QTabWidget()
        self.ad_da_sub_tabs.setStyleSheet("""
            QTabWidget::tab-bar { alignment: center; }
            QTabWidget::pane { border: none; border-top: 1px solid #D0D0D0; margin-top: 5px; }
            QTabBar::tab {
                background: #FFFFFF;
                border: 1px solid #C0C0C0;
                padding: 6px 20px;
                color: #333333;
                font-size: 13px;
                }
            QTabBar::tab:first { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
            QTabBar::tab:last { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
            QTabBar::tab:!first { margin-left: -1px; }
            QTabBar::tab:selected {
                background: #007AFF;
                color: white;
                border-color: #007AFF;
            }
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
        self.ad_da_sub_tabs.addTab(ad_fb_scroll, "   ADC FB DAC控制   ")
        
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
        self.ad_da_sub_tabs.addTab(gate_scroll, "   选通 DAC 板   ")
        
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
        self.data_read_switch.stateChanged.connect(self.on_data_read_changed)
        control_layout.addWidget(self.data_read_switch)
        
        self.fb_control_switch = QCheckBox("反馈控制开关")
        self.fb_control_switch.stateChanged.connect(self.on_fb_control_changed)
        control_layout.addWidget(self.fb_control_switch)
        
        self.gate_control_switch = QCheckBox("选通控制开关")
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
        self.storage_path = QLineEdit()
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
        self.storage_format = QComboBox()
        self.storage_format.addItems(["二进制(.bin)", "数据(.dat)"])
        format_layout.addWidget(self.storage_format)
        
        format_layout.addSpacing(10)
        format_layout.addWidget(QLabel("前缀:"))
        self.file_prefix = QLineEdit("TDM_data")
        self.file_prefix.setMaximumWidth(100)
        format_layout.addWidget(self.file_prefix)
        
        format_layout.addSpacing(10)
        format_layout.addWidget(QLabel("分卷间隔:"))
        self.save_interval = QSpinBox()
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
        btn_layout.addWidget(self.start_storage_btn)
        
        self.stop_storage_btn = QPushButton("停止存储")
        self.stop_storage_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_storage_btn)
        btn_layout.addStretch()
        storage_layout.addLayout(btn_layout)
        
        # # 第四行：专属数据日志框
        # # 用蓝色背景，把它和底部的全局灰色日志区分开
        
        storage_group.setLayout(storage_layout)
        top_h_layout.addWidget(storage_group, stretch=3) # 占 3 份宽度
        
        main_layout.addLayout(top_h_layout)
        
        # ================= 下半部分：PID 参数控制区 (20行16列) =================
        
        
        
        
        
        
        
        
        
        # row_headers = [f" {i+1} " for i in range(20)]
        # col_headers = [f" {i+1} " for i in range(16)]
        
        
        # for row in range(20):
        #     row_switches, row_values = [], []
        #     for col in range(16):
                
        #         row_switches.append(switch)
                
        #         value = QDoubleSpinBox()
        #         value.setRange(-10, 10)
        #         value.setDecimals(3)
        #         row_values.append(value)
                
        #         cell_widget.setLayout(cell_layout)
            
        
        
        # pid_group.setLayout(pid_main_layout)
        # widget.setLayout(main_layout)
# ================= 下半部分：PID 参数控制区 (20行16列) =================
        pid_group = QGroupBox("PID参数控制 (20行 × 16列)")
        pid_main_layout = QVBoxLayout()
        
        pid_param_layout = QHBoxLayout()
        self.pid_master_switch = QCheckBox("PID参数 总开关")
        self.pid_master_switch.stateChanged.connect(self.toggle_all_pid)
        pid_param_layout.addWidget(self.pid_master_switch)
        
        pid_param_layout.addSpacing(30)
        
        # 顶部的全局 PID 输入框 (注意我给它们加上了 .editingFinished 的联动)
        pid_param_layout.addWidget(QLabel("全局 P(HEX):"))
        self.pid_p_value = QLineEdit("0x100")
        self.pid_p_value.setMaximumWidth(60)
        self.pid_p_value.editingFinished.connect(self.sync_global_pid)
        pid_param_layout.addWidget(self.pid_p_value)
        
        pid_param_layout.addWidget(QLabel("全局 I:"))
        self.pid_i_value = QLineEdit("0x1")
        self.pid_i_value.setMaximumWidth(60)
        self.pid_i_value.editingFinished.connect(self.sync_global_pid)
        pid_param_layout.addWidget(self.pid_i_value)
        
        pid_param_layout.addWidget(QLabel("全局 D:"))
        self.pid_d_value = QLineEdit("0x0")
        self.pid_d_value.setMaximumWidth(60)
        self.pid_d_value.editingFinished.connect(self.sync_global_pid)
        pid_param_layout.addWidget(self.pid_d_value)
        
        pid_param_layout.addWidget(QLabel("全局 S:"))
        self.pid_scale_value = QLineEdit("0xD")
        self.pid_scale_value.setMaximumWidth(60)
        self.pid_scale_value.editingFinished.connect(self.sync_global_pid)
        pid_param_layout.addWidget(self.pid_scale_value)
        
        pid_param_layout.addStretch()
        pid_main_layout.addLayout(pid_param_layout)
        
        self.pid_selection_mode = None
        self.pid_selected_row = None
        self.pid_selected_col = None

        self.pid_table = QTableWidget()
        self.pid_table.setRowCount(20)
        self.pid_table.setColumnCount(16)
        self.pid_horizontal_header = ColoredHeaderView(Qt.Horizontal, self.pid_table)
        self.pid_vertical_header = ColoredHeaderView(Qt.Vertical, self.pid_table)
        self.pid_table.setHorizontalHeader(self.pid_horizontal_header)
        self.pid_table.setVerticalHeader(self.pid_vertical_header)
        
        self.pid_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.pid_table.setFocusPolicy(Qt.NoFocus)
        # 表头颜色由 ColoredHeaderView 绘制，避免样式表覆盖 setBackground。
        # 显式实例化表头对象，并赋上默认的浅灰色
        for r in range(20):
            item = QTableWidgetItem(f" {r+1} ")
            item.setBackground(QBrush(QColor("#F0F0F0"))) # 默认浅灰
            self.pid_table.setVerticalHeaderItem(r, item)
            
        for c in range(16):
            item = QTableWidgetItem(f" {c+1} ")
            item.setBackground(QBrush(QColor("#F0F0F0"))) # 默认浅灰
            self.pid_table.setHorizontalHeaderItem(c, item)
            
                    # 绑定行列号（表头）的单击和双击事件
        self.pid_table.horizontalHeader().sectionClicked.connect(self.on_col_header_clicked)
        self.pid_table.horizontalHeader().sectionDoubleClicked.connect(self.on_col_header_double_clicked)
        self.pid_table.verticalHeader().sectionClicked.connect(self.on_row_header_clicked)
        self.pid_table.verticalHeader().sectionDoubleClicked.connect(self.on_row_header_double_clicked)
        # row_headers = [f" {i+1} " for i in range(20)]
        # col_headers = [f" {i+1} " for i in range(16)]
        
        # 原来装 checkbox 和 value 的两个列表，现在只需要一个存卡片的列表即可
        self.pid_cells = []
        
        for row in range(20):
            row_cells = []
            for col in range(16):
                cell_widget = PIDCellWidget(row, col)
                # 将卡片的“被点击”信号，连到主窗口的处理函数上
                cell_widget.single_clicked.connect(self.on_pid_cell_clicked)
                self.pid_table.setCellWidget(row, col, cell_widget)
                row_cells.append(cell_widget)
            
            self.pid_cells.append(row_cells)
            
        self.pid_table.horizontalHeader().setDefaultSectionSize(120)
        self.pid_table.verticalHeader().setDefaultSectionSize(75)
        pid_main_layout.addWidget(self.pid_table)
        pid_group.setLayout(pid_main_layout)
        main_layout.addWidget(pid_group, stretch=1)
        
        widget.setLayout(main_layout)
        self.tabs.addTab(widget, "FPGA数据汇总")
    def on_data_read_changed(self, state):
        if state == 2:
            self.sys_status_labels["数据读出"].setText("开")
            self.sys_status_labels["数据读出"].setStyleSheet("color: green; font-size: 13px;")
            # 【修改】：采用极其硬核的等宽日志风格
            self.connection_log.append("数据读出: [ ON ]")
        else:
            self.sys_status_labels["数据读出"].setText("关")
            self.sys_status_labels["数据读出"].setStyleSheet("color: red; font-size: 13px;")
            # 【修改】
            self.connection_log.append("数据读出: [ OFF ]")

    def on_fb_control_changed(self, state):
        if state == 2:
            self.sys_status_labels["反馈控制"].setText("开")
            self.sys_status_labels["反馈控制"].setStyleSheet("color: green; font-size: 13px;")
            self.connection_log.append("反馈控制: [ ON ]")
        else:
            self.sys_status_labels["反馈控制"].setText("关")
            self.sys_status_labels["反馈控制"].setStyleSheet("color: red; font-size: 13px;")
            self.connection_log.append("反馈控制: [ OFF ]")
            
    def on_gate_control_changed(self, state):
        if state == 2:
            self.sys_status_labels["选通控制"].setText("开")
            self.sys_status_labels["选通控制"].setStyleSheet("color: green; font-size: 13px;")
            self.connection_log.append("选通控制: [ ON ]")
        else:
            self.sys_status_labels["选通控制"].setText("关")
            self.sys_status_labels["选通控制"].setStyleSheet("color: red; font-size: 13px;")
            self.connection_log.append("选通控制: [ OFF ]")

    def setup_fb_dac_control(self, parent_layout):
        """FB DAC控制 (紧凑排版 + 呼吸空间)"""
        group = QGroupBox("FB DAC控制 (16列)")
        layout = QGridLayout()
        layout.setHorizontalSpacing(10)
        
        # --- 总开关 ---
        self.fb_dac_master_switch = QCheckBox("DAC 总开关")
        self.fb_dac_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.fb_dac_switches])
        layout.addWidget(self.fb_dac_master_switch, 0, 1, 1, 2)
        
        self.fb_dac_offset_master_switch = QCheckBox("DAC offset 总开关")
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
        self.adc_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.adc_switches])
        layout.addWidget(self.adc_master_switch, 0, 1, 1, 2)
        
        self.adc_offset_master_switch = QCheckBox("offset 总开关")
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
            
            v1 = QDoubleSpinBox()
            v1.setRange(-10, 10)
            v1.setSuffix(" V")
            v1.setDecimals(3)
            self.adc_values.append(v1)
            layout.addWidget(v1, row, 2)
            
            s2 = QCheckBox()
            self.adc_offset_switches.append(s2)
            layout.addWidget(s2, row, 4)
            
            v2 = QDoubleSpinBox()
            v2.setRange(-10, 10)
            v2.setSuffix(" V")
            v2.setDecimals(3)
            self.adc_offset_values.append(v2)
            layout.addWidget(v2, row, 5)
            
        layout.setColumnStretch(6, 1) # 右侧压紧弹簧
        group.setLayout(layout)
        parent_layout.addWidget(group)

    def probe_single_board(self, board_type):
        ip = self.board_ip_edits[board_type].text().strip()
        port_str = self.board_port_edits[board_type].text().strip()
        local_ip = self.board_local_ip_edits[board_type].text().strip()
        port = int(port_str) if port_str.isdigit() else 24
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            msg = f"{board_type} Invalid IP Address: {ip}"
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            QMessageBox.warning(self, "Test Link Failed", msg)
            return

        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} Test Link started ({ip}:{port})... (5s)")
        self.tcp_manager.probe_board(board_type, ip, port, 5.0, local_ip)

    def connect_single_board(self, board_type):
        """处理单个板卡的连接/断开点击"""
        current_text = self.board_connection_btns[board_type].text()
        
        # 状态 1：明确要求【连接】
        if current_text == "Connect":
            ip = self.board_ip_edits[board_type].text().strip()
            port_str = self.board_port_edits[board_type].text().strip()
            local_ip = self.board_local_ip_edits[board_type].text().strip()
            port = int(port_str) if port_str.isdigit() else 24
            
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                msg = f"{board_type} 的 IP 地址格式无效: {ip}"
                self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
                QMessageBox.warning(self, "连接失败", msg)
                return

            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 正在后台尝试连接 ({ip}:{port})...")
            
            self.board_name_labels[board_type].setStyleSheet("background-color: orange; color: white; padding: 4px; border-radius: 4px;")
            self.board_connection_btns[board_type].setEnabled(False)
            
            # Propagate to bias boards if applicable
            for bw in getattr(self, "bias_boards", []):
                if bw.board_type == board_type:
                    bw.set_badge_state("connecting")
            
            self.tcp_manager.connect_board(board_type, ip, port, local_ip)

        # 状态 2：明确要求【断开】
        elif current_text == "Disconnect":
            self.tcp_manager.disconnect_board(board_type)
            
        # 状态 3：如果是连接中等其他状态，直接无视（防狂点）
        else:
            pass

    def setup_gate_dac_control(self, parent_layout):
        """选通DAC控制 (20行矩阵, 极致紧凑 + 竖线隔离 + 居左防拉伸)"""
        # --- 1. 顶部的参数设置区 ---
        param_group = QGroupBox("20行选通全局参数设定")
        param_layout = QGridLayout()
        param_layout.setHorizontalSpacing(20)
        
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
        
        param_layout.addWidget(QLabel("幅值(HEX):"), 1, 0)
        self.gate_amplitude = QLineEdit("0xFFFF")
        param_layout.addWidget(self.gate_amplitude, 1, 1)
        
        param_layout.addWidget(QLabel("选通开始延迟:"), 1, 2)
        self.gate_start_delay = QSpinBox()
        self.gate_start_delay.setRange(0, 10000)
        self.gate_start_delay.setValue(0)
        self.gate_start_delay.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_delay, 1, 3)
        
        param_layout.addWidget(QLabel("选通开始稳态:"), 2, 0)
        self.gate_start_steady = QSpinBox()
        self.gate_start_steady.setRange(0, 10000)
        self.gate_start_steady.setValue(100)
        self.gate_start_steady.setSuffix(" ns")
        param_layout.addWidget(self.gate_start_steady, 2, 1)
        
        param_layout.addWidget(QLabel("选通结束稳态:"), 2, 2)
        self.gate_end_steady = QSpinBox()
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
        self.gate_dac_master_switch.stateChanged.connect(lambda state: [s.setChecked(state == 2) for s in self.gate_dac_switches])
        dac_layout.addWidget(self.gate_dac_master_switch, 0, 1, 1, 2)
        
        self.gate_dac_offset_master_switch = QCheckBox("offset 总开关")
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
            
            v1 = QDoubleSpinBox()
            v1.setRange(-10, 10)
            v1.setSuffix(" V")
            v1.setDecimals(3)
            self.gate_dac_values.append(v1)
            dac_layout.addWidget(v1, row, 2)
            
            s2 = QCheckBox()
            self.gate_dac_offset_switches.append(s2)
            dac_layout.addWidget(s2, row, 4)
            
            v2 = QDoubleSpinBox()
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
        
    def probe_single_board(self, board_type):
        """探测单个板卡的网络链路状态"""
        ip = self.board_ip_edits[board_type].text().strip()
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            msg = f"{board_type} Invalid IP Address: {ip}"
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            QMessageBox.warning(self, "Test Link Failed", msg)
            return

        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} Test Link started ({ip})... (5s)")
        self.tcp_manager.probe_board(board_type, ip, 24, 5.0)

    def connect_all_boards(self):
        """一键连接所有板卡 (严格判断状态)"""
        self.connection_log.append(f"\n[{time.strftime('%H:%M:%S')}] 开始尝试连接未连的板卡...")
        for board_type in self.board_ip_edits.keys():
            # 只有明确处于“连接”待机状态的按钮，才去触发
            if self.board_connection_btns[board_type].text() == "Connect":
                self.connect_single_board(board_type)

    def disconnect_all_boards(self):
        """一键断开所有板卡 (严格判断状态)"""
        self.connection_log.append(f"\n[{time.strftime('%H:%M:%S')}] 开始断开已连的板卡...")
        self.tcp_manager.disconnect_all()

    def on_board_connected(self, board_type):
        self.board_connection_btns[board_type].setEnabled(True)
        self.board_name_labels[board_type].setStyleSheet("background-color: #2ecc71; color: white; padding: 4px; border-radius: 4px;")
        self.board_connection_btns[board_type].setText("Disconnect")
        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接成功！")
        
        # Propagate to bias boards if applicable
        for bw in getattr(self, "bias_boards", []):
            if bw.board_type == board_type:
                bw.update_connection_state(True)

    def on_board_disconnected(self, board_type, error_msg=""):
        was_connecting = "orange" in self.board_name_labels[board_type].styleSheet()
        
        self.board_connection_btns[board_type].setEnabled(True)
        self.board_name_labels[board_type].setStyleSheet("background-color: #7F8C8D; color: white; padding: 4px; border-radius: 4px;")
        self.board_connection_btns[board_type].setText("Connect")
        
        # Propagate to bias boards if applicable
        for bw in getattr(self, "bias_boards", []):
            if bw.board_type == board_type:
                bw.update_connection_state(False)
        
        reason = f" ({error_msg})" if error_msg else ""
        if was_connecting:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接失败{reason}")
            # QMessageBox.warning(self, "连接失败", f"{board_type} 连接失败:\n{error_msg}")
        else:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 连接已断开{reason}")

    def on_bias_sync_params(self, board_type, ip, port, local_ip):
        if board_type in self.board_ip_edits:
            # Update without triggering feedback loop
            self.board_ip_edits[board_type].blockSignals(True)
            self.board_port_edits[board_type].blockSignals(True)
            self.board_local_ip_edits[board_type].blockSignals(True)
            
            self.board_ip_edits[board_type].setText(ip)
            self.board_port_edits[board_type].setText(port)
            self.board_local_ip_edits[board_type].setText(local_ip)
            
            self.board_ip_edits[board_type].blockSignals(False)
            self.board_port_edits[board_type].blockSignals(False)
            self.board_local_ip_edits[board_type].blockSignals(False)

    def log_from_bias(self, msg):
        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def on_board_data_received(self, board_type, length, raw_data):
        try:
            # Try to decode as text (like TDM_V4 did for string responses)
            response_str = raw_data.decode('utf-8', errors='strict').strip()
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] <- 收到 {board_type} 回复: {response_str}")
        except UnicodeDecodeError:
            # Fallback to Hex preview for binary frames
            hex_preview = raw_data.hex().upper()
            if len(hex_preview) > 40:
                hex_preview = hex_preview[:40] + "..."
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] <- 收到 {board_type} 数据包: {length} 字节 [{hex_preview}]")

    def on_board_probe_finished(self, board_type, success, msg):
        status = "✅ Test Link Success" if success else "❌ Test Link Failed"
        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {status}: {board_type} {msg}")

    def on_test_send_clicked(self):
        """点击测试发送按钮"""
        board_type = self.test_board_selector.currentText()
        
        if not self.tcp_manager.is_connected(board_type):
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 错误: {board_type} 尚未连接！")
            return
            
        # =================【模拟生成二进制指令】=================
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
        
        hex_str = ' '.join([f'{b:02X}' for b in test_frame])
        self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] -> 发送给 {board_type}:")
        self.connection_log.append(f"HEX: {hex_str}")
        
        # 纯异步发送，无需等待回复
        self.tcp_manager.send_data(board_type, test_frame)
    
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
        board_type = f"Bias{current_index+1}"
        if not self.tcp_manager.is_connected(board_type):
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 错误: {board_type} 尚未连接！")
            QMessageBox.warning(self, "警告", f"尚未连接 {board_type} 板卡！")
            return         
        
        try:
            packets = current_board_widget.generate_write_packets()
            for pkt in packets:
                self.tcp_manager.send_data(board_type, pkt)
                
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] 已向 {board_type} 发送写入指令 ({len(packets)} 条)")           
        except Exception as e:
            self.connection_log.append(f"[{time.strftime('%H:%M:%S')}] {board_type} 写入失败: {str(e)}")
 
# PID交互
# ================= PID 矩阵交互与智能对比逻辑 =================

    def update_pid_cell_custom_flag(self, cell):
        """判断单个 PID 单元是否使用了独立参数。"""
        cell.is_custom = (cell.p_edit.text() != self.pid_p_value.text() or
                          cell.i_edit.text() != self.pid_i_value.text() or
                          cell.d_edit.text() != self.pid_d_value.text() or
                          cell.s_edit.text() != self.pid_scale_value.text())

    def refresh_all_cells_color(self):
        """根据全局 PID 参数和启用状态刷新所有单元颜色。"""
        for r in range(20):
            for c in range(16):
                cell = self.pid_cells[r][c]
                self.update_pid_cell_custom_flag(cell)
                cell.update_color()

    def sync_global_pid(self):
        """当修改顶部全局参数时，把参数覆盖给所有【非蓝色】的跟随单元格。"""
        gp = self.pid_p_value.text()
        gi = self.pid_i_value.text()
        gd = self.pid_d_value.text()
        gs = self.pid_scale_value.text()
        
        for r in range(20):
            for c in range(16):
                cell = self.pid_cells[r][c]
                # 只有没有被独立设置的卡片，才会被全局修改覆盖
                if not cell.is_custom:
                    cell.set_pid_values(gp, gi, gd, gs)
                    
        # 覆盖完后，刷新一遍颜色
        self.refresh_all_cells_color()

    def _set_pid_header_color(self, row=None, col=None, color="#FFCDD2"):
        if row is not None:
            self.pid_vertical_header.set_section_color(row, color)
        if col is not None:
            self.pid_horizontal_header.set_section_color(col, color)

    def clear_pid_selection(self):
        """清除所有 PID 卡片和表头的红色预选中状态。"""
        self.pid_selection_mode = None
        self.pid_selected_row = None
        self.pid_selected_col = None
        for row in range(20):
            for col in range(16):
                self.pid_cells[row][col].set_selected(False)
        for row in range(20):
            self._set_pid_header_color(row=row, color="#F0F0F0")
        for col in range(16):
            self._set_pid_header_color(col=col, color="#F0F0F0")

    def on_pid_cell_clicked(self, row, col):
        """单击单元格：只预选当前单元格和对应行列号。"""
        self.clear_pid_selection()
        self.pid_selection_mode = "cell"
        self.pid_selected_row = row
        self.pid_selected_col = col
        self.pid_cells[row][col].set_selected(True)
        self._set_pid_header_color(row=row, col=col)

    def on_pid_cell_input_clicked(self, row, col):
        """点击输入框时，行/列预选范围内保持批量编辑语义。"""
        if self.pid_selection_mode == "row" and self.pid_selected_row == row:
            return
        if self.pid_selection_mode == "col" and self.pid_selected_col == col:
            return
        self.on_pid_cell_clicked(row, col)

    def on_pid_cell_double_clicked(self, row, col):
        """兼容旧信号：双击后清除全局的红色瞄准线。"""
        self.clear_pid_selection()
        self.refresh_all_cells_color()

    def on_row_header_clicked(self, row):
        """单击行号：预选整行，不改变启用状态。"""
        self.clear_pid_selection()
        self.pid_selection_mode = "row"
        self.pid_selected_row = row
        self._set_pid_header_color(row=row)
        for col in range(16):
            self.pid_cells[row][col].set_selected(True)

    def on_col_header_clicked(self, col):
        """单击列号：预选整列，不改变启用状态。"""
        self.clear_pid_selection()
        self.pid_selection_mode = "col"
        self.pid_selected_col = col
        self._set_pid_header_color(col=col)
        for row in range(20):
            self.pid_cells[row][col].set_selected(True)

    def apply_pid_bulk_edit_from_cell(self, row, col):
        """行/列预选时，把当前单元的整组 PID 参数同步到预选范围。"""
        if self.pid_selection_mode not in ("row", "col"):
            return
        if self.pid_selection_mode == "row" and self.pid_selected_row != row:
            return
        if self.pid_selection_mode == "col" and self.pid_selected_col != col:
            return

        source = self.pid_cells[row][col]
        values = (source.p_edit.text(), source.i_edit.text(), source.d_edit.text(), source.s_edit.text())
        target_cells = []
        if self.pid_selection_mode == "row":
            target_cells = [self.pid_cells[row][target_col] for target_col in range(16)]
        elif self.pid_selection_mode == "col":
            target_cells = [self.pid_cells[target_row][col] for target_row in range(20)]

        for cell in target_cells:
            if cell is not source:
                cell.set_pid_values(*values)
            cell.is_enabled = True
            self.update_pid_cell_custom_flag(cell)
            cell.set_selected(True)

    def on_row_header_double_clicked(self, row):
        """双击某个行号：整行全开/全关，并恢复真实颜色。"""
        self.clear_pid_selection()
        any_disabled = any(not self.pid_cells[row][c].is_enabled for c in range(16))
        for col in range(16):
            self.pid_cells[row][col].set_enabled(any_disabled)
        self.refresh_all_cells_color()

    def on_col_header_double_clicked(self, col):
        """双击某个列号：整列全开/全关，并恢复真实颜色。"""
        self.clear_pid_selection()
        any_disabled = any(not self.pid_cells[r][col].is_enabled for r in range(20))
        for row in range(20):
            self.pid_cells[row][col].set_enabled(any_disabled)
        self.refresh_all_cells_color()
        
    def toggle_all_pid(self, state):
        """总开关：一键开启/关闭所有，并刷新颜色。"""
        checked = (state == 2)
        self.clear_pid_selection()
        for row in range(20):
            for col in range(16):
                self.pid_cells[row][col].set_enabled(checked)
        self.refresh_all_cells_color()          
        



def main():
        # 仅在 Windows 下启用高 DPI 缩放，避免破坏 Mac 的原生 Retina 缩放
        if sys.platform == 'win32':
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
            
        app = QApplication(sys.argv)
        
        # 仅在 Windows 下注入优化的现代原生字体组合，避免默认的丑陋宋体
        if sys.platform == 'win32':
            global_font = QFont("Segoe UI")
            global_font.insertSubstitutions("Segoe UI", ["Microsoft YaHei UI", "Microsoft YaHei", "Arial", "sans-serif"])
            global_font.setPointSize(10)
            global_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality)
            app.setFont(global_font)
        
        # Use Fusion as base to ensure cross-platform geometry consistency
        app.setStyle('Fusion')
        
        # Apply a global Modern Light Theme to force beautiful rounded corners
        # and soft borders on all platforms, mimicking macOS aesthetics.
        app.setStyleSheet("""
            QGroupBox {
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                margin-top: 2ex;
                padding-top: 10px;
                background-color: #FAFAFA;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                left: 10px;
                color: #4A4A4A;
                }
        """)
        
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()
