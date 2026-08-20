# visomat comfort soft BT Gateway

BLE-Gateway für das Blutdruckmessgerät **visomat comfort soft BT** (UEBE
Medical, Art.-Nr. 24065). Jede Messung wird per MQTT-Discovery als
Home-Assistant-Entitäten veröffentlicht. Optionaler Sync nach Garmin Connect.

## Bluetooth-Zugriff

Das Add-on nutzt das **BlueZ des Hosts** über den Host-D-Bus (`host_dbus`)
und startet keinen eigenen Bluetooth-Daemon. Voraussetzung ist, dass der
Dongle vom Host (BlueZ) erkannt wird.

**Koexistenz mit einer BLE-Waage:** Zwei unabhängige BLE-Add-ons auf einem
Dongle koexistieren nicht zuverlässig (BlueZ-„stuck discovery"-Bug). Erprobter
Weg: die Waage im Einmal-Modus via `switch.ble_scale_sync` starten (siehe
README, Abschnitt *Betriebsmodell*).

## Konfiguration

| Option | Bedeutung |
|---|---|
| `visomat.ble.mac` | MAC des Geräts (`DD:67:E2:1E:C0:93`), leer für Name-Scan |
| `visomat.ble.name` | Name-Substring (`comfort soft`), falls keine MAC |
| `visomat.ble.adapter` | BlueZ-Adapter (`hci0`) |
| `visomat.mqtt.host` | MQTT-Broker; HA-Add-on: `core-mosquitto` |
| `visomat.mqtt.username/password` | Broker-Zugang |
| `garmin_sync.enabled` | Garmin-Connect-Sync aktivieren |
| `garmin_sync.garmin.email/password` | Garmin-Konto |

Gerät einmalig als trusted markieren (GATT-Cache, empfohlen):

```bash
docker exec -it addon_<slug> bluetoothctl trust DD:67:E2:1E:C0:93
```

> `<slug>` ist der vollständige Add-on-Slug (z.B. `789c84b3_visomat`);
> den Container-Namen mit `docker ps | grep visomat` ermitteln.

## Garmin-Sync (optional)

`garmin_sync.enabled: true` setzen und einmalig den MFA-Login ausführen:

```bash
docker exec -it addon_<slug> python -m garmin_sync.main --login
```

Tokens werden persistent unter `/data/garminconnect` gespeichert und bleiben
über Updates erhalten.
