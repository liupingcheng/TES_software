import socket

s = socket.socket()
s.bind(('127.0.0.1', 5000))
s.listen(1)
print("【模拟FPGA板卡】已启动，端口 5000...")

while True:
    print("等待上位机连接...")
    conn, addr = s.accept()
    print(f"上位机 {addr} 连进来了！")
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                print("上位机正常断开。")
                break
            
            # 把收到的纯二进制流转化为 HEX 字符串打印出来
            hex_str = ' '.join([f'{b:02X}' for b in data])
            print(f"==> 收到指令包: {hex_str}")
            
            # 模拟 FPGA 处理完毕，回发一个简单的应答包 (比如 0xAA 0x55 0x04)
            conn.sendall(bytes([0xAA, 0x55, 0x04, 0x00]))
            
    except ConnectionResetError:
        print("上位机异常断开。")
    finally:
        conn.close()