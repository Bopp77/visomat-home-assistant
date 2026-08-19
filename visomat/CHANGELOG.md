# Changelog

## 0.2.1
- Puls-Sensor: ungültigen `device_class: heart_rate` entfernt (wird von HA
  abgelehnt, der Sensor fehlte dadurch).
- Messzeitpunkt: State jetzt mit Zeitzone (Gerät liefert lokale Zeit ohne
  Zone; wird als lokale Systemzeit interpretiert) — `device_class: timestamp`
  verlangt TZ-ISO.
- `bluetoothctl trust DD:67:E2:1E:C0:93` auf dem Host-BlueZ empfohlen
  (GATT-Cache, sonst schlägt die Service-Discovery im kurzen Sync-Fenster fehl).

## 0.2.0
- Transformation in ein Home Assistant Add-on (Ordner `visomat/`).
- Bluetooth-Sharing über Host-BlueZ via `host_dbus` — kein exklusiver
  Dongle-Zugriff mehr, gemeinsame Nutzung mit der HA-Bluetooth-Integration.
- Konfiguration über `/data/options.json` (Add-on-Optionen in der HA-Oberfläche).
- Unified Entrypoint `visomat_addon.main`: Gateway + optionaler Garmin-Sync
  in einem Prozess, mit Persistenz der Garmin-Tokens unter `/data/garminconnect`.
- Multi-Arch-Builds (amd64 + arm64) für das ghcr-Image.
- Ablösung des Portainer-Stacks (192.168.178.102): Dongle wandert auf die
  HA-VM (192.168.178.105), Konfiguration via Add-on-Optionen (MQTT-User
  `visomat` im HA-Mosquitto), Garmin-Tokens unter `/data/garminconnect`.
