# TDM_20r16c_3mode_SITCPXG 寄存器配置文档

## 概述

`TDM_20r16c_3mode_SITCPXG` 是 `TDM_20r16c_3mode` 的 SiTCPXG 版本，用 64-bit 寄存器写入替代 VIO 手动控制。

PC 通过 TCP 发送 64-bit 指令字：

```
User_data_rx[63:0] = {addr[7:0], data[55:0]}
```

- `addr`：寄存器地址（8 bit）
- `data`：寄存器数据（56 bit）

每次 `User_data_rx_valid=1` 时写入一个寄存器。

---

## 寄存器映射

### 0x00 — MODE（模式选择）

| Bits    | 名称      | 默认值 | 说明                              |
| ------- | --------- | ------ | --------------------------------- |
| [1:0]   | mode      | 0      | 0=TDM, 1=单cell高速PID, 2=ADC直通 |
| [12:8]  | mode1_row | 0      | Mode1 激活行 (0~19)               |
| [16:13] | mode1_col | 0      | Mode1 激活列 (0~15)               |

> **mode 必须优先于所有其它操作配置。**

### 0x01 — COUNTER_LIMIT（周期）

| Bits   | 名称          | 默认值     | 说明                                           |
| ------ | ------------- | ---------- | ---------------------------------------------- |
| [23:0] | counter_limit | 2500 (dec) | Mode0 行周期 / Mode1 方波周期（125MHz 时钟数） |

### 0x02 — AMP_FACTOR（PID 幅度）

| Bits   | 名称       | 默认值 | 说明             |
| ------ | ---------- | ------ | ---------------- |
| [31:0] | amp_factor | 0xA    | PID 输出右移因子 |

### 0x03 — DAC_ROW_SELEC（行选通电压）

| Bits   | 名称          | 默认值 | 说明                                 |
| ------ | ------------- | ------ | ------------------------------------ |
| [15:0] | dac_row_selec | 0xC070 | 行选通 DAC 输出电压（offset binary） |

### 0x04 — ADC_OFFSET（ADC 偏移）

| Bits   | 名称       | 默认值 | 说明                               |
| ------ | ---------- | ------ | ---------------------------------- |
| [15:0] | adc_offset | 0      | ADC 偏移，施加到 ADC_data + offset |

### 0x05 — DAC_OFFSET（DAC 偏移）

| Bits   | 名称       | 默认值 | 说明                    |
| ------ | ---------- | ------ | ----------------------- |
| [15:0] | dac_offset | 0      | DAC 偏移，加到 PID 输出 |

### 0x06 — KP（比例增益）

| Bits   | 名称 | 默认值 | 说明               |
| ------ | ---- | ------ | ------------------ |
| [31:0] | Kp   | 0      | 比例增益（固定点） |

### 0x07 — KI（积分增益）

| Bits   | 名称 | 默认值 | 说明               |
| ------ | ---- | ------ | ------------------ |
| [31:0] | Ki   | 0      | 积分增益（固定点） |

### 0x08 — TX_COL_SEL（上传列选择）

| Bits  | 名称   | 默认值 | 说明                    |
| ----- | ------ | ------ | ----------------------- |
| [3:0] | tx_col | 0      | 上传 FB 数据的列 (0~15) |

### 0x09 — WRITE_CTRL（参数写入触发）

| Bits    | 名称      | 默认值 | 说明                                          |
| ------- | --------- | ------ | --------------------------------------------- |
| [0]     | write_en  | 0      | 单个 cell 写入触发（0→1 脉冲, 用完清 0）     |
| [1]     | write_all | 0      | 全部 cell 广播写入触发（0→1 脉冲, 用完清 0） |
| [12:8]  | param_row | 0      | 写入目标行 (0~19)                             |
| [16:13] | param_col | 0      | 写入目标列 (0~15)                             |

> **write_en / write_all 是脉冲信号**——先写 1 触发，再写 0 复位，确保下次可以再次触发。

### 0x0A — TIMING（时序参数）

| Bits    | 名称         | 默认值 | 说明                     |
| ------- | ------------ | ------ | ------------------------ |
| [7:0]   | delay_factor | 0xFF   | 行选通 settle 延时因子   |
| [15:8]  | settle_begin | 0x1A   | PID 积分开始 settle 因子 |
| [23:16] | settle_end   | 0x1A   | PID 积分结束 settle 因子 |

### 0x0B — DFB_EN（使能 / 监控）

| Bits  | 名称     | 默认值 | 说明                             |
| ----- | -------- | ------ | -------------------------------- |
| [0]   | dfb_lock | 0      | DFB 使能，**必须最后写 1** |
| [7:4] | mon_col  | 0      | 监控/上传列地址 (0~15)           |

> **dfb_lock 是配置流程的最后一步**——所有参数、mode 配置完毕后才置 1。

---

## 寄存器速查表

| Addr | 名称          | 功能                    |
| ---- | ------------- | ----------------------- |
| 0x00 | MODE          | 模式 + Mode1 行列       |
| 0x01 | COUNTER_LIMIT | 周期                    |
| 0x02 | AMP_FACTOR    | PID 衰减                |
| 0x03 | DAC_ROW_SELEC | 行选通电压              |
| 0x04 | ADC_OFFSET    | ADC 偏移                |
| 0x05 | DAC_OFFSET    | DAC 偏移                |
| 0x06 | KP            | 比例增益                |
| 0x07 | KI            | 积分增益                |
| 0x08 | TX_COL_SEL    | 上传列                  |
| 0x09 | WRITE_CTRL    | 参数写入触发 + 行列地址 |
| 0x0A | TIMING        | delay / settle          |
| 0x0B | DFB_EN        | 使能 + 监控列           |

---

## 配置序列

```python
# === Step 1: 选模式 ===
write_reg(0x00, mode=0)

# === Step 2: 写全局参数 ===
write_reg(0x01, counter_limit=2500)
write_reg(0x02, amp_factor=0xA)
write_reg(0x03, dac_row=0xC070)
write_reg(0x0A, delay=0xFF, settle_beg=0x1A, settle_end=0x1A)

# === Step 3: 写 per-cell PID 参数 (row=5, col=3) ===
write_reg(0x06, Kp=0x1234)
write_reg(0x07, Ki=0x0567)
write_reg(0x04, adc_offset=256)
write_reg(0x05, dac_offset=512)

# === Step 4: 触发写入 pulse ===
write_reg(0x09, param_row=5, param_col=3, write_en=1)
write_reg(0x09, param_row=5, param_col=3, write_en=0)   # 清零，准备下次触发

# === Step 5: 选上传列 ===
write_reg(0x08, tx_col=0)

# === Step 6: 最后使能 DFB ===
write_reg(0x0B, dfb_lock=1, mon_col=0)
```

---

## 64-bit 指令字编码（Python 参考）

```python
def make_cmd(addr: int, **kwargs) -> int:
    data = 0
    if   addr == 0x00:
        data |= (kwargs.get('mode', 0)      & 0x3)  << 0
        data |= (kwargs.get('mode1_row', 0) & 0x1F) << 8
        data |= (kwargs.get('mode1_col', 0) & 0xF)  << 13
    elif addr == 0x01: data = kwargs.get('counter_limit', 2500) & 0xFFFFFF
    elif addr == 0x02: data = kwargs.get('amp_factor', 0xA) & 0xFFFFFFFF
    elif addr == 0x03: data = kwargs.get('dac_row', 0xC070) & 0xFFFF
    elif addr == 0x04: data = kwargs.get('adc_offset', 0) & 0xFFFF
    elif addr == 0x05: data = kwargs.get('dac_offset', 0) & 0xFFFF
    elif addr == 0x06: data = kwargs.get('Kp', 0) & 0xFFFFFFFF
    elif addr == 0x07: data = kwargs.get('Ki', 0) & 0xFFFFFFFF
    elif addr == 0x08: data = kwargs.get('tx_col', 0) & 0xF
    elif addr == 0x09:
        data |= (kwargs.get('write_en', 0)     & 0x1)  << 0
        data |= (kwargs.get('write_all', 0)    & 0x1)  << 1
        data |= (kwargs.get('param_row', 0)    & 0x1F) << 8
        data |= (kwargs.get('param_col', 0)    & 0xF)  << 13
    elif addr == 0x0A:
        data |= (kwargs.get('delay', 0xFF)     & 0xFF) << 0
        data |= (kwargs.get('settle_beg', 0x1A) & 0xFF) << 8
        data |= (kwargs.get('settle_end', 0x1A) & 0xFF) << 16
    elif addr == 0x0B:
        data |= (kwargs.get('dfb_lock', 0)     & 0x1)  << 0
        data |= (kwargs.get('mon_col', 0)      & 0xF)  << 4
    return (addr << 56) | data
```

---

## 与原始 TDM_20r16c_3mode 的差异

| 项目      | 原版（VIO）      | SiTCPXG 版               |
| --------- | ---------------- | ------------------------ |
| 控制方式  | Vivado VIO GUI   | TCP 64-bit 寄存器写入    |
| 寄存器数  | 18 个 VIO 探针   | 12 个寄存器（0x00~0x0B） |
| mode 配置 | 与其它参数同探针 | 独立寄存器 0x00          |
| write_en  | 与 mode 同探针   | 独立寄存器 0x09          |
| dfb_lock  | VIO 探针         | 独立寄存器 0x0B          |
| 数据监控  | VIO / ILA 探针   | User_data_tx 上传选定列  |
