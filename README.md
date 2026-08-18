# visomat comfort soft BT → Home Assistant (BLE-Gateway)

Liest das Blutdruckmessgerät **visomat comfort soft BT** (UEBE Medical, Art.-Nr.
24065) rein lokal per Bluetooth Low Energy aus. Das Gerät implementiert den
Standard **Blood Pressure Service (0x1810)**; jede Messung kommt als
Notification auf Characteristic **0x2A35** und wird per MQTT-Discovery als
Home-Assistant-Entitäten veröffentlicht.

Gegen ein reales Gerät verifiziert:

- Advertising-Name `comfort soft BT` (statische Random-Adresse, stabil),
  Service-UUID `0x1810` wird beworben.
- GATT-Dump: `0x2A35` (Messung) + `0x2A49` (Feature) + `0x2A19` (Batterie)
  + `0x180A` (Device Info). **Kein** `0x2A52` (RACP).
- **Automatischer Offline-Sync**: Das Gerät puffert Messungen intern und sendet
  beim Verbindungsaufbau automatisch alle gespeicherten Messwerte nacheinander
  als Notifications. Der Dienst muss also nicht 24/7 empfangsbereit sein;
  gesammelte Messungen werden beim nächsten Sync vollständig nachgeliefert.
- **Device-Trusting empfohlen**: Damit BlueZ die GATT-Struktur dauerhaft cacht
  und nicht bei jedem kurzen Sync-Fenster neu über BLE abfragen muss, das Gerät
  einmalig als vertrauenswürdig markieren:
  `bluetoothctl trust DD:67:E2:1E:C0:93`
- Der Dienst nutzt einen **kontinuierlichen Scanner** mit sofortigem Connect:
  Das visomat wirbt nur während seines kurzen Sync-Fensters (aktive Messung),
  ein periodischer Scan mit Lücken würde dieses Fenster verpassen.

## Voraussetzungen
- Host mit BLE-Adapter (z.B. Intel AX201) und BlueZ ≥ 5.43, D-Bus erreichbar.
- Das Gerät muss in BLE-Reichweite des Homeservers sein (~10–15 m).
- Mosquitto-Broker in Home Assistant.

## Konfiguration
```bash
cp config.example.yaml config.yaml
# Abschnitt `visomat:` anpassen (ble.mac oder Name-Scan, mqtt.*)
```

| Abschnitt | Bedeutung |
|---|---|
| `visomat.ble.mac` | MAC (`DD:67:E2:1E:C0:93`), `auto` oder leer für Name-Scan |
| `visomat.ble.name` | Name-Substring (`comfort soft`), falls keine MAC |
| `visomat.ble.scan_timeout_sec` | Scan-Zeitfenster pro Versuch |
| `visomat.ble.reconnect_delay_sec` | Pause zwischen Reconnect-Versuchen |
| `visomat.mqtt.*` | Broker-Zugang, `base_topic` (`visomat_bt`) + Discovery-Prefix |

Hinweis: Der `visomat-bt`-Container läuft mit `network_mode: host` (BLE via
hci0) und erreicht den Mosquitto-Broker daher über dessen **Host-Adresse/IP**,
nicht über einen Docker-DNS-Namen. In `config.yaml` ggf. `host` entsprechend
setzen.
## Start (lokal / Entwicklung)
```bash
docker compose up -d --build
```

## Produktiv-Deployment (ghcr.io + Portainer)

### 1. GitHub Actions baut das Image automatisch
Bei jedem Push auf `main` (oder Tag `v*`) baut der Workflow
`.github/workflows/build-push-ghcr.yml` das Image und pusht es nach
`ghcr.io/bopp77/visomat-home-assistant` (`:latest`, `:main`, bzw. `:vX.Y.Z`).

### 2. Portainer-Stack auf dem Produktiv-Host
Auf `192.168.178.102` (Portainer-Web-UI → **Stacks → Add stack**):

- **Voraussetzungen auf dem Host:**
  - BlueZ/D-Bus für BLE, Gerät einmalig als trusted markieren:
    `bluetoothctl trust DD:67:E2:1E:C0:93`
  - Konfiguration nach `/opt/visomat/config.yaml` legen
    (Vorlage: `config.prod.example.yaml`; Sektionen `visomat:` + `garmin_sync:`)
- **Stack-YAML:** `docker-compose.prod.yml` aus diesem Repo verwenden
  (image-basiert von ghcr.io, Mount-Pfad `/opt/visomat/config.yaml`).
- Nach dem Anlegen einmalig den Garmin-MFA-Login ausführen:
  ```bash
  docker compose -f /opt/visomat/docker-compose.prod.yml run --rm garmin-sync python -m garmin_sync.main --login
  ```
  (Tokens landen persistent im Volume `garmin-tokens`.)

### 3. Update des Stacks
Push auf `main` → ghcr-Image `:latest` neu → in Portainer **Stack → Update**
(Image neu pullen / Stack neu deployen).


## Home Assistant
Per MQTT-Discovery erscheint das Gerät **visomat comfort soft BT** mit:

- Sensoren: Systole/Diastole/Mittlerer arterieller Druck (`mmHg`), Puls (`bpm`,
  `device_class: heart_rate`), Messzeitpunkt, Benutzer-ID, Batterie (%), Feature
- Binär-Sensoren (diagnostisch): Körperbewegung, Manschette zu locker,
  unregelmäßiger Puls, Puls außerhalb Bereich, falsche Messposition

## Lokal entwickeln & testen
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check visomat_bt/ garmin_sync/
pytest -q
```

## Garmin-Sync (visomat-Messwerte → Garmin Connect)

Der optionale Dienst `garmin-sync` abonniert die MQTT-Topics des Gateways und
lädt jede neue Messung (Systole/Diastole/Puls + Messzeitpunkt) nach Garmin
Connect hoch. Die Messungen erscheinen dort als manuell erfasste
Blutdruckwerte.

**Hinweis:** Der Dienst nutzt die inoffizielle Garmin-Connect-API
(`garminconnect`). Bei MFA-aktivem Konto ist einmalig ein interaktiver Login
nötig; die Tokens werden danach persistent gespeichert.

### Konfiguration (config.yaml)
```yaml
garmin_sync:
  enabled: true
  mqtt:
    host: "192.168.178.105"
    port: 1883
    username: "bopp"
    password: ""
    topic_base: "visomat_bt"
  garmin:
    email: "mein.garmin@example.com"
    password: "..."               # einmalig für --login nötig
    timezone: "Europe/Berlin"
    token_path: "~/.garminconnect"
```

### Einmaliger Garmin-Login (MFA)
```bash
docker compose run --rm garmin-sync python -m garmin_sync.main --login
# MFA-Code am Prompt eingeben; Tokens werden im Volume garmin-tokens gespeichert
```

### Start
```bash
docker compose up -d --build
```

Deduplizierung: Eine Messung wird nur dann hochgeladen, wenn
`measurementTimestampGMT` noch nicht in Garmin vorhanden ist — damit werden
wiederholte Zustellungen des Geräts (Offline-Sync beim Connect) nicht
doppelt übertragen.

## Inbetriebnahme
1. Gerät in Sync-Bereitschaft versetzen (Messung am Gerät starten).
2. `ble.mac` setzen (per `bluetoothctl scan on` ermitteln) und Dienst starten.
3. Messung durchführen → Log prüfen (`published measurement: ...`), Werte gegen
   Geräte-Display plausibilisieren.

## Projektstruktur
```
visomat_bt/
├── protocol.py      # BLS-Parser: Flags, IEEE-11073 SFLOAT, Timestamp, Status, Feature
├── transport.py     # BleTransport (bleak): Connect, Subscribe 0x2A35/0x2A19, Device-Info
├── listener.py      # Kontinuierlicher Scanner + Reconnect-Watchdog
├── publisher.py     # MQTT-Discovery + State-Publishing
├── config.py        # config.yaml (Sektion `visomat:`)
├── main.py          # Entrypoint
└── tests/           # Parser- und Publisher-Tests gegen Hex-Vektoren

garmin_sync/
├── mqtt_listener.py # Abonniert visomat-Topics, assembliert Messungen
├── garmin_uploader.py # Garmin-Auth, set_blood_pressure, Dedupe
├── syncer.py        # Verknüpft Listener + Uploader
├── config.py        # config.yaml (Sektion `garmin_sync:`)
├── main.py          # Entrypoint (+ --login für MFA)
└── tests/           # Assemblierung, Dedupe, Validierung
```
