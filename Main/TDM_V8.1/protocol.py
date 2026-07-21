import struct

class TDMProtocol:
    """16字节二进制通信协议打包"""
    CMD_WRITE = 0x01
    
    # 板卡 ID 映射
    BOARD_BIAS1 = 0x01
    BOARD_BIAS2 = 0x02
    BOARD_BIAS3 = 0x03
    BOARD_FPGA = 0x07 
    
    # 参数 ID 映射
    PARAM_ENABLE   = 0x01  # 通道开关 (0/1)
    PARAM_TES_V    = 0x02  # TES 偏置电压
    PARAM_SA_IB    = 0x03  # SQUID 偏置电流 (μA)
    PARAM_SA_PHIX  = 0x04  # SQUID 磁通偏置 (μA)
    PARAM_VB       = 0x05  # VB 温度偏压
    PARAM_IS_I     = 0x06  # IS 偏置电流 (μA)
    PARAM_IS_PHIB  = 0x07  # IS 磁通偏置 (μA)
    PARAM_AC_FREQ  = 0x10  # 交流频率
    PARAM_AC_AMP   = 0x11  # 交流幅值
    PARAM_WAVEFORM = 0x12  # 波形类型 (0=正弦 1=方波 2=三角)
    PARAM_DC_VALUE = 0x13  # 直流幅值
    PARAM_SIG_TYPE = 0x14  # 信号类型 (0=直流, 1=交流)
    
    @staticmethod
    def calc_crc16(data: bytes) -> int:
        """计算 CRC-16/CCITT False (多项式 0x1021，初始值 0xFFFF)"""
        crc = 0xFFFF
        for byte in data:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc = crc << 1
                crc &= 0xFFFF
        return crc
    
    @staticmethod
    def pack_frame(cmd_type, board_id, param_id, channel_state, row_id, col_id, value, is_float=True) -> bytes:
        """打包 16 字节数据帧"""
        # 限制为单字节范围 (0~255)
        row_id = int(row_id) & 0xFF
        col_id = int(col_id) & 0xFF
        channel_state = int(channel_state) & 0x01
        board_id = int(board_id) & 0xFF
        cmd_type = int(cmd_type) & 0xFF
        param_id = int(param_id) & 0xFF
        
        if is_float:
            frame_head = struct.pack('>BBBBBBBBfBB', 
                                     0xAA, 0x55,        # 0~1: SYNC
                                     cmd_type,          # 2: CMD_TYPE
                                     board_id,          # 3: BOARD_ID
                                     param_id,          # 4: PARAM_ID
                                     channel_state,     # 5: CHANNEL_STATE
                                     row_id,            # 6: ROW_ID
                                     col_id,            # 7: COL_ID
                                     float(value),      # 8~11: VALUE
                                     0x00, 0x00)        # 12~13: RESERVED
        else:
            frame_head = struct.pack('>BBBBBBBBIBB', 
                                     0xAA, 0x55, 
                                     cmd_type, board_id, param_id, channel_state, row_id, col_id,
                                     int(value), 0x00, 0x00)
                                     
        # 计算 Byte 2 到 Byte 13 的 CRC16 (共12字节)
        crc_val = TDMProtocol.calc_crc16(frame_head[2:])
        final_frame = frame_head + struct.pack('>H', crc_val)
        
        return final_frame 
