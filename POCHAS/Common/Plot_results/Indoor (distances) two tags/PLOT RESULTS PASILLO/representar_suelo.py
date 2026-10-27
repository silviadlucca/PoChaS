import pyvista as pv
import numpy as np
import math as m
import json
import glob
import os


mesh = pv.read("blender_suelo.stl")
p = pv.Plotter()
p.add_mesh(mesh, color='lightblue', opacity=1.0)

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

x_1 = -3.5
y_1 = -6.3
z_1 = 0
alpha = 9
alpha_rad = m.radians(alpha)

posiciones_etiquetas = []
textos_etiquetas = []

x_rot = -8.137
y_rot = -12.664

for i in range(len(anchors)):
    if anchors[i] != 0:
        x, y, z = anchors[i]

        x = -x
        y = -y

        x_rot = x * m.cos(alpha_rad) - y * m.sin(alpha_rad)
        y_rot = x * m.sin(alpha_rad) + y * m.cos(alpha_rad)
        
        x_final = x_rot + x_1
        y_final = y_rot + y_1

        sphere = pv.Sphere(radius=0.3, center=(x_final, y_final, z))
        print(f"Anchor {i}: x={x_final}, y={y_final}, z={z}")
        p.add_mesh(sphere, color='red', opacity=1.0)
        posiciones_etiquetas.append([x_final, y_final, z])
        textos_etiquetas.append(str(i))

#mesh.plot( cpos='xy', show_grid=True, line_width=1, point_size=20)

p.add_point_labels(
    posiciones_etiquetas, 
    textos_etiquetas, 
    font_size=25,           # Tamaño de la letra
    text_color='white',     # Color del texto
    shape_color='black',    # Color del recuadrito de fondo
    shape_opacity=0.5,      # Transparencia del recuadro
    point_size=0,           # Lo ponemos a 0 porque ya dibujamos las esferas nosotros
    margin=3,               # Margen dentro del recuadro
    name='etiquetas'
)
p.show_grid()
p.camera_position = 'yz'
p.show()

points = mesh.points
coordenadas_x = points[:, 0]
coordenadas_y = points[:, 1]
coordenadas_z = points[:, 2]
with open('floor_coords.txt', 'w') as f:
    f.write("COORDINATES:\n")
    for x, y, z in zip(coordenadas_x, coordenadas_y, coordenadas_z):
        if z < 0.01:  # filtrar puntos con coordenada z menor a 0.1
            f.write(f"x:{x},y:{y},z:0\n")
        else:
            f.write(f"x: {x}, y: {y}, z: {z}\n")
    f.write("\n")
    i = 0
    while i < len(mesh.faces):
        n_puntos = mesh.faces[i]
        indices = mesh.faces[i+1 : i+1+n_puntos]
        indices_str = ",".join(map(str, indices))
        f.write(f"FACE:{indices_str}\n")
        i += 1 + n_puntos

