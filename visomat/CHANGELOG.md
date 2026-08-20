# Changelog

## 0.2.5
- Fix: `scanner.stop()`-Fehler (BlueZ `No discovery started` bei parallelen
  Clients auf dem geteilten Adapter) verliert das gefundene Gerät nicht mehr
  — es wird trotzdem zum Connect übergegangen. Verbessert die Erfassung im
  Koexistenzbetrieb mit dem BLE-Scale-Add-on.


## 0.2.4
- Fix: `_set_current_time` brach Sessions ab, wenn die Service-Liste nicht
  vollständig aufgelöst war (`Service Discovery has not been performed yet`);
  der Uhr-Write ist jetzt voll defensiv und loggt sichtbar (WARNING).
- Debug: GATT-Dump (Services/Chars/Properties) bei Connect für die Analyse
  des Zeit-Mechanismus.


## 0.2.3
- Geräteuhr wird bei jedem erfolgreichen Connect gesetzt (Current Time Service
  0x2A2B) — das Gerät verliert Datum/Uhrzeit nach Batterie-Entnahme; so bleiben
  die Messzeitstempel korrekt.


## 0.2.2
- Transport: Batterie-`start_notify` ist nicht mehr fatal — der visomat
  unterstützt Notifications auf der Batterie-Charakteristik nicht zuverlässig;
  ein Fehler dort brach die Session ab und verlor Blutdruck-Messungen, die
  bereits im kurzen Sync-Fenster ankamen.
- Transport: `dangerous_use_bleak_cache=True` — nutzt den BlueZ-GATT-Cache,
  damit die Discovery in das sehr kurze Verbindungsfenster des Geräts passt.

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
