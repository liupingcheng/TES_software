# data.py
from dataclasses import dataclass, field


@dataclass
class RawPacket:
    ts: float
    payload: bytes


@dataclass
class Event:
    ts_start: float
    ts_end: float
    raw_bytes: bytes
    header_pos: int = 0
    tail_pos: int = 0
    middle_len: int = 0
    event_id: int = -1

    @property
    def total_len(self) -> int:
        return len(self.raw_bytes)
