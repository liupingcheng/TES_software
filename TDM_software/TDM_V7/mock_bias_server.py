import socket
import threading
import struct
import time
import argparse

CMD_NAMES = {
    0x0: "CMD_CTRL (Wave Type)",
    0x1: "CMD_FREQ_L",
    0x2: "CMD_FREQ_H",
    0x3: "CMD_AMP",
    0x4: "CMD_OFFSET",
    0x5: "CMD_EDIT_IDX (Channel Select)"
}

WAVE_TYPES = {
    0: "DC",
    1: "Triangle",
    2: "Square",
    3: "Sine"
}

def parse_packet(packet_bytes):
    if len(packet_bytes) != 4:
        return "Invalid packet length"
    
    val = struct.unpack('>I', packet_bytes)[0]
    
    header = (val >> 28) & 0xF
    chip_id = (val >> 24) & 0xF
    cmd = (val >> 20) & 0xF
    data = val & 0xFFFFF
    
    hex_str = packet_bytes.hex().upper()
    hex_formatted = " ".join([hex_str[i:i+2] for i in range(0, len(hex_str), 2)])
    
    if header != 0xA:
        return f"[{hex_formatted}] ERROR: Invalid Header {hex(header)}"
        
    cmd_name = CMD_NAMES.get(cmd, f"UNKNOWN({hex(cmd)})")
    
    details = f"Data={data} (0x{data:05X})"
    if cmd == 0x0: # CTRL / 类型
        wtype = WAVE_TYPES.get(data, "Unknown")
        details = f"Waveform={wtype} ({data})"
    elif cmd == 0x5: # 编辑索引 (Channel Select)
        details = f"Channel={data}"
    
    return f"[{hex_formatted}] Chip={chip_id} | Cmd={cmd_name.ljust(25)} | {details}"

def handle_client(conn, addr, server_ip):
    print(f"\n[+] {server_ip} accepted connection from {addr}")
    freq_h = 0
    freq_l = 0
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
                
            print(f"\n[{server_ip}] Received {len(data)} bytes:")
            
            # 数据包固定为4字节
            for i in range(0, len(data), 4):
                chunk = data[i:i+4]
                if len(chunk) == 4:
                    parsed = parse_packet(chunk)
                    print(f"  {parsed}")
                    
                    # 如果接收到 H 和 L 频率字节，尝试重组出真实频率值
                    val = struct.unpack('>I', chunk)[0]
                    cmd = (val >> 20) & 0xF
                    val_data = val & 0xFFFFF
                    if cmd == 0x1:
                        freq_l = val_data
                    elif cmd == 0x2:
                        freq_h = val_data
                        ftw = (freq_h << 20) | freq_l
                        freq_hz = (ftw * 100_000_000) / (2**32)
                        print(f"      -> Reconstructed Freq: {freq_hz:.2f} Hz (FTW=0x{ftw:08X})")
                else:
                    print(f"  [Partial chunk, length={len(chunk)}] {chunk.hex()}")
                    
    except ConnectionResetError:
        print(f"[-] {server_ip} Connection reset by peer")
    except Exception as e:
        print(f"[-] {server_ip} Error: {e}")
    finally:
        conn.close()
        print(f"[-] {server_ip} Connection closed")

def start_server(ip, port):
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((ip, port))
        server.listen(5)
        print(f"[*] Mock Bias Board Server listening on {ip}:{port}")
        
        while True:
            conn, addr = server.accept()
            client_thread = threading.Thread(target=handle_client, args=(conn, addr, ip))
            client_thread.daemon = True
            client_thread.start()
    except Exception as e:
        print(f"[!] Failed to start server on {ip}:{port} - {e}")

if __name__ == "__main__":
    servers = [
        ("127.0.0.1", 8024),
        ("127.0.0.1", 8025),
        ("127.0.0.1", 8026)
    ]
    
    print("========================================")
    print("   TDM Bias Mock Hardware Simulator     ")
    print("========================================")
    print("To test, set V6 software IP and Port to:")
    for ip, port in servers:
        print(f" - IP: {ip} | Port: {port}")
    print("========================================\n")
    
    threads = []
    for ip, port in servers:
        t = threading.Thread(target=start_server, args=(ip, port))
        t.daemon = True
        t.start()
        threads.append(t)
        
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down mock servers.")
