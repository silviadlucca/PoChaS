import matplotlib.pyplot as plt

import numpy as np

 

def cargar_datos(nombre_archivo):

    muestras = []

    rssi_values = []

    try:

        with open(nombre_archivo, 'r') as f:

            for linea in f:

                linea = linea.strip()

                if not linea or linea.startswith('#'):

                    continue

                partes = linea.split(',')

                if len(partes) == 2:

                    muestras.append(int(partes[0]))

                    rssi_values.append(float(partes[1]))

        return muestras, rssi_values

    except FileNotFoundError:

        print(f"Error: El archivo '{nombre_archivo}' no existe.")

        return None, None

 

# --- CONFIGURACIÓN Y CARGA ---

archivo = "datos1.txt" # Asegúrate de que el archivo se llame así

muestras, rssi = cargar_datos(archivo)

 

if rssi:

    # Preparación de datos para el gráfico polar (360°)

    n_medidas = len(rssi)

    angulos = np.linspace(0, 2 * np.pi, n_medidas, endpoint=False)

    

    # Cerramos el círculo para que no quede un hueco en el gráfico polar

    rssi_polar = rssi + [rssi[0]]

    angulos_polar = np.append(angulos, angulos[0])

 

    # Crear la figura con dos subplots

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), 

                                   gridspec_kw={'width_ratios': [1.2, 1]})

 

    # --- 1. GRÁFICO DE LÍNEA RECTA (CARTESIANO) ---

    ax1.plot(muestras, rssi, color='dodgerblue', marker='o', linestyle='-', linewidth=2, markersize=4)

    ax1.axhline(y=np.mean(rssi), color='red', linestyle='--', alpha=0.6, label=f'Promedio: {np.mean(rssi):.2f} dB')

    

    ax1.set_title('RSSI en Función de la Muestra (Lineal)', fontsize=14)

    ax1.set_xlabel('Número de Muestra / Tiempo', fontsize=12)

    ax1.set_ylabel('Intensidad de Señal (dB)', fontsize=12)

    ax1.grid(True, linestyle=':', alpha=0.7)

    ax1.legend()

 

    # --- 2. GRÁFICO POLAR (RADIAL) ---

    # Cambiamos a proyección polar

    ax2 = plt.subplot(122, projection='polar')

    ax2.plot(angulos_polar, rssi_polar, color='darkorange', linewidth=2.5)

    ax2.fill(angulos_polar, rssi_polar, color='orange', alpha=0.2)

    

    ax2.set_theta_zero_location('N') # 0° arriba

    ax2.set_theta_direction(-1) # Sentido horario

    ax2.set_title('Patrón de Radiación (Polar)', fontsize=14, pad=20)

    

    # Ajustamos el límite inferior para que los nulos se vean profundos

    ax2.set_ylim(min(rssi) - 5, max(rssi) + 2)

 

    # Título general

    plt.suptitle(f'Análisis Completo de Antena - Archivo: {archivo}', fontsize=16, y=1.02)

    

    plt.tight_layout()

    plt.show()

