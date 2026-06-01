import os
import glob
import json
import re
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares

# --- CONFIGURATION ---
USE_MIN_ANCHORS = 1  # 1: Use only the 4 anchors with the best RSSI. 0: Use all detected anchors.
# -2: Dinámico (Combina el mejor punto a punto). -1: Auto-First. 0: Todos. 1: Tag 1. 2: Tag 2.
TARGET_TAG = -2      

# --- FILE SEARCH FUNCTIONS ---
def get_latest_file(extension, directory="."):
    """Searches the specified directory for the most recent file with the given extension."""
    search_pattern = os.path.join(directory, f'*{extension}')
    list_of_files = glob.glob(search_pattern)
    if not list_of_files:
        return None
    return max(list_of_files, key=os.path.getmtime)

def load_anchors_config(filepath):
    with open(filepath, 'r') as file:
        return json.load(file)

# --- AUTO SELECTION (Mode -1) ---
def auto_select_best_tag(filepath):
    first_rssi_per_tag = {}
    log_pattern = re.compile(r'^\s*([-\d\.]+)\s*,\s*(\{.*?\})\s*,\s*(\{.*?\}),\s*(\d+)')
    
    with open(filepath, 'r') as file:
        for line in file:
            if not line.strip() or line.startswith('#'):
                continue
            match = log_pattern.match(line)
            if match:
                try:
                    rssis = ast.literal_eval(match.group(3))
                    tag_id = int(match.group(4))
                    if tag_id not in first_rssi_per_tag and rssis:
                        avg_rssi = sum(rssis.values()) / len(rssis)
                        first_rssi_per_tag[tag_id] = avg_rssi
                    if len(first_rssi_per_tag) >= 2:
                        break
                except Exception:
                    continue
                    
    if not first_rssi_per_tag:
        return None
    best_tag = max(first_rssi_per_tag, key=first_rssi_per_tag.get)
    return best_tag

# --- MATHEMATICAL FUNCTIONS ---
def residuals(position, anchor_positions, measured_distances):
    x, y, z = position
    errors = []
    for (anchor_x, anchor_y, anchor_z), d_measured in zip(anchor_positions, measured_distances):
        d_calc = np.sqrt((x - anchor_x)**2 + (y - anchor_y)**2 + (z - anchor_z)**2)
        errors.append(d_calc - d_measured)
    return errors

def calculate_tag_position(distances_dict, anchors_config, initial_guess):
    anchor_coords = []
    measured_dists = []
    for anchor_id, distance in distances_dict.items():
        if str(anchor_id) in anchors_config:
            anchor_coords.append(anchors_config[str(anchor_id)])
            measured_dists.append(distance)
            
    if len(measured_dists) < 4:
        return None

    result = least_squares(residuals, initial_guess, args=(anchor_coords, measured_dists), method='lm')
    return result.x if result.success else None

# --- FILE PROCESSING ---
def process_log_file(filepath, anchors_config, target_tag):
    tags_data = {}
    log_pattern = re.compile(r'^\s*([-\d\.]+)\s*,\s*(\{.*?\})\s*,\s*(\{.*?\}),\s*(\d+)')
    
    # ---------------------------------------------------------
    # MODO DINÁMICO (-2): Combina el mejor de cada par
    # ---------------------------------------------------------
    if target_tag == -2:
        tags_data['Dynamic'] = {'x': [], 'y': [], 'z': [], 'rssi': [], 'source_tag': []}
        last_position = (0.0, 0.0, 0.0)
        current_pair = {} # Búfer para guardar temporalmente el par de medidas
        
        with open(filepath, 'r') as file:
            for line_num, line in enumerate(file, 1):
                if not line.strip() or line.startswith('#'): continue
                match = log_pattern.match(line)
                if match:
                    try:
                        sdr_rssi_val = float(match.group(1))
                        distances = ast.literal_eval(match.group(2))
                        rssis = ast.literal_eval(match.group(3))
                        tag_id = int(match.group(4))
                        
                        if not distances: continue 
                        
                        avg_anchor_rssi = sum(rssis.values()) / len(rssis)
                        current_pair[tag_id] = {
                            'sdr_rssi': sdr_rssi_val,
                            'distances': distances,
                            'avg_rssi': avg_anchor_rssi,
                            'raw_rssis': rssis
                        }
                        
                        if len(current_pair) >= 2:
                            best_tag = max(current_pair, key=lambda k: current_pair[k]['avg_rssi'])
                            best_data = current_pair[best_tag]
                            
                            dists = best_data['distances']
                            if USE_MIN_ANCHORS == 1 and len(dists) > 4:
                                sorted_ids = sorted(dists.keys(), key=lambda k: best_data['raw_rssis'].get(k, -100), reverse=True)
                                dists = {k: dists[k] for k in sorted_ids[:4]}
                                
                            pos = calculate_tag_position(dists, anchors_config, last_position)
                            
                            if pos is not None:
                                tags_data['Dynamic']['x'].append(pos[0])
                                tags_data['Dynamic']['y'].append(pos[1])
                                tags_data['Dynamic']['z'].append(pos[2])
                                tags_data['Dynamic']['rssi'].append(best_data['sdr_rssi'])
                                tags_data['Dynamic']['source_tag'].append(best_tag)
                                last_position = pos
                                
                            current_pair = {}
                    except Exception:
                        pass
        return tags_data

    # ---------------------------------------------------------
    # MODOS NORMALES (0, 1, 2, etc.)
    # ---------------------------------------------------------
    last_positions = {}
    with open(filepath, 'r') as file:
        for line_num, line in enumerate(file, 1):
            if not line.strip() or line.startswith('#'): continue
            match = log_pattern.match(line)
            if match:
                try:
                    sdr_rssi_val = float(match.group(1))
                    distances = ast.literal_eval(match.group(2))
                    rssis = ast.literal_eval(match.group(3))
                    tag_id = int(match.group(4))
                    
                    if target_tag != 0 and tag_id != target_tag: continue
                    if not distances: continue 
                    
                    if tag_id not in tags_data:
                        tags_data[tag_id] = {'x': [], 'y': [], 'z': [], 'rssi': []}
                        last_positions[tag_id] = (0.0, 0.0, 0.0)
                        
                    if USE_MIN_ANCHORS == 1 and len(distances) > 4:
                        sorted_anchor_ids = sorted(distances.keys(), key=lambda k: rssis.get(k, -100), reverse=True)
                        distances = {k: distances[k] for k in sorted_anchor_ids[:4]}
                        
                    pos = calculate_tag_position(distances, anchors_config, last_positions[tag_id])
                    
                    if pos is not None:
                        tags_data[tag_id]['x'].append(pos[0])
                        tags_data[tag_id]['y'].append(pos[1])
                        tags_data[tag_id]['z'].append(pos[2])
                        tags_data[tag_id]['rssi'].append(sdr_rssi_val)
                        last_positions[tag_id] = pos
                except Exception:
                    pass
    return tags_data

# --- VISUALIZATION ---
def plot_trajectory_2d_and_height(tags_data, anchors_config, title_context):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # Dibujar Anclas
    for a_id, coords in anchors_config.items():
        ax1.scatter(coords[0], coords[1], c='red', marker='^', s=150, zorder=5)
        ax1.text(coords[0], coords[1] + 0.15, f"A{a_id}", fontsize=11, fontweight='bold')

    # Si estamos en modo dinámico, separamos visualmente por tag origen
    if 'Dynamic' in tags_data:
        data = tags_data['Dynamic']
        x_all, y_all, z_all = np.array(data['x']), np.array(data['y']), np.array(data['z'])
        rssi_all = np.array(data['rssi'])
        sources = np.array(data['source_tag'])
        
        vmin, vmax = rssi_all.min(), rssi_all.max()
        
        # Línea continua uniendo todo
        ax1.plot(x_all, y_all, c='gray', linestyle='--', alpha=0.6, zorder=2)
        
        sc = None
        # Tag 1 (Círculos)
        if np.any(sources == 1):
            sc = ax1.scatter(x_all[sources == 1], y_all[sources == 1], c=rssi_all[sources == 1], 
                             vmin=vmin, vmax=vmax, cmap='viridis', marker='o', s=70, edgecolor='black', zorder=3, label='Tag 1')
        # Tag 2 (Cuadrados)
        if np.any(sources == 2):
            sc2 = ax1.scatter(x_all[sources == 2], y_all[sources == 2], c=rssi_all[sources == 2], 
                              vmin=vmin, vmax=vmax, cmap='viridis', marker='s', s=70, edgecolor='black', zorder=3, label='Tag 2')
            if sc is None: sc = sc2
            
        if sc:
            cbar = plt.colorbar(sc, ax=ax1, pad=0.02, shrink=0.8)
            cbar.set_label('RSSI (dBm)')

        # Gráfica Z
        muestras = np.arange(1, len(z_all) + 1)
        ax2.plot(muestras, z_all, c='gray', linestyle='-', alpha=0.5, zorder=1)
        if np.any(sources == 1):
            ax2.scatter(muestras[sources == 1], z_all[sources == 1], c='#1f77b4', marker='o', s=40, zorder=2, label='Tag 1')
        if np.any(sources == 2):
            ax2.scatter(muestras[sources == 2], z_all[sources == 2], c='#ff7f0e', marker='s', s=40, zorder=2, label='Tag 2')

    else:
        # Modo normal
        cmaps = ['viridis', 'plasma', 'inferno', 'magma']
        line_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']
        for i, (tag_id, data) in enumerate(tags_data.items()):
            cmap, color = cmaps[i % len(cmaps)], line_colors[i % len(line_colors)]
            scatter = ax1.scatter(data['x'], data['y'], c=data['rssi'], cmap=cmap, s=60, edgecolor='black', zorder=3, label=f'Tag {tag_id}')
            ax1.plot(data['x'], data['y'], c='gray', linestyle='--', alpha=0.6, zorder=2)
            cbar = plt.colorbar(scatter, ax=ax1, pad=0.02, shrink=0.8)
            cbar.set_label(f'RSSI (dBm) - Tag {tag_id}')

            muestras = list(range(1, len(data['z']) + 1))
            ax2.plot(muestras, data['z'], marker='o', linestyle='-', color=color, markersize=5, alpha=0.8, label=f'Tag {tag_id}')

    ax1.set_title(f'2D Trajectory (X vs Y) - {title_context}')
    ax1.set_xlabel('X (m)')
    ax1.set_ylabel('Y (m)')
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.set_aspect('equal', adjustable='datalim')
    if len(tags_data) > 1 or 'Dynamic' in tags_data:
        ax1.legend(loc='upper right')

    ax2.set_title(f'Height over Time: Z vs Sample - {title_context}')
    ax2.set_xlabel('Sample Number')
    ax2.set_ylabel('Height Z (m)')
    ax2.grid(True, linestyle=':', alpha=0.7)
    if len(tags_data) > 1 or 'Dynamic' in tags_data:
        ax2.legend()

    plt.tight_layout()


def plot_trajectory_3d(tags_data, anchors_config, title_context):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    for a_id, coords in anchors_config.items():
        ax.scatter(coords[0], coords[1], coords[2], c='red', marker='^', s=150, zorder=5)
        ax.text(coords[0], coords[1], coords[2] + 0.3, f"A{a_id}", fontsize=11, fontweight='bold')

    if 'Dynamic' in tags_data:
        data = tags_data['Dynamic']
        x_all, y_all, z_all = np.array(data['x']), np.array(data['y']), np.array(data['z'])
        rssi_all = np.array(data['rssi'])
        sources = np.array(data['source_tag'])
        
        vmin, vmax = rssi_all.min(), rssi_all.max()
        ax.plot(x_all, y_all, z_all, c='gray', linestyle='--', alpha=0.6, zorder=2)
        
        sc = None
        if np.any(sources == 1):
            sc = ax.scatter(x_all[sources == 1], y_all[sources == 1], z_all[sources == 1], 
                            c=rssi_all[sources == 1], vmin=vmin, vmax=vmax, cmap='viridis', 
                            marker='o', s=70, edgecolor='black', alpha=0.9, zorder=3, label='Tag 1')
        if np.any(sources == 2):
            sc2 = ax.scatter(x_all[sources == 2], y_all[sources == 2], z_all[sources == 2], 
                             c=rssi_all[sources == 2], vmin=vmin, vmax=vmax, cmap='viridis', 
                             marker='s', s=70, edgecolor='black', alpha=0.9, zorder=3, label='Tag 2')
            if sc is None: sc = sc2

        if sc:
            cbar = plt.colorbar(sc, ax=ax, pad=0.05, shrink=0.7)
            cbar.set_label('RSSI (dBm)')
            
    else:
        cmaps = ['viridis', 'plasma', 'inferno', 'magma']
        for i, (tag_id, data) in enumerate(tags_data.items()):
            cmap = cmaps[i % len(cmaps)]
            scatter = ax.scatter(data['x'], data['y'], data['z'], c=data['rssi'], cmap=cmap, s=60, edgecolor='black', alpha=0.9, zorder=3, label=f'Tag {tag_id}')
            ax.plot(data['x'], data['y'], data['z'], c='gray', linestyle='--', alpha=0.6, zorder=2)
            cbar = plt.colorbar(scatter, ax=ax, pad=0.05, shrink=0.7)
            cbar.set_label(f'RSSI (dBm)')

    ax.set_title(f'3D Trajectory - {title_context}')
    ax.set_xlabel('X (metros)')
    ax.set_ylabel('Y (metros)')
    ax.set_zlabel('Z (metros)')
    
    if len(tags_data) > 1 or 'Dynamic' in tags_data:
        ax.legend()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))

    latest_json = get_latest_file('.json', directory=script_dir)
    if not latest_json:
        print(">> Error: No .json file found.")
        exit(1)
        
    anchors_config = load_anchors_config(latest_json)
    latest_txt = get_latest_file('.txt', directory=script_dir)
    
    if not latest_txt:
        print(">> Error: No data .txt file found.")
        exit(1)
        
    active_target = TARGET_TAG
    title_context = ""
    
    if TARGET_TAG == -2:
        print(">> Modo Dinámico activado. Seleccionando la mejor señal punto a punto...")
        title_context = "Trayectoria Óptima Combinada"
    elif TARGET_TAG == -1:
        print(">> Auto-selección activada. Analizando señal inicial...")
        best_tag = auto_select_best_tag(latest_txt)
        if best_tag is not None:
            active_target = best_tag
            print(f">> Se ha fijado el Tag {active_target} como objetivo para todo el recorrido.")
            title_context = f"Tag {active_target} (Auto-Seleccionado)"
        else:
            print(">> No se pudo determinar el mejor Tag. Mostrando todos.")
            active_target = 0
            title_context = "Todos los Tags"
    elif TARGET_TAG == 0:
        title_context = "Todos los Tags"
    else:
        title_context = f"Tag {TARGET_TAG}"
    
    tags_data = process_log_file(latest_txt, anchors_config, active_target)
    
    if tags_data:
        # Calcular el total sumando la longitud de los arrays 'x'
        if 'Dynamic' in tags_data:
            total_positions = len(tags_data['Dynamic']['x'])
        else:
            total_positions = sum(len(d['x']) for d in tags_data.values())
            
        print(f">> Successfully calculated {total_positions} valid positions. Generando gráficos...")
        
        # Estadísticas si es dinámico
        if TARGET_TAG == -2 and 'Dynamic' in tags_data:
            t1_count = list(tags_data['Dynamic']['source_tag']).count(1)
            t2_count = list(tags_data['Dynamic']['source_tag']).count(2)
            print(f">> Puntos elegidos del Tag 1: {t1_count}")
            print(f">> Puntos elegidos del Tag 2: {t2_count}")
        
        plot_trajectory_2d_and_height(tags_data, anchors_config, title_context)
        plot_trajectory_3d(tags_data, anchors_config, title_context)
        
        plt.show()
    else:
        print(">> No valid positions found.")