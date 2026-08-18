#!/bin/sh
# Startet D-Bus + BlueZ (bluetoothd) im Container und führt dann den
# eigentlichen Befehl aus (default: visomat BLE-Gateway).
set -e

# D-Bus-Daemon starten (eigene Session-Bus, da der Host keinen exponiert).
if [ ! -e /run/dbus/system_bus_socket ]; then
    mkdir -p /run/dbus
    dbus-daemon --system --fork
fi

# BlueZ-Daemon starten (bindet an den Host-HCI hci0).
if ! pgrep -x bluetoothd >/dev/null 2>&1; then
    bluetoothd --noplugin=input &
    sleep 2
fi

# HCI-Adapter hochfahren (falls vom Kernel bereitgestellt).
hciconfig hci0 up 2>/dev/null || true

# Ausführenden Befehl starten (bleak braucht BlueZ/D-Bus).
exec "$@"
