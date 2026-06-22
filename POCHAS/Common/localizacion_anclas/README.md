# Localizacion de anclas con ESP32 UWB

Este repositorio contiene firmware para estimar y registrar la posicion de anclas UWB usando placas Makerfabs ESP32 UWB.

La idea del flujo es:

1. `Ancla 1` define el origen del sistema: `(0, 0)`.
2. El `beacon` crea una red WiFi propia y sirve una pagina web.
3. Para registrar una nueva ancla, colocas el beacon justo delante del tripode donde ira esa ancla, con la ancla nueva apagada.
4. Desde el movil pulsas `Medir y registrar`.
5. El beacon mide distancias UWB a las anclas ya encendidas y calcula la coordenada de la nueva ancla.
6. Despues enciendes la nueva ancla ya flasheada con su ID, y repites el proceso para la siguiente.
7. La pagina permite descargar `anchors.json` con todas las coordenadas `[x, y, z]`.

## Hardware detectado

Por las fotos, las placas son Makerfabs ESP32 UWB con ESP32-WROOM-32 y modulo UWB compatible con la libreria `DW3000` ya incluida en `Tag_Serial_two_tags/lib/DW3000`.

## Proyectos importantes

- `Anchor/`: firmware para una ancla fija. Responde a peticiones UWB.
- `Beacon_Calibrator/`: firmware nuevo para el beacon/calibrador con WiFi AP y pagina web.
- `Tag_Serial_two_tags/`: firmware previo de tag continuo por serie. Lo he usado como base para el ranging.
- `Plot_results/`: herramientas previas de postprocesado y trilateracion.

## Flashear anclas

Cada ancla debe tener un ID UWB distinto. El firmware `Anchor` ahora usa entornos PlatformIO por ID:

```bash
cd Anchor
pio run -e anchor0 -t upload
pio run -e anchor1 -t upload
pio run -e anchor2 -t upload
pio run -e anchor3 -t upload
```

Si el puerto no coincide, puedes pasarlo en el comando:

```bash
pio run -e anchor1 -t upload --upload-port COM8
```

La `ancla 0` debe quedar encendida y fija en la posicion fisica que quieras considerar `(0, 0)`.

## Flashear el beacon

```bash
cd Beacon_Calibrator
pio run -e esp32dev -t upload
pio device monitor -b 921600
```

Por defecto:

- WiFi SSID: `Beacon-Calibrador`
- WiFi password: `anclas1234`
- Web: `http://192.168.4.1/`
- ID UWB del beacon: `250`
- ID UWB del origen: `1`

Estos valores se pueden cambiar en `Beacon_Calibrator/platformio.ini`.

## Flujo de calibracion recomendado

1. Usa la placa ya programada como `ancla 1` para el origen.
2. Coloca `ancla 1` en el tripode y enciendela.
3. Flashea el beacon con `Beacon_Calibrator`.
4. Conecta el movil al WiFi `Beacon-Calibrador` y abre `http://192.168.4.1/`.
5. Para registrar `ancla 2`, coloca el beacon exactamente donde ira su antena, con `ancla 2` apagada, y pulsa `Medir y registrar`.
6. Coloca y enciende `ancla 2`.
7. Coloca el beacon donde ira `ancla 3`, con A1 y A2 encendidas y A3 apagada. Elige el lado Y y registra A3.
8. Coloca y enciende `ancla 3`.
9. Apoya el beacon en el suelo exactamente debajo de la antena de A1. Introduce solo el pequeno offset entre el suelo y la antena del beacon.
10. Pulsa `Calibrar alturas A1-A3`. El sistema usa las seis distancias del tetraedro para recalcular X, Y y Z automaticamente.
11. Registra A4 midiendo contra A1-A3. Si la solucion automatica no corresponde al lugar fisico, repite A4 seleccionando `Alternativa`.
12. A partir de A5, el beacon usa cuatro o mas anclas y minimos cuadrados 3D.

## Convencion de coordenadas

- `A1 = (0, 0)`.
- A2 y A3 se muestran primero en una geometria 2D provisional que conserva `d12`, `d13` y `d23`.
- El punto del suelo bajo A1 define la referencia vertical y permite reconstruir automaticamente A1-A3 en 3D.
- A4 se obtiene por interseccion de tres esferas; existen dos soluciones y la web conserva una opcion alternativa.
- A5 y posteriores se calculan por minimos cuadrados 3D usando cuatro o mas anclas.
- No se introducen alturas de anclas manualmente. Solo se indica el offset fisico de la antena del beacon cuando esta apoyado en el suelo.

## Descargar coordenadas

El boton `Descargar JSON` genera un archivo `anchors.json` compatible con este formato:

```json
{
  "1": [0.000, 0.000, 1.700],
  "2": [3.800, 1.150, 1.750]
}
```

## Calidad de senal PD

`PD` es la diferencia entre la potencia total recibida y la potencia del primer trayecto, expresada en dB. Como referencia usada por la libreria local:

- Menos de 6 dB: normalmente LOS o vision directa.
- Entre 6 y 10 dB: posible multitrayecto o NLOS moderado.
- Mas de 10 dB: NLOS fuerte; la distancia puede ser menos fiable.

## Consejos de medicion

- Mantener el beacon quieto durante la medicion.
- Poner el beacon lo mas cerca posible del punto real donde quedara la antena UWB del ancla.
- Evitar que el cuerpo quede entre las placas durante la medicion.
- Usar linea de vision cuando sea posible.
- Si el error RMS sube mucho, repetir la medicion con mas muestras o recolocar las anclas para que no esten casi alineadas.

## Limitaciones

- El beacon debe quedar verticalmente debajo de A1 durante la calibracion del suelo.
- A1, A2 y A3 no deben quedar casi alineadas.
- Para una Z estable en A5+, las anclas conocidas deben tener diversidad de alturas; una geometria casi coplanar empeora el calculo vertical.
