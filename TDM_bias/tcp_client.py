from PyQt5.QtCore import QObject, pyqtSignal
import socket
import threading
import time

class TCPClient(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal(str) # Error msg
    data_sent = pyqtSignal(int)    # Bytes sent
    data_received = pyqtSignal(int)
    probe_finished = pyqtSignal(bool, str)
    
    def __init__(self):
        super().__init__()
        self.sock = None
        self.is_connected = False
        self._recv_thread = None
        self._stop_event = threading.Event()
        self._probe_thread = None
        
    def connect_to_server(self, ip, port, local_ip=""):
        if self.is_connected:
            self.disconnect_from_server()
            
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(3.0)
            if local_ip:
                self.sock.bind((local_ip, 0))
            self.sock.connect((ip, int(port)))
            self.sock.settimeout(0.5)
            self.is_connected = True
            self._stop_event.clear()
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            self.connected.emit()
        except Exception as e:
            self.is_connected = False
            self.disconnected.emit(str(e))
            
    def disconnect_from_server(self):
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.sock.close()
            except:
                pass
        self.sock = None
        self.is_connected = False
        self._recv_thread = None

    def send_data(self, data_bytes):
        if not self.is_connected or not self.sock:
            return False
        
        try:
            self.sock.sendall(data_bytes)
            self.data_sent.emit(len(data_bytes))
            return True
        except Exception as e:
            self.is_connected = False
            self.disconnected.emit(f"Send Error: {str(e)}")
            return False

    def probe_server(self, ip, port, hold_seconds=5.0, local_ip=""):
        if self._probe_thread and self._probe_thread.is_alive():
            self.probe_finished.emit(False, "Probe already running.")
            return

        self._probe_thread = threading.Thread(
            target=self._probe_worker,
            args=(ip, int(port), float(hold_seconds), local_ip),
            daemon=True,
        )
        self._probe_thread.start()

    def _recv_loop(self):
        while not self._stop_event.is_set():
            if not self.sock:
                return

            try:
                data = self.sock.recv(4096)
                if not data:
                    if self.is_connected:
                        self.is_connected = False
                        self.disconnected.emit("Remote closed connection")
                    return

                self.data_received.emit(len(data))
            except socket.timeout:
                continue
            except OSError as e:
                if not self._stop_event.is_set() and self.is_connected:
                    self.is_connected = False
                    self.disconnected.emit(f"Recv Error: {str(e)}")
                return

    def _probe_worker(self, ip, port, hold_seconds, local_ip):
        sock = None
        start_time = time.time()
        total_rx = 0

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            if local_ip:
                sock.bind((local_ip, 0))
            sock.connect((ip, port))
            local_ip, local_port = sock.getsockname()
            sock.settimeout(0.5)

            while (time.time() - start_time) < hold_seconds:
                try:
                    data = sock.recv(4096)
                    if not data:
                        elapsed = time.time() - start_time
                        self.probe_finished.emit(
                            False,
                            f"Probe connected from {local_ip}:{local_port}, but remote closed after {elapsed:.1f}s.",
                        )
                        return
                    total_rx += len(data)
                except socket.timeout:
                    continue

            elapsed = time.time() - start_time
            self.probe_finished.emit(
                True,
                f"Probe connected from {local_ip}:{local_port}, stayed open for {elapsed:.1f}s, RX {total_rx} bytes.",
            )
        except Exception as e:
            self.probe_finished.emit(False, f"Probe failed: {str(e)}")
        finally:
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                try:
                    sock.close()
                except:
                    pass

