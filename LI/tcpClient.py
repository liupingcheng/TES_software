# tcpClient.py
import socket
import time
import queue

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from data import RawPacket


class TCPClient(QObject):
    # packetReceived = pyqtSignal()
    connectedSignal = pyqtSignal()
    disconnectedSignal = pyqtSignal()
    errorSignal = pyqtSignal(str)
    bytesReceived = pyqtSignal(int)
    commandSent = pyqtSignal(bytes)

    def __init__(self, raw_queue):
        super().__init__()
        self.raw_queue = raw_queue

        self.ip = "192.168.10.16"
        self.port = 24
        self.timeout = 0.5
        self.socket_buffer_size = 655360
        self.acqmode = "normal"

        # setting阶段：连接后发送的初始化命令
        self.connect_command = {
            "normal": [b"\xab\xab", b"\xa0\xa0"],
            "baseline": [b"\xab\xab", b"\xa1\xa1"],
            "calib": [b"\xab\xab", b"\xa2\xa2"]
        }

        # start阶段：正式开始采集前发送
        self.start_command = [b"\x00\x00", b"\x86\xb1",b"\x00\x00"]

        # stop阶段：停止采集前发送
        self.stop_command = [b"\x00\x00", b"\x86\xb1",b"\x00\x00",]

        self.sock = None
        self.running = False
        self.connected = False

        self.packet_count = 0
        self.total_bytes_recv = 0
        self.last_packet_time = None

        self.raw_data = bytearray()
        self.raw_data_limit = 10000

    def _create_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, self.socket_buffer_size)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.socket_buffer_size)
        return sock

    def _safe_close(self):
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _send_command(self, cmd: bytes):
        if not cmd:
            return
        if not self.connected or self.sock is None:
            raise ConnectionError("TCP socket is not connected")
        self.sock.sendall(cmd)
        self.commandSent.emit(cmd)

    def _reset_runtime_counters(self):
        self.packet_count = 0
        self.total_bytes_recv = 0
        self.last_packet_time = None
        self.raw_data.clear()

    @pyqtSlot()
    def connect_and_configure(self):
        """
        建立TCP连接，并发送初始化命令。
        该函数用于在UI点击Setting时执行。
        """
        if self.connected and self.sock is not None:
            self.errorSignal.emit("TCP socket is already connected")
            return

        try:
            self._safe_close()

            self.sock = self._create_socket()
            self.sock.connect((self.ip, self.port))

            self.connected = True
            self.connectedSignal.emit()

            init_cmds = self.connect_command.get(
                self.acqmode,
                self.connect_command["normal"]
            )

            for cmd in init_cmds:
                self._send_command(cmd)

        except Exception as e:
            self.connected = False
            self._safe_close()
            self.errorSignal.emit(f"TCP connect/config failed: {e}")

    @pyqtSlot()
    def start(self):
        """
        只负责发送start command并进入接收循环。
        TCP连接和初始化命令发送已由 connect_and_configure() 完成。
        """
        if self.running:
            return

        if not self.connected or self.sock is None:
            self.errorSignal.emit("TCP is not connected. Please apply setting first.")
            return

        self.running = True
        self._reset_runtime_counters()

        try:
            # start阶段命令
            for cmd in self.start_command:
                self._send_command(cmd)

            # 接收循环
            while self.running:
                try:
                    data = self.sock.recv(self.socket_buffer_size)

                    if not data:
                        raise ConnectionError("Peer closed the connection")

                    now = time.time()
                    self.packet_count += 1
                    self.total_bytes_recv += len(data)
                    self.last_packet_time = now

                    self.raw_data.extend(data)
                    if len(self.raw_data) > self.raw_data_limit:
                        self.raw_data = self.raw_data[-self.raw_data_limit:]

                    rp = RawPacket(ts=now, payload=data)

                    try:
                        self.raw_queue.put_nowait(rp)
                        self.packetReceived.emit()
                        self.bytesReceived.emit(len(data))
                    except queue.Full:
                        self.errorSignal.emit("raw_queue is full, packet dropped")

                except socket.timeout:
                    continue

        except Exception as e:
            self.errorSignal.emit(f"TCP recv failed: {e}")

        finally:
            self.running = False
            # 这里不主动断开连接，保留socket
            # 这样如果只是采集结束但还想保持连接，不会重复connect

    @pyqtSlot()
    def stop(self):
        """
        停止采集：
        1. running=False
        2. 若socket仍连接，发送stop command
        3. 保留TCP连接；如需彻底断开，调用disconnect_tcp()
        """
        self.running = False

        if self.connected and self.sock is not None:
            try:
                for cmd in self.stop_command:
                    self._send_command(cmd)
            except Exception as e:
                self.errorSignal.emit(f"Failed to send stop command: {e}")

    @pyqtSlot()
    def disconnect_tcp(self):
        """
        主动断开TCP连接
        """
        was_connected = self.connected

        self.running = False
        self.connected = False
        self._safe_close()

        if was_connected:
            self.disconnectedSignal.emit()

    @pyqtSlot(bytes)
    def send_bytes_slot(self, data: bytes):
        try:
            self._send_command(data)
        except Exception as e:
            self.errorSignal.emit(f"Send command failed: {e}")