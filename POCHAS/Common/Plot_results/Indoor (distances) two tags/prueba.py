import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import least_squares
import re
import json

# 1. Coordenadas de las anclas
ANCHORS = {
    "1": [0.0, 0.0, 1.7],
    "2": [3.8, 1.15, 1.75],
    "3": [-0.7, 9.6, 2.8],
    "4": [0.8, 13.8, 3.2],
    "5": [3.8, 8.95, 2.3]
}

# 2. Matemática para calcular X, Y, Z (Trilateración pura)
def calcular_posicion(distancias):
    coords_activas = []
    dists_medidas = []
    
    # Filtramos solo las anclas de las que tenemos lectura en este instante
    for id_ancla, dist in distancias.items():
        if id_ancla in ANCHORS:
            coords_activas.append(ANCHORS[id_ancla])
            dists_medidas.append(dist)
            
    # Si hay menos de 3 anclas, es imposible triangular en un plano
    if len(coords_activas) < 3:
        return np.nan, np.nan, np.nan
        
    def error(posicion_estimada):
        errores = []
        for c, d in zip(coords_activas, dists_medidas):
            # Teorema de Pitágoras en 3D
            dist_calculada = np.sqrt((posicion_estimada[0]-c[0])**2 + (posicion_estimada[1]-c[1])**2 + (posicion_estimada[2]-c[2])**2)
            errores.append(dist_calculada - d)
        return errores
        
    # [1.0, 5.0, 1.0] es un punto inicial aproximado en el medio de la sala para ayudar al algoritmo
    resultado = least_squares(error, x0=[1.0, 5.0, 1.0]) 
    return resultado.x[0], resultado.x[1], resultado.x[2]

# 3. Leer el log línea a línea y construir una tabla
filas = []

with open("2026-05-27_13-33-13_Rxfile.txt", "r") as archivo:
    for linea in archivo:
        if "{" not in linea: 
            continue # Descartar comentarios o líneas vacías
        
        # Buscar el bloque de distancias usando expresiones regulares
        bloques_json = re.findall(r'\{.*?\}', linea)
        if not bloques_json: 
            continue
            
        distancias = json.loads(bloques_json[0])
        
        # Cortar la parte final de la línea para sacar el Tag y el Timestamp
        datos_finales = linea[linea.rfind('}')+1 :].strip(',\n').split(',')
        if len(datos_finales) < 2:
            continue
            
        tag = int(datos_finales[0])
        timestamp = int(datos_finales[1])
        
        # --- FILTRO DE TIEMPO AQUÍ ---
        if not (82000 <= timestamp <= 100000):
           continue 
            
        x, y, z = calcular_posicion(distancias)
        
        # Guardar los datos en formato plano
        filas.append({
            "Tag": tag,
            "Timestamp": timestamp,
            "X": x, 
            "Y": y,
            "A1": distancias.get("1", np.nan),
            "A2": distancias.get("2", np.nan),
            "A3": distancias.get("3", np.nan),
            "A4": distancias.get("4", np.nan),
            "A5": distancias.get("5", np.nan)
        })

# Convertir la lista a un DataFrame (Tabla bidimensional)
df = pd.DataFrame(filas)

# 4. Representación Gráfica
if df.empty:
    print("No se encontraron datos en ese rango de timestamps (82000 - 100000).")
else:
    # Separar los datos por Tag para que sea más cómodo graficar
    df_t1 = df[df["Tag"] == 1]
    df_t2 = df[df["Tag"] == 2]
    lista_anclas = ["A1", "A2", "A3", "A4", "A5"]

    # --- VENTANA 1: Distancias en el tiempo ---
    fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    # Gráfica Tag 1
    for ancla in lista_anclas:
        ax1.plot(df_t1["Timestamp"], df_t1[ancla], marker='.', linestyle='-', label=ancla)
    ax1.set_title("Distancias - Tag 1 (Filtrado)")
    ax1.set_ylabel("Distancia (m)")
    ax1.grid(True, linestyle='--', alpha=0.7)
    ax1.legend(loc="upper right")
    
    # Gráfica Tag 2
    for ancla in lista_anclas:
        ax2.plot(df_t2["Timestamp"], df_t2[ancla], marker='.', linestyle='-', label=ancla)
    ax2.set_title("Distancias - Tag 2 (Filtrado)")
    ax2.set_ylabel("Distancia (m)")
    ax2.set_xlabel("Timestamp")
    ax2.grid(True, linestyle='--', alpha=0.7)
    ax2.legend(loc="upper right")
    
    fig1.tight_layout()
    plt.show()

    # --- VENTANA 2: Plano XY ---
    plt.figure(figsize=(8, 8))
    
    # Dibujar las posiciones fijas de las anclas
    for id_ancla, coord in ANCHORS.items():
        plt.scatter(coord[0], coord[1], c='red', s=150, marker='^', zorder=5)
        plt.text(coord[0] + 0.2, coord[1] + 0.2, f'A{id_ancla}', color='darkred', fontweight='bold', zorder=6)
        
    # Dibujar trayectorias filtrando los puntos que fallaron (donde X es nulo)
    t1_valido = df_t1.dropna(subset=['X'])
    t2_valido = df_t2.dropna(subset=['X'])
    
    plt.plot(t1_valido["X"], t1_valido["Y"], c='blue', marker='o', markersize=4, alpha=0.6, label="Trayectoria Tag 1")
    plt.plot(t2_valido["X"], t2_valido["Y"], c='green', marker='s', markersize=4, alpha=0.6, label="Trayectoria Tag 2")
    
    plt.title("Plano XY (Timestamps 82000 - 100000)")
    plt.xlabel("Eje X (m)")
    plt.ylabel("Eje Y (m)")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.axis('equal') # Mantiene la proporción 1:1 entre los ejes
    
    plt.tight_layout()
    plt.show()