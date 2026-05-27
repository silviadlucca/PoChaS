import json
import pyvista as pv
import numpy as np

# 1. Leer y parsear el archivo JSON
with open('anchors.json', 'r', encoding='utf-8') as f:
    datos_json = json.load(f)

coordenadas = []
etiquetas = []

# --- PANEL DE CONTROL DE ORIENTACIÓN ---
# Juega con estos tres valores hasta que la constelación encaje con la forma del pasillo
angulo_grados = 20  # Prueba con 0, 90, 180, o -90
espejo_x = True    # Cambia a False si no necesitas invertir el eje X
espejo_y = False   # Cambia a True si necesitas invertir el eje Y
# ---------------------------------------

angulo_rad = np.radians(angulo_grados)

for id_ancla, coords in datos_json.items():
    x, y, z = coords
    
    # 1. Aplicar efecto espejo si está activado
    if espejo_x:
        x = -x
    if espejo_y:
        y = -y
        
    # 2. Aplicar rotación trigonométrica sobre el eje Z
    x_rot = x * np.cos(angulo_rad) - y * np.sin(angulo_rad)
    y_rot = x * np.sin(angulo_rad) + y * np.cos(angulo_rad)
    
    coordenadas.append([x_rot, y_rot, z])
    etiquetas.append(f"Ancla {id_ancla}")

# Guardamos las coordenadas listas para usarlas de base
coordenadas_base = np.array(coordenadas)

# 2. Cargar el modelo geométrico del pasillo (STL)
pasillo_mesh = pv.read('pasillo_medidas_correctas.stl')

# Crear el objeto de puntos inicial en PyVista para las anclas
anclas_nube = pv.PolyData(coordenadas_base)

# 3. Configurar el entorno de renderizado
plotter = pv.Plotter()

# Añadir el pasillo (color gris claro y semitransparente)
plotter.add_mesh(pasillo_mesh, color='lightgrey', opacity=0.3)

# Añadir las anclas y sus etiquetas
plotter.add_mesh(anclas_nube, color='red', point_size=18, render_points_as_spheres=True)
plotter.add_point_labels(anclas_nube, etiquetas, font_size=12, point_color='red', text_color='black')

# 4. Función de Callback: ¿Qué pasa cuando haces clic?
def al_hacer_click(punto_elegido):
    print(f"\n--- Nuevo origen seleccionado ---")
    print(f"Coordenadas del clic: {punto_elegido}")
    
    # Mueve todas las anclas tomando el clic como nuevo origen
    nuevas_coordenadas = coordenadas_base + np.array(punto_elegido)
    anclas_nube.points = nuevas_coordenadas
    print("¡Anclas reubicadas con éxito!")

# 5. Activar la selección interactiva con el ratón
plotter.enable_surface_point_picking(callback=al_hacer_click, left_clicking=True, show_point=True)

# Añadir instrucciones y ejes visuales
plotter.add_text("Haz clic izquierdo en el STL donde deberia estar el Ancla 3", font_size=12, color='black')
plotter.add_axes()

# 6. Mostrar la ventana interactiva
plotter.show()