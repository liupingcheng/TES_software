# V8 配置发送虚拟硬件测试

## 1. 准备两个固定虚拟IP（macOS，仅需设置一次）

参考脚本连接 `192.168.10.16:5024`。V8的DFB ADC测试连接
`192.168.104.1:5024`，并将本机地址绑定为 `192.168.104.2`。没有真实设备时，
先把这三个地址临时添加到macOS回环接口：

```bash
sudo ifconfig lo0 alias 192.168.10.16 255.255.255.255
sudo ifconfig lo0 alias 192.168.104.1 255.255.255.255
sudo ifconfig lo0 alias 192.168.104.2 255.255.255.255
```

如果提示地址已经存在，可以忽略对应提示。不要在连接相同地址的真实硬件时使用这些回环别名。

## 2. 第一个窗口：启动参考脚本虚拟板卡

```bash
cd "/Users/liupingcheng/Nutstore Files/.symlinks/坚果云/AI/project/TES/TES_software/Main/tests"
/opt/anaconda3/envs/myroot/bin/python virtual_reference_adc_board.py
```

该窗口固定监听 `192.168.10.16:5024`，与参考脚本中的地址完全一致。

## 3. 第二个窗口：启动V8虚拟DFB ADC板卡

```bash
cd "/Users/liupingcheng/Nutstore Files/.symlinks/坚果云/AI/project/TES/TES_software/Main/tests"
/opt/anaconda3/envs/myroot/bin/python virtual_v8_adc_board.py
```

该窗口固定监听 `192.168.104.1:5024`。

两块虚拟板卡除监听IP外完全一致：均使用端口 `5024`、4字节命令、确认值
`A5A50001`、相同回复时机，以及同一个参考ADC配置文件快照进行逐条校验。

## 4. 分别运行参考脚本和V8

在第三个终端直接运行未修改的参考脚本：

```bash
cd "/Users/liupingcheng/Nutstore Files/.symlinks/坚果云/AI/project/TES/TES_software/ref/AD_DA_SPI_config"
/opt/anaconda3/envs/myroot/bin/python adc_board_tcp_send.py adc_configuration.txt
```

V8保持DFB ADC默认网络参数：

| IP Address | Port | Local IP |
| --- | ---: | --- |
| `192.168.104.1` | `5024` | `192.168.104.2` |

在V8中点击DFB ADC的 `Connect`，再点击居中的 `ADC板卡寄存器配置`。两个虚拟板卡窗口会分别显示参考脚本和V8实际发送的命令值与时间，互不干扰。

## 5. 测试结束后删除临时IP

先按 `Ctrl+C` 停止两个虚拟板卡，再运行：

```bash
sudo ifconfig lo0 -alias 192.168.10.16
sudo ifconfig lo0 -alias 192.168.104.1
sudo ifconfig lo0 -alias 192.168.104.2
```

## 6. 可选：启动四块本机高端口虚拟板卡

打开一个终端：

```bash
cd "/Users/liupingcheng/Nutstore Files/.symlinks/坚果云/AI/project/TES/TES_software/Main/tests"
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py
```

脚本默认创建四个本机 TCP 服务：

| V8 板卡 | IP Address | Port | Local IP | 命令宽度 |
| --- | --- | ---: | --- | ---: |
| DFB ADC板卡 | `127.0.0.1` | `5104` | `127.0.0.1` | 4字节 |
| DFB DAC板卡 | `127.0.0.1` | `5105` | `127.0.0.1` | 4字节 |
| 选通 DAC板卡 | `127.0.0.1` | `5106` | `127.0.0.1` | 4字节 |
| FPGA算法板卡 | `127.0.0.1` | `5200` | `127.0.0.1` | 默认4字节（时钟） |

## 7. 在 V8 中连接本机高端口板卡

1. 打开“板卡连接”或“时钟/AD/DA配置”页面。
2. 按上表修改对应板卡的 IP、Port 和 Local IP。
3. 每个修改过的输入框都按 `Enter` 确认。
4. 点击对应板卡的 `Connect`。
5. 点击该板卡居中的配置按钮。

虚拟板卡会为每条命令自动返回4字节确认 `A5A50001`，因此V8会继续发送下一条命令。

## 8. 查看结果

虚拟板卡终端会实时显示类似内容：

```text
[2026-07-17T10:56:17.796+02:00] [DFB ADC板卡] RX #0001 连接后=0.000s 间隔=0.000s 4B HEX=10000080 expected=10000080 校验=一致 ACK=A5A50001
[2026-07-17T10:56:17.901+02:00] [DFB ADC板卡] RX #0002 连接后=0.106s 间隔=0.105s 4B HEX=10000000 expected=10000000 校验=一致 ACK=A5A50001
```

- 方括号中的第一项是命令到达虚拟板卡的本地时间，精确到毫秒。
- `连接后` 是从本次TCP连接建立到该命令到达的时间。
- `间隔` 是本条与上一条命令之间的时间。
- `HEX` 是V8通过TCP实际发送的原始值。
- `expected` 是配置文件中对应的预期值。
- `校验=一致` 表示值和顺序都符合配置文件。
- `ACK` 是虚拟板卡返回给V8的4字节确认。

测试完成后按 `Ctrl+C` 停止虚拟板卡。

## 9. 保存CSV记录

```bash
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py \
  --log virtual_board_capture.csv
```

CSV会记录板卡、连接编号、序号、接收时间、间隔、实际Hex、预期Hex和校验结果。

## 10. 测试 FPGA JESD 的8字节命令

时钟和JESD共用FPGA连接，但命令宽度不同。测试JESD时先停止原虚拟板卡，再运行：

```bash
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py \
  --only fpga \
  --fpga-word-bytes 8
```

V8中的FPGA连接仍使用 `127.0.0.1:5200`，连接后点击 `JESD 配置`。当前JESD文件为空时V8不会发送；需要先在 `../TDM_V8/config_files/JESD_configuration.txt` 中加入每行16个Hex字符的实际配置。

## 11. 验证3秒无回复超时

```bash
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py --only adc --no-ack
```

连接 `127.0.0.1:5104` 后点击ADC配置。虚拟板卡会显示收到第一条命令，但不返回确认；V8应在约3秒后停止并报告等待回复超时。

## 12. 只启动一块板卡

```bash
# ADC
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py --only adc

# DFB DAC
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py --only dfb-dac

# 选通 DAC
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py --only gate-dac

# FPGA时钟
/opt/anaconda3/envs/myroot/bin/python virtual_adda_hardware.py --only fpga
```

若要重复测试同一配置，建议先在V8中断开再重新连接，这样虚拟板卡的接收序号和预期值序号会从1重新开始。
