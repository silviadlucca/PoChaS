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
    
    # EXPRESIÓN REGULAR ACTUALIZADA: Captura SDR RSSI, dict de distancias y dict de RSSIs de anclas
    log_pattern = re.compile(r'^\s*([-\d\.]+)\s*,\s*(\{.*?\})\s*,\s*(\{.*?\})')
    
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
                    
                    if not distances:
                        continue 
                        
                    # Logic to select only the 4 anchors with the best signal (highest RSSI)
                    if USE_MIN_ANCHORS == 1 and len(distances) > 4:
                        # Order the anchor IDs based on their RSSI values from highest to lowest.
                        # We use reverse=True because an RSSI of -60 is better than one of -90.
                        sorted_anchor_ids = sorted(
                            distances.keys(), 
                            key=lambda k: rssis.get(k, -100), 
                            reverse=True
                        )
                        
                        # We keep only the 4 best
                        top_4_ids = sorted_anchor_ids[:4]
                        
                        # Reconstruct the distances dictionary with only these 4 anchors
                        distances = {k: distances[k] for k in top_4_ids}
                        
                    pos = calculate_tag_position(distances, anchors_config, last_position)
                    
                    if pos is not None:
                        x_history.append(pos[0])
                        y_history.append(pos[1])
                        z_history.append(pos[2])
                        rssi_history.append(sdr_rssi_val)
                        last_position = pos # Update seed for next iteration
                        
                except Exception as e:
                    print(f"Error processing line {line_num}: {e}")

    return x_history, y_history, z_history, rssi_history

def plot_trajectory_2d_and_height(x_vals, y_vals, z_vals, rssi_vals, anchors_config):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    # ---------------------------------------------------------
    for a_id, coords in anchors_config.items():
        ax1.scatter(coords[0], coords[1], c='red', marker='^', s=150, zorder=5)
        ax1.text(coords[0], coords[1] + 0.15, f"A{a_id}", fontsize=11, fontweight='bold')

    scatter = ax1.scatter(x_vals, y_vals, c=rssi_vals, cmap='viridis', s=60, edgecolor='black', zorder=3)
    
    cbar = plt.colorbar(scatter, ax=ax1, pad=0.05)
    cbar.set_label('SDR RSSI (dBm)')

    ax1.plot(x_vals, y_vals, c='gray', linestyle='--', alpha=0.6, zorder=2)
    ax1.set_title('2D Trajectory (X vs Y)')
    ax1.set_xlabel('X (m)')
    ax1.set_ylabel('Y (m)')
    ax1.grid(True, linestyle=':', alpha=0.7)
    ax1.set_aspect('equal', adjustable='datalim')

    # ---------------------------------------------------------
    muestras = list(range(1, len(z_vals) + 1))
    
    ax2.plot(muestras, z_vals, marker='o', linestyle='-', color='#1f77b4', markersize=5, alpha=0.8)
    ax2.set_title('Height over Time: Height in Z vs Sample Number')
    ax2.set_xlabel('Sample Number')
    ax2.set_ylabel('Height Z (m)')
    ax2.grid(True, linestyle=':', alpha=0.7)

    plt.tight_layout()

# --- VISUALIZATION 3D ---
def plot_trajectory_3d(x_vals, y_vals, z_vals, rssi_vals, anchors_config):
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    for a_id, coords in anchors_config.items():
        ax.scatter(coords[0], coords[1], coords[2], c='red', marker='^', s=150, zorder=5)
        ax.text(coords[0], coords[1], coords[2] + 0.3, f"A{a_id}", fontsize=11, fontweight='bold')

    # Dibujar la trayectoria del Tag
    scatter = ax.scatter(x_vals, y_vals, z_vals, c=rssi_vals, cmap='viridis', s=60, edgecolor='black', alpha=0.9, zorder=3)
    
    # Unir los puntos con una línea
    ax.plot(x_vals, y_vals, z_vals, c='gray', linestyle='--', alpha=0.6, zorder=2)

    cbar = plt.colorbar(scatter, ax=ax, pad=0.1, shrink=0.7)
    cbar.set_label('SDR RSSI (dBm)')

    ax.set_title('3D Trajectory of the Tag (X, Y, Z)')
    ax.set_xlabel('X (metros)')
    ax.set_ylabel('Y (metros)')
    ax.set_zlabel('Z (metros)')

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
    
    x, y, z, rssi = process_log_file(latest_txt, anchors_config)
    
    if x:
        print(f">> Successfully calculated {len(x)} valid positions. Generating 2D, Height and 3D plots...")
        plot_trajectory_2d_and_height(x, y, z, rssi, anchors_config)
        plot_trajectory_3d(x, y, z, rssi, anchors_config)
        
        plt.show()
    else:
        print(">> No valid positions found. Check that the file has lines with at least 4 anchors detected.")