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
        self.serial_port = None     # 串口对象，初始为None
        self.baud_rate = 57600      # 默认波特率
        self.port_name = None       # 当前连接的串口名称
        self.is_connected = False   # 连接状态
        self.gui_callback = gui_callback  # GUI回调函数，用于更新界面状态
        self.receive_thread = None  # 接收线程
        self.receive_queue = queue.Queue()  # 接收数据队列
        self.send_queue = queue.Queue()  # 发送数据队列
        self.running = False    # 线程控制标志
        self.lock = Lock()      # 串口操作锁，防止多个线程同时访问串口
        
        # 命令队列，用于处理需要等待响应的命令，确保命令按顺序发送和处理响应
        self.command_queue = deque()    # 存储待发送的命令
        self.command_lock = Lock()      # 命令队列锁，确保线程安全
        
        # 通信参数
        self.timeout = 1.0      # 读写超时时间，单位为秒
        self.write_timeout = 1.0    # 写入超时时间，单位为秒
        
    def get_available_ports(self):
        """获取可用串口列表"""
        ports = []
        try:
            available_ports = serial.tools.list_ports.comports()    # 获取系统中所有可用的串口列表
            for port in available_ports:
                ports.append(port.device)   # 将串口设备名称添加到列表中，在Windows上通常是COM1, COM2等，在Linux上通常是/dev/ttyUSB0, /dev/ttyS0等
        except Exception as e:      # 捕获获取串口列表时的异常，Exception是一个通用的异常类，可以捕获所有类型的异常,可以根据需要捕获更具体的异常类型，如serial.SerialException等
            print(f"获取串口列表错误: {e}")
        return ports
    
    def connect(self, port, baud_rate=9600):
        """连接串口"""
        try:
            with self.lock:     # 确保在连接过程中没有其他线程访问串口
                if self.serial_port and self.serial_port.is_open:  # 如果已经有一个打开的串口连接，先关闭它 
                    self.serial_port.close()
                
                self.serial_port = serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    write_timeout=self.write_timeout
                )       # 创建一个新的串口连接对象，使用指定的端口和波特率，并设置其他通信参数，如数据位、校验位、停止位和超时时间
                # 工业届8N1配置是指8个数据位、无校验位和1个停止位，这是一种常见的串口通信配置，适用于大多数设备。
                
                self.port_name = port
                self.baud_rate = baud_rate
                self.is_connected = True
                
                # 启动接收线程
                self.running = True
                self.receive_thread = Thread(target=self._receive_loop, daemon=True) 
                # 创建一个新的线程来处理串口数据的接收，target参数指定线程执行的函数，这里是_receive_loop方法，daemon=True表示这个线程是守护线程，当主线程退出时，守护线程会自动结束
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
        
        with self.lock:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            
            self.is_connected = False
            
        if self.gui_callback:   # 断开连接后通过回调函数通知GUI更新连接状态
            self.gui_callback("connection_update", {"connected": False, "port": None})
    
    def send_command(self, command, response_callback=None, timeout=2.0):
        """发送命令到设备"""
        if not self.is_connected or not self.serial_port:
            print("串口未连接")
            return False
        
        try:
            # 添加命令到队列
            with self.command_lock:     #线程锁
                command_data = {
                    'command': command + '\r\n',  # 添加换行符，命令结尾
                    'timestamp': time.time(),
                    'callback': response_callback,
                    'timeout': timeout
                }
                self.command_queue.append(command_data)     # 将命令数据添加到命令队列中，等待命令处理线程发送和处理响应
            
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
                with self.command_lock:     # 确保在处理命令队列时没有其他线程修改它
                    if self.command_queue:
                        command_data = self.command_queue.popleft()     # 从命令队列中取出最左边的命令数据进行处理
                        
                        # 发送命令
                        with self.lock:    # 串口锁，发送瞬间确保串口不被其他线程访问
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
                        if self.serial_port.in_waiting > 0:     #in_waiting属性表示串口接收缓冲区中等待读取的字节数，如果大于0，说明有数据可读
                            data = self.serial_port.read(self.serial_port.in_waiting)
                            buffer += data.decode('utf-8', errors='ignore')     
                            
                            # 按行分割
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                #split()方法用于将字符串分割成两部分，第一部分是line，包含当前行的数据.('\n', 1)  表示以换行符为分隔符进行分割，1表示只分割一次，即只分割出第一行数据，剩余的数据保存在buffer中
                                #第二部分是buffer，包含剩余的数据，如果buffer中还有数据但没有换行符，则会保留在buffer中等待下一次接收  
                                # 将接收到的数据按行分割，line是当前行数据，buffer是剩余的数据，如果buffer中还有数据但没有换行符，则会保留在buffer中等待下一次接收
                                line = line.strip()
                                #strip()方法用于去除字符串两端的空白字符，包括空格、制表符、换行符等，确保line中只包含有效的数据内容
                                if line:    
                                    self.receive_queue.put(line)        # 将接收到的行数据放入接收队列中，供GUI或其他线程处理
                                    
                                    # 调用GUI回调
                                    if self.gui_callback:   # 如果定义了GUI回调函数，则调用它来通知GUI有新数据接收
                                        self.gui_callback("data_received", {"data": line})
        
                time.sleep(0.01)
            #捕获串口断开异常——Lpc
            except(serial.SerialException,OSError) as e:
                print(f"串口连接异常: {e}")
                # Channel disconnected, update GUI and stop threads
                self.is_connected = False
                self.running = False # 停止接收和发送线程
                try:
                    if self.serial_port and self.serial_port.is_open:
                        self.serial_port.close()
                except Exception :
                    pass # 关闭串口时可能会抛出异常，忽略它
                if self.gui_callback:
                    self.gui_callback("connection_update", {"connected": False, "port": None})
                break
            # 捕获其他类型错误
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
            time.sleep(0.01)        # 减少CPU占用
    
    def get_data(self):
        """从队列获取接收到的数据"""
        data = []
        while not self.receive_queue.empty():
            data.append(self.receive_queue.get())
        return data
    
    def send_raw_data(self, data):  #和send_loop协同工作，将数据放入发送队列中，由发送线程处理实际的串口写入操作
        """发送原始数据"""
        if self.is_connected and self.serial_port:
            self.send_queue.put(data)       
            #put和append方法类似，都是将数据添加到队列的末尾，put方法是queue.Queue不会发生数据冲突或丢失
            return True
        return False

class StarCryoControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("STAR Cryoelectronics Control System")      # 设置窗口标题
        self.root.geometry("1200x900")                              # 设置窗口初始大小  
        self.root.configure(bg="#f0f0f0")                         # 设置背景颜色

        self._create_scrollable_container()
        
        # 初始化串口通信
        self.serial_comm = SerialCommunication(gui_callback=self.serial_callback)
        
        # 系统状态变量
        self.current_channel = 1
        self.max_channels = 8
        self.pci_type = "PCI-1000"
        self.squid_states = {i: "TUNE" for i in range(1, self.max_channels+1)}  
        # 初始化每个通道的SQUID状态为"TUNE"，使用字典来存储每个通道的状态，键是通道号，值是状态字符串
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
        
        # 创建主布局
        self.create_main_layout()
        
        # 创建串口监控窗口
        self.create_serial_monitor()

        # 创建命令日志窗口
        self.create_command_log_panel()
        
        # 绑定热键
        self.bind_hotkeys()
        
        # 设置自动保存
        self.schedule_auto_save()
        
        # 设置退出事件处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 启动串口数据更新定时器
        self.update_serial_data()

    def _create_scrollable_container(self):
        self.outer_frame = ttk.Frame(self.root)
        self.outer_frame.pack(fill=tk.BOTH, expand=True)

        self.v_scrollbar = ttk.Scrollbar(self.outer_frame, orient=tk.VERTICAL)
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.scroll_canvas = tk.Canvas(self.outer_frame, highlightthickness=0)
        self.scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.v_scrollbar.config(command=self.scroll_canvas.yview)
        self.scroll_canvas.config(yscrollcommand=self.v_scrollbar.set)

        self.content_frame = ttk.Frame(self.scroll_canvas)
        self.canvas_window = self.scroll_canvas.create_window(
            (0, 0), window=self.content_frame, anchor="nw"
        )

        self.content_frame.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))
        )
        self.scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self.scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        self.scroll_canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        delta = -1 * int(event.delta / 120) if event.delta else 0
        if delta == 0 and event.delta:
            delta = -1 if event.delta > 0 else 1
        self.scroll_canvas.yview_scroll(delta, "units")
    
    def create_main_layout(self):
        # 主面板分为四个区域：控制区、调谐区、配置区、串口区
        main_frame = ttk.Frame(self.content_frame, padding="10")     #padding参数设置边界和子组件之间的空白距离，这里设置为10像素
        main_frame.pack(fill=tk.BOTH, expand=True)      
        #pack()方法用于将组件添加到父组件中，fill=tk.BOTH表示组件在水平和垂直方向上都填充父组件，expand=True表示组件会扩展以占满父组件的剩余空间
        
        # 创建左侧面板（控制区）
        left_frame = ttk.Frame(main_frame)      #创建一个新的Frame组件作为左侧面板，父组件是main_frame
        left_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")     
        #使用grid布局管理器将left_frame放置在主面板的第一行第一列，padx和pady设置组件之间的水平和垂直间距，sticky="nsew"表示组件在单元格内扩展以填满整个单元格
        
        # 1. 串口连接配置 - 放在左侧最上方
        serial_frame = ttk.LabelFrame(left_frame, text="串口连接", padding="10")
        #创建一个带有标题的LabelFrame组件作为串口连接配置区域，父组件是left_frame，text参数设置标题，padding参数设置内部边距
        serial_frame.pack(fill=tk.X, pady=(0, 10))
        #pack()方法将serial_frame添加到left_frame中，fill=tk.X表示组件在水平方向上填充父组件，pady=(0, 10)设置组件之间的垂直间距，上边距为0，下边距为10像素
        
        # 串口连接状态
        self.connection_status = tk.StringVar(value="未连接")
        #StringVar是Tkinter提供的一个变量类，用于在GUI中存储和管理字符串数据，value参数设置初始值为"未连接"
        status_label = ttk.Label(serial_frame, textvariable=self.connection_status, 
                                foreground="red", font=("Arial", 10, "bold"))
        #创建一个Label组件用于显示串口连接状态，父组件是serial_frame
        # textvariable参数绑定到self.connection_status变量，这样当变量值改变时，标签文本会自动更新
        # foreground设置文本颜色为红色，font设置字体为Arial，大小为10，加粗
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
        
        # 连接/断开按钮
        btn_frame = ttk.Frame(serial_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.connect_btn = ttk.Button(btn_frame, text="连接", command=self.connect_serial, width=10)
        self.connect_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="断开", command=self.disconnect_serial, 
                                        width=10, state="disabled")
        self.disconnect_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # 测试按钮
        test_btn_frame = ttk.Frame(serial_frame)
        test_btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(test_btn_frame, text="测试连接", command=self.test_connection, width=10).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(test_btn_frame, text="发送测试", command=self.send_test_command, width=10).grid(row=0, column=1, padx=5, pady=5)
        
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
            
            select_btn = ttk.Checkbutton(frame, command=lambda ch=i: self.select_channel(ch))
            select_btn.grid(row=0, column=3, padx=5)
            
            # 串口状态指示
            serial_indicator = ttk.Label(frame, text="●", width=1, foreground="red")
            serial_indicator.grid(row=0, column=4, padx=5)
            
            self.channel_controls.append({
                "frame": frame,
                "squid_state": squid_state,
                "array_state": array_state,
                "select_btn": select_btn,
                "serial_indicator": serial_indicator
            })
        
        # 模式控制按钮
        mode_frame = ttk.LabelFrame(control_frame, text="模式控制", padding="10")
        mode_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(mode_frame, text="S-LOCK", command=self.s_lock).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(mode_frame, text="S-TUNE", command=self.s_tune).grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(mode_frame, text="A-LOCK", command=self.a_lock).grid(row=1, column=0, padx=5, pady=5)
        ttk.Button(mode_frame, text="A-TUNE", command=self.a_tune).grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(mode_frame, text="RESET", command=self.reset).grid(row=2, column=0, padx=5, pady=5)
        ttk.Button(mode_frame, text="HEAT", command=self.heat).grid(row=2, column=1, padx=5, pady=5)
        
        # 创建中间面板（调谐区）
        center_frame = ttk.Frame(main_frame)
        center_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        
        # 3. 调制参数区域
        tune_frame = ttk.LabelFrame(center_frame, text="调制参数", padding="10")
        tune_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # SQUID调谐参数
        squid_frame = ttk.LabelFrame(tune_frame, text="SQUID 参数", padding="10")
        squid_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(squid_frame, text="S-BIAS (mA):").grid(row=0, column=0, sticky="w", pady=5)
        self.s_bias = tk.DoubleVar(value=0.0)
        ttk.Entry(squid_frame, textvariable=self.s_bias, width=10).grid(row=0, column=1, pady=5)
        ttk.Button(squid_frame, text="Set", command=lambda: self.set_parameter("s_bias")).grid(row=0, column=2, padx=5)
        
        ttk.Label(squid_frame, text="S-FLUX (µA):").grid(row=1, column=0, sticky="w", pady=5)
        self.s_flux = tk.DoubleVar(value=0.0)
        ttk.Entry(squid_frame, textvariable=self.s_flux, width=10).grid(row=1, column=1, pady=5)
        ttk.Button(squid_frame, text="Set", command=lambda: self.set_parameter("s_flux")).grid(row=1, column=2, padx=5)
        
        ttk.Button(squid_frame, text="COARSE/FINE", command=self.toggle_squid_step).grid(row=2, column=0, pady=5)
        ttk.Button(squid_frame, text="ZERO/RESTORE", command=self.zero_restore_squid).grid(row=2, column=1, pady=5)
        
        # 阵列调谐参数
        array_frame = ttk.LabelFrame(tune_frame, text="Array 参数", padding="10")
        array_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(array_frame, text="A-BIAS (µA):").grid(row=0, column=0, sticky="w", pady=5)
        self.a_bias = tk.DoubleVar(value=0.0)
        ttk.Entry(array_frame, textvariable=self.a_bias, width=10).grid(row=0, column=1, pady=5)
        ttk.Button(array_frame, text="Set", command=lambda: self.set_parameter("a_bias")).grid(row=0, column=2, padx=5)
        
        ttk.Label(array_frame, text="A-FLUX (µA):").grid(row=1, column=0, sticky="w", pady=5)
        self.a_flux = tk.DoubleVar(value=0.0)
        ttk.Entry(array_frame, textvariable=self.a_flux, width=10).grid(row=1, column=1, pady=5)
        ttk.Button(array_frame, text="Set", command=lambda: self.set_parameter("a_flux")).grid(row=1, column=2, padx=5)
        
        ttk.Label(array_frame, text="OFFSET (mV):").grid(row=2, column=0, sticky="w", pady=5)
        self.offset = tk.DoubleVar(value=0.0)
        ttk.Entry(array_frame, textvariable=self.offset, width=10).grid(row=2, column=1, pady=5)
        ttk.Button(array_frame, text="Set", command=lambda: self.set_parameter("offset")).grid(row=2, column=2, padx=5)
        
        ttk.Button(array_frame, text="COARSE/FINE", command=self.toggle_array_step).grid(row=3, column=0, pady=5)
        ttk.Button(array_frame, text="ZERO/RESTORE", command=self.zero_restore_array).grid(row=3, column=1, pady=5)
        
        # 创建右侧面板（配置区）
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        
        # 4. 配置区域
        config_frame = ttk.LabelFrame(right_frame, text="系统配置", padding="10")
        config_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 反馈环路配置
        feedback_frame = ttk.LabelFrame(config_frame, text="反馈环路配置", padding="10")
        feedback_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(feedback_frame, text="SENSITIVITY:").grid(row=0, column=0, sticky="w", pady=5)
        self.sensitivity = tk.StringVar(value="High")
        ttk.Combobox(feedback_frame, textvariable=self.sensitivity, 
                    values=["Low", "Medium", "High", "Select R&C"], width=12).grid(row=0, column=1, pady=5)
        
        ttk.Label(feedback_frame, text="FEEDBACK:").grid(row=1, column=0, sticky="w", pady=5)
        self.feedback = tk.StringVar(value="100kOhm")
        ttk.Combobox(feedback_frame, textvariable=self.feedback, 
                    values=["1kOhm","10kOhm", "30kOhm", "100kOhm"], width=12).grid(row=1, column=1, pady=5)
        
        ttk.Label(feedback_frame, text="INTEGRATOR:").grid(row=2, column=0, sticky="w", pady=5)
        self.integrator = tk.StringVar(value="1.5nF")
        ttk.Combobox(feedback_frame, textvariable=self.integrator, 
                    values=["1.5nF", "15nF", "150nF"], width=12).grid(row=2, column=1, pady=5)
        
        # 测试信号配置
        test_frame = ttk.LabelFrame(config_frame, text="测试信号配置", padding="10")
        test_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(test_frame, text="TEST SIGNAL:").grid(row=0, column=0, sticky="w", pady=5)
        self.test_signal_switch = ttk.Checkbutton(test_frame, text="Enabled", 
                                                 variable=self.test_signal_enabled,
                                                 command=self.toggle_test_signal)
        self.test_signal_switch.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(test_frame, text="TEST INPUT:").grid(row=1, column=0, sticky="w", pady=5)
        self.test_input = tk.StringVar(value="Array Flux")
        ttk.Combobox(test_frame, textvariable=self.test_input, 
                    values=["SQUID Bias", "SQUID Flux", "Array Bias", "Array Flux"], width=12).grid(row=1, column=1, pady=5)
        
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
        
        # 系统控制按钮
        sys_frame = ttk.LabelFrame(config_frame, text="系统控制", padding="10")
        sys_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(sys_frame, text="REFRESH", command=self.refresh).pack(fill=tk.X, pady=2)
        ttk.Button(sys_frame, text="MASTER", command=self.toggle_master).pack(fill=tk.X, pady=2)
        ttk.Button(sys_frame, text="System Config", command=self.open_system_config).pack(fill=tk.X, pady=2)
        ttk.Button(sys_frame, text="PCI Config", command=self.open_pci_config).pack(fill=tk.X, pady=2)
        
        # 文件操作按钮
        file_frame = ttk.LabelFrame(config_frame, text="文件操作", padding="10")
        file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(file_frame, text="New File", command=self.new_file).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Open", command=self.open_file).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Save", command=self.save).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Save As", command=self.save_as).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Import Data", command=self.import_data).grid(row=2, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(file_frame, text="Export Data", command=self.export_data).grid(row=2, column=1, padx=2, pady=2, sticky="ew")
        
        # 配置网格权重
        main_frame.grid_columnconfigure(0, weight=1)  # 左侧面板
        main_frame.grid_columnconfigure(1, weight=2)  # 中间面板
        main_frame.grid_columnconfigure(2, weight=1)  # 右侧面板
        main_frame.grid_rowconfigure(0, weight=1)
    
    def create_serial_monitor(self):
        """创建串口数据监控窗口"""
        monitor_frame = ttk.LabelFrame(self.content_frame, text="串口数据监控", padding="10")
        monitor_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 工具栏
        toolbar = ttk.Frame(monitor_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Button(toolbar, text="清空", command=self.clear_serial_monitor, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="开始记录", command=self.start_recording, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="停止记录", command=self.stop_recording, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="保存日志", command=self.save_serial_log, width=8).pack(side=tk.LEFT, padx=2)
        
        # 数据显示区域
        self.serial_text = scrolledtext.ScrolledText(monitor_frame, height=10, width=100)
        self.serial_text.pack(fill=tk.BOTH, expand=True)
        self.serial_text.config(state=tk.DISABLED)
        
        # 状态栏
        status_frame = ttk.Frame(monitor_frame)
        status_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.rx_count = tk.IntVar(value=0)
        self.tx_count = tk.IntVar(value=0)
        
        ttk.Label(status_frame, text="接收:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.rx_count, foreground="green").pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(status_frame, text="发送:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(status_frame, textvariable=self.tx_count, foreground="blue").pack(side=tk.LEFT)
        
        # 记录状态
        self.recording = False
        self.record_file = None

    def create_command_log_panel(self):
        """创建命令日志窗口"""
        log_frame = ttk.LabelFrame(self.content_frame, text="命令日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        toolbar = ttk.Frame(log_frame)
        toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(toolbar, text="清空日志", command=self.clear_command_log, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="保存日志", command=self.save_command_log, width=8).pack(side=tk.LEFT, padx=2)

        self.command_log_text = scrolledtext.ScrolledText(log_frame, height=8, width=100)
        self.command_log_text.pack(fill=tk.BOTH, expand=True)
        self.command_log_text.config(state=tk.DISABLED)

    def clear_command_log(self):
        self.command_log_text.config(state=tk.NORMAL)
        self.command_log_text.delete(1.0, tk.END)
        self.command_log_text.config(state=tk.DISABLED)

    def save_command_log(self):
        log_content = self.command_log_text.get(1.0, tk.END).strip()
        if not log_content:
            messagebox.showinfo("提示", "没有可保存的数据")
            return

        file_path = filedialog.asksaveasfilename(
            title="保存命令日志",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content + "\n")
            except Exception as e:
                messagebox.showerror("错误", f"保存日志失败: {e}")

    def append_command_log(self, operation, command):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] 操作: {operation} | 指令: {command}\n"

        self.command_log_text.config(state=tk.NORMAL)
        self.command_log_text.insert(tk.END, log_line)
        self.command_log_text.see(tk.END)
        self.command_log_text.config(state=tk.DISABLED)
        
    def serial_callback(self, event_type, data):
        """串口通信回调函数"""
        if event_type == "data_received":
            self.display_serial_data(f"← {data}", "receive")
            self.rx_count.set(self.rx_count.get() + 1)
        elif event_type == "connection_update":
            if data["connected"]:
                self.connection_status.set(f"已连接: {data['port']}")
                self.connect_btn.config(state="disabled")
                self.disconnect_btn.config(state="normal")
                self.display_serial_data(f"已连接到串口: {data['port']}", "system")
            else:
                self.connection_status.set("未连接")
                self.connect_btn.config(state="normal")
                self.disconnect_btn.config(state="disabled")
                self.display_serial_data("串口连接已断开", "system")
        elif event_type == "connection_error":
            self.connection_status.set(f"连接失败: {data['error']}")
            self.connect_btn.config(state="normal")
            self.disconnect_btn.config(state="disabled")
            self.display_serial_data(f"连接错误: {data['error']}", "error")
    
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
            messagebox.showerror("错误", "请选择串口")
            return
        
        success = self.serial_comm.connect(port, baud_rate)
        if success:
            self.display_serial_data(f"正在连接串口: {port} @ {baud_rate} baud", "system")
    
    def disconnect_serial(self):
        """断开串口连接"""
        self.serial_comm.disconnect()
    
    def test_connection(self):
        """测试连接"""
        if not self.serial_comm.is_connected:
            messagebox.showwarning("警告", "请先连接串口")
            return
        
        # 发送测试命令
        command = "*IDN?"
        self.send_serial_command(command, lambda response, error: 
            messagebox.showinfo("测试结果", f"响应: {response}" if response else f"错误: {error}"))
    
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
            messagebox.showwarning("警告", "请先连接串口")
            return

        operation = command.split()[0] if command else "UNKNOWN"
        self.append_command_log(operation, command)
        
        # 显示发送的命令
        self.display_serial_data(f"→ {command}", "send")
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
            title="保存串口数据记录",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                self.record_file = open(file_path, 'a', encoding='utf-8')
                self.record_file.write("timestamp,type,data\n")
                self.recording = True
                self.display_serial_data(f"开始记录到: {file_path}", "system")
            except Exception as e:
                messagebox.showerror("错误", f"无法创建记录文件: {e}")
    
    def stop_recording(self):
        """停止记录串口数据"""
        if self.recording and self.record_file:
            self.recording = False
            self.record_file.close()
            self.record_file = None
            self.display_serial_data("已停止记录", "system")
    
    def save_serial_log(self):
        """保存串口日志"""
        if not self.serial_log:
            messagebox.showinfo("提示", "没有可保存的数据")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="保存串口日志",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(list(self.serial_log), f, indent=2, ensure_ascii=False)
                self.display_serial_data(f"日志已保存到: {file_path}", "system")
            except Exception as e:
                messagebox.showerror("错误", f"保存日志失败: {e}")
    
    def update_serial_data(self):
        """更新串口数据"""
        if self.serial_comm.is_connected:
            # 更新通道状态指示灯
            for i in range(self.max_channels):
                indicator = self.channel_controls[i]["serial_indicator"]
                # 模拟通信状态变化
                if i == (self.current_channel - 1):
                    indicator.config(foreground="green")
                else:
                    indicator.config(foreground="orange")
        
        # 每秒更新一次
        self.root.after(1000, self.update_serial_data)
    
    def bind_hotkeys(self):
        # 热键绑定
        self.root.bind("<Alt-1>", lambda e: self.select_channel(1))
        self.root.bind("<Alt-2>", lambda e: self.select_channel(2))
        self.root.bind("<Alt-3>", lambda e: self.select_channel(3))
        self.root.bind("<Alt-4>", lambda e: self.select_channel(4))
        self.root.bind("<Alt-5>", lambda e: self.select_channel(5))
        self.root.bind("<Alt-6>", lambda e: self.select_channel(6))
        self.root.bind("<Alt-7>", lambda e: self.select_channel(7))
        self.root.bind("<Alt-8>", lambda e: self.select_channel(8))
        
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
        self.log_operation("Test Signal Toggled", {"state": "ON" if new_state else "OFF"})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"TEST {1 if new_state else 0}"
            self.send_serial_command(command)
    
    def toggle_heater(self):
        """切换加热器开关状态"""
        new_state = self.heater_enabled.get()
        self.log_operation("Heater Toggled", {"state": "ON" if new_state else "OFF"})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"HEAT {1 if new_state else 0}"
            self.send_serial_command(command)
    
    def select_channel(self, channel):
        """选择通道"""
        # 取消之前选中的通道
        for i in range(self.max_channels):
            self.channel_controls[i]["select_btn"].state(["!selected"])
        
        # 选中当前通道
        self.current_channel = channel
        self.channel_controls[channel-1]["select_btn"].state(["selected"])
        self.update_channel_display()
        self.log_operation("Selected Channel", {"channel": channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"CH {channel}"
            self.send_serial_command(command)
    
    def update_channel_display(self):
        """更新通道显示（模拟）"""
        pass
    
    def s_lock(self):
        """SQUID锁定模式"""
        self.squid_states[self.current_channel] = "LOCK"
        self.array_states[self.current_channel] = "TUNE"
        self.update_state_indicators()
        self.log_operation("S-LOCK Mode", {"channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"SLOCK {self.current_channel}"
            self.send_serial_command(command)
    
    def s_tune(self):
        """SQUID调谐模式"""
        self.squid_states[self.current_channel] = "TUNE"
        self.update_state_indicators()
        self.log_operation("S-TUNE Mode", {"channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"STUNE {self.current_channel}"
            self.send_serial_command(command)
    
    def a_lock(self):
        """阵列锁定模式"""
        self.array_states[self.current_channel] = "LOCK"
        self.squid_states[self.current_channel] = "TUNE"
        self.update_state_indicators()
        self.log_operation("A-LOCK Mode", {"channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"ALOCK {self.current_channel}"
            self.send_serial_command(command)
    
    def a_tune(self):
        """阵列调谐模式"""
        self.array_states[self.current_channel] = "TUNE"
        self.update_state_indicators()
        self.log_operation("A-TUNE Mode", {"channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"ATUNE {self.current_channel}"
            self.send_serial_command(command)
    
    def update_state_indicators(self):
        """更新状态指示灯"""
        squid_state = self.squid_states[self.current_channel]
        array_state = self.array_states[self.current_channel]
        
        squid_label = self.channel_controls[self.current_channel-1]["squid_state"]
        array_label = self.channel_controls[self.current_channel-1]["array_state"]
        
        squid_label.config(
            text="SL" if squid_state == "LOCK" else "ST",
            background="green" if squid_state == "LOCK" else "yellow"
        )
        
        array_label.config(
            text="AL" if array_state == "LOCK" else "AT",
            background="green" if array_state == "LOCK" else "yellow"
        )
    
    def set_parameter(self, param):
        """设置参数"""
        value = getattr(self, param).get()
        print(f"Setting {param} to {value} for channel {self.current_channel}")
        self.is_modified = True
        self.log_operation("Set Parameter", {"parameter": param, "value": value, "channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            if param == "s_bias":
                command = f"SB {self.current_channel} {value}"
            elif param == "s_flux":
                command = f"SF {self.current_channel} {value}"
            elif param == "a_bias":
                command = f"AB {self.current_channel} {value}"
            elif param == "a_flux":
                command = f"AF {self.current_channel} {value}"
            elif param == "offset":
                command = f"OF {self.current_channel} {value}"
            else:
                command = ""
            
            if command:
                self.send_serial_command(command)
    
    def toggle_squid_step(self):
        """切换SQUID参数调节步长"""
        print("Toggling SQUID coarse/fine step")
        self.is_modified = True
        self.log_operation("Toggle SQUID Step")
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"SCF {self.current_channel}"
            self.send_serial_command(command)
    
    def toggle_array_step(self):
        """切换阵列参数调节步长"""
        print("Toggling Array coarse/fine step")
        self.is_modified = True
        self.log_operation("Toggle Array Step")
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"ACF {self.current_channel}"
            self.send_serial_command(command)
    
    def zero_restore_squid(self):
        """SQUID参数归零/恢复"""
        print("Zeroing/restoring SQUID parameters")
        self.is_modified = True
        self.log_operation("Zero/Restore SQUID")
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"SZR {self.current_channel}"
            self.send_serial_command(command)
    
    def zero_restore_array(self):
        """阵列参数归零/恢复"""
        print("Zeroing/restoring Array parameters")
        self.is_modified = True
        self.log_operation("Zero/Restore Array")
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"AZR {self.current_channel}"
            self.send_serial_command(command)
    
    def reset(self):
        """重置反馈环路"""
        print(f"Resetting channel {self.current_channel}")
        self.is_modified = True
        self.log_operation("Reset Channel", {"channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"RST {self.current_channel}"
            self.send_serial_command(command)
    
    def heat(self):
        """启动加热循环"""
        print(f"Heating channel {self.current_channel}")
        self.is_modified = True
        self.log_operation("Heat", {"channel": self.current_channel})
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"HEAT {self.current_channel} {self.heat_time.get()}"
            self.send_serial_command(command)
    
    def refresh(self):
        """刷新所有设置"""
        print("Refreshing all settings")
        self.log_operation("Refresh System")
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = f"REF {self.current_channel}"
            self.send_serial_command(command)
    
    def toggle_master(self):
        """切换主模式"""
        print("Toggling master mode")
        self.is_modified = True
        self.log_operation("Toggle Master Mode")
        
        # 发送串口命令
        if self.serial_comm.is_connected:
            command = "MST"
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
    
    def new_file(self):
        """创建新文件"""
        if self.is_modified:
            if not self.prompt_save():
                return
        
        # 重置所有状态
        self.reset_system()
        
    def reset_system(self):
        """重置系统状态"""
        self.current_channel = 1
        self.max_channels = 8
        self.pci_type = "PCI-1000"
        self.squid_states = {i: "TUNE" for i in range(1, self.max_channels+1)}
        self.array_states = {i: "TUNE" for i in range(1, self.max_channels+1)}
        self.data_history = []
        self.is_modified = False
        self.file_path = None
        self.root.title("STAR Cryoelectronics Control System - New File")
        
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
                
                # 加载开关状态
                self.test_signal_enabled.set(params.get("test_signal_enabled", False))
                self.heater_enabled.set(params.get("heater_enabled", False))
                
                # 更新UI状态
                self.update_state_indicators()
                self.file_path = file_path
                self.is_modified = False
                self.root.title(f"STAR Cryoelectronics Control System - {os.path.basename(file_path)}")
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
                    "test_signal_enabled": self.test_signal_enabled.get(),
                    "heater_enabled": self.heater_enabled.get()
                },
                "data_history": self.data_history
            }
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.file_path = file_path
            self.is_modified = False
            self.root.title(f"STAR Cryoelectronics Control System - {os.path.basename(file_path)}")
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
