import os
import glob
import json
import re
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares

# --- CONFIGURATION ---
USE_MIN_ANCHORS = 0  # 1: Use only the 4 anchors with the best RSSI. 0: Use all detected anchors.
TARGET_TAG = 0       # 0: Mostrar TODOS los tags. 1: Mostrar solo el tag 1. 2: Mostrar solo el tag 2.

# --- FILE SEARCH FUNCTIONS ---
def get_latest_file(extension, directory="."):
    """
    Searches the specified directory for the most recent file with the given extension.
    """
    search_pattern = os.path.join(directory, f'*{extension}')
    list_of_files = glob.glob(search_pattern)
    
    if not list_of_files:
        return None
        
    latest_file = max(list_of_files, key=os.path.getmtime)
    return latest_file

def load_anchors_config(filepath):
    """Loads and returns the anchors dictionary from a JSON file."""
    with open(filepath, 'r') as file:
        return json.load(file)

# --- MATHEMATICAL FUNCTIONS ---
def residuals(position, anchor_positions, measured_distances):
    """Calculates the error between theoretical and measured distances (3D)."""
    x, y, z = position
    errors = []
    for (anchor_x, anchor_y, anchor_z), d_measured in zip(anchor_positions, measured_distances):
        d_calc = np.sqrt((x - anchor_x)**2 + (y - anchor_y)**2 + (z - anchor_z)**2)
        errors.append(d_calc - d_measured)
    return errors

def calculate_tag_position(distances_dict, anchors_config, initial_guess):
    """Solves the 3D trilateration using least squares."""
    anchor_coords = []
    measured_dists = []
    
    for anchor_id, distance in distances_dict.items():
        if str(anchor_id) in anchors_config:
            # Expecting [x, y, z] from the JSON config
            anchor_coords.append(anchors_config[str(anchor_id)])
            measured_dists.append(distance)
            
    # At least 4 anchors are needed
    if len(measured_dists) < 4:
        return None

    result = least_squares(
        residuals, 
        initial_guess, 
        args=(anchor_coords, measured_dists),
        method='lm'
    )
    
    return result.x if result.success else None

# --- FILE PROCESSING ---
def process_log_file(filepath, anchors_config, target_tag):
    # Diccionario para almacenar los datos separados por Tag
    tags_data = {}
    
    # Diccionario para guardar la posición anterior como semilla, separada por tag
    last_positions = {}
    
    # Captura SDR RSSI, dict de distancias, dict de RSSIs de anclas y el ID del Tag
    log_pattern = re.compile(r'^\s*([-\d\.]+)\s*,\s*(\{.*?\})\s*,\s*(\{.*?\}),\s*(\d+)')
    
    with open(filepath, 'r') as file:
        for line_num, line in enumerate(file, 1):
            if not line.strip() or line.startswith('#'):
                continue
                
            match = log_pattern.match(line)
            if match:
                try:
                    sdr_rssi_val = float(match.group(1))
                    distances = ast.literal_eval(match.group(2))
                    rssis = ast.literal_eval(match.group(3))
                    tag_id = int(match.group(4))
                    
                    # Filtramos por el tag elegido (si es 0, procesamos todos)
                    if target_tag != 0 and tag_id != target_tag:
                        continue
                        
                    if not distances:
                        continue 
                    
                    # Inicializamos las listas y semilla para este tag si es la primera vez que lo vemos
                    if tag_id not in tags_data:
                        tags_data[tag_id] = {'x': [], 'y': [], 'z': [], 'rssi': []}
                        last_positions[tag_id] = (0.0, 0.0, 0.0)
                        
                    # Logic to select only the 4 anchors with the best signal (highest RSSI)
                    if USE_MIN_ANCHORS == 1 and len(distances) > 4:
                        sorted_anchor_ids = sorted(
                            distances.keys(), 
                            key=lambda k: rssis.get(k, -100), 
                            reverse=True
                        )
                        top_4_ids = sorted_anchor_ids[:4]
                        distances = {k: distances[k] for k in top_4_ids}
                        
                    pos = calculate_tag_position(distances, anchors_config, last_positions[tag_id])
                    
                    if pos is not None:
                        tags_data[tag_id]['x'].append(pos[0])
                        tags_data[tag_id]['y'].append(pos[1])
                        tags_data[tag_id]['z'].append(pos[2])
                        tags_data[tag_id]['rssi'].append(sdr_rssi_val)
                        last_positions[tag_id] = pos # Update seed for next iteration for this specific tag
                        
                except Exception as e:
                    print(f"Error processing line {line_num}: {e}")

    return tags_data

def plot_trajectory_2d_and_height(tags_data, anchors_config, target_tag):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # Dibujar Anclas
    for a_id, coords in anchors_config.items():
        ax1.scatter(coords[0], coords[1], c='red', marker='^', s=150, zorder=5)
        ax1.text(coords[0], coords[1] + 0.15, f"A{a_id}", fontsize=11, fontweight='bold')

    # Paletas de color diferentes para no confundir distintos tags
    cmaps = ['viridis', 'plasma', 'inferno', 'magma']
    line_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']

    for i, (tag_id, data) in enumerate(tags_data.items()):
        cmap = cmaps[i % len(cmaps)]
        color = line_colors[i % len(line_colors)]
        
        # Plot 2D
        scatter = ax1.scatter(data['x'], data['y'], c=data['rssi'], cmap=cmap, s=60, edgecolor='black', zorder=3, label=f'Tag {tag_id}')
        ax1.plot(data['x'], data['y'], c='gray', linestyle='--', alpha=0.6, zorder=2)
        
        # Cada tag tendrá su propia mini-barra de color (SDR RSSI)
        cbar = plt.colorbar(scatter, ax=ax1, pad=0.02, shrink=0.8)
        cbar.set_label(f'RSSI (dBm) - Tag {tag_id}')

        # Plot Height
        muestras = list(range(1, len(data['z']) + 1))
        ax2.plot(muestras, data['z'], marker='o', linestyle='-', color=color, markersize=5, alpha=0.8, label=f'Tag {tag_id}')

    title_str = "Todos los Tags" if target_tag == 0 else f"Tag {target_tag}"
    
    ax1.set_title(f'2D Trajectory (X vs Y) - {title_str}')
    ax1.set_xlabel('X (m)')
    ax1.set_ylabel('Y (m)')
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.set_aspect('equal', adjustable='datalim')
    if len(tags_data) > 1:
        ax1.legend(loc='upper right')

    ax2.set_title(f'Height over Time: Z vs Sample Number - {title_str}')
    ax2.set_xlabel('Sample Number (per tag)')
    ax2.set_ylabel('Height Z (m)')
    ax2.grid(True, linestyle=':', alpha=0.7)
    if len(tags_data) > 1:
        ax2.legend()

    plt.tight_layout()

# --- VISUALIZATION 3D ---
def plot_trajectory_3d(tags_data, anchors_config, target_tag):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # Dibujar anclas
    for a_id, coords in anchors_config.items():
        ax.scatter(coords[0], coords[1], coords[2], c='red', marker='^', s=150, zorder=5)
        ax.text(coords[0], coords[1], coords[2] + 0.3, f"A{a_id}", fontsize=11, fontweight='bold')

    cmaps = ['viridis', 'plasma', 'inferno', 'magma']
    
    for i, (tag_id, data) in enumerate(tags_data.items()):
        cmap = cmaps[i % len(cmaps)]
        
        # Dibujar la trayectoria del Tag
        scatter = ax.scatter(data['x'], data['y'], data['z'], c=data['rssi'], cmap=cmap, s=60, edgecolor='black', alpha=0.9, zorder=3, label=f'Tag {tag_id}')
        
        # Unir los puntos con una línea
        ax.plot(data['x'], data['y'], data['z'], c='gray', linestyle='--', alpha=0.6, zorder=2)

        cbar = plt.colorbar(scatter, ax=ax, pad=0.05, shrink=0.7)
        cbar.set_label(f'RSSI (dBm) - Tag {tag_id}')

    title_str = "Todos los Tags" if target_tag == 0 else f"Tag {target_tag}"
    ax.set_title(f'3D Trajectory - {title_str} (X, Y, Z)')
    ax.set_xlabel('X (metros)')
    ax.set_ylabel('Y (metros)')
    ax.set_zlabel('Z (metros)')
    
    if len(tags_data) > 1:
        # Trick for making the legend work nicely with 3d scatter plots
        ax.legend()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Search for the latest anchors JSON
    latest_json = get_latest_file('.json', directory=script_dir)
    if not latest_json:
        print(">> Error: No .json file found in the script directory.")
        exit(1)
        
    print(f">> Anchors file detected: {latest_json}")
    anchors_config = load_anchors_config(latest_json)

    # 2. Search for the latest TXT data log
    latest_txt = get_latest_file('.txt', directory=script_dir)
    if not latest_txt:
        print(">> Error: No data .txt file found in the script directory.")
        exit(1)
        
    print(f">> Data file detected: {latest_txt}")
    
    if TARGET_TAG == 0:
        print(">> Extrayendo posiciones para TODOS los tags...")
    else:
        print(f">> Filtrando posiciones para el Tag: {TARGET_TAG}")
    
    tags_data = process_log_file(latest_txt, anchors_config, TARGET_TAG)
    
    if tags_data:
        total_positions = sum(len(d['x']) for d in tags_data.values())
        print(f">> Successfully calculated {total_positions} valid positions across {len(tags_data)} tag(s). Generating 2D, Height and 3D plots...")
        
        plot_trajectory_2d_and_height(tags_data, anchors_config, TARGET_TAG)
        plot_trajectory_3d(tags_data, anchors_config, TARGET_TAG)
        
        plt.show()
    else:
        print(f">> No valid positions found. Check that the file has lines for the selected tag(s) with at least 4 anchors detected.")