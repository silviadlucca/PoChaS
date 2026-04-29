import pandas as pd
import matplotlib.pyplot as plt

# Nombre del fichero (asegúrate de que está en la misma carpeta)
filename = "Measure_20260317_124044.txt"

# Leer el archivo ignorando líneas que empiezan con '#'
df = pd.read_csv(
    filename,
    comment='#',          # Ignora las líneas de cabecera
    header=None,          # No hay fila de encabezado para los datos
    names=["Measure", "RSSI_dB"]   # Nombres de las columnas
)

# Graficar Measure vs RSSI
plt.figure(figsize=(8,4))
plt.plot(df["Measure"], df["RSSI_dB"], marker='o', linestyle='-')
plt.title("RSSI Measurement Log")
plt.xlabel("Measurement")
plt.ylabel("RSSI (dB)")
plt.grid(True)
plt.tight_layout()
plt.show()
