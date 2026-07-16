#V5 PID参数界面优化，增加单元格预选和批量编辑功能
#V6 整合子豪的bias界面连接控制逻辑
#V7 增加参数存储，日志保存
import sys
import json
import datetime
from PyQt5.QtWidgets import QFileDialog
import time
import socket
import ipaddress
from PyQt5.QtWidgets import (QApplication, QGridLayout, QHBoxLayout, QLineEdit as _QLineEdit, QMainWindow, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
                             QTabWidget, QGroupBox, QComboBox as _QComboBox, QDoubleSpinBox as _QDoubleSpinBox, QCheckBox, QSpinBox as _QSpinBox, QTableWidget, QFileDialog,
                             QMessageBox, QFrame, QTableWidgetItem, QAbstractItemView, QHeaderView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent
from PyQt5.QtGui import QFont, QBrush, QColor

from tcp_manager import TCPManager
from protocol import TDMProtocol
from tdm_bias_widget import TDMBiasWidget
from fpga_widget import FPGAControlWidget
from adda_widget import ADDAControlWidget

# V8 偏置源板卡唯一的名称与默认网络配置。board_id 和 TCP 标识保持不变。
BIAS_BOARD_CONFIGS = (
    (0, "Bias1", "偏置源板卡1-IS Bias", "192.168.101.1", "192.168.101.2"),
    (1, "Bias2", "偏置源板卡2-SA Bias", "192.168.102.1", "192.168.102.2"),
    (2, "Bias3", "偏置源板卡3-TES Bias", "192.168.103.1", "192.168.103.2"),
)

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

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        # 点击单位区域时也能激活编辑：延迟全选数字部分
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._original_value = self.value() # 记下修改前的值
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)

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



    def get_config(self):
        return {
            "p": self.p_edit.text(),
            "i": self.i_edit.text(),
            "d": self.d_edit.text(),
            "s": self.s_edit.text()
        }
        
    def set_config(self, cfg):
        if "p" in cfg: self.p_edit.setText(cfg["p"])
        if "i" in cfg: self.i_edit.setText(cfg["i"])
        if "d" in cfg: self.d_edit.setText(cfg["d"])
        if "s" in cfg: self.s_edit.setText(cfg["s"])
        self.update_color()

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
        if self._is_editing:
            self.setValue(self._original_value)
            self.setStyleSheet("")
            self._is_editing = False
        super().focusOutEvent(event)

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
        
    
    def get_fpga_config(self):
        return self.fpga_widget.get_config()

    def set_fpga_config(self, data):
        return self.fpga_widget.set_config(data)


    def save_connection_log(self):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"TDM_Log_{ts}.txt"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存日志", default_name, "Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.connection_log.toPlainText())
                self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 日志已成功保存至: {file_path}")
            except Exception as e:
                self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 保存日志失败: {str(e)}")

    def save_current_page_config(self):
        tab_idx = self.tabs.currentIndex()
        data = None
        default_name = ""
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        if tab_idx == 1:
            bias_board = self.bias_sub_tabs.currentWidget()
            if bias_board:
                data = bias_board.get_board_config()
                if data:
                    ip = data['board_ip'].replace('.', '_')
                    default_name = f"Bias_{ip}_{ts}.json"
        elif tab_idx == 3:
            data = self.get_fpga_config()
            default_name = f"FPGA_Config_{ts}.json"
            
        if not data:
            self.connection_log.append("[系统] 当前页面不支持保存或未找到参数！")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "保存页面参数", default_name, "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                self.connection_log.append(f"[系统] 页面参数已成功保存至: {file_path}")
            except Exception as e:
                self.connection_log.append(f"[系统] 保存失败: {str(e)}")

    def load_current_page_config(self):
        tab_idx = self.tabs.currentIndex()
        if tab_idx in (0, 2, 4):
            self.connection_log.append("[系统] 当前页面不支持读取参数！")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(self, "读取页面参数", "", "JSON Files (*.json)")
        if not file_path: return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            success = False
            msg = ""
            if tab_idx == 1:
                bias_board = self.bias_sub_tabs.currentWidget()
                if bias_board:
                    success, msg = bias_board.set_board_config(data)
            elif tab_idx == 3:
                success, msg = self.set_fpga_config(data)
                
            if success:
                self.connection_log.append(f"[系统] 从 {file_path} 读取并恢复了参数")
            else:
                self.connection_log.append(f"[系统] 恢复失败: {msg}")
                
        except Exception as e:
            self.connection_log.append(f"[系统] 读取异常: {str(e)}")

    def init_ui(self):
        self.setWindowTitle("TDM Software V8")
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
            ("DFB状态", "关闭", "red"),   ("选通控制", "关", "red"),
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
        
        # --- 右侧边缘：页面参数管理 ---
        config_group = QGroupBox("页面参数管理")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(10)
        
        self.btn_save_page = QPushButton("保存参数")
        self.btn_save_page.setFixedHeight(35)
        self.btn_save_page.clicked.connect(self.save_current_page_config)
        
        self.btn_load_page = QPushButton("读取参数")
        self.btn_load_page.setFixedHeight(35)
        self.btn_load_page.clicked.connect(self.load_current_page_config)
        
        self.btn_save_log = QPushButton("保存日志")
        self.btn_save_log.setFixedHeight(35)
        self.btn_save_log.clicked.connect(self.save_connection_log)
        
        config_layout.addWidget(self.btn_save_page)
        config_layout.addWidget(self.btn_load_page)
        config_layout.addWidget(self.btn_save_log)
        config_layout.addStretch()
        config_group.setLayout(config_layout)
        config_group.setMaximumWidth(140)  # 限制最大宽度，使其看起来更紧凑
        
        bottom_layout.addWidget(config_group, stretch=0) # 取消拉伸权重，让它保持自身所需的最小宽度
        
        main_layout.addLayout(bottom_layout, stretch=1) # 底座整体占据 20% 高度
        
        # ================= 3. 初始化选项卡 =================
        self.setup_connection_tab()
        self.setup_bias_control_tab()
        self.setup_ad_da_tab()
        self.setup_fpga_tab()
        self.setup_storage_tab()

        
    def setup_connection_tab(self):
        widget = QWidget()  # 创建连接配置页
        layout = QVBoxLayout() # 创建连接配置页垂直布局
        
        connection_group = QGroupBox("Connection Settings")  # 创建连接配置组
        connection_layout = QGridLayout()  # 创建连接配置组垂直布局
        
        board_configs = [
            (name, board_type, default_ip, default_local_ip)
            for _, board_type, name, default_ip, default_local_ip in BIAS_BOARD_CONFIGS
        ] + [
            ('ADC 读出板',   'ADC_readout',  '192.168.104.1', '192.168.104.2'),
            ('FB DAC 板',    'FB_DAC',       '192.168.105.1', '192.168.105.2'),
            ('选通 DAC 板',  'gate_DAC',     '192.168.106.1', '192.168.106.2'),
            ('FPGA 汇总板',  'fpga',         '192.168.200.1', '192.168.200.2'),
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
        for i, (name, board_type, default_ip, default_local_ip) in enumerate(board_configs):
            # 第1列：板卡名称标签（用作状态指示）
            name_label = QLabel(f" {name} ")
            name_label.setStyleSheet("background-color: #7F8C8D; color: white; padding: 4px; border-radius: 4px;")
            name_label.setAlignment(Qt.AlignCenter)
            self.board_name_labels[board_type] = name_label
            connection_layout.addWidget(name_label, i, 0) 
            
            # 第2列：IP 地址输入框
            ip_edit = SafeLineEdit(default_ip) 
            ip_edit.setMinimumWidth(120) 
            self.board_ip_edits[board_type] = ip_edit 
            connection_layout.addWidget(ip_edit, i, 1)
            
            # 第3列：端口输入框
            port_edit = SafeLineEdit("24")
            port_edit.setMaximumWidth(60)
            self.board_port_edits[board_type] = port_edit
            connection_layout.addWidget(QLabel("Port:"), i, 2)
            connection_layout.addWidget(port_edit, i, 3)

            # 第4列：本地 IP 输入框
            local_ip_edit = SafeLineEdit(default_local_ip)
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
        
        for i, board_type, tab_name, default_ip, default_local_ip in BIAS_BOARD_CONFIGS:
            # 实例化新的板卡界面
            board_widget = TDMBiasWidget(
                board_type=board_type,
                board_name=tab_name,
                default_ip=default_ip,
                default_local_ip=default_local_ip,
            )
            
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
            
            ip_edit.returnPressed.connect(lambda bw=board_widget, e=ip_edit: bw.set_connection_params(e.text(), bw.txt_port.text(), bw.txt_local_ip.text()))
            port_edit.returnPressed.connect(lambda bw=board_widget, e=port_edit: bw.set_connection_params(bw.txt_ip.text(), e.text(), bw.txt_local_ip.text()))
            local_ip_edit.returnPressed.connect(lambda bw=board_widget, e=local_ip_edit: bw.set_connection_params(bw.txt_ip.text(), bw.txt_port.text(), e.text()))
            
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
        """装配独立的 AD/DA 控制页。"""
        self.adda_widget = ADDAControlWidget(self)
        self.tabs.addTab(self.adda_widget, "AD/DA控制")

    def setup_fpga_tab(self):
        """FPGA数据汇总选项卡 (顶部双拼布局 + 底部大表格)"""
        self.fpga_widget = FPGAControlWidget(self)
        self.fpga_widget.log_signal.connect(self.log_from_fpga_ui)
        self.fpga_widget.dfb_state_changed.connect(self.on_fpga_dfb_ui_changed)
        self.tabs.addTab(self.fpga_widget, "FPGA控制")
        return

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

    def probe_single_board(self, board_type):
        ip = self.board_ip_edits[board_type].text().strip()
        port_str = self.board_port_edits[board_type].text().strip()
        local_ip = self.board_local_ip_edits[board_type].text().strip()
        port = int(port_str) if port_str.isdigit() else 24
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            msg = f"{board_type} Invalid IP Address: {ip}"
            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
            QMessageBox.warning(self, "Test Link Failed", msg)
            return

        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {board_type} Test Link started ({ip}:{port})... (5s)")
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
                self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
                QMessageBox.warning(self, "连接失败", msg)
                return

            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {board_type} 正在连接 ({ip}:{port})...")
            
            self.tcp_manager.connect_board(board_type, ip, port, local_ip)

        # 状态 2：明确要求【断开】
        elif current_text == "Disconnect":
            self.tcp_manager.disconnect_board(board_type)
            
        # 状态 3：如果是连接中等其他状态，直接无视（防狂点）
        else:
            pass

    def connect_all_boards(self):
        """一键连接所有板卡 (严格判断状态)"""
        self.connection_log.append(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始尝试连接未连的板卡...")
        for board_type in self.board_ip_edits.keys():
            # 只有明确处于“连接”待机状态的按钮，才去触发
            if self.board_connection_btns[board_type].text() == "Connect":
                self.connect_single_board(board_type)

    def disconnect_all_boards(self):
        """一键断开所有板卡 (严格判断状态)"""
        has_connected = False
        for btn in self.board_connection_btns.values():
            if btn.text() == "Disconnect":
                has_connected = True
                break
                
        if not has_connected:
            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 当前没有任何已连接的板卡。")
            return
            
        self.connection_log.append(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始断开已连的板卡...")
        self.tcp_manager.disconnect_all()

    def on_board_connected(self, board_type):
        self.board_connection_btns[board_type].setEnabled(True)
        self.board_name_labels[board_type].setStyleSheet("background-color: #2ecc71; color: white; padding: 4px; border-radius: 4px;")
        self.board_connection_btns[board_type].setText("Disconnect")
        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {board_type} 连接成功！")
        
        # Propagate to bias boards if applicable
        for bw in getattr(self, "bias_boards", []):
            if bw.board_type == board_type:
                bw.update_connection_state(True)

    def on_board_disconnected(self, board_type, error_msg=""):
        self.board_connection_btns[board_type].setEnabled(True)
        self.board_name_labels[board_type].setStyleSheet("background-color: #7F8C8D; color: white; padding: 4px; border-radius: 4px;")
        self.board_connection_btns[board_type].setText("Connect")
        
        # Propagate to bias boards if applicable
        for bw in getattr(self, "bias_boards", []):
            if bw.board_type == board_type:
                bw.update_connection_state(False)
        
        reason = f" ({error_msg})" if error_msg else ""
        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {board_type} 连接已断开{reason}")

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
        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def on_board_data_received(self, board_type, length, raw_data):
        try:
            # Try to decode as text (like TDM_V4 did for string responses)
            response_str = raw_data.decode('utf-8', errors='strict').strip()
            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] <- 收到 {board_type} 回复: {response_str}")
        except UnicodeDecodeError:
            # Fallback to Hex preview for binary frames
            hex_preview = raw_data.hex().upper()
            if len(hex_preview) > 40:
                hex_preview = hex_preview[:40] + "..."
            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] <- 收到 {board_type} 数据包: {length} 字节 [{hex_preview}]")

    def on_board_probe_finished(self, board_type, success, msg):
        status = "Test Link Success" if success else "Test Link Failed"
        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {status}: {board_type} {msg}")

    def on_test_send_clicked(self):
        """点击测试发送按钮"""
        board_type = self.test_board_selector.currentText()
        
        if not self.tcp_manager.is_connected(board_type):
            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 错误: {board_type} 尚未连接！")
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
        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] -> 发送给 {board_type}:")
        self.connection_log.append(f"HEX: {hex_str}")
        
        # 纯异步发送，无需等待回复
        self.tcp_manager.send_data(board_type, test_frame)
    
    def setup_storage_tab(self):
        """数据存储独立一级标签页；本阶段仅迁移现有 UI。"""
        widget = QWidget()
        main_layout = QVBoxLayout(widget)

        storage_group = QGroupBox("数据存储设置")
        storage_layout = QVBoxLayout(storage_group)

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

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("存储格式:"))
        self.storage_format = QComboBox()
        self.storage_format.addItems(["二进制(.bin)", "数据(.dat)"])
        format_layout.addWidget(self.storage_format)
        format_layout.addSpacing(20)
        format_layout.addWidget(QLabel("文件前缀:"))
        self.file_prefix = QLineEdit("TDM_data")
        self.file_prefix.setMaximumWidth(160)
        format_layout.addWidget(self.file_prefix)
        format_layout.addSpacing(20)
        format_layout.addWidget(QLabel("分卷间隔:"))
        self.save_interval = QSpinBox()
        self.save_interval.setRange(1, 86400)
        self.save_interval.setValue(60)
        self.save_interval.setSuffix(" 秒")
        format_layout.addWidget(self.save_interval)
        format_layout.addStretch()
        storage_layout.addLayout(format_layout)

        button_layout = QHBoxLayout()
        self.start_storage_btn = QPushButton("开始存储")
        self.stop_storage_btn = QPushButton("停止存储")
        self.stop_storage_btn.setEnabled(False)
        self.storage_status_label = QLabel("状态：未存储")
        self.storage_status_label.setStyleSheet("color: #616161; font-weight: bold;")
        button_layout.addWidget(self.start_storage_btn)
        button_layout.addWidget(self.stop_storage_btn)
        button_layout.addSpacing(20)
        button_layout.addWidget(self.storage_status_label)
        button_layout.addStretch()
        storage_layout.addLayout(button_layout)

        note = QLabel("当前阶段仅完成数据存储页面迁移，数据接收、落盘和分卷逻辑尚未接入。")
        note.setStyleSheet("color: #607D8B;")
        storage_layout.addWidget(note)

        main_layout.addWidget(storage_group)
        main_layout.addStretch()
        self.tabs.addTab(widget, "数据存储")

    def log_from_fpga_ui(self, msg):
        self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

    def on_fpga_dfb_ui_changed(self, enabled):
        label = self.sys_status_labels.get("DFB状态")
        if not label:
            return
        label.setText("开启" if enabled else "关闭")
        color = "green" if enabled else "red"
        label.setStyleSheet(f"color: {color}; font-size: 13px;")

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
            self.connection_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 存储路径已更新: {directory}")

                
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
