"""Asynchronous register-configuration file sender for AD/DA boards."""

from dataclasses import dataclass, field
from pathlib import Path
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


WAIT_MARKER = "FFFFFFFF"


class ConfigFileError(ValueError):
    """Raised when a configuration file cannot be parsed safely."""


@dataclass(frozen=True)
class ConfigStep:
    line_number: int
    payload: bytes = None

    @property
    def is_wait(self):
        return self.payload is None


def parse_configuration_file(file_path, word_bytes):
    """Parse and validate the entire file before any command is sent."""
    file_path = Path(file_path)
    if int(word_bytes) <= 0:
        raise ConfigFileError("命令字节数必须大于 0")

    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigFileError(f"无法读取配置文件：{exc}") from exc
    except UnicodeError as exc:
        raise ConfigFileError(f"配置文件编码错误：{exc}") from exc

    expected_hex_length = int(word_bytes) * 2
    steps = []
    command_count = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        value = raw_line.strip()
        if not value:
            continue
        if value.upper() == WAIT_MARKER:
            steps.append(ConfigStep(line_number=line_number))
            continue
        if len(value) != expected_hex_length:
            raise ConfigFileError(
                f"第 {line_number} 行长度错误：应为 "
                f"{expected_hex_length} 个十六进制字符，实际为 {len(value)} 个"
            )
        if any(character not in "0123456789abcdefABCDEF" for character in value):
            raise ConfigFileError(f"第 {line_number} 行包含非十六进制字符：{value}")
        steps.append(
            ConfigStep(line_number=line_number, payload=bytes.fromhex(value))
        )
        command_count += 1

    if command_count == 0:
        raise ConfigFileError("配置文件为空或不包含可发送命令")
    return steps, command_count


@dataclass
class _Transfer:
    board_type: str
    action_id: str
    steps: list
    total_commands: int
    reply_bytes: int
    step_index: int = 0
    completed_commands: int = 0
    current_line: int = 0
    pending_payload: bytes = None
    awaiting_reply: bool = False
    reply_buffer: bytearray = field(default_factory=bytearray)
    started_at: float = field(default_factory=time.monotonic)
    delay_timer: QTimer = None
    reply_timer: QTimer = None


class ADDAConfigSender(QObject):
    """Send one command at a time and advance after a fixed-size reply."""

    started = pyqtSignal(str, str, int)
    progress = pyqtSignal(str, str, int, int)
    finished = pyqtSignal(str, str, bool, str)

    def __init__(
        self,
        send_callback,
        parent=None,
        command_delay_ms=100,
        wait_marker_delay_ms=1000,
        reply_timeout_ms=3000,
    ):
        super().__init__(parent)
        self._send_callback = send_callback
        self.command_delay_ms = max(0, int(command_delay_ms))
        self.wait_marker_delay_ms = max(0, int(wait_marker_delay_ms))
        self.reply_timeout_ms = max(1, int(reply_timeout_ms))
        self._transfers = {}

    def start(self, board_type, action_id, file_path, word_bytes, reply_bytes=4):
        if board_type in self._transfers:
            return False, "该板卡已有配置任务正在进行"
        if int(reply_bytes) <= 0:
            return False, "回包字节数必须大于 0"

        try:
            steps, command_count = parse_configuration_file(file_path, word_bytes)
        except ConfigFileError as exc:
            return False, str(exc)

        transfer = _Transfer(
            board_type=str(board_type),
            action_id=str(action_id),
            steps=steps,
            total_commands=command_count,
            reply_bytes=int(reply_bytes),
        )
        transfer.delay_timer = QTimer(self)
        transfer.delay_timer.setSingleShot(True)
        transfer.delay_timer.timeout.connect(
            lambda current=transfer: self._on_delay_finished(current)
        )
        transfer.reply_timer = QTimer(self)
        transfer.reply_timer.setSingleShot(True)
        transfer.reply_timer.timeout.connect(
            lambda current=transfer: self._on_reply_timeout(current)
        )
        self._transfers[transfer.board_type] = transfer
        self.started.emit(
            transfer.board_type,
            transfer.action_id,
            transfer.total_commands,
        )
        self._advance(transfer)
        return True, ""

    def is_active(self, board_type):
        return board_type in self._transfers

    def feed_received(self, board_type, data):
        incoming = bytes(data)
        transfer = self._transfers.get(board_type)
        if transfer is None or not transfer.awaiting_reply:
            return incoming

        required = transfer.reply_bytes - len(transfer.reply_buffer)
        consumed = min(required, len(incoming))
        transfer.reply_buffer.extend(incoming[:consumed])
        remaining = incoming[consumed:]
        if len(transfer.reply_buffer) < transfer.reply_bytes:
            return remaining

        transfer.reply_timer.stop()
        transfer.awaiting_reply = False
        transfer.reply_buffer.clear()
        transfer.completed_commands += 1
        self.progress.emit(
            transfer.board_type,
            transfer.action_id,
            transfer.completed_commands,
            transfer.total_commands,
        )
        self._advance(transfer)
        return remaining

    def cancel(self, board_type, reason=""):
        transfer = self._transfers.get(board_type)
        if transfer is None:
            return False
        message = "配置已中止"
        if reason:
            message += f"：{reason}"
        self._finish(transfer, False, message)
        return True

    def cancel_all(self, reason=""):
        for board_type in list(self._transfers):
            self.cancel(board_type, reason)

    def _is_current(self, transfer):
        return self._transfers.get(transfer.board_type) is transfer

    def _advance(self, transfer):
        if not self._is_current(transfer):
            return
        if transfer.step_index >= len(transfer.steps):
            elapsed = time.monotonic() - transfer.started_at
            self._finish(
                transfer,
                True,
                f"配置完成，共 {transfer.completed_commands} 条命令，"
                f"耗时 {elapsed:.1f} 秒",
            )
            return

        step = transfer.steps[transfer.step_index]
        transfer.step_index += 1
        transfer.current_line = step.line_number
        transfer.pending_payload = step.payload
        delay_ms = (
            self.wait_marker_delay_ms if step.is_wait else self.command_delay_ms
        )
        transfer.delay_timer.start(delay_ms)

    def _on_delay_finished(self, transfer):
        if not self._is_current(transfer):
            return
        if transfer.pending_payload is None:
            self._advance(transfer)
            return

        transfer.awaiting_reply = True
        transfer.reply_buffer.clear()
        try:
            sent = bool(
                self._send_callback(transfer.board_type, transfer.pending_payload)
            )
        except Exception as exc:
            transfer.awaiting_reply = False
            self._finish(
                transfer,
                False,
                f"第 {transfer.current_line} 行发送异常：{exc}",
            )
            return
        if not sent:
            transfer.awaiting_reply = False
            self._finish(
                transfer,
                False,
                f"第 {transfer.current_line} 行发送失败",
            )
            return
        transfer.reply_timer.start(self.reply_timeout_ms)

    def _on_reply_timeout(self, transfer):
        if not self._is_current(transfer) or not transfer.awaiting_reply:
            return
        self._finish(
            transfer,
            False,
            f"第 {transfer.current_line} 行等待 {transfer.reply_bytes} 字节回复超时",
        )

    def _finish(self, transfer, success, message):
        if not self._is_current(transfer):
            return
        self._transfers.pop(transfer.board_type, None)
        transfer.delay_timer.stop()
        transfer.reply_timer.stop()
        transfer.delay_timer.deleteLater()
        transfer.reply_timer.deleteLater()
        self.finished.emit(
            transfer.board_type,
            transfer.action_id,
            bool(success),
            str(message),
        )
