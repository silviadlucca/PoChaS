import ast
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import minimize

# 1. Definición de las coordenadas de las anclas (x, y, z)
anchors = {
    "1": np.array([0.0, 0.0, 1.7]),
    "2": np.array([3.8, 1.15, 1.75]),
    "5": np.array([3.8, 8.95, 2.3]),
    "3": np.array([-0.7, 9.6, 2.8]),
    "4": np.array([0.8, 13.8, 3.2])
}

# 2. Función de error: Mínimos Cuadrados Ponderados (WLS)
def wls_error_function(pos, active_anchors, measured_distances, rssi_dict):
    error = 0.0
    for anc_id, meas_dist in measured_distances.items():
        if anc_id in active_anchors and anc_id in rssi_dict:
            calc_dist = np.linalg.norm(pos - active_anchors[anc_id])
            
            # Pasamos de dB a lineal dividiendo por 10 en el exponente.
            # Sumamos +100 al RSSI para que la base del cálculo (ej. -90dBm) 
            # no genere números excesivamente microscópicos en Python (underflow).
            rssi = rssi_dict[anc_id]
            weight = 10 ** ((rssi + 100) / 10.0)
            
            error += weight * (calc_dist - meas_dist)**2
    return error

def main():
    file_path = '2026-05-27_13-33-13_Rxfile.txt' 
    
    guess_t1 = np.array([1.5, 6.0, 1.0])
    guess_t2 = np.array([1.5, 6.0, 1.0])
    
    raw_points = []

    # 3. Lectura y procesado del archivo
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or 'RSSI' in line or not line:
                continue
            
            try:
                parsed_line = ast.literal_eval(f"({line})")
                
                distances = parsed_line[1]
                rssi_dict = parsed_line[2] # Ahora SI cogemos el RSSI para usarlo
                tag_id = parsed_line[3]
                timestamp = parsed_line[4]
                
                # Retiramos el filtro artificial de "solo las 4 mejores".
                # Dejamos que WLS decida la importancia de todas las anclas disponibles.
                if tag_id in [1, 2] and len(distances) >= 3:
                    current_guess = guess_t1 if tag_id == 1 else guess_t2
                    
                    result = minimize(
                        wls_error_function, 
                        current_guess, 
                        args=(anchors, distances, rssi_dict), # Pasamos los RSSIs al optimizador
                        method='Nelder-Mead'
                    )
                    
                    if result.success:
                        raw_points.append({
                            'tag': tag_id,
                            't': timestamp,
                            'pos': result.x,
                            'error': result.fun 
                        })
                        
                        if tag_id == 1:
                            guess_t1 = result.x
                        else:
                            guess_t2 = result.x

            except Exception as e:
                continue

    raw_points.sort(key=lambda k: k['t'])

    # 4. LÓGICA DE FUSIÓN Y FILTRADO
    merged_x, merged_y, merged_z, merged_t = [], [], [], []
    tag_origen = [] 
    
    TIME_WINDOW_MS = 300 
    MAX_SALTO_METROS = 0.8  
    ALPHA = 0.3             
    pos_filtrada = None
    
    i = 0
    while i < len(raw_points):
        p1 = raw_points[i]
        best_p = p1
        salto_idx = 1
        
        # Fusión de los dos tags ortogonales
        if i + 1 < len(raw_points):
            p2 = raw_points[i+1]
            time_diff = abs(p2['t'] - p1['t'])
            
            if p1['tag'] != p2['tag'] and time_diff <= TIME_WINDOW_MS:
                best_p = p1 if p1['error'] < p2['error'] else p2
                salto_idx = 2 

        nueva_pos = best_p['pos']

        # Filtros (Rechazo de picos y Media Móvil Exponencial)
        if pos_filtrada is None:
            pos_filtrada = nueva_pos 
            guardar_punto = True
        else:
            dist_salto = np.linalg.norm(nueva_pos - pos_filtrada)
            
            if dist_salto > MAX_SALTO_METROS:
                guardar_punto = False
            else:
                pos_filtrada = ALPHA * nueva_pos + (1 - ALPHA) * pos_filtrada
                guardar_punto = True

        if guardar_punto:
            merged_x.append(pos_filtrada[0])
            merged_y.append(pos_filtrada[1])
            merged_z.append(pos_filtrada[2])
            merged_t.append(best_p['t'])
            tag_origen.append(best_p['tag'])

        i += salto_idx

    # 5. Representación
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8), gridspec_kw={'width_ratios': [2, 1]})
    
    # --- AX 1: Plano 2D ---
    for anc_id, coords in anchors.items():
        ax1.scatter(coords[0], coords[1], c='red', marker='^', s=120, zorder=5)
        ax1.text(coords[0] + 0.2, coords[1] + 0.2, f'A{anc_id}', fontsize=12, fontweight='bold', color='darkred')

    if merged_x:
        ax1.plot(merged_x, merged_y, c='purple', marker='.', markersize=6, linestyle='-', alpha=0.8, label='Trayectoria Optimizada WLS')
        ax1.scatter(merged_x[0], merged_y[0], c='green', marker='s', s=80, edgecolors='black', zorder=4, label='Inicio')
        ax1.scatter(merged_x[-1], merged_y[-1], c='red', marker='X', s=100, edgecolors='black', zorder=4, label='Fin')

    ax1.set_title('Plano 2D: Fusión Inteligente de Tags con WLS')
    ax1.set_xlabel('Eje X (metros)')
    ax1.set_ylabel('Eje Y (metros)')
    ax1.grid(True, linestyle='--', alpha=0.7)
    ax1.legend()
    ax1.axis('equal')

    # --- AX 2: Altura vs Tiempo ---
    if merged_t:
        for j in range(len(merged_t)):
            color = 'blue' if tag_origen[j] == 1 else 'orange'
            ax2.scatter(merged_t[j], merged_z[j], c=color, s=20, zorder=3)
            
        ax2.plot(merged_t, merged_z, c='gray', alpha=0.4, zorder=2)
        
        ax2.scatter([], [], c='blue', label='Origen: Tag 1')
        ax2.scatter([], [], c='orange', label='Origen: Tag 2')

    ax2.set_title('Altura (Eje Z) vs Tiempo')
    ax2.set_xlabel('Timestamp (ms)')
    ax2.set_ylabel('Altura Z (metros)')
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend()

    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    main()