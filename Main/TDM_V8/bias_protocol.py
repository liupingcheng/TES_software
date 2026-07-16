import struct


# Bias 固件 CMD_CTRL 的波形编号。UI、协议测试和 Mock Server 共用此映射，
# 避免下拉框顺序与调试端解析含义不一致。
WAVE_TYPES = {
    0: "Sine",
    1: "Square",
    2: "Triangle",
    3: "DC",
}

class ProtocolEncoder:
    """
    将控制指令编码为 32 位大端整数。
    格式: Header(4) | Chip_ID(4) | Command(4) | Data(20)
    Header 恒定为 0xA
    """
    HEADER = 0xA
    
    CMD_CTRL     = 0x0
    CMD_FREQ_L   = 0x1
    CMD_FREQ_H   = 0x2
    CMD_AMP      = 0x3
    CMD_OFFSET   = 0x4
    CMD_EDIT_IDX = 0x5

    @staticmethod
    def pack_packet(chip_id, cmd, data):
        """
        打包单条指令。
        :param chip_id: 芯片 ID (0-5)
        :param cmd: 指令类型 (0-5)
        :param data: 指令数据 (最大 20 位)
        :return: 编码后的 4 字节数据包 (bytes)
        """
        chip_id &= 0xF
        cmd &= 0xF
        data &= 0xFFFFF
        
        val = (ProtocolEncoder.HEADER << 28) | (chip_id << 24) | (cmd << 20) | data
        return struct.pack('>I', val)

    @staticmethod
    def calc_ftw(freq_hz, sys_clk_hz=100_000_000):
        ftw = int((freq_hz * (2**32)) / sys_clk_hz)
        return ftw & 0xFFFFFFFF

    @staticmethod
    def calc_amp_reg(amp_norm):
        """
        将归一化幅值 (0.0 - 1.0) 转换为寄存器值 (0 - 65535)。
        """
        val = int(amp_norm * 65535)
        return max(0, min(65535, val))

    @staticmethod
    def calc_offset_reg(offset_mA):
        """
        将偏置电流 (0 - 20mA) 转换为寄存器值 (0 - 65535)。
        """
        val = int((offset_mA / 20.0) * 65535)
        return max(0, min(65535, val))

    @staticmethod
    def commands_for_channel_config(chip_id, ch_idx, wtype, freq_hz, amp_norm, offset_mA, sys_clk=100_000_000):
        packets = []
        
        # 1. 选中通道
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_EDIT_IDX, ch_idx))
        
        # 2. 设置波形类型
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_CTRL, wtype))
        
        # 3. 设置频率
        ftw = ProtocolEncoder.calc_ftw(freq_hz, sys_clk)
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_FREQ_L, ftw & 0xFFFFF))
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_FREQ_H, (ftw >> 20) & 0xFFF))
        
        # 4. 设置幅值
        amp_reg = ProtocolEncoder.calc_amp_reg(amp_norm)
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_AMP, amp_reg))
        
        # 5. 设置偏置
        offset_reg = ProtocolEncoder.calc_offset_reg(offset_mA)
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_OFFSET, offset_reg))
        
        return b''.join(packets)

