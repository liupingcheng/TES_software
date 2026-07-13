#!/usr/bin/env python3
"""
tdm_config.py — 读取 txt 配置文件，通过 SiTCPXG TCP 发送 64-bit 寄存器配置到 FPGA

txt 格式: 每行一个 64-bit 十六进制数 (0x 开头), 空行/# 注释跳过

用法:
    python3 tdm_config.py
    python3 tdm_config.py --ip 192.168.200.1 --port 24
    python3 tdm_config.py --file my_config.txt
"""

import socket
import argparse
import sys
import time

FPGA_IP   = "192.168.200.1"
FPGA_PORT = 24


def load_cmds(path: str):
    """读取 txt 文件，返回 64-bit 整数列表"""
    cmds = []
    with open(path, "r") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                val = int(line, 16)
            except ValueError:
                print(f"  [line {lineno}] 跳过: {line!r}")
                continue
            if not (0 <= val <= 0xFFFFFFFFFFFFFFFF):
                print(f"  [line {lineno}] 超出 64-bit 范围, 跳过")
                continue
            cmds.append(val)
    return cmds


def main():
    parser = argparse.ArgumentParser(description="TDM SiTCPXG 寄存器配置发送")
    parser.add_argument("--file", default="tdm_config.txt",
                        help="配置文件路径 (默认: %(default)s)")
    parser.add_argument("--ip",   default=FPGA_IP,
                        help="FPGA IP (默认: %(default)s)")
    parser.add_argument("--port", default=FPGA_PORT, type=int,
                        help="TCP 端口 (默认: %(default)s)")
    args = parser.parse_args()

    cmds = load_cmds(args.file)
    if not cmds:
        print("无有效配置数据, 退出")
        sys.exit(1)

    print(f"读取 {len(cmds)} 条 64-bit 配置指令")
    print(f"连接 {args.ip}:{args.port} ...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.connect((args.ip, args.port))
    except Exception as e:
        print(f"连接失败: {e}")
        sys.exit(1)

    print("已连接, 开始发送...\n")
    payload = bytearray()
    for i, val in enumerate(cmds):
        payload += val.to_bytes(8, "big")
        print(f"  [{i:3d}]  0x{val:016X}")
    print()

    sock.sendall(bytes(payload))
    sock.close()
    print(f"发送完毕, 共 {len(cmds)} 条指令, {len(payload)} 字节")


if __name__ == "__main__":
    main()
