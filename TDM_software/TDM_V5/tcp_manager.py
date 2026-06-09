from PyQt5.QtCore import QObject, pyqtSignal
from tcp_client import TCPClient

class TCPManager(QObject):
    """
    Manages multiple TCPClient connections (e.g. Bias1, Bias2, Bias3, FPGA)
    and multiplexes their signals to the main application.
    """
    # Multiplexed signals
    board_connected = pyqtSignal(str) # board_type
    board_disconnected = pyqtSignal(str, str) # board_type, error_msg
    board_data_sent = pyqtSignal(str, int) # board_type, bytes_sent
    board_data_received = pyqtSignal(str, int, bytes) # board_type, bytes_received, raw_data
    board_probe_finished = pyqtSignal(str, bool, str) # board_type, success, msg

    def __init__(self):
        super().__init__()
        self.clients = {}

    def _get_or_create_client(self, board_type: str) -> TCPClient:
        if board_type not in self.clients:
            client = TCPClient()
            # Hook up signals, injecting board_type
            client.connected.connect(lambda b=board_type: self.board_connected.emit(b))
            client.disconnected.connect(lambda err, b=board_type: self.board_disconnected.emit(b, err))
            client.data_sent.connect(lambda bytes_sent, b=board_type: self.board_data_sent.emit(b, bytes_sent))
            client.data_received.connect(lambda bytes_recv, data_bytes, b=board_type: self.board_data_received.emit(b, bytes_recv, data_bytes))
            client.probe_finished.connect(lambda success, msg, b=board_type: self.board_probe_finished.emit(b, success, msg))
            self.clients[board_type] = client
        return self.clients[board_type]

    def connect_board(self, board_type: str, ip: str, port: int, local_ip: str = ""):
        client = self._get_or_create_client(board_type)
        client.connect_to_server(ip, port, local_ip)

    def disconnect_board(self, board_type: str):
        if board_type in self.clients:
            self.clients[board_type].disconnect_from_server()

    def send_data(self, board_type: str, data: bytes) -> bool:
        if board_type in self.clients:
            return self.clients[board_type].send_data(data)
        return False

    def probe_board(self, board_type: str, ip: str, port: int, hold_seconds: float = 5.0, local_ip: str = ""):
        client = self._get_or_create_client(board_type)
        client.probe_server(ip, port, hold_seconds, local_ip)

    def is_connected(self, board_type: str) -> bool:
        if board_type in self.clients:
            return self.clients[board_type].is_connected
        return False

    def disconnect_all(self):
        for board_type, client in self.clients.items():
            client.disconnect_from_server()
