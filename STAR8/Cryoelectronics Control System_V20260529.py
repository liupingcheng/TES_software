import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import numpy as np
import json
import os
import datetime
import serial
import serial.tools.list_ports
from threading import Thread, Lock
import time
import queue
from collections import deque

class SerialCommunication:
    """串口通信管理类"""
    def __init__(self, gui_callback=None):
        self.serial_port = None
        self.baud_rate = None
        self.port_name = None
        self.is_connected = False
        self.gui_callback = gui_callback
        self.receive_thread = None
        self.receive_queue = queue.Queue()
        self.send_queue = queue.Queue()
        self.running = False
        self.lock = Lock()
        
        # 命令队列
        self.command_queue = deque()
        self.command_lock = Lock()
        
        # 通信参数
        self.timeout = 1.0
        self.write_timeout = 1.0
        
    def get_available_ports(self):
        """获取可用串口列表"""
        ports = []
        try:
            available_ports = serial.tools.list_ports.comports()
            for port in available_ports:
                ports.append(port.device)
        except Exception as e:
            print(f"获取串口列表错误: {e}")
        return ports
    
    def connect(self, port, baud_rate):
        """连接串口"""
        try:
            with self.lock:
                if self.serial_port and self.serial_port.is_open:
                    self.serial_port.close()
                
                self.serial_port = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_EVEN,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    write_timeout=self.write_timeout
                )
                
                self.port_name = port
                self.baud_rate = baud_rate
                self.is_connected = True
                
                # 启动接收线程
                self.running = True
                self.receive_thread = Thread(target=self._receive_loop, daemon=True)
                self.receive_thread.start()
                
                # 启动发送线程
                self.send_thread = Thread(target=self._send_loop, daemon=True)
                self.send_thread.start()
                
                # 启动命令处理线程
                self.command_thread = Thread(target=self._command_processor, daemon=True)
                self.command_thread.start()
                
                if self.gui_callback:
                    self.gui_callback("connection_update", {"connected": True, "port": port})
                
                return True
                
        except Exception as e:
            print(f"串口连接失败: {e}")
            if self.gui_callback:
                self.gui_callback("connection_error", {"error": str(e)})
            return False
    
    def disconnect(self):
        """断开串口连接"""
        self.running = False
        self.is_connected = False
        
        # 将真正阻塞的串口关闭操作放到独立的后台线程里，防止GUI卡死
        def _close_serial():
            try:
                with self.lock:
                    if self.serial_port and self.serial_port.is_open:
                        self.serial_port.close()
            except Exception as e:
                print(f"关闭串口时发生错误: {e}")
                
        Thread(target=_close_serial, daemon=True).start()
            
        if self.gui_callback:
            self.gui_callback("connection_update", {"connected": False, "port": None})
    
    def send_command(self, command, response_callback=None, timeout=2.0):
        """发送命令到设备"""
        if not self.is_connected or not self.serial_port:
            print("串口未连接")
            return False
        
        try:
            # 添加命令到队列
            with self.command_lock:
                command_data = {
                    'command': command + '\r\n',  # 添加换行符
                    'timestamp': time.time(),
                    'callback': response_callback,
                    'timeout': timeout
                }
                self.command_queue.append(command_data)
            
            return True
            
        except Exception as e:
            print(f"发送命令失败: {e}")
            return False
    
    def _command_processor(self):
        """命令处理线程"""
        pending_commands = {}
        
        while self.running:
            try:
                # 处理命令队列
                with self.command_lock:
                    if self.command_queue:
                        command_data = self.command_queue.popleft()
                        
                        # 发送命令
                        with self.lock:
                            if self.serial_port and self.serial_port.is_open:
                                self.serial_port.write(command_data['command'].encode('utf-8'))
                                self.serial_port.flush()
                                
                                # 将命令添加到待处理列表
                                pending_commands[command_data['timestamp']] = {
                                    'command': command_data['command'].strip(),
                                    'callback': command_data['callback'],
                                    'expire_time': time.time() + command_data['timeout']
                                }
                
                # 清理过期的命令
                current_time = time.time()
                expired = [k for k, v in pending_commands.items() 
                          if current_time > v['expire_time']]
                for key in expired:
                    if pending_commands[key]['callback']:
                        pending_commands[key]['callback'](None, "响应超时")
                    del pending_commands[key]
                
                time.sleep(0.01)  # 减少CPU占用
                
            except Exception as e:
                print(f"命令处理错误: {e}")
                time.sleep(0.1)
    
    def _receive_loop(self):
        """接收数据线程"""
        buffer = ""
        
        while self.running:
            try:
                with self.lock:
                    if self.serial_port and self.serial_port.is_open:
                        if self.serial_port.in_waiting > 0:
                            data = self.serial_port.read(self.serial_port.in_waiting)
                            buffer += data.decode('utf-8', errors='ignore')
                            
                            # 按行分割
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                line = line.strip()
                                if line:
                                    self.receive_queue.put(line)
                                    
                                    # 调用GUI回调
                                    if self.gui_callback:
                                        self.gui_callback("data_received", {"data": line})
            
                time.sleep(0.01)
                
            except Exception as e:
                print(f"接收数据错误: {e}")
                time.sleep(0.1)
    
    def _send_loop(self):
        """发送数据线程"""
        while self.running:
            try:
                if not self.send_queue.empty():
                    data = self.send_queue.get()
                    with self.lock:
                        if self.serial_port and self.serial_port.is_open:
                            self.serial_port.write(data.encode('utf-8'))
            except Exception as e:
                print(f"发送数据错误: {e}")
            time.sleep(0.01)
    
    def get_data(self):
        """从队列获取接收到的数据"""
        data = []
        while not self.receive_queue.empty():
            data.append(self.receive_queue.get())
        return data
    
    def send_raw_data(self, data):
        """发送原始数据"""
        if self.is_connected and self.serial_port:
            self.send_queue.put(data)
            return True
        return False

class StarCryoControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Cryoelectronics Control System")
        self.root.geometry("1400x900")
        self.root.configure(bg="#f0f0f0")
        
        # 初始化串口通信
        self.serial_comm = SerialCommunication(gui_callback=self.serial_callback)
        
        # 系统状态变量
        self.current_channel = 1
        self.max_channels = 8
        self.pci_type = "PCI-1000"
        self.squid_states = {i: "TUNE" for i in range(1, self.max_channels+1)}
        self.array_states = {i: "TUNE" for i in range(1, self.max_channels+1)}
        
        # 数据保存相关变量
        self.file_path = None
        self.data_history = []
        self.is_modified = False
        self.auto_save_interval = 300000
        
        # 串口数据记录
        self.serial_log = deque(maxlen=1000)  # 记录最近1000条数据
        
        # 开关状态变量
        self.test_signal_enabled = tk.BooleanVar(value=False)
        self.heater_enabled = tk.BooleanVar(value=False)
        
        # 添加滚动条和主容器
        self.canvas = tk.Canvas(self.root, bg="#f0f0f0")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.main_container = ttk.Frame(self.canvas)
        self.canvas_window_id = self.canvas.create_window((0, 0), window=self.main_container, anchor="nw")
        
        def _configure_canvas(event):
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        def _configure_window(event):
            if self.canvas.winfo_width() > self.main_container.winfo_reqwidth():
                self.canvas.itemconfig(self.canvas_window_id, width=self.canvas.winfo_width())
        
        self.main_container.bind("<Configure>", _configure_canvas)
        self.canvas.bind("<Configure>", _configure_window)
        
        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                self.canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                self.canvas.yview_scroll(-1, "units")
                
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        self.root.bind_all("<Button-4>", _on_mousewheel)
        self.root.bind_all("<Button-5>", _on_mousewheel)
        
        # 创建主布局
        self.create_main_layout()
        
        # 创建串口监控窗口
        self.create_serial_monitor()
        
        # 绑定热键
        self.bind_hotkeys()
        
        # 设置自动保存
        self.schedule_auto_save()
        
        # 设置退出事件处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 启动串口数据更新定时器
        self.update_serial_data()
    
    def create_main_layout(self):
        # 主面板分为四个区域：控制区、调谐区、配置区、串口区
        main_frame = ttk.Frame(self.main_container, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建左侧面板（控制区）
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        # 1. 串口连接配置 - 放在左侧最上方
        serial_frame = ttk.LabelFrame(left_frame, text="串口连接", padding="10")
        serial_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 串口连接状态
        self.connection_status = tk.StringVar(value="未连接")
        status_label = ttk.Label(serial_frame, textvariable=self.connection_status, 
                                foreground="red", font=("Arial", 10, "bold"))
        status_label.pack(pady=5)
        
        # 串口参数设置
        param_frame = ttk.Frame(serial_frame)
        param_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(param_frame, text="串口:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.serial_port_var = tk.StringVar()
        self.serial_port_combo = ttk.Combobox(param_frame, textvariable=self.serial_port_var, width=15)
        self.serial_port_combo.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Button(param_frame, text="刷新", command=self.refresh_serial_ports, width=6).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(param_frame, text="波特率:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.baud_rate_var = tk.StringVar(value="9600")
        baud_combo = ttk.Combobox(param_frame, textvariable=self.baud_rate_var, 
                                values=["9600", "19200", "38400", "57600", "115200"], width=15)
        baud_combo.grid(row=1, column=1, padx=5, pady=5)
        
        # 将测试按钮移至波特率同行的第2、3列
        ttk.Button(param_frame, text="测试连接", command=self.test_connection, width=8).grid(row=1, column=2, padx=5, pady=5)
        ttk.Button(param_frame, text="发送测试", command=self.send_test_command, width=8).grid(row=1, column=3, padx=5, pady=5)
        
        # 连接/断开按钮 (保持不变，删除了旧的测试按钮容器)
        btn_frame = ttk.Frame(serial_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(btn_frame, text="连接", command=self.connect_serial, width=10)
        self.connect_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="断开", command=self.disconnect_serial, 
                                        width=10, state="disabled")
        self.disconnect_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # 2. 控制区域
        control_frame = ttk.LabelFrame(left_frame, text="通道控制", padding="10")
        control_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 通道选择与状态显示
        self.channel_controls = []
        for i in range(1, self.max_channels+1):
            frame = ttk.Frame(control_frame, padding="5")
            frame.pack(fill=tk.X, pady=2)
            
            ch_label = ttk.Label(frame, text=f"Ch{i}")
            ch_label.grid(row=0, column=0, padx=5)
            
            squid_state = ttk.Label(frame, text="ST", width=3, relief="solid", background="yellow")
            squid_state.grid(row=0, column=1, padx=2)
            
            array_state = ttk.Label(frame, text="AT", width=3, relief="solid", background="yellow")
            array_state.grid(row=0, column=2, padx=2)
            
            select_var = tk.BooleanVar(value=(i == 1))
            select_btn = ttk.Checkbutton(frame, variable=select_var, command=lambda ch=i: self.select_channel(ch))
            select_btn.grid(row=0, column=3, padx=5)
            
            # 串口状态指示
            serial_indicator = ttk.Label(frame, text="●", width=1, foreground="red")
            serial_indicator.grid(row=0, column=4, padx=5)
            
            self.channel_controls.append({
                "frame": frame,
                "squid_state": squid_state,
                "array_state": array_state,
                "select_var": select_var,
                "select_btn": select_btn,
                "serial_indicator": serial_indicator
            })

       
        # # 模式控制按钮
        # mode_frame = ttk.LabelFrame(control_frame, text="模式控制", padding="10")
        # mode_frame.pack(fill=tk.X, pady=10)
        
        # ttk.Button(mode_frame, text="S-LOCK", command=self.s_lock).grid(row=0, column=0, padx=5, pady=5)
        # ttk.Button(mode_frame, text="S-TUNE", command=self.s_tune).grid(row=0, column=1, padx=5, pady=5)
        # ttk.Button(mode_frame, text="A-LOCK", command=self.a_lock).grid(row=1, column=0, padx=5, pady=5)
        # ttk.Button(mode_frame, text="A-TUNE", command=self.a_tune).grid(row=1, column=1, padx=5, pady=5)
        # ttk.Button(mode_frame, text="RESET", command=self.reset).grid(row=2, column=0, padx=5, pady=5)
        # ttk.Button(mode_frame, text="HEAT", command=self.heat).grid(row=2, column=1, padx=5, pady=5)
        
        # 创建中间面板（调谐区）
        center_frame = ttk.Frame(main_frame)
        center_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        # 3. 调制参数区域
        tune_frame = ttk.LabelFrame(center_frame, text="调制参数", padding="10")
        tune_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # SQUID调谐参数
        squid_frame = ttk.LabelFrame(tune_frame, text="SQUID 参数", padding="10")
        squid_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(squid_frame, text="S-BIAS (0~48.8 µA):").grid(row=0, column=0, sticky="w", pady=5)
        self.s_bias = tk.DoubleVar(value=0.0)
        ttk.Entry(squid_frame, textvariable=self.s_bias, width=10).grid(row=0, column=1, pady=5)
        ttk.Button(squid_frame, text="Set", command=lambda: self.set_parameter("s_bias")).grid(row=0, column=2, padx=5)
        
        ttk.Label(squid_frame, text="S-FLUX (0~48.8 µA):").grid(row=1, column=0, sticky="w", pady=5)
        self.s_flux = tk.DoubleVar(value=0.0)
        ttk.Entry(squid_frame, textvariable=self.s_flux, width=10).grid(row=1, column=1, pady=5)
        ttk.Button(squid_frame, text="Set", command=lambda: self.set_parameter("s_flux")).grid(row=1, column=2, padx=5)
        
        ttk.Button(squid_frame, text="COARSE/FINE", command=self.toggle_squid_step).grid(row=2, column=0, pady=5)
        ttk.Button(squid_frame, text="ZERO/RESTORE", command=self.zero_restore_squid).grid(row=2, column=1, pady=5)
        
        # 阵列调谐参数
        array_frame = ttk.LabelFrame(tune_frame, text="Array 参数", padding="10")
        array_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(array_frame, text="A-BIAS ((0~48.8 µA):").grid(row=0, column=0, sticky="w", pady=5)
        self.a_bias = tk.DoubleVar(value=0.0)
        ttk.Entry(array_frame, textvariable=self.a_bias, width=10).grid(row=0, column=1, pady=5)
        ttk.Button(array_frame, text="Set", command=lambda: self.set_parameter("a_bias")).grid(row=0, column=2, padx=5)
        
        ttk.Label(array_frame, text="A-FLUX (0~48.8 µA):").grid(row=1, column=0, sticky="w", pady=5)
        self.a_flux = tk.DoubleVar(value=0.0)
        ttk.Entry(array_frame, textvariable=self.a_flux, width=10).grid(row=1, column=1, pady=5)
        ttk.Button(array_frame, text="Set", command=lambda: self.set_parameter("a_flux")).grid(row=1, column=2, padx=5)
        
        ttk.Label(array_frame, text="OFFSET (±2500mV):").grid(row=2, column=0, sticky="w", pady=5)
        self.offset = tk.DoubleVar(value=0.0)
        ttk.Entry(array_frame, textvariable=self.offset, width=10).grid(row=2, column=1, pady=5)
        ttk.Button(array_frame, text="Set", command=lambda: self.set_parameter("offset")).grid(row=2, column=2, padx=5)
        
        ttk.Button(array_frame, text="COARSE/FINE", command=self.toggle_array_step).grid(row=3, column=0, pady=5)
        ttk.Button(array_frame, text="ZERO/RESTORE", command=self.zero_restore_array).grid(row=3, column=1, pady=5)
        
        # 新：模式控制按钮 (移至中间参数外侧的下方)
        mode_frame = ttk.LabelFrame(center_frame, text="模式控制", padding="10")  # <-- 这里把 tune_frame 改为了 center_frame
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 让两列均匀铺满
        mode_frame.columnconfigure(0, weight=1)
        mode_frame.columnconfigure(1, weight=1)
        
        ttk.Button(mode_frame, text="S-LOCK", command=self.s_lock).grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        ttk.Button(mode_frame, text="S-TUNE", command=self.s_tune).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(mode_frame, text="A-LOCK", command=self.a_lock).grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        ttk.Button(mode_frame, text="A-TUNE", command=self.a_tune).grid(row=1, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(mode_frame, text="RESET", command=self.reset).grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        ttk.Button(mode_frame, text="HEAT", command=self.heat).grid(row=2, column=1, padx=10, pady=5, sticky="ew")
        # 创建右侧面板（配置区）
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        
        # 4. 配置区域
        config_frame = ttk.LabelFrame(right_frame, text="系统配置", padding="10")
        config_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 反馈环路配置
        feedback_frame = ttk.LabelFrame(config_frame, text="反馈环路配置", padding="10")
        feedback_frame.pack(fill=tk.X, pady=5)
        
        # ttk.Label(feedback_frame, text="SENSITIVITY:").grid(row=0, column=0, sticky="w", pady=5)
        # self.sensitivity = tk.StringVar(value="High")
        # ttk.Combobox(feedback_frame, textvariable=self.sensitivity, 
        # values=["Low", "Medium", "High", "Select R&C"], width=12).grid(row=0, column=1, pady=5)
        # self.sensitivity = tk.StringVar(value="High")
        # self.integrator = tk.StringVar(value="1.5nF") #保持原有的积分电容选择，作为备用选项
        
        #新：input SQUID和SQUID Array选择
        ttk.Label(feedback_frame, text="Coil:").grid(row=0, column=0, sticky="w", pady=5)
        self.fb_target = tk.StringVar(value="SQUID Array")
        ttk.Combobox(feedback_frame, textvariable=self.fb_target, 
                    values=["SQUID Array", "Input SQUID"], width=12).grid(row=0, column=1, pady=5)       
        ttk.Label(feedback_frame, text="FEEDBACK:").grid(row=1, column=0, sticky="w", pady=5)
        self.feedback = tk.StringVar(value="100kΩ")
        ttk.Combobox(feedback_frame, textvariable=self.feedback, 
                    values=["10 kΩ","30 kΩ", "100 kΩ"], width=12).grid(row=1, column=1, pady=5)
        ttk.Button(feedback_frame, text="Set", command=self.set_feedback_resistor, width=5).grid(row=1, column=2, padx=5)
        
        ttk.Label(feedback_frame, text="PID Cap:").grid(row=2, column=0, sticky="w", pady=5)
        self.set_integrator = tk.StringVar(value="10 nF")
        ttk.Combobox(feedback_frame, textvariable=self.set_integrator, 
                    values=["10 nF", "100 nF"], width=12).grid(row=2, column=1, pady=5)
        ttk.Button(feedback_frame, text="Set", command=self.set_integrator, width=5).grid(row=2, column=2, padx=5)


        ttk.Label(feedback_frame, text="PID Res:").grid(row=3, column=0, sticky="w", pady=5)
        self.integrator = tk.StringVar(value="10 kΩ")
        ttk.Combobox(feedback_frame, textvariable=self.integrator, 
                    values=["10 kΩ", "20 kΩ"], width=12).grid(row=3, column=1, pady=5)
        ttk.Button(feedback_frame, text="Set", command=self.set_integrator, width=5).grid(row=3, column=2, padx=5)


        # 测试信号配置
        test_frame = ttk.LabelFrame(config_frame, text="测试信号配置", padding="10")
        test_frame.pack(fill=tk.X, pady=5)
        # 测试线圈选择 (下拉框) 
        ttk.Label(test_frame, text="TEST COIL:").grid(row=3, column=0, sticky="w", pady=5)
        self.test_coil_var = tk.StringVar(value="Array FB Coil")
        
        coil_combo = ttk.Combobox(test_frame, textvariable=self.test_coil_var, 
                                 values=["Array FB Coil", "SQUID FB Coil"], width=12)
        coil_combo.grid(row=3, column=1, pady=5)
        ttk.Button(test_frame, text="Set", command=self.set_test_coil, width=5).grid(row=3, column=2, padx=5)
            
        # ttk.Label(test_frame, text="TEST SIGNAL:").grid(row=0, column=0, sticky="w", pady=5)
        # self.test_signal_switch = ttk.Checkbutton(test_frame, text="Enabled", 
        #                                          variable=self.test_signal_enabled,
        #                                          command=self.toggle_test_signal)
        # self.test_signal_switch.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # ttk.Label(test_frame, text="TEST INPUT:").grid(row=1, column=0, sticky="w", pady=5)
        # self.test_input = tk.StringVar(value="Array Flux")
        # ttk.Combobox(test_frame, textvariable=self.test_input, 
        #             values=["SQUID Bias", "SQUID Flux", "Array Bias", "Array Flux"], width=12).grid(row=1, column=1, pady=5)
        
        # 加热器配置
        heater_frame = ttk.LabelFrame(config_frame, text="加热器配置", padding="10")
        heater_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(heater_frame, text="HEATER:").grid(row=0, column=0, sticky="w", pady=5)
        self.heater_switch = ttk.Checkbutton(heater_frame, text="Enabled", 
                                            variable=self.heater_enabled,
                                            command=self.toggle_heater)
        self.heater_switch.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(heater_frame, text="Heat Time (s):").grid(row=1, column=0, sticky="w", pady=5)
        self.heat_time = tk.DoubleVar(value=2.0)
        ttk.Entry(heater_frame, textvariable=self.heat_time, width=10).grid(row=1, column=1, pady=5)
        
        ttk.Label(heater_frame, text="Cool Time (s):").grid(row=2, column=0, sticky="w", pady=5)
        self.cool_time = tk.DoubleVar(value=5.0)
        ttk.Entry(heater_frame, textvariable=self.cool_time, width=10).grid(row=2, column=1, pady=5)
        
        ttk.Label(heater_frame, text="Group Size:").grid(row=3, column=0, sticky="w", pady=5)
        self.group_size = tk.IntVar(value=1)
        ttk.Combobox(heater_frame, textvariable=self.group_size, 
                    values=[1,2,3,4,5,6,7,8,9,10], width=5).grid(row=3, column=1, pady=5)
  
        # # 系统控制按钮
        # sys_frame = ttk.LabelFrame(config_frame, text="系统控制", padding="10")
        # sys_frame.pack(fill=tk.X, pady=5)
        
        # ttk.Button(sys_frame, text="REFRESH", command=self.refresh).pack(fill=tk.X, pady=2)
        # ttk.Button(sys_frame, text="MASTER", command=self.toggle_master).pack(fill=tk.X, pady=2)
        # ttk.Button(sys_frame, text="System Config", command=self.open_system_config).pack(fill=tk.X, pady=2)
        # ttk.Button(sys_frame, text="PCI Config", command=self.open_pci_config).pack(fill=tk.X, pady=2)
        
        # # 文件操作按钮
        # file_frame = ttk.LabelFrame(config_frame, text="文件操作", padding="10")
        # file_frame.pack(fill=tk.X, pady=5)
        
        # ttk.Button(file_frame, text="New File", command=self.new_file).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        # ttk.Button(file_frame, text="Open", command=self.open_file).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        # ttk.Button(file_frame, text="Save", command=self.save).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        # ttk.Button(file_frame, text="Save As", command=self.save_as).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        # ttk.Button(file_frame, text="Import Data", command=self.import_data).grid(row=2, column=0, padx=2, pady=2, sticky="ew")
        # ttk.Button(file_frame, text="Export Data", command=self.export_data).grid(row=2, column=1, padx=2, pady=2, sticky="ew")
        
        # 配置网格权重
        main_frame.grid_columnconfigure(0, weight=1)  # 左侧面板
        main_frame.grid_columnconfigure(1, weight=2)  # 中间面板
        main_frame.grid_columnconfigure(2, weight=1)  # 右侧面板
        main_frame.grid_rowconfigure(0, weight=1)
    
    def create_serial_monitor(self):
        """创建串口数据监控窗口"""
        # 1. 创建一个容纳底部所有元素的横向大容器
        bottom_main_frame = ttk.Frame(self.main_container)
        bottom_main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 2. 左侧：日志监控窗口
        monitor_frame = ttk.LabelFrame(bottom_main_frame, text="Operation Log & Serial Monitor", padding="10")
        monitor_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 3. 右侧：系统控制与文件操作的容器
        bottom_right_frame = ttk.Frame(bottom_main_frame)
        bottom_right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        # --- 将刚才删掉的控制按钮贴到右侧容器中 ---
        # 系统控制按钮 (2x2排列)
        sys_frame = ttk.LabelFrame(bottom_right_frame, text="系统控制", padding="10")
        sys_frame.pack(fill=tk.X, pady=(0, 5))
        sys_frame.columnconfigure(0, weight=1)
        sys_frame.columnconfigure(1, weight=1)
        
        ttk.Button(sys_frame, text="REFRESH", command=self.refresh).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(sys_frame, text="MASTER", command=self.toggle_master).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(sys_frame, text="System Config", command=self.open_system_config).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(sys_frame, text="PCI Config", command=self.open_pci_config).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        
        # 文件操作按钮 (2x3排列)
        file_frame = ttk.LabelFrame(bottom_right_frame, text="文件操作", padding="10")
        file_frame.pack(fill=tk.X, pady=5)
        file_frame.columnconfigure(0, weight=1)
        file_frame.columnconfigure(1, weight=1)
        file_frame.columnconfigure(2, weight=1)
        
        ttk.Button(file_frame, text="New File", command=self.new_file).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Open", command=self.open_file).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Save", command=self.save).grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Save As", command=self.save_as).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Import Data", command=self.import_data).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Export Data", command=self.export_data).grid(row=1, column=2, padx=2, pady=2, sticky="ew")
        toolbar = ttk.Frame(monitor_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(toolbar, text="Clear", command=self.clear_serial_monitor, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Start Recording", command=self.start_recording, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Stop Recording", command=self.stop_recording, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save Log", command=self.save_serial_log, width=8).pack(side=tk.LEFT, padx=2)
        
        # 数据显示区域
        self.serial_text = scrolledtext.ScrolledText(monitor_frame, height=9, width=100)
        self.serial_text.pack(fill=tk.BOTH, expand=True)
        self.serial_text.config(state=tk.DISABLED)
        
        # 状态栏
        status_frame = ttk.Frame(monitor_frame)
        status_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.rx_count = tk.IntVar(value=0)
        self.tx_count = tk.IntVar(value=0)
        
        ttk.Label(status_frame, text="RX:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.rx_count, foreground="green").pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(status_frame, text="TX:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.tx_count, foreground="blue").pack(side=tk.LEFT)
        
        # 记录状态
        self.recording = False
        self.record_file = None
        
    def serial_callback(self, event_type, data):
        """串口通信回调函数"""
        if event_type == "data_received":
            self.display_serial_data(f"← {data}", "receive")
            self.rx_count.set(self.rx_count.get() + 1)
        elif event_type == "connection_update":
            if data["connected"]:
                self.connection_status.set(f"Connected: {data['port']}")
                self.connect_btn.config(state="disabled")
                self.disconnect_btn.config(state="normal")
                self.display_serial_data(f"Successfully connected to port: {data['port']}", "system")
            else:
                self.connection_status.set("Disconnected")
                self.connect_btn.config(state="normal")
                self.disconnect_btn.config(state="disabled")
                self.display_serial_data("Serial connection disconnected", "system")
        elif event_type == "connection_error":
            self.connection_status.set(f"Connection failed: {data['error']}")
            self.connect_btn.config(state="normal")
            self.disconnect_btn.config(state="disabled")
            self.display_serial_data(f"Connection error: {data['error']}", "error")
    
    def refresh_serial_ports(self):
        """刷新串口列表"""
        ports = self.serial_comm.get_available_ports()
        self.serial_port_combo['values'] = ports
        if ports:
            self.serial_port_combo.set(ports[0])
    
    def connect_serial(self):
        """连接串口"""
        port = self.serial_port_var.get()
        baud_rate = int(self.baud_rate_var.get())
        
        if not port:
            messagebox.showerror("Error", "Please select a port")
            return
        
        success = self.serial_comm.connect(port, baud_rate)
        if success:
            self.display_serial_data(f"Connecting to port: {port} @ {baud_rate} baud", "system")
    
    def disconnect_serial(self):
        """断开串口连接"""
        self.serial_comm.disconnect()
    
    def test_connection(self):
        """测试连接"""
        if not self.serial_comm.is_connected:
            messagebox.showwarning("Warning", "Please connect to serial port first")
            return
        
        # 发送测试命令
        command = "*IDN?"
        self.send_serial_command(command, lambda response, error: 
            messagebox.showinfo("Test Result", f"Response: {response}" if response else f"Error: {error}"))
    
    def send_test_command(self):
        """发送测试命令"""
        if not self.serial_comm.is_connected:
            messagebox.showwarning("警告", "请先连接串口")
            return
        
        # 发送测试命令
        command = "TEST"
        self.send_serial_command(command)
    
    def send_serial_command(self, command, callback=None):
        """发送串口命令"""
        if not self.serial_comm.is_connected:
            messagebox.showwarning("Warning", "Please connect to serial port first")
            return
        
        # 显示发送的命令
        self.display_serial_data(f"→ TX: {command}", "send")
        self.tx_count.set(self.tx_count.get() + 1)
        
        # 发送命令
        if callback:
            self.serial_comm.send_command(command, callback)
        else:
            self.serial_comm.send_command(command)
    
    def display_serial_data(self, data, data_type="receive"):
        """在串口监控窗口显示数据"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        if data_type == "receive":
            tag = "receive"
            color = "green"
        elif data_type == "send":
            tag = "send"
            color = "blue"
        elif data_type == "error":
            tag = "error"
            color = "red"
        else:
            tag = "system"
            color = "gray"
        
        self.serial_text.config(state=tk.NORMAL)
        self.serial_text.insert(tk.END, f"[{timestamp}] {data}\n", tag)
        
        # 滚动到底部
        self.serial_text.see(tk.END)
        self.serial_text.config(state=tk.DISABLED)
        
        # 记录到日志
        self.serial_log.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "type": data_type,
            "data": data
        })
        
        # 如果正在记录，写入文件
        if self.recording and self.record_file:
            try:
                self.record_file.write(f"{datetime.datetime.now().isoformat()},{data_type},{data}\n")
                self.record_file.flush()
            except Exception as e:
                print(f"记录数据失败: {e}")
    
    def clear_serial_monitor(self):
        """清空串口监控窗口"""
        self.serial_text.config(state=tk.NORMAL)
        self.serial_text.delete(1.0, tk.END)
        self.serial_text.config(state=tk.DISABLED)
        self.rx_count.set(0)
        self.tx_count.set(0)
    
    def start_recording(self):
        """开始记录串口数据"""
        if self.recording:
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Save Serial Data Record",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                self.record_file = open(file_path, 'a', encoding='utf-8')
                self.record_file.write("timestamp,type,data\n")
                self.recording = True
                self.display_serial_data(f"Started recording to: {file_path}", "system")
            except Exception as e:
                messagebox.showerror("Error", f"Cannot create record file: {e}")
    
    def stop_recording(self):
        """停止记录串口数据"""
        if self.recording and self.record_file:
            self.recording = False
            self.record_file.close()
            self.record_file = None
            self.display_serial_data("Stopped recording", "system")
    
    def save_serial_log(self):
        """保存串口日志"""
        if not self.serial_log:
            messagebox.showinfo("Info", "No data to save")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Save Serial Log",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(list(self.serial_log), f, indent=2, ensure_ascii=False)
                self.display_serial_data(f"Log saved to: {file_path}", "system")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save log: {e}")
    
    def update_serial_data(self):
        """更新串口数据"""
        # 更新通道状态指示灯
        for i in range(self.max_channels):
            indicator = self.channel_controls[i]["serial_indicator"]
            if self.serial_comm.is_connected:
                # 如果已连接：勾选的通道为绿色通信状态，未勾选的为待机橙色
                if self.channel_controls[i]["select_var"].get():
                    indicator.config(foreground="green")
                else:
                    indicator.config(foreground="orange")
            else:
                # 如果未连接硬件，指示灯全部显红
                indicator.config(foreground="red")
                
        # 每秒更新一次
        self.update_timer = self.root.after(1000, self.update_serial_data)
    
    def toggle_channel_via_hotkey(self, channel):
        """通过快捷键切换通道勾选状态"""
        var_obj = self.channel_controls[channel-1]["select_var"]
        # 反转状态
        var_obj.set(not var_obj.get())
        self.select_channel(channel)
        
    def bind_hotkeys(self):
        # 热键绑定
        self.root.bind("<Alt-1>", lambda e: self.toggle_channel_via_hotkey(1))
        self.root.bind("<Alt-2>", lambda e: self.toggle_channel_via_hotkey(2))
        self.root.bind("<Alt-3>", lambda e: self.toggle_channel_via_hotkey(3))
        self.root.bind("<Alt-4>", lambda e: self.toggle_channel_via_hotkey(4))
        self.root.bind("<Alt-5>", lambda e: self.toggle_channel_via_hotkey(5))
        self.root.bind("<Alt-6>", lambda e: self.toggle_channel_via_hotkey(6))
        self.root.bind("<Alt-7>", lambda e: self.toggle_channel_via_hotkey(7))
        self.root.bind("<Alt-8>", lambda e: self.toggle_channel_via_hotkey(8))
        
        self.root.bind("l", lambda e: self.s_lock())
        self.root.bind("t", lambda e: self.s_tune())
        self.root.bind("<Alt-l>", lambda e: self.a_lock())
        self.root.bind("<Alt-t>", lambda e: self.a_tune())
        self.root.bind("r", lambda e: self.reset())
        self.root.bind("h", lambda e: self.heat())
        self.root.bind("x", lambda e: self.refresh())
        
        # 文件操作快捷键
        self.root.bind("<Control-n>", lambda e: self.new_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save())
        
        # 串口操作快捷键
        self.root.bind("<Control-c>", lambda e: self.connect_serial())
        self.root.bind("<Control-d>", lambda e: self.disconnect_serial())
        self.root.bind("<Control-r>", lambda e: self.refresh_serial_ports())
    
    def toggle_test_signal(self):
        """切换测试信号开关状态"""
        new_state = self.test_signal_enabled.get()
        command = f"TEST {1 if new_state else 0}"
        self.log_operation("Test Signal Toggled", {"state": "ON" if new_state else "OFF", "command": command})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            self.send_serial_command(command)
    
    def toggle_heater(self):
        """切换加热器开关状态"""
        new_state = self.heater_enabled.get()
        command = f"HEAT {1 if new_state else 0}"
        self.log_operation("Heater Toggled", {"state": "ON" if new_state else "OFF", "command": command})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            self.send_serial_command(command)
    
    def get_selected_channels(self):
        """获取当前所有选中的通道"""
        selected = []
        for i in range(self.max_channels):
            if self.channel_controls[i]["select_var"].get():
                selected.append(i + 1)
        if not selected:
            # 如果没有勾选任何通道，默认使用当前活动通道
            selected = [self.current_channel]
        return selected

    def select_channel(self, channel):
        """选择通道"""
        # 更新当前焦点通道
        self.current_channel = channel
        self.update_channel_display()
        
        is_selected = self.channel_controls[channel-1]["select_var"].get()
        action = "Selected Channel" if is_selected else "Deselected Channel"
        
        # command = f"CH {channel}"
        # self.log_operation(action, {"channel": channel, "command": command})
        
        # # 发送串口命令 (如果是选中操作)
        # if self.serial_comm.is_connected and is_selected:
        #     self.send_serial_command(command)
    
    def update_channel_display(self):
        """更新通道显示（模拟）"""
        pass
    
    def s_lock(self):
            """SQUID锁定模式 (Input SQUID)"""
            self.is_modified = True
            # 目标: Input SQUID (00001111) | 动作: 锁定 (11110000)
            data_16bit = "00001111" + "11110000"
            
            for ch in self.get_selected_channels():
                self.squid_states[ch] = "LOCK"
                self.update_state_indicators(ch)
                
                # 命令类型 "01"(反馈), 命令对象 "01"(锁定操作)
                bin_str, raw_bytes = self.build_fpga_command_binary("01", "01", ch, data_16bit)
                
                log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:24]} {bin_str[24:32]}"
                self.log_operation("S-LOCK", {"channel": ch, "BIN": log_display})
                
                if self.serial_comm.is_connected:
                    self.serial_comm.serial_port.write(raw_bytes)
                    time.sleep(0.01) # 连续发包时微小延时，防止串口塞满
        
    def s_tune(self):
        """SQUID调谐/解锁模式 (Input SQUID)"""
        self.is_modified = True
        # 目标: Input SQUID (00001111) | 动作: 非锁定 (00001111)
        data_16bit = "00001111" + "00001111"
        
        for ch in self.get_selected_channels():
            self.squid_states[ch] = "TUNE"
            self.update_state_indicators(ch)
            
            bin_str, raw_bytes = self.build_fpga_command_binary("01", "01", ch, data_16bit)
            
            log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:24]} {bin_str[24:32]}"
            self.log_operation("S-TUNE", {"channel": ch, "BIN": log_display})
            
            if self.serial_comm.is_connected:
                self.serial_comm.serial_port.write(raw_bytes)
                time.sleep(0.01)
    
    def a_lock(self):
        """阵列锁定模式 (Array)"""
        self.is_modified = True
        # 目标: Array (11110000) | 动作: 锁定 (11110000)
        data_16bit = "11110000" + "11110000"
        
        for ch in self.get_selected_channels():
            self.array_states[ch] = "LOCK"
            self.update_state_indicators(ch)
            
            bin_str, raw_bytes = self.build_fpga_command_binary("01", "01", ch, data_16bit)
            
            log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:24]} {bin_str[24:32]}"
            self.log_operation("A-LOCK", {"channel": ch, "BIN": log_display})
            
            if self.serial_comm.is_connected:
                self.serial_comm.serial_port.write(raw_bytes)
                time.sleep(0.01)
    
    def a_tune(self):
        """阵列调谐/解锁模式 (Array)"""
        self.is_modified = True
        # 目标: Array (11110000) | 动作: 非锁定 (00001111)
        data_16bit = "11110000" + "00001111"
        
        for ch in self.get_selected_channels():
            self.array_states[ch] = "TUNE"
            self.update_state_indicators(ch)
            
            bin_str, raw_bytes = self.build_fpga_command_binary("01", "01", ch, data_16bit)
            
            log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:24]} {bin_str[24:32]}"
            self.log_operation("A-TUNE", {"channel": ch, "BIN": log_display})
            
            if self.serial_comm.is_connected:
                self.serial_comm.serial_port.write(raw_bytes)
                time.sleep(0.01)
    
    def update_state_indicators(self, channel=None):
        """更新状态指示灯"""
        channels_to_update = [channel] if channel else self.get_selected_channels()
        
        for ch in channels_to_update:
            squid_state = self.squid_states[ch]
            array_state = self.array_states[ch]
            
            squid_label = self.channel_controls[ch-1]["squid_state"]
            array_label = self.channel_controls[ch-1]["array_state"]
            
            squid_label.config(
                text="SL" if squid_state == "LOCK" else "ST",
                background="green" if squid_state == "LOCK" else "yellow"
            )
            
            array_label.config(
                text="AL" if array_state == "LOCK" else "AT",
                background="green" if array_state == "LOCK" else "yellow"
            )
    
    def set_parameter(self, param):
            """设置偏置、磁通、偏移电压等参数"""
            physical_value = getattr(self, param).get()
            self.is_modified = True
            # 1. 极限限幅
            if param == "offset":
                # Offset: -2500mV 到 2500mV
                if physical_value > 2500.0:
                    physical_value = 2500.0
                    self.offset.set(2500.0)
                elif physical_value < -2500.0:
                    physical_value = -2500.0
                    self.offset.set(-2500.0)
                    
                unit = "mV"
                dac_code_float = 4096.0 * (physical_value + 2500.0) / 5000.0
                dac_code_int = int(dac_code_float)
                log_v_info = f"{physical_value:.1f}mV (Bipolar)"
                
            else:
                if physical_value > 48.828:
                    physical_value = 48.828
                    getattr(self, param).set(48.828)
                elif physical_value < 0.0:        
                    physical_value = 0.0          
                    getattr(self, param).set(0.0) 
                    
                unit = "µA"
                v_out = physical_value * 0.1024 
                #  Code = 4096 * (V_out / 5.0)
                dac_code_int = int(4096 * (v_out / 5.0))
                log_v_info = f"{v_out:.4f}V (Unipolar)"

            dac_code_int = max(0, min(4095, dac_code_int))
            dac_12bit = f"{dac_code_int:012b}" 
            
            # 1. DAC 计算 
            if param == "offset":
                # Voffset(mV) = 5000 * (DAC/4096) - 2500
                # 得到: DAC = 4096 * (Voffset + 2500) / 5000
                unit = "mV"
                dac_code_float = 4096.0 * (physical_value + 2500.0) / 5000.0
                dac_code_int = int(dac_code_float)
                
                log_v_info = f"{physical_value:.1f}mV (Bipolar)"
                
            else:
                # ---- Bias/Flux: 单极性 (Unipolar) ----
                unit = "µA"
                # 电流转电压绝对值 (I * 102.4k), V_ref = 5.0V
                v_out_abs = abs(physical_value) * 0.1024 
                # 单极性公式: Code = 4096 * (|V_out| / V_ref)
                dac_code_int = int(4096 * (v_out_abs / 5.0))
                
                log_v_info = f"|{v_out_abs:.4f}V| (Unipolar)"

            dac_code_int = max(0, min(4095, dac_code_int))
            dac_12bit = f"{dac_code_int:012b}" 


            # 2.  硬件映射 (DS2-DS0) 

            ds_map = {
                "s_bias": "110",  # DAC G 
                "s_flux": "001",  # DAC B  
                "a_bias": "100",  # DAC E 
                "a_flux": "101",   # DAC F
                "offset": "010"  # DAC C 
            }
            ds_3bit = ds_map.get(param, "000")

            # 3. 遍历通道，组装 A0 
            for ch in self.get_selected_channels():
                
                # 奇数通道 A0=1，偶数 A0=0
                a0_bit = "1" if ch % 2 != 0 else "0"
                
                # 组合 4 位 DAC 通道地址 (A0 + DS2~DS0)
                dac_addr_4bit = a0_bit + ds_3bit
                
                # 拼装 16-bit 数据：[12位DAC电压码] + [4位硬件地址]
                data_16bit = dac_12bit + dac_addr_4bit
                
                # 偏置相关的命令对象固定为 "00"
                cmd_obj = "00"  
                
                # 调用底层拼接函数 ("10" 代表偏置相关)
                bin_str, raw_bytes = self.build_fpga_command_binary("10", cmd_obj, ch, data_16bit)
                
                log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:28]} {bin_str[28:32]}"
                self.log_operation("Set Param", {
                    "param": param.upper(), 
                    "val": f"{physical_value} {unit}", 
                    "V_Drive": log_v_info,
                    "DAC": dac_code_int,
                    "BIN": log_display
                })
                
                if self.serial_comm.is_connected:
                    self.serial_comm.serial_port.write(raw_bytes)
        
        # value = getattr(self, param).get()
        # self.is_modified = True
        
        # for ch in self.get_selected_channels():
        #     # print(f"Setting {param} to {value} for channel {ch}")
        #     command = ""
        #     if param == "s_bias":
        #         command = f"SB {ch} {value}"
        #     elif param == "s_flux":
        #         command = f"SF {ch} {value}"
        #     elif param == "a_bias":
        #         command = f"AB {ch} {value}"
        #     elif param == "a_flux":
        #         command = f"AF {ch} {value}"
        #     elif param == "offset":
        #         command = f"OF {ch} {value}"
                
        #     self.log_operation("Set Parameter", {"parameter": param, "value": value, "channel": ch, "command": command})
            
        #     # 发送串口命令
        #     if self.serial_comm.is_connected and command:
        #         self.send_serial_command(command)
    
    def toggle_squid_step(self):
        """切换SQUID参数调节步长"""
        print("Toggling SQUID coarse/fine step")
        self.is_modified = True
        for ch in self.get_selected_channels():
            command = f"SCF {ch}"
            self.log_operation("Toggle SQUID Step", {"command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
    
    def toggle_array_step(self):
        """切换阵列参数调节步长"""
        print("Toggling Array coarse/fine step")
        self.is_modified = True
        for ch in self.get_selected_channels():
            command = f"ACF {ch}"
            self.log_operation("Toggle Array Step", {"command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
                
    def build_fpga_command_binary(self, bin_cmd_type, bin_cmd_obj, channel, bin_data_16bit):
        """根据表格定义构建FPGA命令的二进制字符串
        :param bin_cmd_type: 命令类型 (字符串)，例如 "01"
        :param bin_cmd_obj: 命令对象 (字符串)，例如线圈是 "11"
        :param channel: 通道编号 (1-8，整数)
        :param bin_data_16bit: 16位数据 (字符串)，例如 "0000000011110000"
        :return: (要在日志显示的二进制字符串, 真正要发送的物理字节流)
        """
        # 1. 31-24 bit: mac addr (固定 1111 1111)
        mac_addr = "11111111"
        
        # 2. 通道号转换: 比如通道1 -> "0000", 通道2 -> "0001" 
        ch_num = channel - 1
        bin_channel = f"{ch_num:04b}" 
        
        # 3. 拼接
        full_bin_str = mac_addr + bin_cmd_type + bin_cmd_obj + bin_channel + bin_data_16bit
        
        # 4. 【核心步骤】把这32个 '0'和'1'的字符串，打包成 4个真正的硬件字节
        # int(..., 2) 意思是把字符串当成二进制数字去读
        # to_bytes(4, 'big') 意思是把这个大数字切成4个字节，高位在前(大端序)
        raw_bytes_to_send = int(full_bin_str, 2).to_bytes(4, byteorder='big')
        
        return full_bin_str, raw_bytes_to_send

    def set_test_coil(self):
        #测试线圈选择指令
        coil = self.test_coil_var.get()
        self.is_modified = True
        
        if coil == "Array FB Coil":
            target_8bit = "11110000"  # 目标：Array 模块
            action_8bit = "11110000"  # 动作：切换到 Array FB coil
        else:
            target_8bit = "00001111"  # 目标：Input SQUID 模块
            action_8bit = "00001111"  # 动作：切换到 Input FB coil
            
        data_16bit = target_8bit + action_8bit
            
        for ch in self.get_selected_channels():
            # "01"反馈相关，"11"反馈线圈
            bin_str, raw_bytes = self.build_fpga_command_binary("01", "11", ch, data_16bit)
            
            log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:24]} {bin_str[24:32]}"
            self.log_operation("Set Test Coil", {"channel": ch, "coil": coil, "BIN": log_display})
            
            if self.serial_comm.is_connected:
                self.serial_comm.serial_port.write(raw_bytes)
                
    def set_feedback_resistor(self):
            #反馈电阻设定指令
            resistor = self.feedback.get()
            target = self.fb_target.get()  # 获取新增加的目标选项
            self.is_modified = True
            
            # 1. 前8位：根据 TARGET 下拉框决定发给谁
            if target == "SQUID Array":
                target_8bit = "11110000"  # 目标：Array 模块
            else:
                target_8bit = "00001111"  # 目标：Input SQUID 模块
                
            # 2. 后8位：根据电阻下拉框获取具体动作
            if resistor == "10kOhm":
                action_8bit = "00011111" # 反馈电阻1
            elif resistor == "30kOhm":
                action_8bit = "00101111" # 反馈电阻2
            elif resistor == "100kOhm":
                action_8bit = "00111111" # 反馈电阻3
            else:
                action_8bit = "00011111" # 默认兜底
                
            # 拼接成 16-bit 数据
            data_16bit = target_8bit + action_8bit
                
            for ch in self.get_selected_channels():
                # 表格定义："01"反馈相关，"10"反馈电阻
                bin_str, raw_bytes = self.build_fpga_command_binary("01", "10", ch, data_16bit)
                
                # 在日志中打印出目标和电阻
                log_display = f"{bin_str[0:8]} {bin_str[8:16]} {bin_str[16:24]} {bin_str[24:32]}"
                self.log_operation("Set FB Resistor", {"channel": ch, "target": target, "resistor": resistor, "BIN": log_display})
                
                if self.serial_comm.is_connected:
                    # 发送物理字节
                    self.serial_comm.serial_port.write(raw_bytes)
                    
    def zero_restore_squid(self):
        """SQUID参数归零/恢复"""
        print("Zeroing/restoring SQUID parameters")
        self.is_modified = True
        for ch in self.get_selected_channels():
            command = f"SZR {ch}"
            self.log_operation("Zero/Restore SQUID", {"command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
    
    def zero_restore_array(self):
        """阵列参数归零/恢复"""
        print("Zeroing/restoring Array parameters")
        self.is_modified = True
        for ch in self.get_selected_channels():
            command = f"AZR {ch}"
            self.log_operation("Zero/Restore Array", {"command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
    
    def reset(self):
        """重置反馈环路"""
        self.is_modified = True
        for ch in self.get_selected_channels():
            print(f"Resetting channel {ch}")
            command = f"RST {ch}"
            self.log_operation("Reset Channel", {"channel": ch, "command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
    
    def heat(self):
        """启动加热循环"""
        self.is_modified = True
        for ch in self.get_selected_channels():
            print(f"Heating channel {ch}")
            command = f"HEAT {ch} {self.heat_time.get()}"
            self.log_operation("Heat", {"channel": ch, "command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
    
    def refresh(self):
        """刷新所有设置"""
        print("Refreshing all settings")
        for ch in self.get_selected_channels():
            command = f"REF {ch}"
            self.log_operation("Refresh System", {"command": command})
            
            # 发送串口命令
            if self.serial_comm.is_connected:
                self.send_serial_command(command)
    
    def toggle_master(self):
        """切换主模式"""
        print("Toggling master mode")
        self.is_modified = True
        command = "MST"
        self.log_operation("Toggle Master Mode", {"command": command})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            self.send_serial_command(command)
    
    def schedule_auto_save(self):
        """设置定期自动保存"""
        self.root.after(self.auto_save_interval, self.auto_save)
    
    def auto_save(self):
        """自动保存功能"""
        if self.is_modified and self.file_path:
            self.save_file(self.file_path)
            self.log_operation("Auto-saved configuration")
        
        # 重新调度下一次自动保存
        self.schedule_auto_save()
    
    def log_operation(self, action, params=None):
        """记录操作历史"""
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "channel": self.current_channel,
            "action": action,
            "params": params or {}
        }
        self.data_history.append(entry)
        
        # 在界面底部显示的日志内容包含时间、操作以及下发的命令指令
        # 2. 优化在屏幕底部日志框里的显示
        log_msg = f"Action: {action}"
        
        if params and isinstance(params, dict):
            disp_params = params.copy()
            command = disp_params.pop("command", None)
            
            if disp_params:
                clean_values = " , ".join([str(v) for v in disp_params.values()])
                log_msg += f" : {clean_values}"
                
            if command:
                log_msg += f" | Expected TX: {command}"
                
        elif params:
            log_msg += f" | {params}"
                
        self.display_serial_data(log_msg, "system")
    
    def new_file(self):
        """创建新文件"""
        if self.is_modified:
            if not self.prompt_save():
                return
        
        # 重置所有状态
        self.reset_system()
        
    def reset_system(self):
        #重置系统状态
        self.current_channel = 1
        self.max_channels = 8
        self.pci_type = "PCI-1000"
        self.squid_states = {i: "TUNE" for i in range(1, self.max_channels+1)}
        self.array_states = {i: "TUNE" for i in range(1, self.max_channels+1)}
        self.data_history = []
        self.is_modified = False
        self.file_path = None
        self.root.title("Cryoelectronics Control System - New File")
        
        # 重置参数值
        self.s_bias.set(0.0)
        self.s_flux.set(0.0)
        self.a_bias.set(0.0)
        self.a_flux.set(0.0)
        self.offset.set(0.0)
        self.sensitivity.set("High")
        self.feedback.set("100kOhm")
        self.integrator.set("1.5nF")
        self.test_input.set("Array Flux")
        self.heat_time.set(2.0)
        self.cool_time.set(5.0)
        self.group_size.set(1)
        self.test_coil_var.set("Array FB Coil")
        
        # 重置开关状态
        self.test_signal_enabled.set(False)
        self.heater_enabled.set(False)
        
        # 重置串口状态
        self.serial_comm.disconnect()
        self.connection_status.set("未连接")
        self.clear_serial_monitor()
        
        self.update_state_indicators()
        self.log_operation("Created New File")
    
    def open_file(self):
        """打开配置文件"""
        if self.is_modified:
            if not self.prompt_save():
                return
        
        file_path = filedialog.askopenfilename(
            title="Open Configuration File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # 加载系统配置
                self.current_channel = data.get("current_channel", 1)
                self.max_channels = data.get("max_channels", 8)
                self.pci_type = data.get("pci_type", "PCI-1000")
                self.squid_states = data.get("squid_states", {i: "TUNE" for i in range(1, self.max_channels+1)})
                self.array_states = data.get("array_states", {i: "TUNE" for i in range(1, self.max_channels+1)})
                self.data_history = data.get("data_history", [])
                
                # 加载参数值
                params = data.get("parameters", {})
                self.s_bias.set(params.get("s_bias", 0.0))
                self.s_flux.set(params.get("s_flux", 0.0))
                self.a_bias.set(params.get("a_bias", 0.0))
                self.a_flux.set(params.get("a_flux", 0.0))
                self.offset.set(params.get("offset", 0.0))
                self.sensitivity.set(params.get("sensitivity", "High"))
                self.feedback.set(params.get("feedback", "100kOhm"))
                self.integrator.set(params.get("integrator", "1.5nF"))
                self.test_input.set(params.get("test_input", "Array Flux"))
                self.heat_time.set(params.get("heat_time", 2.0))
                self.cool_time.set(params.get("cool_time", 5.0))
                self.group_size.set(params.get("group_size", 1))
                self.test_coil_var.set(params.get("test_coil", "Array FB Coil"))
                
                # 加载开关状态
                self.test_signal_enabled.set(params.get("test_signal_enabled", False))
                self.heater_enabled.set(params.get("heater_enabled", False))
                
                # 更新UI状态
                self.update_state_indicators()
                self.file_path = file_path
                self.is_modified = False
                self.root.title(f"Cryoelectronics Control System - {os.path.basename(file_path)}")
                self.log_operation("Opened File", {"file": file_path})
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open file: {str(e)}")
    
    def save(self):
        """保存文件"""
        if self.file_path:
            self.save_file(self.file_path)
        else:
            self.save_as()
    
    def save_as(self):
        """另存为文件"""
        file_path = filedialog.asksaveasfilename(
            title="Save Configuration File",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            self.save_file(file_path)
    
    def save_file(self, file_path):
        """保存文件到指定路径"""
        try:
            data = {
                "current_channel": self.current_channel,
                "max_channels": self.max_channels,
                "pci_type": self.pci_type,
                "squid_states": self.squid_states,
                "array_states": self.array_states,
                "parameters": {
                    "s_bias": self.s_bias.get(),
                    "s_flux": self.s_flux.get(),
                    "a_bias": self.a_bias.get(),
                    "a_flux": self.a_flux.get(),
                    "offset": self.offset.get(),
                    "sensitivity": self.sensitivity.get(),
                    "feedback": self.feedback.get(),
                    "integrator": self.integrator.get(),
                    "test_input": self.test_input.get(),
                    "heat_time": self.heat_time.get(),
                    "cool_time": self.cool_time.get(),
                    "group_size": self.group_size.get(),
                    "test_coil": self.test_coil_var.get(),
                    "test_signal_enabled": self.test_signal_enabled.get(),
                    "heater_enabled": self.heater_enabled.get()
                },
                "data_history": self.data_history
            }
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.file_path = file_path
            self.is_modified = False
            self.root.title(f"Cryoelectronics Control System - {os.path.basename(file_path)}")
            self.log_operation("Saved File", {"file": file_path})
            messagebox.showinfo("Success", "File saved successfully")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {str(e)}")
    
    def prompt_save(self):
        """提示保存更改"""
        response = messagebox.askyesnocancel(
            "Unsaved Changes",
            "Do you want to save your changes before continuing?"
        )
        
        if response is None:  # Cancel
            return False
        elif response:  # Yes
            self.save()
        
        return True
    
    def import_data(self):
        """导入数据文件"""
        file_path = filedialog.askopenfilename(
            title="Import Data File",
            filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if file_path:
            print(f"Importing data from {file_path}")
            self.is_modified = True
            self.log_operation("Imported Data", {"file": file_path})
            messagebox.showinfo("Import", f"Data imported from {os.path.basename(file_path)}")
    
    def export_data(self):
        """导出数据文件"""
        file_path = filedialog.asksaveasfilename(
            title="Export Data",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        
        if file_path:
            print(f"Exporting data to {file_path}")
            self.log_operation("Exported Data", {"file": file_path})
            messagebox.showinfo("Export", f"Data exported to {os.path.basename(file_path)}")
    
    def on_close(self):
        """处理窗口关闭事件"""
        # 停止UI循环刷新，防止退出时卡顿
        if hasattr(self, 'update_timer'):
            self.root.after_cancel(self.update_timer)
            
        # 停止记录
        if self.recording and self.record_file:
            self.stop_recording()
        
        # 断开串口连接
        if self.serial_comm.is_connected:
            self.serial_comm.disconnect()
        
        # 提示保存
        if self.is_modified:
            if not self.prompt_save():
                return
        
        self.root.destroy()
    
    def open_system_config(self):
        """打开系统配置窗口"""
        config_window = tk.Toplevel(self.root)
        config_window.title("System Configuration")
        config_window.geometry("400x300")
        
        ttk.Label(config_window, text="Number of Channels:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.num_channels = tk.IntVar(value=self.max_channels)
        ttk.Combobox(config_window, textvariable=self.num_channels, values=list(range(1, 33))).grid(row=0, column=1, padx=10, pady=10)
        
        ttk.Label(config_window, text="PCI Units:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.pci_units = tk.StringVar(value=self.pci_type)
        ttk.Combobox(config_window, textvariable=self.pci_units, values=["PCI-100", "PCI-1000 x1", "PCI-1000 x2", "PCI-1000 x3"]).grid(row=1, column=1, padx=10, pady=10)
        
        ttk.Label(config_window, text="Port:").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.port = tk.StringVar(value="COM1")
        ttk.Combobox(config_window, textvariable=self.port, values=[f"COM{i}" for i in range(1, 10)] + ["LPT1"]).grid(row=2, column=1, padx=10, pady=10)
        
        def save_config():
            self.max_channels = self.num_channels.get()
            self.pci_type = self.pci_units.get().split()[0]
            self.is_modified = True
            self.log_operation("Changed System Config", {
                "channels": self.max_channels,
                "pci_type": self.pci_type,
                "port": self.port.get()
            })
            config_window.destroy()
        
        def restart_system():
            self.max_channels = self.num_channels.get()
            self.pci_type = self.pci_units.get().split()[0]
            self.is_modified = True
            self.log_operation("Restarted System", {
                "channels": self.max_channels,
                "pci_type": self.pci_type,
                "port": self.port.get()
            })
            config_window.destroy()
            messagebox.showinfo("Info", "System will restart with new configuration")
        
        ttk.Button(config_window, text="OK", command=save_config).grid(row=3, column=0, pady=20)
        ttk.Button(config_window, text="Restart", command=restart_system).grid(row=3, column=1, pady=20)
    
    def open_pci_config(self):
        """打开PCI配置窗口"""
        if self.pci_type != "PCI-1000":
            messagebox.showinfo("Info", "PCI configuration is only available for PCI-1000")
            return
            
        pci_window = tk.Toplevel(self.root)
        pci_window.title("PCI-1000 Configuration")
        pci_window.geometry("500x400")
        
        # 测试信号发生器设置
        sig_frame = ttk.LabelFrame(pci_window, text="Test Signal Generator", padding="10")
        sig_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.sig_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(sig_frame, text="On/Off", variable=self.sig_on).grid(row=0, column=0, padx=10, pady=5)
        
        ttk.Label(sig_frame, text="Frequency (Hz):").grid(row=1, column=0, sticky="w", pady=5)
        self.sig_freq = tk.DoubleVar(value=1000.0)
        ttk.Entry(sig_frame, textvariable=self.sig_freq, width=10).grid(row=1, column=1, pady=5)
        
        ttk.Label(sig_frame, text="Amplitude (V):").grid(row=2, column=0, sticky="w", pady=5)
        self.sig_amp = tk.DoubleVar(value=1.0)
        ttk.Entry(sig_frame, textvariable=self.sig_amp, width=10).grid(row=2, column=1, pady=5)
        
        ttk.Button(sig_frame, text="COARSE/FINE").grid(row=3, column=0, pady=5)
        
        # 信号调理设置
        cond_frame = ttk.LabelFrame(pci_window, text="Signal Conditioning", padding="10")
        cond_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(cond_frame, text="Channel:").grid(row=0, column=0, sticky="w", pady=5)
        self.cond_channel = tk.IntVar(value=1)
        ttk.Combobox(cond_frame, textvariable=self.cond_channel, values=list(range(1, 9)), width=5).grid(row=0, column=1, pady=5)
        
        ttk.Label(cond_frame, text="Filter:").grid(row=1, column=0, sticky="w", pady=5)
        self.filter_setting = tk.StringVar(value="15 kHz")
        ttk.Combobox(cond_frame, textvariable=self.filter_setting, 
                     values=["Unfiltered", "3 kHz", "6 kHz", "15 kHz", "30 kHz"], width=10).grid(row=1, column=1, pady=5)
        
        ttk.Label(cond_frame, text="Multiplexer:").grid(row=2, column=0, sticky="w", pady=5)
        self.mux_setting = tk.StringVar(value="Sensor Output")
        ttk.Combobox(cond_frame, textvariable=self.mux_setting, 
                     values=["Sensor Output", "Test Signal", "Ground", "4.5V Reference"], width=15).grid(row=2, column=1, pady=5)
        
        def save_pci_config():
            self.is_modified = True
            self.log_operation("Changed PCI Config", {
                "signal_on": self.sig_on.get(),
                "frequency": self.sig_freq.get(),
                "amplitude": self.sig_amp.get(),
                "channel": self.cond_channel.get(),
                "filter": self.filter_setting.get(),
                "mux": self.mux_setting.get()
            })
            pci_window.destroy()
        
        ttk.Button(pci_window, text="OK", command=save_pci_config).pack(pady=10)

if __name__ == "__main__":
    root = tk.Tk()
    app = StarCryoControlGUI(root)
    root.mainloop()
