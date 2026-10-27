import json
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

import glob
import os

data = {
    '1': {str(i): {'times': [], 'dists': [], 'rssis': []} for i in range(1, 6)},
    '2': {str(i): {'times': [], 'dists': [], 'rssis': []} for i in range(1, 6)}
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
    error = d_calc - measured_distances
    return error

def calc_position(anchors,distances,initial_guess):

    anchors_np = np.array(anchors)
    distances_np = np.array(distances)

    
    indices_ordenados = np.argsort(distances_np)
    indices_mejores = indices_ordenados[:4]

    anchors_filt = anchors_np[indices_mejores]
    distances_filt = distances_np[indices_mejores]

    '''
    ref_anchor = anchors_filt[0] # coge el primer ancla para referencia
    other_anchors = anchors_filt[1:] # coge todos los anclas menos el primero

    ref_dist = distances_fil[0]
    other_dists = distances_fil[1:]

    A = 2 * (other_anchors-ref_anchor)
    b = (ref_dist**2-other_dists**2 + np.sum(other_anchors**2, axis=1) - np.sum(ref_anchor**2))
    pos, res, rank, s = np.linalg.lstsq(A, b, rcond=None)

    '''
    result = least_squares(residuals, initial_guess, args=(anchors_filt, distances_filt), method='lm')
    
    return result.x

# find json
all_files_json = glob.glob('*.json')

if not all_files_json:
    raise FileNotFoundError("No file found matching the pattern '*.json' in the current directory.")

json_f = max(all_files_json, key=os.path.getmtime)
with open(json_f, 'r') as f:
    anchors_json = json.load(f)
    max_ = 0
    for idx in anchors_json:
        max_ = max_ + 1
    anchors = [0] * (max_+1)
    for idx in anchors_json:
        anchors[int(idx)] = anchors_json[idx]
    # print(anchors)

# find files

all_files = glob.glob('*_Rxfile.txt')

if not all_files:
    raise FileNotFoundError("No file found matching the pattern '*_Rxfile.txt' in the current directory.")

file = max(all_files, key=os.path.getmtime)

with open(file, 'r') as f:
    for line in f:
        if line.startswith('#') or line.startswith('RSSI'):
            continue
        
        try:
            c1 = line.find(',')
            rssi_value = float(line[:c1])
            # json distances
            s1 = line.find('{')
            e1 = line.find('}', s1)
            dist_data = json.loads(line[s1:e1+1])
            
            # json rssi
            s2 = line.find('{', e1)
            e2 = line.find('}', s2)
            rssi_data = json.loads(line[s2:e2+1])
            


            end = line[e2+1:];
            end_str = end.split(',')
            tag = end_str[1]
            timestamp = float(end_str[2])
            
            for anchor in dist_data:
                data[tag][anchor]['times'].append(timestamp)
                data[tag][anchor]['dists'].append(dist_data[anchor])
                data[tag][anchor]['rssis'].append(rssi_data[anchor])

            ## 

            anchors_line = []
            dists_line = []
            for idx in dist_data:
                anchors_line.append(anchors[int(idx)])
                dists_line.append(dist_data[idx])

            if (len(anchors_line) >= 4):
                pos = calc_position(anchors_line, dists_line, last_guess[tag])
                last_guess[tag] = pos
                positions[tag]['x'].append(pos[0])
                positions[tag]['y'].append(pos[1])
                positions[tag]['z'].append(pos[2])
                positions[tag]['times'].append(timestamp)
                positions[tag]['rssi'].append(rssi_value)
        except Exception:
            continue

colors = {'1': 'red', '2': 'green', '3': 'blue', '4': 'orange', '5': 'purple'}
linestyles = {'1': '-', '2': '--'}

# figure
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)

for tag in ['1', '2']:
    for anchor in ['1', '2', '3', '4', '5']:
        times = data[tag][anchor]['times']
        dists = data[tag][anchor]['dists']
        rssis = data[tag][anchor]['rssis']
        
        if times:
            label = f'Tag {tag} - Anchor {anchor}'
            # distancias
            ax1.plot(times, dists, color=colors[anchor], linestyle=linestyles[tag], label=label)
            # rssis
            ax2.plot(times, rssis, color=colors[anchor], linestyle=linestyles[tag], label=label)

# 1 plot: distances
ax1.set_ylabel('Distance (m)')
ax1.set_title('Distance vs Time')
ax1.grid()
ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

# 2 plot: rssi
ax2.set_xlabel('Time')
ax2.set_ylabel('RSSI (dB)')
ax2.set_title('RSSI tag vs Time')
ax2.grid(True)
ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

plt.tight_layout()

# second figure: xy 
fig_2, ax3 = plt.subplots(figsize=(8, 6))

all_rssis = positions['1']['rssi'] + positions['2']['rssi']
if all_rssis and min(all_rssis) == max(all_rssis):
    vmin, vmax = all_rssis[0] - 1.0, all_rssis[0] + 1.0
else:
    vmin, vmax = None, None

# 1st tag
x1, y1, r1 = positions['1']['x'], positions['1']['y'], positions['1']['rssi']
if x1:
    ax3.plot(x1, y1, color='darkred', alpha=0.4, linestyle='-', linewidth=1.5, zorder=1)
    # colour (red)
    sc1 = ax3.scatter(x1, y1, c=r1, cmap='Reds', vmin=vmin, vmax=vmax, s=40, marker='o', label='Tag 1', zorder=2)
    cbar1 = fig_2.colorbar(sc1, ax=ax3, pad=0.01, shrink=0.7)
    cbar1.set_label('RSSI Tag 1 (dB)')

# 2nd tag
x2, y2, r2 = positions['2']['x'], positions['2']['y'], positions['2']['rssi']
if x2:
    ax3.plot(x2, y2, color='darkblue', alpha=0.4, linestyle='-', linewidth=1.5, zorder=1)
    # colour (blue)
    sc2 = ax3.scatter(x2, y2, c=r2, cmap='Blues', vmin=vmin, vmax=vmax, s=40, marker='o', label='Tag 2', zorder=2)
    cbar2 = fig_2.colorbar(sc2, ax=ax3, pad=0.08, shrink=0.7)
    cbar2.set_label('RSSI Tag 2 (dB)')

# anchors
for idx in range(len(anchors)):
    anchor = anchors[(idx)]
    if anchor != 0:
        ax3.plot(anchor[0], anchor[1], 'D', markersize=10, color='black', zorder=3)
ax3.plot([], [], 'D', color='black', label='Anchors')

ax3.set_title('2D Position (Color según RSSI)')
ax3.set_xlabel('X (m)')
ax3.set_ylabel('Y (m)')
ax3.grid()
ax3.legend(loc='upper left')
ax3.axis('equal')
plt.tight_layout()


# third figure: height
fig_3, ax4 = plt.subplots(figsize=(8, 4))

for tag in ['1', '2']:
    z = positions[tag]['z']
    times = positions[tag]['times']
    if z:
        ax4.plot(times, z, label=f'Height vs Time Tag {tag}', linewidth=2)

ax4.set_title('Height vs Time')
ax4.set_xlabel('Time')
ax4.set_ylabel('Height (m)')
ax4.grid()
ax4.legend()
plt.tight_layout()

plt.show()