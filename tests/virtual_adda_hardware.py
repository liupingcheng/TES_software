"""Local virtual AD/DA/clock/JESD boards for testing the V8 UI.

Run this script, point the four V8 board connections at the printed localhost
ports, connect, and click a configuration button.  Every received command is
printed with its wall-clock timestamp and timing relative to the connection.
"""

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import socketserver
import threading
import time


TEST_DIRECTORY = Path(__file__).resolve().parent
MAIN_DIRECTORY = TEST_DIRECTORY.parent
V8_DIRECTORY = MAIN_DIRECTORY / "TDM_V8"
PROJECT_DIRECTORY = MAIN_DIRECTORY.parent
CONFIG_DIRECTORY = V8_DIRECTORY / "config_files"
REFERENCE_ADC_CONFIG = (
    PROJECT_DIRECTORY / "ref" / "AD_DA_SPI_config" / "adc_configuration.txt"
)
ADC_COMPARISON_PORT = 5024
WAIT_MARKER = "FFFFFFFF"


def timestamp_now():
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def parse_hex_bytes(value, option_name, expected_bytes=None):
    value = str(value).strip()
    try:
        result = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{option_name} 必须是十六进制数据：{value}") from exc
    if expected_bytes is not None and len(result) != expected_bytes:
        raise ValueError(
            f"{option_name} 必须是 {expected_bytes} 字节"
            f"（{expected_bytes * 2} 个 Hex 字符）"
        )
    return result


def load_expected_frames(file_path, word_bytes):
    """Load the commands that V8 should send, excluding blank/wait lines."""
    file_path = Path(file_path)
    try:
        lines = file_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"无法读取校验文件 {file_path}：{exc}") from exc

    expected_hex_length = int(word_bytes) * 2
    frames = []
    for line_number, raw_line in enumerate(lines, start=1):
        value = raw_line.strip()
        if not value or value.upper() == WAIT_MARKER:
            continue
        if len(value) != expected_hex_length:
            raise ValueError(
                f"校验文件 {file_path.name} 第 {line_number} 行长度错误："
                f"应为 {expected_hex_length} 个 Hex 字符"
            )
        try:
            frames.append(bytes.fromhex(value))
        except ValueError as exc:
            raise ValueError(
                f"校验文件 {file_path.name} 第 {line_number} 行不是有效 Hex：{value}"
            ) from exc
    return frames


@dataclass
class BoardSpec:
    key: str
    board_type: str
    display_name: str
    port: int
    word_bytes: int
    config_path: Path
    expected_frames: list


class CaptureLog:
    FIELD_NAMES = (
        "timestamp",
        "board_type",
        "board_name",
        "peer",
        "connection",
        "sequence",
        "elapsed_seconds",
        "interval_seconds",
        "byte_count",
        "received_hex",
        "expected_hex",
        "comparison",
        "ack_hex",
    )

    def __init__(self, path=None):
        self._lock = threading.Lock()
        self._file = None
        self._writer = None
        if path:
            path = Path(path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = path.open("w", encoding="utf-8-sig", newline="")
            self._writer = csv.DictWriter(self._file, fieldnames=self.FIELD_NAMES)
            self._writer.writeheader()
            self._file.flush()
            self.path = path
        else:
            self.path = None

    def write(self, row):
        if self._writer is None:
            return
        with self._lock:
            self._writer.writerow(row)
            self._file.flush()

    def close(self):
        with self._lock:
            if self._file is not None:
                self._file.close()
                self._file = None
                self._writer = None


PRINT_LOCK = threading.Lock()


def print_live(message=""):
    with PRINT_LOCK:
        print(message, flush=True)


class VirtualBoardHandler(socketserver.BaseRequestHandler):
    def handle(self):
        server = self.server
        spec = server.board_spec
        connection_number = server.next_connection_number()
        peer = f"{self.client_address[0]}:{self.client_address[1]}"
        connected_at = time.monotonic()
        last_frame_at = connected_at
        sequence = 0
        buffer = bytearray()

        print_live(
            f"[{timestamp_now()}] [{spec.display_name}] 已连接 "
            f"peer={peer} connection={connection_number}"
        )
        try:
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                buffer.extend(data)

                while len(buffer) >= spec.word_bytes:
                    frame = bytes(buffer[: spec.word_bytes])
                    del buffer[: spec.word_bytes]
                    now = time.monotonic()
                    received_timestamp = timestamp_now()
                    sequence += 1
                    elapsed = now - connected_at
                    interval = now - last_frame_at
                    last_frame_at = now
                    received_hex = frame.hex().upper()

                    expected = (
                        spec.expected_frames[sequence - 1]
                        if sequence <= len(spec.expected_frames)
                        else None
                    )
                    if not server.check_values:
                        comparison = "未校验"
                        expected_hex = ""
                    elif expected is None:
                        comparison = "无对应预期值"
                        expected_hex = ""
                    elif frame == expected:
                        comparison = "一致"
                        expected_hex = expected.hex().upper()
                    else:
                        comparison = "不一致"
                        expected_hex = expected.hex().upper()

                    ack_hex = ""
                    if server.send_ack:
                        if server.ack_delay_seconds:
                            time.sleep(server.ack_delay_seconds)
                        self.request.sendall(server.acknowledgement)
                        ack_hex = server.acknowledgement.hex().upper()

                    expected_text = (
                        f" expected={expected_hex}" if expected_hex else ""
                    )
                    ack_text = f" ACK={ack_hex}" if ack_hex else " ACK=关闭"
                    print_live(
                        f"[{received_timestamp}] [{spec.display_name}] "
                        f"RX #{sequence:04d} 连接后={elapsed:8.3f}s "
                        f"间隔={interval:7.3f}s {len(frame)}B "
                        f"HEX={received_hex}{expected_text} "
                        f"校验={comparison}{ack_text}"
                    )
                    server.capture_log.write(
                        {
                            "timestamp": received_timestamp,
                            "board_type": spec.board_type,
                            "board_name": spec.display_name,
                            "peer": peer,
                            "connection": connection_number,
                            "sequence": sequence,
                            "elapsed_seconds": f"{elapsed:.6f}",
                            "interval_seconds": f"{interval:.6f}",
                            "byte_count": len(frame),
                            "received_hex": received_hex,
                            "expected_hex": expected_hex,
                            "comparison": comparison,
                            "ack_hex": ack_hex,
                        }
                    )
        except (ConnectionError, OSError) as exc:
            print_live(
                f"[{timestamp_now()}] [{spec.display_name}] 连接异常 "
                f"connection={connection_number}: {exc}"
            )
        finally:
            if buffer:
                print_live(
                    f"[{timestamp_now()}] [{spec.display_name}] 警告：断开时还有 "
                    f"{len(buffer)} 个未组成完整命令的字节："
                    f"{bytes(buffer).hex().upper()}"
                )
            print_live(
                f"[{timestamp_now()}] [{spec.display_name}] 已断开 "
                f"connection={connection_number}，共收到 {sequence} 条命令"
            )


class VirtualBoardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address,
        board_spec,
        acknowledgement,
        ack_delay_ms,
        send_ack,
        check_values,
        capture_log,
    ):
        self.board_spec = board_spec
        self.acknowledgement = acknowledgement
        self.ack_delay_seconds = max(0, int(ack_delay_ms)) / 1000.0
        self.send_ack = bool(send_ack)
        self.check_values = bool(check_values)
        self.capture_log = capture_log
        self._connection_count = 0
        self._connection_lock = threading.Lock()
        super().__init__(address, VirtualBoardHandler)

    def next_connection_number(self):
        with self._connection_lock:
            self._connection_count += 1
            return self._connection_count


def make_board_specs(args):
    requested = set(args.only or ("adc", "dfb-dac", "gate-dac", "fpga"))
    definitions = (
        (
            "adc",
            "ADC_readout",
            "DFB ADC板卡",
            args.adc_port,
            4,
            args.adc_config,
        ),
        (
            "dfb-dac",
            "FB_DAC",
            "DFB DAC板卡",
            args.dfb_dac_port,
            4,
            args.dac_config,
        ),
        (
            "gate-dac",
            "gate_DAC",
            "选通 DAC板卡",
            args.gate_dac_port,
            4,
            args.dac_config,
        ),
        (
            "fpga",
            "fpga",
            "FPGA算法板卡",
            args.fpga_port,
            args.fpga_word_bytes,
            args.jesd_config if args.fpga_word_bytes == 8 else args.clock_config,
        ),
    )

    specs = []
    for key, board_type, display_name, port, word_bytes, config_path in definitions:
        if key not in requested:
            continue
        expected_frames = (
            []
            if args.no_check
            else load_expected_frames(config_path, word_bytes)
        )
        specs.append(
            BoardSpec(
                key=key,
                board_type=board_type,
                display_name=display_name,
                port=int(port),
                word_bytes=int(word_bytes),
                config_path=Path(config_path),
                expected_frames=expected_frames,
            )
        )
    return specs


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "在本机创建四块虚拟板卡，实时显示 V8 配置按钮发送的值和时间。"
        )
    )
    parser.add_argument(
        "--profile",
        choices=("local-all", "reference-adc", "v8-adc"),
        default="local-all",
        help=(
            "固定连接模式：local-all为本机高端口；reference-adc为"
            "192.168.10.16:5024；v8-adc为192.168.104.1:5024。"
        ),
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听IP。")
    parser.add_argument("--adc-port", type=int, default=5104)
    parser.add_argument("--dfb-dac-port", type=int, default=5105)
    parser.add_argument("--gate-dac-port", type=int, default=5106)
    parser.add_argument("--fpga-port", type=int, default=5200)
    parser.add_argument(
        "--only",
        action="append",
        choices=("adc", "dfb-dac", "gate-dac", "fpga"),
        help="只启动指定板卡；可重复使用。默认启动全部。",
    )
    parser.add_argument(
        "--fpga-word-bytes",
        type=int,
        choices=(4, 8),
        default=4,
        help="FPGA按4字节测试时钟，按8字节测试JESD（默认4）。",
    )
    parser.add_argument(
        "--ack",
        default="A5A50001",
        help="每条命令返回的4字节确认，默认 A5A50001。",
    )
    parser.add_argument(
        "--ack-delay-ms",
        type=int,
        default=0,
        help="回复确认前额外等待的毫秒数。",
    )
    parser.add_argument(
        "--no-ack",
        action="store_true",
        help="不返回确认，用于验证V8的3秒超时。",
    )
    parser.add_argument(
        "--no-check",
        action="store_true",
        help="只显示实际值，不与配置文件逐条比较。",
    )
    parser.add_argument(
        "--log",
        type=Path,
        help="可选CSV记录文件，例如 virtual_board_capture.csv。",
    )
    parser.add_argument(
        "--adc-config",
        type=Path,
        default=CONFIG_DIRECTORY / "adc_configuration.txt",
    )
    parser.add_argument(
        "--dac-config",
        type=Path,
        default=CONFIG_DIRECTORY / "dac39j84_0_1_2_configuration.txt",
    )
    parser.add_argument(
        "--clock-config",
        type=Path,
        default=CONFIG_DIRECTORY / "control_lmk_configuration.txt",
    )
    parser.add_argument(
        "--jesd-config",
        type=Path,
        default=CONFIG_DIRECTORY / "JESD_configuration.txt",
    )
    return parser


def apply_profile(args):
    """Apply fixed addresses used by the reference script and V8 defaults."""
    if args.profile == "reference-adc":
        args.host = "192.168.10.16"
        args.only = ["adc"]
        args.adc_port = ADC_COMPARISON_PORT
        args.adc_config = REFERENCE_ADC_CONFIG
        args.client_local_ip = "系统自动选择"
        args.profile_title = "参考脚本 ADC：192.168.10.16:5024"
    elif args.profile == "v8-adc":
        args.host = "192.168.104.1"
        args.only = ["adc"]
        args.adc_port = ADC_COMPARISON_PORT
        # 两个对比用虚拟板卡使用同一个文件快照校验，确保除IP外行为一致。
        args.adc_config = REFERENCE_ADC_CONFIG
        args.client_local_ip = "192.168.104.2"
        args.profile_title = "V8 DFB ADC：192.168.104.1:5024"
    else:
        args.client_local_ip = "127.0.0.1"
        args.profile_title = "本机四板卡高端口测试"


def print_startup(host, specs, acknowledgement, args, capture_log):
    print_live(f"虚拟板卡已启动：{args.profile_title}")
    if args.profile == "reference-adc":
        print_live("参考脚本无需修改IP和端口，直接运行即可。")
    else:
        print_live("请在 V8 中填写以下参数并按 Enter 确认：")
    print_live()
    for spec in specs:
        mode = (
            "JESD，8字节命令"
            if spec.key == "fpga" and spec.word_bytes == 8
            else "4字节命令"
        )
        print_live(
            f"  {spec.display_name:<12} IP={host:<15} "
            f"Port={spec.port:<5} Local IP={args.client_local_ip}  ({mode})"
        )
        if not args.no_check:
            print_live(
                f"    校验文件：{spec.config_path}，"
                f"有效命令 {len(spec.expected_frames)} 条"
            )
    print_live()
    if args.no_ack:
        print_live("确认回复：关闭（V8应在约3秒后报告超时）")
    else:
        print_live(
            f"确认回复：{acknowledgement.hex().upper()}，"
            f"额外延迟 {max(0, args.ack_delay_ms)} ms"
        )
    if capture_log.path:
        print_live(f"CSV记录：{capture_log.path}")
    print_live("连接板卡后点击居中的配置按钮；按 Ctrl+C 停止虚拟板卡。")
    print_live()


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    apply_profile(args)
    try:
        acknowledgement = parse_hex_bytes(args.ack, "--ack", expected_bytes=4)
        specs = make_board_specs(args)
    except ValueError as exc:
        parser.error(str(exc))

    capture_log = CaptureLog(args.log)
    servers = []
    threads = []
    try:
        for spec in specs:
            server = VirtualBoardServer(
                (args.host, spec.port),
                spec,
                acknowledgement,
                args.ack_delay_ms,
                not args.no_ack,
                not args.no_check,
                capture_log,
            )
            servers.append(server)
            thread = threading.Thread(
                target=server.serve_forever,
                name=f"virtual-{spec.key}",
                daemon=True,
            )
            threads.append(thread)
            thread.start()
    except OSError as exc:
        for server in servers:
            server.server_close()
        capture_log.close()
        parser.error(f"无法启动虚拟板卡：{exc}")

    print_startup(args.host, specs, acknowledgement, args, capture_log)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print_live("\n正在停止虚拟板卡……")
    finally:
        for server in servers:
            server.shutdown()
        for server in servers:
            server.server_close()
        for thread in threads:
            thread.join(timeout=1.0)
        capture_log.close()
        print_live("虚拟板卡已停止。")


if __name__ == "__main__":
    main()
