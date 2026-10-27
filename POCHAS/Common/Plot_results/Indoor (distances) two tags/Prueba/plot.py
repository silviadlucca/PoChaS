import json
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares
import glob
import os


data = {
    '1': {str(i): {'times': [], 'dists': [], 'rssis': []} for i in range(1, 9)},
    '2': {str(i): {'times': [], 'dists': [], 'rssis': []} for i in range(1, 9)}
}
positions = {
    '1':{'x': [], 'y': [], 'z': [], 'times': [],'rssi': []},
    '2':{'x': [], 'y': [], 'z': [], 'times': [],'rssi': []}
}

last_guess = {
    '1': [0.0, 0.0, 1.0],
    '2': [0.0, 0.0, 1.0]
}

def residuals(position, anchor_positions, measured_distances):
    d_calc = np.linalg.norm(anchor_positions - position, axis=1)
    return d_calc - measured_distances

def calc_position(anchors, distances, initial_guess):
    anchors_np = np.array(anchors)
    distances_np = np.array(distances)
    
    indices_ordenados = np.argsort(distances_np)
    indices_mejores = indices_ordenados[:4]
    
    anchors_filt = anchors_np[indices_mejores]
    distances_filt = distances_np[indices_mejores]
    
    result = least_squares(residuals, initial_guess, args=(anchors_filt, distances_filt), method='lm')
    return result.x

try:
    json_f = max(glob.glob('*.json'), key=os.path.getmtime)
    with open(json_f, 'r') as f:
        anchors_json = json.load(f)
        max_idx = max(int(k) for k in anchors_json.keys())
        anchors = [0] * (max_idx + 1)
        for idx, coords in anchors_json.items():
            anchors[int(idx)] = coords
except Exception as e:
    print(f"Error cargando anchors.json: {e}")

# Leer archivo
file = "2_4_v1_Rxfile.txt"


with open(file, 'r') as f:
    for line in f:
        if line.startswith('#') or line.startswith('RSSI'):
            continue
        try:
            parts = line.split(',')
            rssi_value = float(parts[0])
            
            s1 = line.find('{')
            e1 = line.find('}', s1)
            dist_data = json.loads(line[s1:e1+1])
            
            s2 = line.find('{', e1)
            e2 = line.find('}', s2)
            rssi_data = json.loads(line[s2:e2+1])
            
            end = line[e2+1:].split(',')
            tag = end[1].strip()
            timestamp = float(end[2])
            
            anchors_line = []
            dists_line = []
            for idx in dist_data:
                anchors_line.append(anchors[int(idx)])
                dists_line.append(dist_data[idx])
                
            if len(anchors_line) >= 4:
                pos = calc_position(anchors_line, dists_line, last_guess[tag])
                last_guess[tag] = pos
                positions[tag]['x'].append(pos[0])
                positions[tag]['y'].append(pos[1])
                positions[tag]['z'].append(pos[2])
                positions[tag]['times'].append(timestamp)
                positions[tag]['rssi'].append(rssi_value)
                
        except Exception as e:
            continue

# Figura sencilla: XY
fig, ax = plt.subplots(figsize=(10, 8))

# Anchors
for i, anchor in enumerate(anchors):
    if anchor != 0:
        ax.plot(anchor[0], anchor[1], 'D', markersize=12, color='black', zorder=3)
        ax.text(anchor[0], anchor[1], str(i), color='white', fontsize=8, fontweight='bold', ha='center', va='center')
ax.plot([], [], 'D', color='black', label='Anchors')

# Tag 1
if positions['1']['x']:
    ax.plot(positions['1']['x'], positions['1']['y'], color='red', alpha=0.5, linestyle='-', label='Trayectoria T1')
    ax.scatter(positions['1']['x'], positions['1']['y'], color='red', s=20, label='Medidas T1')

# Tag 2
if positions['2']['x']:
    ax.plot(positions['2']['x'], positions['2']['y'], color='blue', alpha=0.5, linestyle='-', label='Trayectoria T2')
    ax.scatter(positions['2']['x'], positions['2']['y'], color='blue', s=20, label='Medidas T2')

ax.set_title('Prueba Sencilla: Posición XY de Etiquetas 1 y 2')
ax.set_xlabel('X (m)')
ax.set_ylabel('Y (m)')
ax.grid(True)
ax.legend(loc='upper right')
ax.axis('equal')

plt.tight_layout()
plt.show()