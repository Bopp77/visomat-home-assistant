#!/bin/sh
# Startet D-Bus + BlueZ (bluetoothd) im Container und führt dann den
# eigentlichen Befehl aus (default: visomat BLE-Gateway).
#
# Robust: Fehler beim D-Bus/BlueZ dürfen den Hauptprozess nicht beenden.
# Der garmin-sync-Container braucht BlueZ nicht; er läuft einfach weiter,
# wenn hier nichts startet.
#
# Home Assistant Add-on / Host-BlueZ: Ist der Host-D-Bus gemountet
# (host_dbus: true, /run/dbus/system_bus_socket vorhanden), wird KEIN
# eigener bluetoothd gestartet — stattdessen nutzt bleak das BlueZ des
# Hosts. So können sich HA-Bluetooth-Integration und dieses Gateway den
# selben BLE-Dongle teilen.

# D-Bus-Daemon starten, sofern der Host keinen exponiert.
if [ ! -e /run/dbus/system_bus_socket ]; then
    mkdir -p /run/dbus
    dbus-daemon --system --fork 2>/dev/null || echo "Hinweis: D-Bus start nicht möglich (kein Problem für garmin_sync)"
    # Nur mit eigenem D-Bus einen eigenen BlueZ-Daemon starten (bindet an
    # den Host-HCI hci0). Bei vorhandenem Host-D-Bus übernimmt der Host.
    if command -v bluetoothd >/dev/null 2>&1 && ! pgrep -x bluetoothd >/dev/null 2>&1; then
        bluetoothd --noplugin=input 2>/dev/null &
        sleep 2
    fi

    # HCI-Adapter hochfahren (falls vom Kernel bereitgestellt).
    hciconfig hci0 up 2>/dev/null || true
fi

# Ausführenden Befehl starten (bleak braucht BlueZ/D-Bus).
exec "$@"
