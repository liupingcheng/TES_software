#coding:utf-8
import time
import binascii
import sys

from socket import *
def byte12ToInt(byte12):
    if((byte12&0x8000)==0):
        r= byte12
    else:
        byte12=((byte12*-1)^0x1fff)+0x2000
        byte12=byte12<<2
        r= byte12
    return r
    
#''代表服务器为 localhost
myHost = '192.168.10.16'
#在一个非保留端口号上进行监听
# myPort = 24
myPort = 5024
#设置一个TCP socket对象
sockobj = socket(AF_INET, SOCK_STREAM)
#sockobj.bind(("", 5001))

server_addr = (myHost, myPort)
sockobj.connect(server_addr)
#configuration_file = open('./adc_configuration.txt', 'r')
configuration_file_name=sys.argv[1]
print(configuration_file_name)
configuration_file = open(configuration_file_name, 'r')
#configuration_file = open('./dac_clk_configuration.txt', 'r')
c = 0
while 1:
    configuration_line = configuration_file.readline()
    if not configuration_line:
        if(c==0):
            print('Error File!')
        break
    print('Write ', configuration_line)
    configuration_hex = int(configuration_line,16)
    if(configuration_hex==0xFFFFFFFF):
        time.sleep(1)
        print('sleep 1s')
        continue
    else:
        time.sleep(0.1)
    #print('Hex ', configuration_line)
    configuration_byte=configuration_hex.to_bytes(4, 'big')
    #print('Byte ', configuration_line)
    sockobj.send(configuration_byte)
    time.sleep(0.01)
    data = sockobj.recv(4)
    if not data: break
    print ('Read ', binascii.hexlify(data))
    if(c<2):
        c=c+1    

configuration_file.close()
sockobj.close()
