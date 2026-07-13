import struct

class ProtocolEncoder:
    """
    Encodes control commands into 32-bit Big-Endian integers
    Format: Header(4) | Chip_ID(4) | Command(4) | Data(20)
    Header = 0xA
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
        Pack a single command packet.
        :param chip_id: 0-5
        :param cmd: 0-5
        :param data: Integer data (width depends on cmd, max 20 bits)
        :return: bytes object (4 bytes) ready to send
        """
        chip_id &= 0xF
        cmd &= 0xF
        data &= 0xFFFFF # 20 bits max
        
        val = (ProtocolEncoder.HEADER << 28) | (chip_id << 24) | (cmd << 20) | data
        return struct.pack('>I', val)

    @staticmethod
    def calc_ftw(freq_hz, sys_clk_hz=100_000_000):
        # FTW = (Fout * 2^32) / Fclk
        ftw = int((freq_hz * (2**32)) / sys_clk_hz)
        return ftw & 0xFFFFFFFF

    @staticmethod
    def calc_amp_reg(amp_norm):
        """
        Convert normalized amplitude (0.0 - 1.0) to register value (0 - 65535)
        """
        val = int(amp_norm * 65535)
        return max(0, min(65535, val))

    @staticmethod
    def calc_offset_reg(offset_mA):
        """
        Convert Offset (0 - 20mA) to register value (0 - 65535)
        Assuming mapping: 0mA -> 0, 20mA -> 65535 (Linear)
        Adjust mapping if DAC range is different (e.g. 4-20mA or Voltage DAC)
        User specified: "offset input range 0~20mA".
        """
        # Mapping 0-20mA to 0-65535
        # 1mA = 65535 / 20 = 3276.75
        val = int((offset_mA / 20.0) * 65535)
        return max(0, min(65535, val))

    @staticmethod
    def commands_for_channel_config(chip_id, ch_idx, wtype, freq_hz, amp_norm, offset_mA, sys_clk=100_000_000):
        packets = []
        
        # 1. Select Channel
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_EDIT_IDX, ch_idx))
        
        # 2. Set Type
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_CTRL, wtype))
        
        # 3. Set Frequency
        ftw = ProtocolEncoder.calc_ftw(freq_hz, sys_clk)
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_FREQ_L, ftw & 0xFFFFF))
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_FREQ_H, (ftw >> 20) & 0xFFF))
        
        # 4. Set Amp (Converted from normalized 0-1.0)
        amp_reg = ProtocolEncoder.calc_amp_reg(amp_norm)
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_AMP, amp_reg))
        
        # 5. Set Offset (Converted from 0-20mA)
        offset_reg = ProtocolEncoder.calc_offset_reg(offset_mA)
        packets.append(ProtocolEncoder.pack_packet(chip_id, ProtocolEncoder.CMD_OFFSET, offset_reg))
        
        return b''.join(packets)

