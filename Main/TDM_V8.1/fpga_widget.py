"""FPGA configuration UI for TDM V8.

This module intentionally contains no FPGA protocol encoding and no TCP calls.
It owns only the editable configuration model and the related Qt widgets.
"""

from copy import deepcopy

from PyQt5.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


ROWS = 20
COLS = 16
SELECTOR_EMPTY = -1
SELECTOR_ALL = -2
# Cell 内 P/I/A/D 数值显示的启动默认值；运行时可通过表格右键菜单切换。
SHOW_CELL_PARAMETER_VALUES = False
GLOBAL_REGISTER_ADDRS = {0x00, 0x01, 0x02, 0x03, 0x08, 0x0A, 0x0B}
CELL_PARAMETER_KEYS = ("kp", "ki", "adc_offset", "dac_offset")


def parse_uint(text, bits, label):
    """Parse decimal or 0x-prefixed unsigned integers with a field-specific error."""
    value_text = str(text).strip()
    if not value_text:
        raise ValueError(f"{label} 不能为空")
    try:
        value = int(value_text, 0)
    except ValueError as exc:
        raise ValueError(f"{label} 必须是十进制或 0x 开头的十六进制整数") from exc
    maximum = (1 << bits) - 1
    if not 0 <= value <= maximum:
        raise ValueError(f"{label} 超出范围：0 ～ 0x{maximum:X}")
    return value


class UIntLineEdit(QLineEdit):
    """Unsigned integer editor that only commits when Enter is pressed."""

    value_committed = pyqtSignal(int)

    def __init__(self, value, bits, label, display_hex=True, parent=None):
        super().__init__(parent)
        self.bits = bits
        self.label = label
        self.display_hex = display_hex
        self._last_value = int(value)
        self._is_editing = False
        self.setMaximumWidth(88)
        self.setAlignment(Qt.AlignCenter)
        self.set_value(value)

    def value(self):
        return parse_uint(self.text(), self.bits, self.label)

    def set_value(self, value):
        value = int(value)
        maximum = (1 << self.bits) - 1
        if not 0 <= value <= maximum:
            raise ValueError(f"{self.label} 超出范围")
        self._last_value = value
        text = f"0x{value:X}" if self.display_hex else str(value)
        self.setText(text)

    def _commit(self):
        previous_value = self._last_value
        try:
            value = self.value()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            self.set_value(self._last_value)
            return False
        self.set_value(value)
        if value != previous_value:
            self.value_committed.emit(value)
        return True

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._commit()
            self._is_editing = False
            self.setStyleSheet("")
            self.clearFocus()
        elif event.key() == Qt.Key_Escape:
            self.set_value(self._last_value)
            self._is_editing = False
            self.setStyleSheet("")
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._is_editing:
            self.set_value(self._last_value)
            self._is_editing = False
            self.setStyleSheet("")
        super().focusOutEvent(event)


class ConfirmSpinBox(QSpinBox):
    """Integer spin box whose pending value needs Enter confirmation."""

    value_committed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setKeyboardTracking(False)
        self._committed_value = self.value()
        self._is_editing = False

    def setValue(self, value):
        super().setValue(value)
        if not getattr(self, "_is_editing", False):
            self._committed_value = self.value()

    def wheelEvent(self, event):
        event.ignore()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._committed_value = self.value()
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            previous_value = self._committed_value
            super().keyPressEvent(event)
            self._committed_value = self.value()
            self._is_editing = False
            self.setStyleSheet("")
            if self._committed_value != previous_value:
                self.value_committed.emit(self._committed_value)
            self.clearFocus()
        elif event.key() == Qt.Key_Escape:
            self.setValue(self._committed_value)
            self._is_editing = False
            self.setStyleSheet("")
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._is_editing:
            self.setValue(self._committed_value)
            self._is_editing = False
            self.setStyleSheet("")
        super().focusOutEvent(event)


class ConfirmComboBox(QComboBox):
    """Combo box whose pending selection needs Enter confirmation."""

    index_committed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._committed_index = self.currentIndex()
        self._is_editing = False

    def setCurrentIndex(self, index):
        super().setCurrentIndex(index)
        if not getattr(self, "_is_editing", False):
            self._committed_index = self.currentIndex()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._committed_index = self.currentIndex()
        self._is_editing = True
        self.setStyleSheet("background-color: #FFFF99;")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            previous_index = self._committed_index
            self._committed_index = self.currentIndex()
            self._is_editing = False
            self.setStyleSheet("")
            if self._committed_index != previous_index:
                self.index_committed.emit(self._committed_index)
            self.clearFocus()
            event.accept()
        elif event.key() == Qt.Key_Escape:
            self.setCurrentIndex(self._committed_index)
            self._is_editing = False
            self.setStyleSheet("")
            self.clearFocus()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if self._is_editing:
            self.setCurrentIndex(self._committed_index)
            self._is_editing = False
            self.setStyleSheet("")
        super().focusOutEvent(event)


class ToggleSwitch(QAbstractButton):
    """Compact keyboard-accessible on/off switch."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(44, 24)
        self.setAccessibleName("DFB 开关")
        self.toggled.connect(self.update)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        if not self.isEnabled():
            track_color = QColor("#BDBDBD")
        elif self.isChecked():
            track_color = QColor("#007AFF")
        else:
            track_color = QColor("#8E8E93")

        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        knob_size = track.height() - 4
        knob_x = track.right() - knob_size - 2 if self.isChecked() else track.left() + 2
        knob = QRectF(knob_x, track.top() + 2, knob_size, knob_size)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(knob)

        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#005FCC"), 1))
            painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 6, 6)


class CenteredTabWidget(QTabWidget):
    """Keep the tab bar centered across the full widget, independent of corners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._schedule_tab_bar_centering)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_tab_bar()

    def paintEvent(self, event):
        self._center_tab_bar()
        super().paintEvent(event)

    def tabInserted(self, index):
        super().tabInserted(index)
        self._schedule_tab_bar_centering()

    def _schedule_tab_bar_centering(self, _index=None):
        self._center_tab_bar()
        QTimer.singleShot(0, self._center_tab_bar)

    def _center_tab_bar(self):
        tab_bar = self.tabBar()
        centered_x = max(0, (self.width() - tab_bar.width()) // 2)
        tab_bar.move(centered_x, tab_bar.y())


class CellTableWidget(QTableWidget):
    """Cell matrix with a real select-all button in the header intersection."""

    def __init__(self, rows, columns, parent=None):
        super().__init__(rows, columns, parent)
        self.select_all_button = QPushButton("", self)
        self.select_all_button.setObjectName("fpga_cell_corner_select_all")
        self.select_all_button.setFocusPolicy(Qt.NoFocus)
        self.select_all_button.setAccessibleName("全选或取消全部待写 Cell")
        self.select_all_button.setToolTip(
            "左键：全选 / 取消全选；右键：显示 / 隐藏表格内参数"
        )
        self.select_all_button.setStyleSheet(
            "QPushButton { background:#F2F2F2; border:1px solid #B8B8B8; "
            "padding:0px; }"
            "QPushButton:hover { background:#E3F2FD; border-color:#1976D2; }"
            "QPushButton:pressed { background:#BBDEFB; }"
        )
        self.horizontalHeader().geometriesChanged.connect(
            self._position_select_all_button
        )
        self.verticalHeader().geometriesChanged.connect(
            self._position_select_all_button
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_select_all_button()

    def paintEvent(self, event):
        self._position_select_all_button()
        super().paintEvent(event)

    def _position_select_all_button(self):
        horizontal_header = self.horizontalHeader()
        vertical_header = self.verticalHeader()
        if horizontal_header.isHidden() or vertical_header.isHidden():
            self.select_all_button.hide()
            return
        self.select_all_button.setGeometry(
            vertical_header.x(),
            horizontal_header.y(),
            vertical_header.width(),
            horizontal_header.height(),
        )
        self.select_all_button.show()
        self.select_all_button.raise_()


class CellStatusButton(QToolButton):
    """Compact matrix cell: background is channel status, check is write selection."""

    def __init__(self, row, col, parent=None):
        super().__init__(parent)
        self.row = row
        self.col = col
        self.has_parameters = False
        self.written = False
        self.write_mismatch = False
        self.show_parameter_values = SHOW_CELL_PARAMETER_VALUES
        self.parameters = {"kp": 0, "ki": 0, "adc_offset": 0, "dac_offset": 0}
        self.setCheckable(True)
        self.setMinimumSize(26, 20)
        self.setMaximumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toggled.connect(self.refresh_style)
        self.refresh_style()

    def set_status(
        self, has_parameters, written, parameters=None, write_mismatch=False
    ):
        self.has_parameters = bool(has_parameters)
        self.written = bool(written)
        self.write_mismatch = bool(write_mismatch)
        if parameters is not None:
            for key in self.parameters:
                self.parameters[key] = int(parameters[key])
        self.refresh_style()

    def set_selected(self, selected):
        self.setChecked(bool(selected))

    def set_parameter_visibility(self, visible):
        self.show_parameter_values = bool(visible)
        self.refresh_style()

    def refresh_style(self):
        if not self.has_parameters:
            background = "#E0E0E0"
            state_text = "无参数"
        elif self.write_mismatch:
            background = "#BBDEFB"
            state_text = "已写入"
        elif self.written:
            background = "#C8E6C9"
            state_text = "已写入"
        else:
            background = "#FFF9C4"
            state_text = "已保存，待写入"
        border = "2px solid #D32F2F" if self.isChecked() else "1px solid #9E9E9E"
        self.setToolTip(
            f"[{self.row + 1},{self.col + 1}]\n"
            f"P: {self.parameters['kp']}\n"
            f"I: {self.parameters['ki']}\n"
            f"A: {self.parameters['adc_offset']}\n"
            f"D: {self.parameters['dac_offset']}\n"
            f"状态: {state_text}"
        )
        if self.show_parameter_values:
            selection_mark = "✓" if self.isChecked() else " "
            self.setText(
                f"{selection_mark}P:{self.parameters['kp']} I:{self.parameters['ki']}\n"
                f" A:{self.parameters['adc_offset']} D:{self.parameters['dac_offset']}"
            )
            text_style = (
                "font-family: Menlo, Consolas, monospace; font-size: 10px; "
                "font-weight: normal; color: #202124; text-align: left; padding: 0px 1px;"
            )
        else:
            self.setText("✓" if self.isChecked() else "")
            text_style = "font-weight: bold; color: #B71C1C; padding: 0px;"
        self.setStyleSheet(
            "QToolButton {"
            f"background-color: {background}; border: {border}; border-radius: 3px;"
            f"{text_style}"
            "} QToolButton:hover { border-color: #1976D2; }"
        )


class CellParameterDialog(QDialog):
    """Atomic editor for all 20x16 per-cell parameter sets."""

    def __init__(self, cells, selected_keys, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑通道参数")
        self.resize(930, 680)
        self._source_cells = deepcopy(cells)
        self._selected_keys = set(selected_keys)
        self.result_cells = None

        root = QVBoxLayout(self)
        help_label = QLabel(
            "可编辑全部 320 个通道；参数只保存到本地界面，点击“写入预选”时才进入后续下发流程。"
        )
        help_label.setStyleSheet("color: #546E7A;")
        root.addWidget(help_label)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("显示行:"))
        self.row_filter = QComboBox()
        self.row_filter.addItem("全部", -1)
        for row in range(ROWS):
            self.row_filter.addItem(f"Row {row + 1}", row)
        filter_layout.addWidget(self.row_filter)

        filter_layout.addWidget(QLabel("显示列:"))
        self.col_filter = QComboBox()
        self.col_filter.addItem("全部", -1)
        for col in range(COLS):
            self.col_filter.addItem(f"Col {col + 1}", col)
        filter_layout.addWidget(self.col_filter)

        self.selected_only = QCheckBox("只看矩阵中已预选的通道")
        filter_layout.addWidget(self.selected_only)
        filter_layout.addStretch()
        root.addLayout(filter_layout)

        self.table = QTableWidget(ROWS * COLS, 6)
        self.table.setHorizontalHeaderLabels(
            ["Row", "Col", "Kp", "Ki", "ADC offset", "DAC offset"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        for table_row, cell in enumerate(self._source_cells):
            row = cell["row"]
            col = cell["col"]
            row_item = QTableWidgetItem(str(row + 1))
            col_item = QTableWidgetItem(str(col + 1))
            row_item.setFlags(row_item.flags() & ~Qt.ItemIsEditable)
            col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)

            value_items = [
                QTableWidgetItem(f"0x{cell['kp']:X}"),
                QTableWidgetItem(f"0x{cell['ki']:X}"),
                QTableWidgetItem(f"0x{cell['adc_offset']:X}"),
                QTableWidgetItem(f"0x{cell['dac_offset']:X}"),
            ]
            items = [row_item, col_item] + value_items
            for column, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                if (row, col) in self._selected_keys:
                    item.setBackground(QColor("#FFEBEE"))
                self.table.setItem(table_row, column, item)

        root.addWidget(self.table, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.row_filter.currentIndexChanged.connect(self._apply_filter)
        self.col_filter.currentIndexChanged.connect(self._apply_filter)
        self.selected_only.toggled.connect(self._apply_filter)

    def _apply_filter(self):
        wanted_row = self.row_filter.currentData()
        wanted_col = self.col_filter.currentData()
        only_selected = self.selected_only.isChecked()
        for table_row, cell in enumerate(self._source_cells):
            visible = wanted_row in (-1, cell["row"])
            visible = visible and wanted_col in (-1, cell["col"])
            if only_selected:
                visible = visible and (cell["row"], cell["col"]) in self._selected_keys
            self.table.setRowHidden(table_row, not visible)

    def _validate_and_accept(self):
        parsed_cells = []
        fields = [
            (2, "Kp", 32, "kp"),
            (3, "Ki", 32, "ki"),
            (4, "ADC offset", 16, "adc_offset"),
            (5, "DAC offset", 16, "dac_offset"),
        ]
        for table_row, old_cell in enumerate(self._source_cells):
            new_cell = {
                "row": old_cell["row"],
                "col": old_cell["col"],
            }
            try:
                for column, label, bits, key in fields:
                    new_cell[key] = parse_uint(
                        self.table.item(table_row, column).text(),
                        bits,
                        f"Row {old_cell['row'] + 1} / Col {old_cell['col'] + 1} 的 {label}",
                    )
            except ValueError as exc:
                QMessageBox.warning(self, "参数错误", str(exc))
                self.table.selectRow(table_row)
                self.table.scrollToItem(self.table.item(table_row, column))
                return
            parameters_unchanged = all(
                new_cell[key] == old_cell[key]
                for _column, _label, _bits, key in fields
            )
            new_cell["written"] = (
                bool(old_cell.get("written", False)) and parameters_unchanged
            )
            parsed_cells.append(new_cell)
        self.result_cells = parsed_cells
        self.accept()


class FPGAControlWidget(QWidget):
    """Complete V8 FPGA configuration page (UI and local state only)."""

    log_signal = pyqtSignal(str)
    dfb_state_changed = pyqtSignal(bool)
    mode_write_requested = pyqtSignal(int, int, int)
    counter_limit_write_requested = pyqtSignal(int)
    amp_factor_write_requested = pyqtSignal(int)
    dac_row_write_requested = pyqtSignal(int)
    tx_col_write_requested = pyqtSignal(int)
    timing_write_requested = pyqtSignal(int, int, int)
    dfb_write_requested = pyqtSignal(bool)
    global_write_requested = pyqtSignal(dict, object)
    cell_write_requested = pyqtSignal(object)
    all_cells_write_requested = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = True
        self.show_cell_parameter_values = SHOW_CELL_PARAMETER_VALUES
        self.dirty_registers = set()
        self.cell_defaults = {"kp": 0, "ki": 0, "adc_offset": 0, "dac_offset": 0}
        self.cells = [
            {
                "row": row,
                "col": col,
                "kp": 0,
                "ki": 0,
                "adc_offset": 0,
                "dac_offset": 0,
                "written": False,
            }
            for row in range(ROWS)
            for col in range(COLS)
        ]
        self.cell_buttons = {}
        self._build_ui()
        self._loading = False
        self.dirty_registers.clear()
        self._refresh_dirty_ui()
        self._refresh_all_cells()
        self._update_dfb_indicator(self.dfb_switch.isChecked())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # 与偏置源控制页面保持一致：用居中的分段式子标签拆分参数区域。
        self.fpga_sub_tabs = CenteredTabWidget()
        self.fpga_sub_tabs.setObjectName("fpga_parameter_tabs")
        self.fpga_sub_tabs.setElideMode(Qt.ElideNone)
        self.fpga_sub_tabs.setStyleSheet("""
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

        self.dfb_corner_widget = QWidget(self.fpga_sub_tabs)
        self.dfb_corner_widget.setObjectName("fpga_dfb_corner_control")
        dfb_corner_layout = QHBoxLayout(self.dfb_corner_widget)
        dfb_corner_layout.setContentsMargins(8, 0, 8, 0)
        dfb_corner_layout.setSpacing(6)
        dfb_title = QLabel("DFB")
        dfb_title.setStyleSheet("font-weight: bold;")
        self.dfb_state_label = QLabel("关闭")
        self.dfb_state_label.setAlignment(Qt.AlignCenter)
        self.dfb_state_label.setMinimumWidth(28)
        self.dfb_switch = ToggleSwitch()
        dfb_corner_layout.addWidget(dfb_title)
        dfb_corner_layout.addWidget(self.dfb_state_label)
        dfb_corner_layout.addWidget(self.dfb_switch)

        self.fpga_sub_tabs.setCornerWidget(self.dfb_corner_widget, Qt.TopRightCorner)
        self.fpga_sub_tabs.currentChanged.connect(self._raise_dfb_corner)

        global_page = QWidget()
        global_page.setObjectName("fpga_global_parameter_page")
        global_layout = QVBoxLayout(global_page)
        global_layout.setContentsMargins(8, 8, 8, 8)
        global_layout.setSpacing(8)
        parameter_layout = QGridLayout()
        parameter_layout.setHorizontalSpacing(12)
        parameter_layout.setVerticalSpacing(8)
        parameter_layout.setColumnStretch(0, 1)
        parameter_layout.setColumnStretch(1, 1)

        mode_box = QGroupBox("MODE（模式选择）  0x00")
        mode_layout = QGridLayout(mode_box)
        self.mode_combo = ConfirmComboBox()
        self.mode_combo.addItems(["0 - TDM", "1 - 高速 PID", "2 - ADC 直通"])
        self.mode_combo.setMaximumWidth(150)
        self.mode1_row = ConfirmSpinBox()
        self.mode1_row.setRange(0, ROWS - 1)
        self.mode1_row.setFixedWidth(72)
        self.mode1_col = ConfirmSpinBox()
        self.mode1_col.setRange(0, COLS - 1)
        self.mode1_col.setFixedWidth(72)
        mode_layout.addWidget(QLabel("MODE:"), 0, 0)
        mode_layout.addWidget(self.mode_combo, 0, 1)
        mode_layout.addWidget(QLabel("Row:"), 1, 0)
        mode_layout.addWidget(self.mode1_row, 1, 1)
        mode_layout.addWidget(QLabel("Col:"), 1, 2)
        mode_layout.addWidget(self.mode1_col, 1, 3)
        self.mode_config_btn = QPushButton("配置")
        self.mode_config_btn.setObjectName("fpga_mode_config_button")
        mode_layout.addWidget(self.mode_config_btn, 2, 0, 1, 5, Qt.AlignRight)
        mode_layout.setColumnStretch(4, 1)
        parameter_layout.addWidget(mode_box, 0, 0)

        counter_box = QGroupBox("COUNTER_LIMIT（周期）  0x01")
        counter_layout = QGridLayout(counter_box)
        self.counter_limit = UIntLineEdit(2500, 24, "Counter limit", display_hex=False)
        counter_layout.addWidget(QLabel("Counter limit:"), 0, 0)
        counter_layout.addWidget(self.counter_limit, 0, 1)
        self.counter_limit_config_btn = QPushButton("配置")
        self.counter_limit_config_btn.setObjectName("fpga_counter_limit_config_button")
        counter_layout.addWidget(
            self.counter_limit_config_btn, 1, 0, 1, 3, Qt.AlignRight
        )
        counter_layout.setColumnStretch(2, 1)
        parameter_layout.addWidget(counter_box, 0, 1)

        amp_box = QGroupBox("AMP_FACTOR（PID 幅度）  0x02")
        amp_layout = QGridLayout(amp_box)
        self.amp_factor = UIntLineEdit(0xA, 32, "Amp factor")
        self.amp_factor.setToolTip("PID 输出右移因子")
        amp_layout.addWidget(QLabel("Amp factor:"), 0, 0)
        amp_layout.addWidget(self.amp_factor, 0, 1)
        self.amp_factor_config_btn = QPushButton("配置")
        self.amp_factor_config_btn.setObjectName("fpga_amp_factor_config_button")
        amp_layout.addWidget(self.amp_factor_config_btn, 1, 0, 1, 3, Qt.AlignRight)
        amp_layout.setColumnStretch(2, 1)
        parameter_layout.addWidget(amp_box, 1, 0)

        dac_row_box = QGroupBox("DAC_ROW_SELEC（行选通电压）  0x03")
        dac_row_layout = QGridLayout(dac_row_box)
        self.dac_row = UIntLineEdit(0xC070, 16, "DAC row")
        self.dac_row.setToolTip("行选通 DAC 输出电压（offset binary）")
        dac_row_layout.addWidget(QLabel("DAC row:"), 0, 0)
        dac_row_layout.addWidget(self.dac_row, 0, 1)
        self.dac_row_config_btn = QPushButton("配置")
        self.dac_row_config_btn.setObjectName("fpga_dac_row_config_button")
        dac_row_layout.addWidget(self.dac_row_config_btn, 1, 0, 1, 3, Qt.AlignRight)
        dac_row_layout.setColumnStretch(2, 1)
        parameter_layout.addWidget(dac_row_box, 1, 1)

        tx_col_box = QGroupBox("TX_COL_SEL（上传列选择）  0x08")
        tx_col_layout = QGridLayout(tx_col_box)
        self.tx_col = ConfirmSpinBox()
        self.tx_col.setRange(0, COLS - 1)
        self.tx_col.setFixedWidth(88)
        self.tx_col.setToolTip("上传 FB 数据的列（0～15）")
        tx_col_layout.addWidget(QLabel("TX column:"), 0, 0)
        tx_col_layout.addWidget(self.tx_col, 0, 1)
        self.tx_col_config_btn = QPushButton("配置")
        self.tx_col_config_btn.setObjectName("fpga_tx_col_config_button")
        tx_col_layout.addWidget(self.tx_col_config_btn, 1, 0, 1, 3, Qt.AlignRight)
        tx_col_layout.setColumnStretch(2, 1)
        parameter_layout.addWidget(tx_col_box, 2, 0)

        timing_box = QGroupBox("TIMING（时序参数）  0x0A")
        timing_layout = QGridLayout(timing_box)
        self.delay_factor = UIntLineEdit(0xFF, 8, "Delay factor")
        self.settle_begin = UIntLineEdit(0x1A, 8, "Settle begin")
        self.settle_end = UIntLineEdit(0x1A, 8, "Settle end")
        self.delay_factor.setToolTip("行选通 settle 延时因子")
        self.settle_begin.setToolTip("PID 积分开始 settle 因子")
        self.settle_end.setToolTip("PID 积分结束 settle 因子")
        timing_layout.addWidget(QLabel("Delay:"), 0, 0)
        timing_layout.addWidget(self.delay_factor, 0, 1)
        timing_layout.setColumnMinimumWidth(2, 12)
        timing_layout.addWidget(QLabel("Settle begin:"), 0, 3)
        timing_layout.addWidget(self.settle_begin, 0, 4)
        timing_layout.addWidget(QLabel("Settle end:"), 1, 3)
        timing_layout.addWidget(self.settle_end, 1, 4)
        self.timing_config_btn = QPushButton("配置")
        self.timing_config_btn.setObjectName("fpga_timing_config_button")
        timing_layout.addWidget(self.timing_config_btn, 2, 0, 1, 6, Qt.AlignRight)
        timing_layout.setColumnStretch(5, 1)
        parameter_layout.addWidget(timing_box, 2, 1)

        # 0x0B 的监控/变更卡片已从页面取消。保留这些隐藏对象仅用于
        # 兼容既有配置 schema 与程序接口，不再占用全局参数页空间。
        self.monitor_col = ConfirmSpinBox(self)
        self.monitor_col.setRange(0, COLS - 1)
        self.dirty_label = QLabel("待写寄存器：0", self)
        self.mark_all_global_btn = QPushButton("标记全部", self)
        self.write_global_btn = QPushButton("写入变更项", self)
        for legacy_control in (
            self.monitor_col,
            self.dirty_label,
            self.mark_all_global_btn,
            self.write_global_btn,
        ):
            legacy_control.hide()

        global_layout.addLayout(parameter_layout)
        global_layout.addStretch()
        self.fpga_sub_tabs.addTab(global_page, "   全局参数   ")

        cell_page = QWidget()
        cell_page.setObjectName("fpga_cell_parameter_page")
        cell_layout = QVBoxLayout(cell_page)
        cell_layout.setContentsMargins(8, 8, 8, 8)
        cell_layout.setSpacing(8)
        toolbar = QGridLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setHorizontalSpacing(8)

        selector_group = QWidget()
        selector_group.setObjectName("fpga_cell_selector_group")
        selector_layout = QHBoxLayout(selector_group)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(6)

        selector_layout.addWidget(QLabel("行:"))
        self.cell_row_selector = QComboBox()
        self.cell_row_selector.setObjectName("fpga_cell_row_selector")
        self.cell_row_selector.addItem("", SELECTOR_EMPTY)
        self.cell_row_selector.addItem("All", SELECTOR_ALL)
        for row in range(ROWS):
            self.cell_row_selector.addItem(str(row + 1), row)
        self.cell_row_selector.setFixedWidth(64)
        self.cell_row_selector.setMaxVisibleItems(ROWS + 2)
        self.cell_row_selector.setToolTip("空=未指定；All=全部行")
        selector_layout.addWidget(self.cell_row_selector)

        selector_layout.addWidget(QLabel("列:"))
        self.cell_col_selector = QComboBox()
        self.cell_col_selector.setObjectName("fpga_cell_col_selector")
        self.cell_col_selector.addItem("", SELECTOR_EMPTY)
        self.cell_col_selector.addItem("All", SELECTOR_ALL)
        for col in range(COLS):
            self.cell_col_selector.addItem(str(col + 1), col)
        self.cell_col_selector.setFixedWidth(64)
        self.cell_col_selector.setMaxVisibleItems(COLS + 2)
        self.cell_col_selector.setToolTip("空=未指定；All=全部列")
        selector_layout.addWidget(self.cell_col_selector)
        selector_layout.addSpacing(8)
        self.selected_count_label = QLabel("预选：0")
        self.selected_count_label.setObjectName("fpga_cell_preselection_count")
        selector_layout.addWidget(self.selected_count_label)
        selector_layout.addStretch()

        parameter_group = QWidget()
        parameter_group.setObjectName("fpga_cell_parameter_group")
        parameter_layout = QHBoxLayout(parameter_group)
        parameter_layout.setContentsMargins(0, 0, 0, 0)
        parameter_layout.setSpacing(6)

        parameter_layout.addWidget(QLabel("Kp:"))
        self.default_kp = UIntLineEdit(0, 32, "默认 Kp")
        self.default_kp.setToolTip("比例增益（固定点）")
        parameter_layout.addWidget(self.default_kp)
        parameter_layout.addWidget(QLabel("Ki:"))
        self.default_ki = UIntLineEdit(0, 32, "默认 Ki")
        self.default_ki.setToolTip("积分增益（固定点）")
        parameter_layout.addWidget(self.default_ki)
        parameter_layout.addWidget(QLabel("ADC offset:"))
        self.default_adc_offset = UIntLineEdit(0, 16, "默认 ADC offset")
        self.default_adc_offset.setToolTip("ADC 偏移，施加到 ADC_data + offset")
        parameter_layout.addWidget(self.default_adc_offset)
        parameter_layout.addWidget(QLabel("DAC offset:"))
        self.default_dac_offset = UIntLineEdit(0, 16, "默认 DAC offset")
        self.default_dac_offset.setToolTip("DAC 偏移，加到 PID 输出")
        parameter_layout.addWidget(self.default_dac_offset)

        toolbar_actions = QWidget()
        toolbar_actions.setObjectName("fpga_cell_toolbar_actions")
        toolbar_action_layout = QHBoxLayout(toolbar_actions)
        toolbar_action_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_action_layout.setSpacing(8)
        self.edit_all_cells_btn = QPushButton("编辑通道参数")
        self.edit_all_cells_btn.setMinimumHeight(30)
        self.save_cell_parameters_btn = QPushButton("保存参数")
        self.save_cell_parameters_btn.setObjectName("fpga_save_cell_parameters")
        self.save_cell_parameters_btn.setMinimumHeight(30)
        toolbar_action_layout.addWidget(self.edit_all_cells_btn)
        toolbar_action_layout.addWidget(self.save_cell_parameters_btn)

        toolbar.addWidget(selector_group, 0, 0, Qt.AlignLeft)
        toolbar.addWidget(parameter_group, 0, 1, Qt.AlignCenter)
        toolbar.addWidget(toolbar_actions, 0, 2, Qt.AlignRight)
        toolbar.setColumnMinimumWidth(0, 245)
        toolbar.setColumnMinimumWidth(2, 245)
        toolbar.setColumnStretch(0, 1)
        toolbar.setColumnStretch(2, 1)
        cell_layout.addLayout(toolbar)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(8)
        self.cell_write_status_label = QLabel(
            "写入状态：空闲    进度：0/0    当前：[-,-]"
        )
        self.cell_write_status_label.setObjectName("fpga_cell_write_status")
        self.cell_write_status_label.setStyleSheet("color: #546E7A;")
        self.write_cells_btn = QPushButton("写入预选")
        self.write_cells_btn.setMinimumHeight(32)
        self.write_all_cells_btn = QPushButton("全部写入")
        self.write_all_cells_btn.setMinimumHeight(32)
        action_layout.addWidget(self.cell_write_status_label)
        action_layout.addStretch()
        action_layout.addWidget(self.write_cells_btn)
        action_layout.addWidget(self.write_all_cells_btn)

        self.cell_table = CellTableWidget(ROWS, COLS)
        self.select_all_btn = self.cell_table.select_all_button
        self.cell_table.setHorizontalHeaderLabels([f"Col {col + 1}" for col in range(COLS)])
        self.cell_table.setVerticalHeaderLabels([f"Row {row + 1}" for row in range(ROWS)])
        self.cell_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.cell_table.setFocusPolicy(Qt.NoFocus)
        self.cell_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cell_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.cell_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cell_table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.cell_table.verticalHeader().setDefaultSectionSize(24)
        self.cell_table.horizontalHeader().setMinimumSectionSize(40)
        self.cell_table.verticalHeader().setMinimumSectionSize(24)
        self.cell_table.setMinimumHeight(105)

        for row in range(ROWS):
            for col in range(COLS):
                button = CellStatusButton(row, col)
                button.set_parameter_visibility(self.show_cell_parameter_values)
                button.toggled.connect(self._update_selected_count)
                button.clicked.connect(self._sync_selectors_from_selection)
                self._install_cell_edit_context_menu(button)
                self.cell_buttons[(row, col)] = button
                self.cell_table.setCellWidget(row, col, button)

        self._install_parameter_visibility_context_menu(self.select_all_btn)

        self.cell_table.horizontalHeader().sectionClicked.connect(self._toggle_column_selection)
        self.cell_table.verticalHeader().sectionClicked.connect(self._toggle_row_selection)
        cell_layout.addWidget(self.cell_table, stretch=1)
        cell_layout.addLayout(action_layout)
        self.fpga_sub_tabs.addTab(cell_page, "   Cell 参数   ")
        root.addWidget(self.fpga_sub_tabs, stretch=1)

        self.mode_combo.index_committed.connect(lambda: self._mark_dirty(0x00))
        self.mode_combo.currentIndexChanged.connect(self._update_mode_controls)
        self.mode1_row.value_committed.connect(lambda: self._mark_dirty(0x00))
        self.mode1_col.value_committed.connect(lambda: self._mark_dirty(0x00))
        self.counter_limit.value_committed.connect(lambda: self._mark_dirty(0x01))
        self.amp_factor.value_committed.connect(lambda: self._mark_dirty(0x02))
        self.dac_row.value_committed.connect(lambda: self._mark_dirty(0x03))
        self.tx_col.value_committed.connect(lambda: self._mark_dirty(0x08))
        self.delay_factor.value_committed.connect(lambda: self._mark_dirty(0x0A))
        self.settle_begin.value_committed.connect(lambda: self._mark_dirty(0x0A))
        self.settle_end.value_committed.connect(lambda: self._mark_dirty(0x0A))
        self.dfb_switch.toggled.connect(lambda: self._mark_dirty(0x0B))
        self.monitor_col.value_committed.connect(lambda: self._mark_dirty(0x0B))
        for editor in (
            self.default_kp,
            self.default_ki,
            self.default_adc_offset,
            self.default_dac_offset,
        ):
            editor.value_committed.connect(self._apply_cell_defaults)
        self.dfb_switch.toggled.connect(self._update_dfb_indicator)
        self.dfb_switch.toggled.connect(self.dfb_state_changed)
        self.dfb_switch.toggled.connect(self._request_dfb_write)
        self.cell_row_selector.currentIndexChanged.connect(
            self._sync_selection_from_selectors
        )
        self.cell_col_selector.currentIndexChanged.connect(
            self._sync_selection_from_selectors
        )

        self.mark_all_global_btn.clicked.connect(self._mark_all_global)
        self.write_global_btn.clicked.connect(self._request_global_write)
        self.mode_config_btn.clicked.connect(self._request_mode_write)
        self.counter_limit_config_btn.clicked.connect(
            self._request_counter_limit_write
        )
        self.amp_factor_config_btn.clicked.connect(self._request_amp_factor_write)
        self.dac_row_config_btn.clicked.connect(self._request_dac_row_write)
        self.tx_col_config_btn.clicked.connect(self._request_tx_col_write)
        self.timing_config_btn.clicked.connect(self._request_timing_write)
        self.edit_all_cells_btn.clicked.connect(
            lambda _checked=False: self._open_cell_editor(selected_only=True)
        )
        self.save_cell_parameters_btn.clicked.connect(self._save_selected_cell_parameters)
        self.select_all_btn.clicked.connect(self._toggle_all_cell_selection)
        self.write_cells_btn.clicked.connect(self._request_cell_write)
        self.write_all_cells_btn.clicked.connect(self._request_all_cells_write)
        self._update_mode_controls()

    def _update_mode_controls(self):
        enabled = self.mode_combo.currentIndex() == 1
        self.mode1_row.setEnabled(enabled)
        self.mode1_col.setEnabled(enabled)
        self._update_counter_limit_tooltip()

    def _update_counter_limit_tooltip(self):
        mode = self.mode_combo.currentIndex()

        def mode_tip(mode_index, text):
            if mode == mode_index:
                return f'<span style="color:#D32F2F; font-weight:600;">{text}</span>'
            return text

        self.counter_limit.setToolTip(
            f"{mode_tip(0, 'Mode0：行周期')}<br>"
            f"{mode_tip(1, 'Mode1：方波周期')}<br>"
            "125MHz 时钟数"
        )

    def _raise_dfb_corner(self, _index=None):
        """Keep the shared DFB control above either stacked parameter page."""
        QTimer.singleShot(0, self._apply_dfb_corner_raise)

    def _apply_dfb_corner_raise(self):
        self.dfb_corner_widget.raise_()
        self.dfb_corner_widget.repaint()

    def _mark_dirty(self, address):
        if self._loading:
            return
        self.dirty_registers.add(address)
        self._refresh_dirty_ui()

    def _mark_all_global(self):
        self.dirty_registers.update(GLOBAL_REGISTER_ADDRS)
        self._refresh_dirty_ui()

    def _refresh_dirty_ui(self):
        ordered = sorted(self.dirty_registers)
        address_text = ", ".join(f"0x{addr:02X}" for addr in ordered)
        self.dirty_label.setText(f"待写寄存器：{len(ordered)}")
        self.dirty_label.setToolTip(address_text or "没有待写寄存器")
        self.write_global_btn.setText(f"写入变更项 ({len(ordered)})")

    def _update_dfb_indicator(self, enabled):
        if enabled:
            self.dfb_state_label.setText("开启")
            self.dfb_state_label.setStyleSheet("color:#007AFF; font-weight:bold;")
            self.dfb_switch.setToolTip("DFB 已开启，点击关闭")
        else:
            self.dfb_state_label.setText("关闭")
            self.dfb_state_label.setStyleSheet("color:#616161; font-weight:bold;")
            self.dfb_switch.setToolTip("DFB 已关闭，点击开启")

    def _cell_for(self, row, col):
        return self.cells[row * COLS + col]

    @staticmethod
    def _has_cell_parameters(cell):
        return any(cell[key] != 0 for key in CELL_PARAMETER_KEYS)

    def _refresh_all_cells(self):
        for cell in self.cells:
            write_mismatch = bool(cell["written"]) and any(
                cell[key] != self.cell_defaults[key] for key in CELL_PARAMETER_KEYS
            )
            self.cell_buttons[(cell["row"], cell["col"])].set_status(
                self._has_cell_parameters(cell),
                cell["written"],
                cell,
                write_mismatch=write_mismatch,
            )
        self._update_selected_count()

    def _update_selected_count(self):
        count = sum(button.isChecked() for button in self.cell_buttons.values())
        self.selected_count_label.setText(f"预选：{count}")

    def _install_parameter_visibility_context_menu(self, surface):
        surface.setContextMenuPolicy(Qt.CustomContextMenu)
        surface.customContextMenuRequested.connect(
            lambda position, source=surface: self._show_cell_parameter_context_menu(
                source.mapToGlobal(position)
            )
        )

    def _show_cell_parameter_context_menu(self, global_position):
        menu = QMenu(self.cell_table)
        show_action = menu.addAction("显示表格内参数")
        hide_action = menu.addAction("不显示表格内参数")
        show_action.setCheckable(True)
        hide_action.setCheckable(True)
        show_action.setChecked(self.show_cell_parameter_values)
        hide_action.setChecked(not self.show_cell_parameter_values)
        selected_action = menu.exec_(global_position)
        if selected_action is show_action:
            self._set_cell_parameter_visibility(True)
        elif selected_action is hide_action:
            self._set_cell_parameter_visibility(False)

    def _install_cell_edit_context_menu(self, button):
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(
            lambda position, cell_button=button: self._show_cell_edit_context_menu(
                cell_button, cell_button.mapToGlobal(position)
            )
        )

    def _show_cell_edit_context_menu(self, button, global_position):
        if not button.isChecked():
            return
        menu = QMenu(button)
        edit_action = menu.addAction("编辑参数")
        if menu.exec_(global_position) is edit_action:
            self._open_cell_editor(selected_only=True)

    def _set_cell_parameter_visibility(self, visible):
        self.show_cell_parameter_values = bool(visible)
        for button in self.cell_buttons.values():
            button.set_parameter_visibility(self.show_cell_parameter_values)

    def _toggle_row_selection(self, row):
        row_is_selected = all(
            self.cell_buttons[(row, col)].isChecked() for col in range(COLS)
        )
        for col in range(COLS):
            self.cell_buttons[(row, col)].set_selected(not row_is_selected)
        self._sync_selectors_from_selection()

    def _toggle_column_selection(self, col):
        col_is_selected = all(
            self.cell_buttons[(row, col)].isChecked() for row in range(ROWS)
        )
        for row in range(ROWS):
            self.cell_buttons[(row, col)].set_selected(not col_is_selected)
        self._sync_selectors_from_selection()

    @staticmethod
    def _cell_selector_index(value):
        if value == SELECTOR_EMPTY:
            return 0
        if value == SELECTOR_ALL:
            return 1
        return value + 2

    def _set_cell_selectors(self, row, col):
        self._display_cell_selectors(row, col)
        self._sync_selection_from_selectors()

    def _display_cell_selectors(self, row, col):
        for selector, value in (
            (self.cell_row_selector, row),
            (self.cell_col_selector, col),
        ):
            was_blocked = selector.blockSignals(True)
            selector.setCurrentIndex(self._cell_selector_index(value))
            selector.blockSignals(was_blocked)

    def _reset_cell_selectors(self, _checked=None):
        self._display_cell_selectors(SELECTOR_EMPTY, SELECTOR_EMPTY)

    def _sync_selectors_from_selection(self, _checked=None):
        selected = self._selected_keys()
        if not selected:
            selector_values = (SELECTOR_EMPTY, SELECTOR_EMPTY)
        elif len(selected) == ROWS * COLS:
            selector_values = (SELECTOR_ALL, SELECTOR_ALL)
        elif len(selected) == 1:
            selector_values = next(iter(selected))
        else:
            selected_rows = {row for row, _col in selected}
            selected_cols = {col for _row, col in selected}
            if len(selected_rows) == 1 and len(selected) == COLS:
                selector_values = (next(iter(selected_rows)), SELECTOR_ALL)
            elif len(selected_cols) == 1 and len(selected) == ROWS:
                selector_values = (SELECTOR_ALL, next(iter(selected_cols)))
            else:
                selector_values = (SELECTOR_EMPTY, SELECTOR_EMPTY)
        self._display_cell_selectors(*selector_values)

    def _sync_selection_from_selectors(self, _index=None):
        selected_row = self.cell_row_selector.currentData()
        selected_col = self.cell_col_selector.currentData()
        for (row, col), button in self.cell_buttons.items():
            if (selected_row, selected_col) in (
                (SELECTOR_EMPTY, SELECTOR_EMPTY),
                (SELECTOR_ALL, SELECTOR_EMPTY),
                (SELECTOR_EMPTY, SELECTOR_ALL),
            ):
                selected = False
            elif selected_row == SELECTOR_ALL and selected_col == SELECTOR_ALL:
                selected = True
            elif selected_row == SELECTOR_ALL:
                selected = col == selected_col
            elif selected_col == SELECTOR_ALL:
                selected = row == selected_row
            elif selected_row == SELECTOR_EMPTY:
                selected = col == selected_col
            elif selected_col == SELECTOR_EMPTY:
                selected = row == selected_row
            else:
                selected = row == selected_row and col == selected_col
            button.set_selected(selected)

    def _select_all_cells(self, _checked=None):
        self._set_cell_selectors(SELECTOR_ALL, SELECTOR_ALL)

    def _toggle_all_cell_selection(self, _checked=None):
        all_selected = all(
            button.isChecked() for button in self.cell_buttons.values()
        )
        if all_selected:
            self._clear_cell_selection()
        else:
            self._select_all_cells()

    def _clear_cell_selection(self, _checked=None):
        self._set_cell_selectors(SELECTOR_EMPTY, SELECTOR_EMPTY)

    def _set_all_selected(self, selected):
        for button in self.cell_buttons.values():
            button.set_selected(selected)

    def _selected_keys(self):
        return {key for key, button in self.cell_buttons.items() if button.isChecked()}

    def _save_selected_cell_parameters(self):
        selected = self._selected_keys()
        if not selected:
            QMessageBox.warning(self, "未预选 Cell", "请先预选需要保存参数的 Cell。")
            return
        try:
            parameters = {
                "kp": self.default_kp.value(),
                "ki": self.default_ki.value(),
                "adc_offset": self.default_adc_offset.value(),
                "dac_offset": self.default_dac_offset.value(),
            }
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return
        self.cell_defaults = dict(parameters)
        for row, col in selected:
            cell = self._cell_for(row, col)
            for key, value in parameters.items():
                cell[key] = value
            cell["written"] = False
        self._refresh_all_cells()
        self.log_signal.emit(
            f"[FPGA UI] 已保存 {len(selected)} 个 Cell 的本地参数，尚未下发。"
        )

    def _apply_cell_defaults(self, _value=None):
        self.cell_defaults = {
            "kp": self.default_kp.value(),
            "ki": self.default_ki.value(),
            "adc_offset": self.default_adc_offset.value(),
            "dac_offset": self.default_dac_offset.value(),
        }
        self._refresh_all_cells()

    def _open_cell_editor(self, selected_only=False):
        selected = self._selected_keys()
        dialog = CellParameterDialog(self.cells, selected, self)
        if selected_only:
            dialog.selected_only.setChecked(True)
        if dialog.exec_() != QDialog.Accepted:
            return
        self.cells = dialog.result_cells
        self._refresh_all_cells()
        self.log_signal.emit("[FPGA UI] 已更新全部 Cell 的本地参数，尚未下发。")

    def _request_mode_write(self):
        mode = self.mode_combo.currentIndex()
        mode1_row = self.mode1_row.value() if mode == 1 else 0
        mode1_col = self.mode1_col.value() if mode == 1 else 0
        self.mode_write_requested.emit(mode, mode1_row, mode1_col)

    def _request_counter_limit_write(self):
        self.counter_limit_write_requested.emit(self.counter_limit.value())

    def _request_amp_factor_write(self):
        self.amp_factor_write_requested.emit(self.amp_factor.value())

    def _request_dac_row_write(self):
        self.dac_row_write_requested.emit(self.dac_row.value())

    def _request_tx_col_write(self):
        self.tx_col_write_requested.emit(self.tx_col.value())

    def _request_timing_write(self):
        self.timing_write_requested.emit(
            self.delay_factor.value(),
            self.settle_begin.value(),
            self.settle_end.value(),
        )

    def _request_dfb_write(self, enabled):
        if not self._loading:
            self.dfb_write_requested.emit(bool(enabled))

    def restore_dfb_state(self, enabled):
        was_loading = self._loading
        self._loading = True
        try:
            self.dfb_switch.setChecked(bool(enabled))
        finally:
            self._loading = was_loading
        self.dirty_registers.discard(0x0B)
        self._refresh_dirty_ui()

    def mark_register_written(self, address):
        self.dirty_registers.discard(address)
        self._refresh_dirty_ui()

    def _request_global_write(self):
        if not self.dirty_registers:
            QMessageBox.information(self, "提示", "当前没有待写入的全局参数变更。")
            return
        try:
            config = self.get_global_config()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return
        self.global_write_requested.emit(config, set(self.dirty_registers))
        self.log_signal.emit(
            f"[FPGA UI] 请求写入 {len(self.dirty_registers)} 个全局寄存器；当前仅完成 UI，未发送数据。"
        )

    def _request_cell_write(self):
        if self.dfb_switch.isChecked():
            QMessageBox.warning(self, "DFB 已开启", "写入Cell参数前请关闭DFB")
            self.log_signal.emit("[FPGA UI] 写入Cell参数前请关闭DFB")
            return
        selected = self._selected_keys()
        if not selected:
            QMessageBox.warning(self, "未预选通道", "请先预选需要写入的 Cell。")
            return
        selected_cells = [
            self._cell_write_payload(self._cell_for(row, col))
            for row, col in sorted(selected)
        ]
        self._begin_cell_write_status(selected_cells)
        self.cell_write_requested.emit(selected_cells)

    def _request_all_cells_write(self):
        if self.dfb_switch.isChecked():
            QMessageBox.warning(self, "DFB 已开启", "写入Cell参数前请关闭DFB")
            self.log_signal.emit("[FPGA UI] 写入Cell参数前请关闭DFB")
            return
        try:
            default_parameters = {
                "kp": self.default_kp.value(),
                "ki": self.default_ki.value(),
                "adc_offset": self.default_adc_offset.value(),
                "dac_offset": self.default_dac_offset.value(),
            }
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            return
        all_cells = [self._cell_write_payload(cell) for cell in self.cells]
        self._begin_cell_write_status(all_cells)
        self.all_cells_write_requested.emit(all_cells, default_parameters)

    def _set_cell_write_status(self, state, completed, total, current=None):
        if current is None:
            current_text = "[-,-]"
        else:
            current_text = f"[{current['row'] + 1},{current['col'] + 1}]"
        self.cell_write_status_label.setText(
            f"写入状态：{state}    进度：{completed}/{total}    "
            f"当前：{current_text}"
        )

    def _begin_cell_write_status(self, cells):
        total = len(cells)
        current = cells[0] if cells else None
        self._set_cell_write_status("写入中", 0, total, current)

    def finish_cell_write(self, cells, success):
        total = len(cells)
        if success:
            current = cells[-1] if cells else None
            self._set_cell_write_status("完成", total, total, current)
        else:
            current = cells[0] if cells else None
            self._set_cell_write_status("失败", 0, total, current)

    def mark_cells_written(self, written_cells):
        parameter_keys = ("kp", "ki", "adc_offset", "dac_offset")
        for written_cell in written_cells:
            cell = self._cell_for(written_cell["row"], written_cell["col"])
            if all(cell[key] == written_cell[key] for key in parameter_keys):
                cell["written"] = True
        self._refresh_all_cells()

    @staticmethod
    def _cell_write_payload(cell):
        return {
            key: deepcopy(cell[key])
            for key in ("row", "col", "kp", "ki", "adc_offset", "dac_offset")
        }

    def get_global_config(self):
        return {
            "mode": self.mode_combo.currentIndex(),
            "mode1_row": self.mode1_row.value(),
            "mode1_col": self.mode1_col.value(),
            "counter_limit": self.counter_limit.value(),
            "amp_factor": self.amp_factor.value(),
            "dac_row": self.dac_row.value(),
            "tx_col": self.tx_col.value(),
            "delay_factor": self.delay_factor.value(),
            "settle_begin": self.settle_begin.value(),
            "settle_end": self.settle_end.value(),
            "dfb_enabled": self.dfb_switch.isChecked(),
            "monitor_col": self.monitor_col.value(),
        }

    def get_config(self):
        return {
            "type": "fpga",
            "schema_version": 2,
            "global": self.get_global_config(),
            "cell_defaults": dict(self.cell_defaults),
            "cells": {
                f"{cell['row']}_{cell['col']}": {
                    "kp": cell["kp"],
                    "ki": cell["ki"],
                    "adc_offset": cell["adc_offset"],
                    "dac_offset": cell["dac_offset"],
                    "written": cell["written"],
                }
                for cell in self.cells
            },
        }

    def set_config(self, data):
        if data.get("type") != "fpga" or data.get("schema_version") != 2:
            return False, "FPGA 参数格式不兼容，需要 schema_version 2"
        try:
            global_cfg = data["global"]
            defaults = data["cell_defaults"]
            cell_cfg = data["cells"]
            parsed_global = {
                "mode": parse_uint(global_cfg["mode"], 2, "Mode"),
                "mode1_row": parse_uint(global_cfg["mode1_row"], 5, "Mode1 row"),
                "mode1_col": parse_uint(global_cfg["mode1_col"], 4, "Mode1 col"),
                "counter_limit": parse_uint(global_cfg["counter_limit"], 24, "Counter limit"),
                "amp_factor": parse_uint(global_cfg["amp_factor"], 32, "Amp factor"),
                "dac_row": parse_uint(global_cfg["dac_row"], 16, "DAC row"),
                "tx_col": parse_uint(global_cfg["tx_col"], 4, "TX column"),
                "delay_factor": parse_uint(global_cfg["delay_factor"], 8, "Delay factor"),
                "settle_begin": parse_uint(global_cfg["settle_begin"], 8, "Settle begin"),
                "settle_end": parse_uint(global_cfg["settle_end"], 8, "Settle end"),
                "dfb_enabled": bool(global_cfg["dfb_enabled"]),
                "monitor_col": parse_uint(global_cfg["monitor_col"], 4, "Monitor column"),
            }
            if parsed_global["mode"] > 2 or parsed_global["mode1_row"] >= ROWS:
                raise ValueError("Mode 或 Mode1 row 超出界面支持范围")
            if parsed_global["mode1_col"] >= COLS or parsed_global["tx_col"] >= COLS:
                raise ValueError("Mode1 col 或 TX column 超出界面支持范围")
            if parsed_global["monitor_col"] >= COLS:
                raise ValueError("Monitor column 超出界面支持范围")

            parsed_defaults = {
                "kp": parse_uint(defaults["kp"], 32, "默认 Kp"),
                "ki": parse_uint(defaults["ki"], 32, "默认 Ki"),
                "adc_offset": parse_uint(defaults["adc_offset"], 16, "默认 ADC offset"),
                "dac_offset": parse_uint(defaults["dac_offset"], 16, "默认 DAC offset"),
            }
            parsed_cells = []
            for row in range(ROWS):
                for col in range(COLS):
                    cfg = cell_cfg[f"{row}_{col}"]
                    parsed_cells.append(
                        {
                            "row": row,
                            "col": col,
                            "kp": parse_uint(
                                cfg["kp"], 32, f"Cell {row + 1}/{col + 1} Kp"
                            ),
                            "ki": parse_uint(
                                cfg["ki"], 32, f"Cell {row + 1}/{col + 1} Ki"
                            ),
                            "adc_offset": parse_uint(
                                cfg["adc_offset"],
                                16,
                                f"Cell {row + 1}/{col + 1} ADC offset",
                            ),
                            "dac_offset": parse_uint(
                                cfg["dac_offset"],
                                16,
                                f"Cell {row + 1}/{col + 1} DAC offset",
                            ),
                            "written": bool(cfg["written"]),
                        }
                    )
        except (KeyError, TypeError, ValueError) as exc:
            return False, f"FPGA 参数内容无效：{exc}"

        self._loading = True
        self.mode_combo.setCurrentIndex(parsed_global["mode"])
        self.mode1_row.setValue(parsed_global["mode1_row"])
        self.mode1_col.setValue(parsed_global["mode1_col"])
        self.counter_limit.set_value(parsed_global["counter_limit"])
        self.amp_factor.set_value(parsed_global["amp_factor"])
        self.dac_row.set_value(parsed_global["dac_row"])
        self.tx_col.setValue(parsed_global["tx_col"])
        self.delay_factor.set_value(parsed_global["delay_factor"])
        self.settle_begin.set_value(parsed_global["settle_begin"])
        self.settle_end.set_value(parsed_global["settle_end"])
        self.dfb_switch.setChecked(parsed_global["dfb_enabled"])
        self.monitor_col.setValue(parsed_global["monitor_col"])
        self.cell_defaults = parsed_defaults
        self.default_kp.set_value(parsed_defaults["kp"])
        self.default_ki.set_value(parsed_defaults["ki"])
        self.default_adc_offset.set_value(parsed_defaults["adc_offset"])
        self.default_dac_offset.set_value(parsed_defaults["dac_offset"])
        self.cells = parsed_cells
        self._loading = False
        self.dirty_registers.clear()
        self._clear_cell_selection()
        self._update_mode_controls()
        self._refresh_dirty_ui()
        self._refresh_all_cells()
        self._update_dfb_indicator(self.dfb_switch.isChecked())
        self.dfb_state_changed.emit(self.dfb_switch.isChecked())
        return True, "读取成功"
