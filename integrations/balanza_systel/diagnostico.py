"""Diagnóstico de una balanza Systel Cuora conectada por USB (sin Odoo).

Busca la balanza en los puertos serie, prueba velocidades, paridades y números de
balanza, y muestra la firma del equipo y el peso en vivo. Sirve para confirmar en el
local, antes de probar el POS, los parámetros que usa el módulo
`comercio_pos_balanza_systel` (115200 baudios, 8 bits, sin paridad, número 1).

Protocolo: «Protocolo de comunicaciones MAX CUORA V7» (Systel). Trama:
[número de balanza][función][datos ASCII][XOR de los anteriores]; fin por silencio.

Uso (requiere pyserial: `.venv/bin/pip install pyserial`):

    .venv/bin/python integrations/balanza_systel/diagnostico.py            # busca sola
    .venv/bin/python integrations/balanza_systel/diagnostico.py --puerto /dev/ttyUSB0 --numero 20

Solo lee: no modifica nada en la balanza.
"""
from __future__ import annotations

import argparse
import re
import sys
import time

FUNCION_PESO = 1
FUNCION_FIRMA = 2
PESO_RE = re.compile(r"^(-\d{5}|\d{6})([ei])(\d{6})$")
ERROR_RE = re.compile(r"^E\d$")
# Primero lo que dice el ejemplo oficial; después variantes por si la balanza difiere.
VELOCIDADES = [115200, 9600, 19200, 38400, 57600]
PARIDADES = ["N", "E", "O"]


def xor(datos: bytes) -> int:
    resultado = 0
    for byte in datos:
        resultado ^= byte
    return resultado


def armar_pedido(numero: int, funcion: int, datos: str = "") -> bytes:
    cuerpo = bytes([numero, funcion]) + datos.encode("ascii")
    return cuerpo + bytes([xor(cuerpo)])


def separar_respuesta(recibido: bytes, numero: int, funcion: int) -> str | None:
    """Datos ASCII de la trama (número, función) con que termina lo recibido.

    La respuesta termina por silencio, así que la trama va hasta el final de lo leído;
    lo anterior pueden ser restos de respuestas viejas.
    """
    for inicio in range(len(recibido) - 2):
        trama = recibido[inicio:]
        if trama[0] == numero and trama[1] == funcion and xor(trama[:-1]) == trama[-1]:
            return trama[2:-1].decode("ascii", errors="replace")
    return None


def interpretar_peso(datos: str) -> dict | None:
    """'001250e000000' → {'gramos': 1250, 'estable': True, 'tara_gramos': 0}."""
    peso = PESO_RE.match(datos)
    if peso:
        return {"gramos": int(peso[1]), "estable": peso[2] == "e", "tara_gramos": int(peso[3])}
    if ERROR_RE.match(datos):
        return {"error": datos}
    return None


def consultar(puerto, numero: int, funcion: int, espera: float = 0.3) -> str | None:
    puerto.reset_input_buffer()
    puerto.write(armar_pedido(numero, funcion))
    recibido = b""
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        recibido += puerto.read(64)
        datos = separar_respuesta(recibido, numero, funcion)
        if datos is not None:
            return datos
    return None


def buscar(serial_mod, puertos: list[str], numeros: list[int]):
    for nombre in puertos:
        try:
            serial_mod.Serial(nombre).close()
        except serial_mod.SerialException as error:
            print(f"  {nombre}: no se pudo abrir ({error})")
            if "Permission denied" in str(error):
                print("  En Linux: sudo usermod -aG dialout $USER y volver a iniciar sesión.")
            continue
        for velocidad in VELOCIDADES:
            for paridad in PARIDADES:
                puerto = serial_mod.Serial(nombre, velocidad, bytesize=8, parity=paridad,
                                           stopbits=1, timeout=0.05)
                with puerto:
                    for numero in numeros:
                        datos = consultar(puerto, numero, FUNCION_PESO)
                        if datos is not None:
                            return nombre, velocidad, paridad, numero
                print(f"  {nombre} {velocidad} 8{paridad}1: sin respuesta")
    return None


def restaurar_espera(nombre: str) -> None:
    """Vuelve el puerto a «esperar al menos 1 byte» (VMIN=1, VTIME=0).

    pyserial con timeout deja VMIN=0 y Linux conserva esa configuración al cerrar.
    Chrome no la cambia al abrir: con VMIN=0 su lectura recibe 0 bytes al instante, lo
    toma como desconexión y la balanza «no responde» en el POS (visto el 14/10).
    """
    try:
        import termios
    except ImportError:  # Windows: no aplica
        return
    try:
        with open(nombre, "rb", buffering=0) as tty:
            atributos = termios.tcgetattr(tty)
            atributos[6][termios.VMIN], atributos[6][termios.VTIME] = 1, 0
            termios.tcsetattr(tty, termios.TCSANOW, atributos)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--puerto", help="p. ej. /dev/ttyUSB0 o COM3 (por defecto: todos)")
    parser.add_argument("--numero", type=int, help="número de balanza (por defecto: 1 y luego 2 a 99)")
    parser.add_argument("--segundos", type=int, default=20, help="tiempo mostrando el peso en vivo")
    args = parser.parse_args()
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        print("Falta pyserial: .venv/bin/pip install pyserial")
        return 2

    if args.puerto:
        puertos = [args.puerto]
    else:
        # Solo puertos USB; la Cuora usa un conversor FTDI FT232 (VID 0x0403): primero.
        encontrados = [p for p in list_ports.comports() if p.vid is not None]
        encontrados.sort(key=lambda p: p.vid != 0x0403)
        for p in encontrados:
            print(f"Puerto {p.device}: {p.description} (VID:PID {p.vid:04x}:{p.pid:04x})")
        puertos = [p.device for p in encontrados]
    if not puertos:
        print("No hay puertos serie USB. ¿Está enchufada y encendida la balanza? "
              "En Windows: ¿instalado el driver FTDI? Usar --puerto para indicarlo a mano.")
        return 1
    numeros = [args.numero] if args.numero else list(range(1, 100))

    print("Buscando la balanza...")
    try:
        return diagnosticar(serial, puertos, numeros, args.segundos)
    finally:
        for nombre in puertos:
            restaurar_espera(nombre)


def diagnosticar(serial, puertos: list[str], numeros: list[int], segundos: int) -> int:
    hallada = buscar(serial, puertos, numeros)
    if not hallada:
        print("No respondió ninguna balanza. Revisar: cable, encendido, número de balanza "
              "(menú: Config. equipo → Conectividad → Identificación) y que Qendra no use el puerto.")
        return 1
    nombre, velocidad, paridad, numero = hallada
    print(f"\n✓ Balanza encontrada: puerto {nombre}, {velocidad} baudios, 8{paridad}1, número {numero}")
    if (velocidad, paridad) != (115200, "N"):
        print("  ATENCIÓN: el módulo del POS usa 115200 8N1. Hay que ajustarlo a estos valores.")

    with serial.Serial(nombre, velocidad, bytesize=8, parity=paridad, stopbits=1, timeout=0.05) as puerto:
        firma = consultar(puerto, numero, FUNCION_FIRMA)
        print(f"  Firma del equipo (función 2): {firma!r}")
        print(f"\nPeso en vivo durante {segundos} s (poner y sacar algo de la bandeja):")
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            datos = consultar(puerto, numero, FUNCION_PESO)
            print(f"  {datos!r:>18} → {interpretar_peso(datos) if datos else 'sin respuesta'}")
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
