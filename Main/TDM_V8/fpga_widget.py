"""FPGA configuration UI for TDM V8.

This module intentionally contains no FPGA protocol encoding and no TCP calls.
It owns only the editable configuration model and the related Qt widgets.
"""

from copy import deepcopy

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


ROWS = 20
COLS = 16
GLOBAL_REGISTER_ADDRS = {0x00, 0x01, 0x02, 0x03, 0x08, 0x0A, 0x0B}


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
    """Unsigned integer editor that restores the last valid value on bad input."""

    value_committed = pyqtSignal(int)

    def __init__(self, value, bits, label, display_hex=True, parent=None):
        super().__init__(parent)
        self.bits = bits
        self.label = label
        self.display_hex = display_hex
        self._last_value = int(value)
        self.setMaximumWidth(88)
        self.setAlignment(Qt.AlignCenter)
        self.set_value(value)
        self.editingFinished.connect(self._commit)

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
        try:
            value = self.value()
        except ValueError as exc:
            QMessageBox.warning(self, "参数错误", str(exc))
            self.set_value(self._last_value)
            return
        self.set_value(value)
        self.value_committed.emit(value)


class CellStatusButton(QToolButton):
    """Compact matrix cell: background is channel status, check is write selection."""

    def __init__(self, row, col, parent=None):
        super().__init__(parent)
        self.row = row
        self.col = col
        self.enabled = False
        self.custom = False
        self.setCheckable(True)
        self.setMinimumSize(26, 20)
        self.setMaximumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setToolTip(f"Row {row + 1}, Col {col + 1}")
        self.toggled.connect(self.refresh_style)
        self.refresh_style()

    def set_status(self, enabled, custom):
        self.enabled = bool(enabled)
        self.custom = bool(custom)
        self.refresh_style()

    def set_selected(self, selected):
        self.setChecked(bool(selected))

    def refresh_style(self):
        if not self.enabled:
            background = "#E0E0E0"
        elif self.custom:
            background = "#BBDEFB"
        else:
            background = "#C8E6C9"
        border = "2px solid #D32F2F" if self.isChecked() else "1px solid #9E9E9E"
        self.setText("✓" if self.isChecked() else "")
        self.setStyleSheet(
            "QToolButton {"
            f"background-color: {background}; border: {border}; border-radius: 3px;"
            "font-weight: bold; color: #B71C1C; padding: 0px;"
            "} QToolButton:hover { border-color: #1976D2; }"
        )


class CellParameterDialog(QDialog):
    """Atomic editor for all 20x16 per-cell parameter sets."""

    def __init__(self, cells, selected_keys, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全部 Cell 独立参数")
        self.resize(930, 680)
        self._source_cells = deepcopy(cells)
        self._selected_keys = set(selected_keys)
        self.result_cells = None

        root = QVBoxLayout(self)
        help_label = QLabel(
            "可编辑全部 320 个通道；参数只保存到本地界面，点击“写入勾选通道”时才进入后续下发流程。"
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

        self.selected_only = QCheckBox("只看矩阵中已勾选的通道")
        filter_layout.addWidget(self.selected_only)
        filter_layout.addStretch()
        root.addLayout(filter_layout)

        self.table = QTableWidget(ROWS * COLS, 7)
        self.table.setHorizontalHeaderLabels(
            ["Row", "Col", "启用", "Kp", "Ki", "ADC offset", "DAC offset"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        for table_row, cell in enumerate(self._source_cells):
            row = cell["row"]
            col = cell["col"]
            row_item = QTableWidgetItem(str(row + 1))
            col_item = QTableWidgetItem(str(col + 1))
            row_item.setFlags(row_item.flags() & ~Qt.ItemIsEditable)
            col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)
            enabled_item = QTableWidgetItem()
            enabled_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            enabled_item.setCheckState(Qt.Checked if cell["enabled"] else Qt.Unchecked)

            value_items = [
                QTableWidgetItem(f"0x{cell['kp']:X}"),
                QTableWidgetItem(f"0x{cell['ki']:X}"),
                QTableWidgetItem(f"0x{cell['adc_offset']:X}"),
                QTableWidgetItem(f"0x{cell['dac_offset']:X}"),
            ]
            items = [row_item, col_item, enabled_item] + value_items
            for column, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                if (row, col) in self._selected_keys:
                    item.setBackground(QColor("#FFEBEE"))
                self.table.setItem(table_row, column, item)

        root.addWidget(self.table, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存本地参数")
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
            (3, "Kp", 32, "kp"),
            (4, "Ki", 32, "ki"),
            (5, "ADC offset", 16, "adc_offset"),
            (6, "DAC offset", 16, "dac_offset"),
        ]
        for table_row, old_cell in enumerate(self._source_cells):
            new_cell = {
                "row": old_cell["row"],
                "col": old_cell["col"],
                "enabled": self.table.item(table_row, 2).checkState() == Qt.Checked,
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
            parsed_cells.append(new_cell)
        self.result_cells = parsed_cells
        self.accept()


class FPGAControlWidget(QWidget):
    """Complete V8 FPGA configuration page (UI and local state only)."""

    log_signal = pyqtSignal(str)
    dfb_state_changed = pyqtSignal(bool)
    global_write_requested = pyqtSignal(dict, object)
    cell_write_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = True
        self.dirty_registers = set()
        self.cell_defaults = {"kp": 0, "ki": 0, "adc_offset": 0, "dac_offset": 0}
        self.cells = [
            {
                "row": row,
                "col": col,
                "enabled": False,
                "kp": 0,
                "ki": 0,
                "adc_offset": 0,
                "dac_offset": 0,
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
        self._update_dfb_badge(self.dfb_switch.isChecked())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        global_group = QGroupBox("全局参数")
        global_layout = QVBoxLayout(global_group)
        parameter_grid = QGridLayout()
        parameter_grid.setHorizontalSpacing(14)
        parameter_grid.setVerticalSpacing(8)

        basic_box = QGroupBox("模式与基础参数  0x00 / 0x01 / 0x02")
        basic_layout = QGridLayout(basic_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["0 - TDM", "1 - 高速 PID", "2 - ADC 直通"])
        self.mode_combo.setMaximumWidth(150)
        self.mode1_row = QSpinBox()
        self.mode1_row.setRange(0, ROWS - 1)
        self.mode1_col = QSpinBox()
        self.mode1_col.setRange(0, COLS - 1)
        self.counter_limit = UIntLineEdit(2500, 24, "Counter limit", display_hex=False)
        self.amp_factor = UIntLineEdit(0xA, 32, "Amp factor")
        basic_layout.addWidget(QLabel("Mode:"), 0, 0)
        basic_layout.addWidget(self.mode_combo, 0, 1, 1, 3)
        basic_layout.addWidget(QLabel("Mode1 Row:"), 1, 0)
        basic_layout.addWidget(self.mode1_row, 1, 1)
        basic_layout.addWidget(QLabel("Col:"), 1, 2)
        basic_layout.addWidget(self.mode1_col, 1, 3)
        basic_layout.addWidget(QLabel("Counter limit:"), 2, 0)
        basic_layout.addWidget(self.counter_limit, 2, 1)
        basic_layout.addWidget(QLabel("Amp factor:"), 2, 2)
        basic_layout.addWidget(self.amp_factor, 2, 3)
        parameter_grid.addWidget(basic_box, 0, 0)

        output_box = QGroupBox("选通与时序  0x03 / 0x08 / 0x0A")
        output_layout = QGridLayout(output_box)
        self.dac_row = UIntLineEdit(0xC070, 16, "DAC row")
        self.tx_col = QSpinBox()
        self.tx_col.setRange(0, COLS - 1)
        self.delay_factor = UIntLineEdit(0xFF, 8, "Delay factor")
        self.settle_begin = UIntLineEdit(0x1A, 8, "Settle begin")
        self.settle_end = UIntLineEdit(0x1A, 8, "Settle end")
        output_layout.addWidget(QLabel("DAC row:"), 0, 0)
        output_layout.addWidget(self.dac_row, 0, 1)
        output_layout.addWidget(QLabel("TX column:"), 1, 0)
        output_layout.addWidget(self.tx_col, 1, 1)
        output_layout.addWidget(QLabel("Delay:"), 0, 2)
        output_layout.addWidget(self.delay_factor, 0, 3)
        output_layout.addWidget(QLabel("Settle begin:"), 1, 2)
        output_layout.addWidget(self.settle_begin, 1, 3)
        output_layout.addWidget(QLabel("Settle end:"), 2, 2)
        output_layout.addWidget(self.settle_end, 2, 3)
        parameter_grid.addWidget(output_box, 0, 1)

        dfb_box = QGroupBox("DFB、监控与变更  0x0B")
        dfb_layout = QGridLayout(dfb_box)
        self.dfb_switch = QCheckBox("DFB 使能")
        self.monitor_col = QSpinBox()
        self.monitor_col.setRange(0, COLS - 1)
        self.dirty_label = QLabel("待写寄存器：0")
        self.dirty_label.setStyleSheet("color: #546E7A;")
        self.mark_all_global_btn = QPushButton("标记全部")
        self.write_global_btn = QPushButton("写入变更项")
        self.write_global_btn.setMinimumHeight(32)
        dfb_layout.addWidget(self.dfb_switch, 0, 0, 1, 2)
        dfb_layout.addWidget(QLabel("Monitor column:"), 1, 0)
        dfb_layout.addWidget(self.monitor_col, 1, 1)
        dfb_layout.addWidget(self.dirty_label, 2, 0, 1, 2)
        dfb_layout.addWidget(self.mark_all_global_btn, 3, 0)
        dfb_layout.addWidget(self.write_global_btn, 3, 1)
        parameter_grid.addWidget(dfb_box, 0, 2)

        global_layout.addLayout(parameter_grid)
        root.addWidget(global_group)

        cell_group = QGroupBox("Cell 参数  (20 行 × 16 列)")
        cell_layout = QVBoxLayout(cell_group)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("默认 Kp:"))
        self.default_kp = UIntLineEdit(0, 32, "默认 Kp")
        toolbar.addWidget(self.default_kp)
        toolbar.addWidget(QLabel("Ki:"))
        self.default_ki = UIntLineEdit(0, 32, "默认 Ki")
        toolbar.addWidget(self.default_ki)
        toolbar.addWidget(QLabel("ADC offset:"))
        self.default_adc_offset = UIntLineEdit(0, 16, "默认 ADC offset")
        toolbar.addWidget(self.default_adc_offset)
        toolbar.addWidget(QLabel("DAC offset:"))
        self.default_dac_offset = UIntLineEdit(0, 16, "默认 DAC offset")
        toolbar.addWidget(self.default_dac_offset)
        toolbar.addStretch()

        self.dfb_badge = QLabel()
        self.dfb_badge.setAlignment(Qt.AlignCenter)
        self.dfb_badge.setMinimumWidth(105)
        toolbar.addWidget(self.dfb_badge)
        cell_layout.addLayout(toolbar)

        action_layout = QHBoxLayout()
        self.edit_all_cells_btn = QPushButton("编辑全部通道参数...")
        self.select_all_btn = QPushButton("全选待写")
        self.clear_selection_btn = QPushButton("清除待写")
        self.selected_count_label = QLabel("已勾选：0")
        self.write_cells_btn = QPushButton("写入勾选通道")
        self.write_cells_btn.setMinimumHeight(32)
        action_layout.addWidget(self.edit_all_cells_btn)
        action_layout.addSpacing(12)
        action_layout.addWidget(self.select_all_btn)
        action_layout.addWidget(self.clear_selection_btn)
        action_layout.addWidget(self.selected_count_label)
        action_layout.addStretch()
        action_layout.addWidget(self.write_cells_btn)
        cell_layout.addLayout(action_layout)

        self.cell_table = QTableWidget(ROWS, COLS)
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
                button.toggled.connect(self._update_selected_count)
                self.cell_buttons[(row, col)] = button
                self.cell_table.setCellWidget(row, col, button)

        self.cell_table.horizontalHeader().sectionClicked.connect(self._toggle_column_selection)
        self.cell_table.verticalHeader().sectionClicked.connect(self._toggle_row_selection)
        cell_layout.addWidget(self.cell_table, stretch=1)

        legend = QLabel(
            "状态：  灰色=未启用    绿色=使用默认参数    蓝色=独立参数    红框+✓=本次待写入"
        )
        legend.setStyleSheet("color: #455A64;")
        cell_layout.addWidget(legend)
        root.addWidget(cell_group, stretch=1)

        self.mode_combo.currentIndexChanged.connect(lambda: self._mark_dirty(0x00))
        self.mode_combo.currentIndexChanged.connect(self._update_mode_controls)
        self.mode1_row.valueChanged.connect(lambda: self._mark_dirty(0x00))
        self.mode1_col.valueChanged.connect(lambda: self._mark_dirty(0x00))
        self.counter_limit.textChanged.connect(lambda: self._mark_dirty(0x01))
        self.amp_factor.textChanged.connect(lambda: self._mark_dirty(0x02))
        self.dac_row.textChanged.connect(lambda: self._mark_dirty(0x03))
        self.tx_col.valueChanged.connect(lambda: self._mark_dirty(0x08))
        self.delay_factor.textChanged.connect(lambda: self._mark_dirty(0x0A))
        self.settle_begin.textChanged.connect(lambda: self._mark_dirty(0x0A))
        self.settle_end.textChanged.connect(lambda: self._mark_dirty(0x0A))
        self.dfb_switch.toggled.connect(lambda: self._mark_dirty(0x0B))
        self.monitor_col.valueChanged.connect(lambda: self._mark_dirty(0x0B))
        self.dfb_switch.toggled.connect(self._update_dfb_badge)
        self.dfb_switch.toggled.connect(self.dfb_state_changed)

        for editor in (
            self.default_kp,
            self.default_ki,
            self.default_adc_offset,
            self.default_dac_offset,
        ):
            editor.value_committed.connect(self._apply_cell_defaults)

        self.mark_all_global_btn.clicked.connect(self._mark_all_global)
        self.write_global_btn.clicked.connect(self._request_global_write)
        self.edit_all_cells_btn.clicked.connect(self._open_cell_editor)
        self.select_all_btn.clicked.connect(lambda: self._set_all_selected(True))
        self.clear_selection_btn.clicked.connect(lambda: self._set_all_selected(False))
        self.write_cells_btn.clicked.connect(self._request_cell_write)
        self._update_mode_controls()

    def _update_mode_controls(self):
        enabled = self.mode_combo.currentIndex() == 1
        self.mode1_row.setEnabled(enabled)
        self.mode1_col.setEnabled(enabled)

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

    def _update_dfb_badge(self, enabled):
        if enabled:
            self.dfb_badge.setText("DFB：开启")
            self.dfb_badge.setStyleSheet(
                "background:#2E7D32; color:white; padding:5px 10px; border-radius:4px; font-weight:bold;"
            )
        else:
            self.dfb_badge.setText("DFB：关闭")
            self.dfb_badge.setStyleSheet(
                "background:#757575; color:white; padding:5px 10px; border-radius:4px; font-weight:bold;"
            )

    def _cell_for(self, row, col):
        return self.cells[row * COLS + col]

    def _is_custom(self, cell):
        return any(cell[key] != self.cell_defaults[key] for key in self.cell_defaults)

    def _refresh_all_cells(self):
        for cell in self.cells:
            self.cell_buttons[(cell["row"], cell["col"])].set_status(
                cell["enabled"], self._is_custom(cell)
            )
        self._update_selected_count()

    def _update_selected_count(self):
        count = sum(button.isChecked() for button in self.cell_buttons.values())
        self.selected_count_label.setText(f"已勾选：{count}")

    def _toggle_row_selection(self, row):
        buttons = [self.cell_buttons[(row, col)] for col in range(COLS)]
        target = any(not button.isChecked() for button in buttons)
        for button in buttons:
            button.set_selected(target)

    def _toggle_column_selection(self, col):
        buttons = [self.cell_buttons[(row, col)] for row in range(ROWS)]
        target = any(not button.isChecked() for button in buttons)
        for button in buttons:
            button.set_selected(target)

    def _set_all_selected(self, selected):
        for button in self.cell_buttons.values():
            button.set_selected(selected)

    def _selected_keys(self):
        return {key for key, button in self.cell_buttons.items() if button.isChecked()}

    def _apply_cell_defaults(self, _value=None):
        old_defaults = dict(self.cell_defaults)
        new_defaults = {
            "kp": self.default_kp.value(),
            "ki": self.default_ki.value(),
            "adc_offset": self.default_adc_offset.value(),
            "dac_offset": self.default_dac_offset.value(),
        }
        for cell in self.cells:
            was_custom = any(cell[key] != old_defaults[key] for key in old_defaults)
            if not was_custom:
                for key, value in new_defaults.items():
                    cell[key] = value
        self.cell_defaults = new_defaults
        self._refresh_all_cells()

    def _open_cell_editor(self):
        dialog = CellParameterDialog(self.cells, self._selected_keys(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self.cells = dialog.result_cells
        self._refresh_all_cells()
        self.log_signal.emit("[FPGA UI] 已更新全部 Cell 的本地参数，尚未下发。")

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
            QMessageBox.warning(self, "DFB 已开启", "修改Cell参数前请关闭DFB")
            self.log_signal.emit("[FPGA UI] 修改Cell参数前请关闭DFB")
            return
        selected = self._selected_keys()
        if not selected:
            QMessageBox.warning(self, "未选择通道", "请先勾选需要写入的 Cell。")
            return
        enabled_cells = [
            deepcopy(self._cell_for(row, col))
            for row, col in sorted(selected)
            if self._cell_for(row, col)["enabled"]
        ]
        if not enabled_cells:
            QMessageBox.warning(self, "通道未启用", "勾选的 Cell 均未启用，请先在参数弹窗中启用。")
            return
        self.cell_write_requested.emit(enabled_cells)
        self.log_signal.emit(
            f"[FPGA UI] 请求写入 {len(enabled_cells)} 个 Cell；当前仅完成 UI，未发送数据。"
        )

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
                    "enabled": cell["enabled"],
                    "kp": cell["kp"],
                    "ki": cell["ki"],
                    "adc_offset": cell["adc_offset"],
                    "dac_offset": cell["dac_offset"],
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
                            "enabled": bool(cfg["enabled"]),
                            "kp": parse_uint(cfg["kp"], 32, f"Cell {row + 1}/{col + 1} Kp"),
                            "ki": parse_uint(cfg["ki"], 32, f"Cell {row + 1}/{col + 1} Ki"),
                            "adc_offset": parse_uint(
                                cfg["adc_offset"], 16, f"Cell {row + 1}/{col + 1} ADC offset"
                            ),
                            "dac_offset": parse_uint(
                                cfg["dac_offset"], 16, f"Cell {row + 1}/{col + 1} DAC offset"
                            ),
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
        self._set_all_selected(False)
        self._update_mode_controls()
        self._refresh_dirty_ui()
        self._refresh_all_cells()
        self._update_dfb_badge(self.dfb_switch.isChecked())
        self.dfb_state_changed.emit(self.dfb_switch.isChecked())
        return True, "读取成功"
