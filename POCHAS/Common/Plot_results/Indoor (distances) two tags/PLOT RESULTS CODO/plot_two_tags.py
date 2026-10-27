import json
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares
from matplotlib.collections import PolyCollection
import math as m
import glob
import os
from scipy.interpolate import NearestNDInterpolator
################
select = 1 # 0: ALL 1: 2D position & RSSI, 2: 2D position and height
################
times = {"time": [], "tag": []}
data = {
    '1': {str(i): {'times': [], 'dists': [], 'rssis': []} for i in range(1, 10)},
    '2': {str(i): {'times': [], 'dists': [], 'rssis': []} for i in range(1, 10)}
}
positions = {
    '1':{'x': [], 'y': [], 'z': [], 'times': [],'rssi': []},
    '2':{'x': [], 'y': [], 'z': [], 'times': [],'rssi': []}
}

last_guess = {
    '1': [0.0, 0.0, 1.0],
    '2': [0.0, 0.0, 1.0]
}

def axis(x,y,z):
    x_final = []
    y_final = []
    z_final = []
    for x1,y1,z1 in zip(x,y,z):
        x1 = -x1
        y1 = -y1
        alpha = 9
        alpha_rad = m.radians(alpha)
        x_rot = x1 * m.cos(alpha_rad) - y1 * m.sin(alpha_rad)
        y_rot = x1 * m.sin(alpha_rad) + y1 * m.cos(alpha_rad)
        
        x_final.append(x_rot + 12.8)
        y_final.append(y_rot + -4)
        z_final.append(z1 + 1.82)

    return x_final,y_final,z_final

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

file = "2_4_Rxfile.txt"
#file = "433_Rxfile.txt"

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

            if (len(anchors_line) >= 4): # ONLY IF >= 4 ANCHORS
                pos = calc_position(anchors_line, dists_line, last_guess[tag])
                
                last_guess[tag] = pos
                positions[tag]['x'].append(pos[0])
                positions[tag]['y'].append(pos[1])
                positions[tag]['z'].append(pos[2])
                positions[tag]['times'].append(timestamp)
                positions[tag]['rssi'].append(rssi_value-26.4)
        except Exception:
            continue

colors = {'1': 'red', '2': 'green', '3': 'blue', '4': 'orange', '5': 'purple', '6': 'brown', '7': 'pink', '8': 'black'}
linestyles = {'1': '-', '2': '--'}

##################################
##################################
# PLOT
##################################
##################################

fig_5,ax6 = plt.subplots(figsize=(8, 8))


all_rssis = positions['1']['rssi'] + positions['2']['rssi']
if all_rssis and min(all_rssis) == max(all_rssis):
    vmin, vmax = all_rssis[0] - 1.0, all_rssis[0] + 1.0
else:
    vmin, vmax = None, None

x_1 = 12.8
y_1 = -4
z_1 = 1.82
alpha = 9
alpha_rad = m.radians(alpha)

x1, y1, r1 = positions['1']['x'], positions['1']['y'], positions['1']['rssi']
x_final_1, y_final_1, _ = axis(x1,y1,[0]*len(x1))
for t in positions['1']['times']:
    times['time'].append(t)
    times['tag'].append('1')


#if x1:
    # ax6.plot(x_final_1, y_final_1, color='darkred', alpha=0.4, linestyle='-', linewidth=1.5, zorder=1)
    # colour (red)
    #sc1 = ax6.scatter(x_final_1, y_final_1, c=r1, cmap='Reds', vmin=vmin, vmax=vmax, s=40, marker='o', label='Tag 1', zorder=2)
    #cbar1 = fig_5.colorbar(sc1, ax=ax6, pad=0.01, shrink=0.7)
    #cbar1.set_label('RSSI Tag 1 (dB)')

# 2nd tag
x2, y2, r2 = positions['2']['x'], positions['2']['y'], positions['2']['rssi']
x_final_2, y_final_2, _ = axis(x2,y2,[0]*len(x2))

for t in positions['2']['times']:
    times['time'].append(t)
    times['tag'].append('2')

if x2:
    ax6.plot(x_final_2, y_final_2, color='darkblue', alpha=0.4, linestyle='-', linewidth=1.5, zorder=1)
    # colour (blue)
    sc2 = ax6.scatter(x_final_2, y_final_2, c=r2, cmap='jet', vmin=-100, vmax=-40, s=40, marker='o', label='Tag 2', zorder=2)
    cbar2 = fig_5.colorbar(sc2, ax=ax6, pad=0.08, shrink=0.7)
    cbar2.set_label('RSSI Tag 2 (dBm)')

# anchors
for idx in range(len(anchors)):
    anchor = anchors[(idx)]
    if anchor != 0:
        x_final_anchor, y_final_anchor, _ = axis([anchor[0]],[anchor[1]],([0]*len([anchor[0]])))
        x_final_anchor = x_final_anchor[0]
        y_final_anchor = y_final_anchor[0]
        ax6.plot(x_final_anchor, y_final_anchor, 'D', markersize=14, color='black', zorder=3)

        # num inside anchor
        if idx == 9:
            ax6.text(x_final_anchor, y_final_anchor, "Tx", color='white',fontsize=9, fontweight='bold',ha='center', va='center')
        else:
            ax6.text(x_final_anchor, y_final_anchor, str(idx), color='white',fontsize=9, fontweight='bold',ha='center', va='center')


ax6.plot([], [], 'D', color='black', label='Anchors')
ax6.set_xlabel('X (m)')
ax6.set_ylabel('Y (m)')


#######################


x_coords = []
y_coords = []
z_coords = []
faces = []  

with open('floor_coords.txt', 'r') as f:

    l = 0
    for line in f:
        line = line.strip()
        if line.startswith('x'):
            x, y, z = line.split(',')

            x1 = float(x.split(':')[1])
            y1 = float(y.split(':')[1])
            z1 = float(z.split(':')[1])

            x_coords.append(x1)
            y_coords.append(y1)
            z_coords.append(z1)

        if line.startswith('FACE'):
            p = line.split(':')[1]
            
            points = []
            for idx in p.split(','):
                points.append(int(idx))
            
            vertex = []
            for idx in points:
                vertex.append([x_coords[idx], y_coords[idx]])
            
            faces.append(np.array(vertex))

coleccion = PolyCollection(faces, linewidths=0, facecolors='lightgrey',zorder=0)

ax6.add_collection(coleccion)
ax6.autoscale()
ax6.grid()
plt.tight_layout()

##################
combined = list(zip(times['time'], times['tag']))
combined.sort()

times["time"] = [item[0] for item in combined]
times["tag"] = [item[1] for item in combined]
get_height = NearestNDInterpolator(list(zip(x_coords, y_coords)), z_coords)

idx1 = 0
idx2 = 0

with open('measure_433.txt', 'w') as f:
    f.write("# RSSI Measurements Codo\n")
    f.write("COORDINATES TX (X Y Z):\n")
    tx = anchors[9]
    x_final_anchor, y_final_anchor, _ = axis([tx[0]],[tx[1]],([0]*len([tx[0]])))
    x_final_anchor = x_final_anchor[0]
    y_final_anchor = y_final_anchor[0]
    z_final_anchor = tx[2] + 1.7

    f.write(f"{x_final_anchor:.3f}, {y_final_anchor:.3f}, {z_final_anchor:.3f}\n")
    f.write("COORDINATES RX:\n")
    f.write("X, Y, Z, RSSI, Time, Tag\n")
    
    for i in range(len(times['time'])):
        t = times['time'][i]
        tag = times['tag'][i]
        if tag == '1':
            x = positions['1']['x'][idx1]
            y = positions['1']['y'][idx1]
            z = positions['1']['z'][idx1]
            rssi = positions['1']['rssi'][idx1]
            idx1 += 1
            
        elif tag == '2':
            x = positions['2']['x'][idx2]
            y = positions['2']['y'][idx2]
            z = positions['2']['z'][idx2]
            rssi = positions['2']['rssi'][idx2]
            idx2 += 1
            
        

        x_final, y_final, z_final = axis([x], [y], [z])
        z_final = get_height(x_final[0], y_final[0]) + 1.7  # add height of tag
        f.write(f"{x_final[0]:.3f}, {y_final[0]:.3f}, {z_final:.3f}, {rssi}, {t}, {tag}\n")
  



if select == 0:

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)

    for tag in ['1', '2']:
        for anchor in ['1', '2', '3', '4', '5', '6', '7', '8']:
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
    ax2.set_ylabel('RSSI (dBm)')
    ax2.set_title('RSSI tag vs Time')
    ax2.grid(True)
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    plt.tight_layout()
'''
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
        ax3.plot(anchor[0], anchor[1], 'D', markersize=14, color='black', zorder=3)
        # num inside anchor
        ax3.text(anchor[0], anchor[1], str(idx), color='white',fontsize=9, fontweight='bold',ha='center', va='center')
ax3.plot([], [], 'D', color='black', label='Anchors')

ax3.set_title('2D Position & RSSI')
ax3.set_xlabel('X (m)')
ax3.set_ylabel('Y (m)')
ax3.grid()
ax3.legend(loc='upper left')
ax3.axis('equal')
plt.tight_layout()
'''

####################
# HEIGHT
####################

if select == 0 or select == 2:
    

# third figure: height
    fig_3, ax4 = plt.subplots(figsize=(8, 4))

    for tag in ['1', '2']:
        z = positions[tag]['z']
        for idx in range(len(z)):
            z[idx] = z[idx] + 1.7 # add height of tag
        times = positions[tag]['times']
        if z:
            ax4.plot(times, z, label=f'Height vs Time Tag {tag}', linewidth=2)

    ax4.set_title('Height vs Time')
    ax4.set_xlabel('Time')
    ax4.set_ylabel('Height (m)')
    ax4.grid()
    ax4.legend()
    plt.tight_layout()

# figure height with stl
    fig_2, ax3 = plt.subplots(figsize=(8, 4))
    for tag in ['1', '2']:
        x_anchor, y_anchor, _ = axis(positions[tag]['x'], positions[tag]['y'], [0]*len(positions[tag]['x']))
        z_floor = get_height(x_anchor, y_anchor)
        times = positions[tag]['times']
        z_real = z_floor + 1.7
        ax3.plot(times, z_real, label=f'Height vs Time Tag {tag}', linewidth=2)

    ax3.set_title('Height vs Time')
    ax3.set_xlabel('Time')
    ax3.set_ylabel('Height (m)')
    ax3.grid()
    ax3.legend()
    plt.tight_layout()



plt.show()


