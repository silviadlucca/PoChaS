import pandas as pd
import folium
import branca.colormap as cm
import glob
import os
import tifffile
from PIL import Image
import utm

# Permitir procesar mapas del IGN que tienen muchísima resolución
Image.MAX_IMAGE_PIXELS = None

carpeta_datos = r'C:\Users\sdluc\Documents\PoChaS\PoChaS\POCHAS\Common\Plot_results\Medidas_RSSI'

os.chdir(carpeta_datos)

# 1. Encontrar el archivo de medidas más reciente
archivos_txt = glob.glob(os.path.join(carpeta_datos, '*.txt'))
if not archivos_txt:
    print(f"Error: No se encontró ningún .txt en {carpeta_datos}")
    exit()

archivo_txt = max(archivos_txt, key=os.path.getmtime)
print(f"Procesando archivo: {archivo_txt}")

# 2. Leer las medidas ignorando la cabecera mal formateada
nombres_columnas = ['Latitude', 'Longitude', 'Level', 'HDOP', 'Timestamp', 'Temperature']
df = pd.read_csv(archivo_txt, skiprows=6, header=None, names=nombres_columnas)

# 3. Encontrar automáticamente el mapa .tif que haya en la carpeta
archivos_tif = glob.glob(os.path.join(carpeta_datos, '*.tif'))
if not archivos_tif:
    print(f"Error: No se encontró ningún mapa .tif en {carpeta_datos}")
    exit()

archivo_tif = archivos_tif[0]
archivo_png = os.path.join(carpeta_datos, 'mapa_fondo.png')

print("Calculando coordenadas del mapa base...")
# Usamos tifffile SOLO para la matemática de coordenadas, sin tocar los píxeles
with tifffile.TiffFile(archivo_tif) as tif:
    tags = tif.pages[0].tags
    tiepoint = tags['ModelTiepointTag'].value
    pixel_scale = tags['ModelPixelScaleTag'].value
    
    # Extraemos las dimensiones directamente de los metadatos para evitar el error
    ancho = tags['ImageWidth'].value
    alto = tags['ImageLength'].value

    x_min = tiepoint[3]
    y_max = tiepoint[4]
    scale_x = pixel_scale[0]
    scale_y = pixel_scale[1]
    
    x_max = x_min + (ancho * scale_x)
    y_min = y_max - (alto * scale_y)

# 4. Calcular la zona UTM y convertir esquinas a Lat/Lon
lat_media = df['Latitude'].mean()
lon_media = df['Longitude'].mean()
_, _, numero_zona, letra_zona = utm.from_latlon(lat_media, lon_media)

lat_min, lon_min = utm.to_latlon(x_min, y_min, numero_zona, letra_zona)
lat_max, lon_max = utm.to_latlon(x_max, y_max, numero_zona, letra_zona)
limites_mapa = [[lat_min, lon_min], [lat_max, lon_max]]

# 5. Extraer la imagen visual usando Pillow (soporta compresión JPEG nativa)
if not os.path.exists(archivo_png):
    print("Extrayendo imagen del GeoTIFF con Pillow (solo ocurre la primera vez)...")
    imagen_pil = Image.open(archivo_tif)
    imagen_pil.save(archivo_png)

# 6. Crear el mapa interactivo (Bloqueando descargas de internet)
print("Generando HTML interactivo...")
mapa = folium.Map(location=[lat_media, lon_media], zoom_start=15, tiles=None)

# Añadir nuestra imagen local
folium.raster_layers.ImageOverlay(
    name="Mapa Topográfico Local",
    image='mapa_fondo.png',
    bounds=limites_mapa,
    opacity=1.0,
    interactive=False,
    zindex=1
).add_to(mapa)

# 7. Dibujar los puntos de la antena
min_rssi = df['Level'].min()
max_rssi = df['Level'].max()
colormap = cm.LinearColormap(colors=['blue', 'lime', 'red'], vmin=min_rssi, vmax=max_rssi)
colormap.caption = 'Nivel RSSI (dB)'
mapa.add_child(colormap)

for index, row in df.iterrows():
    folium.CircleMarker(
        location=[row['Latitude'], row['Longitude']],
        radius=6,
        color=colormap(row['Level']),
        fill=True,
        fill_color=colormap(row['Level']),
        fill_opacity=0.8,
        popup=f"RSSI: {row['Level']} dB <br> HDOP: {row['HDOP']}"
    ).add_to(mapa)

# 8. Guardar el archivo final
archivo_salida = os.path.join(carpeta_datos, 'mapa_generar.html')
mapa.save(archivo_salida)
print(f"¡Éxito! HTML offline creado en: {archivo_salida}")