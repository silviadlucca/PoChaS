import uhd

def get_usrp_serial():
    try:
        # Crear un dispositivo USRP
        usrp = uhd.usrp.MultiUSRP()

        # Obtener información del dispositivo
        mboard_info = usrp.get_usrp_rx_info()

        # El número de serie está en la información del motherboard
        usrp_serial = mboard_info.get("mboard_serial", "No encontrado")
        print(f"Número de serie del USRP: {usrp_serial}")
        return usrp_serial

    except Exception as e:
        print(f"Error al leer el número de serie: {e}")
        return None

# Llamar a la función
get_usrp_serial()
