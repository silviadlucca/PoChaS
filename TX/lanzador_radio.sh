#!/bin/bash
echo "esperamos 30 segundos"
sleep 10
echo "ya pasaron 10"
sleep 10
echo "solo faltan 10"
sleep 10
echo "intentamos arrancar"
# Esperamos 30 segundos para asegurarnos de que el entorno gráfico esté listo

cd /home/pi #nos aseguramos de estar en la carpeta del usuario pi
export DISPLAY=: # para el que el entorno grafico funcione bien

/usr/bin/python3 /home/pi/Desktop/TXv01/tx_medidas.py > /home/pi/log_radio.txt 2>&1
#path de python - archivo a ejecutar - path del log de salida y errores

echo "el programa se cerro"
echo -p "presiona enter para cerrar"