# -*- coding: utf-8 -*-
"""
Created on Fri Dec  1 14:34:49 2023

@author: gleon
"""

import serial
import time

arduino = serial.Serial(port='/dev/ttyACM0', baudrate=9600, timeout=.1)
ii=0
Ndata=1
data = 0
value2 = 0



def write_read0(x):
    arduino.write(bytes(x,  'utf-8'))
    time.sleep(01.1)
    data0 = arduino.readline()
    #data = int(data0.decode())
    time.sleep(0.1)
    return  data0

def write_read(x):
    arduino.write(bytes(x,  'utf-8'))
    time.sleep(0.1)
    data0 = arduino.readline()
    data = int(data0.decode())
    time.sleep(0.1)
    return  data

value  = write_read0('1')
while True:
    num = input("Enter a number: ")
    if int(num)>1.1 :
        print('break')
        break
    
    value  = write_read0(num)
   # linea=str(ii)+' '+str(value[0])+'\n'
    
    print(value)
    
   
    
arduino.close()
