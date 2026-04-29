import os
import glob
import json
import re
import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares

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
def process_log_file(filepath, anchors_config):
    x_history = []
    y_history = []
    z_history = []
    rssi_history = []
    
    # We use the last position as the seed for the next calculation
    last_position = (0.0, 0.0, 0.0) 
    
    log_pattern = re.compile(r'^\s*([-\d\.]+)\s*,\s*(\{.*?\})')
    
    with open(filepath, 'r') as file:
        for line_num, line in enumerate(file, 1):
            if not line.strip() or line.startswith('#'):
                continue
                
            match = log_pattern.match(line)
            if match:
                try:
                    rssi_val = float(match.group(1))
                    distances = ast.literal_eval(match.group(2))
                    
                    if not distances:
                        continue 
                        
                    pos = calculate_tag_position(distances, anchors_config, last_position)
                    
                    if pos is not None:
                        x_history.append(pos[0])
                        y_history.append(pos[1])
                        z_history.append(pos[2])
                        rssi_history.append(rssi_val)
                        last_position = pos # Update seed for next iteration
                        
                except Exception as e:
                    print(f"Error processing line {line_num}: {e}")

    return x_history, y_history, z_history, rssi_history

# --- VISUALIZATION ---
def plot_trajectory_2d_and_height(x_vals, y_vals, z_vals, rssi_vals, anchors_config):
    # Creamos una figura con dos subgráficos (1 fila, 2 columnas)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # ---------------------------------------------------------
    # SUBPLOT 1: Trayectoria 2D (Plano XY)
    # ---------------------------------------------------------
    # Dibujamos las anclas en el plano 2D
    for a_id, coords in anchors_config.items():
        ax1.scatter(coords[0], coords[1], c='red', marker='^', s=150, zorder=5)
        # Etiqueta desplazada ligeramente para que no se superponga
        ax1.text(coords[0], coords[1] + 0.15, f"A{a_id}", fontsize=11, fontweight='bold')

    # Puntos de la trayectoria coloreados por RSSI
    scatter = ax1.scatter(x_vals, y_vals, c=rssi_vals, cmap='viridis', s=60, edgecolor='black', zorder=3)
    
    # Barra de color para el RSSI
    cbar = plt.colorbar(scatter, ax=ax1, pad=0.05)
    cbar.set_label('RSSI (dBm)')

    # Línea punteada uniendo los puntos
    ax1.plot(x_vals, y_vals, c='gray', linestyle='--', alpha=0.6, zorder=2)

    ax1.set_title('Vista en Planta: Trayectoria 2D (X vs Y)')
    ax1.set_xlabel('Distancia X (metros)')
    ax1.set_ylabel('Distancia Y (metros)')
    ax1.grid(True, linestyle=':', alpha=0.7)
    
    # Mantenemos la misma proporción para los ejes X e Y si es posible
    ax1.set_aspect('equal', adjustable='datalim')

    # ---------------------------------------------------------
    # SUBPLOT 2: Altura (Eje Z) vs Número de Muestra
    # ---------------------------------------------------------
    muestras = list(range(1, len(z_vals) + 1))
    
    ax2.plot(muestras, z_vals, marker='o', linestyle='-', color='#1f77b4', markersize=5, alpha=0.8)
    ax2.set_title('Evolución de la Altura (Eje Z)')
    ax2.set_xlabel('Número de Muestra')
    ax2.set_ylabel('Altura Z (metros)')
    ax2.grid(True, linestyle=':', alpha=0.7)

    # Ajustamos el layout para que no se pisen los gráficos
    plt.tight_layout()
    plt.show()

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # 1. Search for the latest anchors JSON
    latest_json = get_latest_file('.json')
    if not latest_json:
        print(">> Error: No .json file found in the current directory.")
        exit(1)
        
    print(f">> Anchors file detected: {latest_json}")
    anchors_config = load_anchors_config(latest_json)

    # 2. Search for the latest TXT data log
    latest_txt = get_latest_file('.txt')
    if not latest_txt:
        print(">> Error: No data .txt file found in the current directory.")
        exit(1)
        
    print(f">> Data file detected: {latest_txt}")
    
    # 3. Process and plot
    x, y, z, rssi = process_log_file(latest_txt, anchors_config)
    
    if x:
        print(f">> Successfully calculated {len(x)} valid positions. Generating 2D + Height plots...")
        plot_trajectory_2d_and_height(x, y, z, rssi, anchors_config)
    else:
        print(">> No valid positions found. Check that the file has lines with at least 4 anchors detected.")