import math
import random
import json
import time
from datetime import datetime

# --- 1. CONFIGURACIÓN DEL ESCENARIO ---
# 6 Anclas distribuidas en una sala de 6x6 metros
anchors_config = {
    "1": [0.0, 0.0, 2.5],
    "2": [6.0, 0.0, 2.5],
    "3": [6.0, 6.0, 2.5],
    "4": [0.0, 6.0, 2.5],
    "5": [3.0, 3.0, 3.0],  # Ancla en el techo (centro)
    "6": [3.0, -2.0, 1.5]  # Ancla alejada, debería tener peor RSSI y ser filtrada
}

# Trayectoria circular del tag (radio 2m, centro 3,3, altura 1.0m)
cx, cy, cz = 3.0, 3.0, 1.0
radius = 2.0
num_samples = 100

def get_simulated_rssi(distance):
    """Simula un RSSI basado en la distancia (a más lejos, señal más negativa)"""
    base_rssi = -50  # RSSI a 0 metros
    path_loss = 20 * math.log10(distance) if distance > 0.1 else 0
    noise = random.uniform(-3, 3)
    return round(base_rssi - path_loss + noise, 2)

# --- 2. GENERAR ARCHIVOS ---
print("Generando escenario de prueba...")

# Crear el JSON de anclas
with open("anchors.json", "w") as f:
    json.dump(anchors_config, f, indent=4)
print("-> anchors.json generado.")

# Crear el log file de pruebas
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"{timestamp}_test_Rxfile.txt"

with open(filename, "w") as txt_file:
    # Cabecera típica de tu Flask
    txt_file.write("# RSSI Measurement Log\n")
    txt_file.write(f"# Date: {timestamp}\n")
    txt_file.write("# Frequency: 433.0 MHz\n")
    txt_file.write("# Gain: 40 dB\n")
    txt_file.write("# Measurement\tRSSI (dB)\n")
    txt_file.write("RSSI (dB)\tDistance to anchors\tRSSI of anchors\tTag\tTimestamp\tTemperature\n")

    for i in range(num_samples):
        # Ángulo para el círculo
        angle = (2 * math.pi / num_samples) * i
        
        # Posición real del tag en este instante
        tag_x = cx + radius * math.cos(angle)
        tag_y = cy + radius * math.sin(angle)
        tag_z = cz
        
        distances = {}
        rssis = {}
        
        for a_id, a_coords in anchors_config.items():
            # Distancia euclidiana teórica
            real_dist = math.sqrt((tag_x - a_coords[0])**2 + (tag_y - a_coords[1])**2 + (tag_z - a_coords[2])**2)
            
            # Añadimos un pequeño error (±5 cm) para simular ruido UWB
            noisy_dist = real_dist + random.uniform(-0.05, 0.05)
            distances[str(a_id)] = round(noisy_dist, 3)
            
            # Simulamos el RSSI
            rssis[str(a_id)] = get_simulated_rssi(real_dist)

        # SDR RSSI (ficticio)
        sdr_rssi = round(random.uniform(-75, -80), 2)
        
        # Convertimos diccionarios a string imitando a JSON
        distances_str = json.dumps(distances)
        rssis_str = json.dumps(rssis)
        
        # Formato exacto de tu archivo: {level2},{anchors_str},{rssis_str},{tag},{timestamp_ms},{temperature}
        txt_file.write(f"{sdr_rssi},{distances_str},{rssis_str},1,{int(time.time()*1000)},45.5\n")

print(f"-> Archivo de datos simulados generado: {filename}")
print("\n¡Listo! Ahora ejecuta tu script 'distances.py'.")
print("Deberías ver una gráfica 3D donde el Tag dibuja un círculo alrededor del centro.")