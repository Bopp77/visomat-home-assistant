# visomat comfort soft BT → Home Assistant (BLE-Gateway)

Liest das Blutdruckmessgerät **visomat comfort soft BT** (UEBE Medical, Art.-Nr.
24065) rein lokal per Bluetooth Low Energy aus. Das Gerät implementiert den
Standard **Blood Pressure Service (0x1810)**; jede Messung kommt als
Notification auf Characteristic **0x2A35** und wird per MQTT-Discovery als
Home-Assistant-Entitäten veröffentlicht.

Das Projekt lässt sich als **Home Assistant Add-on** (empfohlen) oder als
eigenständiger Docker-Container (Portainer, Legacy) betreiben.

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
- Home Assistant mit BLE-Adapter (z.B. Intel AX201 oder USB-Dongle) und BlueZ ≥ 5.43.
- Der BLE-Dongle wird vom Host-BlueZ verwaltet; die HA-Bluetooth-Integration und
  dieses Add-on **teilen sich den Adapter** gleichzeitig (Multi-Client über D-Bus).
- Das Gerät muss in BLE-Reichweite des Homeservers sein (~10–15 m).
- Mosquitto-Broker (HA-Add-on `Mosquitto broker` oder extern).

## Installation als Home Assistant Add-on (empfohlen)

Das Add-on wird aus diesem Repository über den Add-on-Store installiert. Das
Image wird per GitHub Actions als Multi-Arch-Image (amd64/aarch64) nach GHCR
gepusht; der Supervisor lädt das passende Image und startet es.

1. **Repository hinzufügen**: Einstellungen → Add-ons → Add-on-Store →
   Menü (⋮) → Repository → `https://github.com/Bopp77/visomat-home-assistant` →
   *Hinzufügen*.
2. **Add-on installieren**: Im Store auf **visomat comfort soft BT Gateway** →
   *Installieren*.
3. **Konfigurieren**: Im Tab *Konfiguration* (siehe Abschnitt unten) die MAC des
   Geräts und ggf. den MQTT-Broker setzen, dann *Speichern*.
4. **Start**: Tab *Info* → *Starten*. Log im Tab *Log* prüfen.

> **Hinweis:** Das Add-on bezieht sein Image mit dem Tag `0.2.0` aus
> `ghcr.io/bopp77/visomat-home-assistant`. Das Tag wird beim Release-Tag
> `v0.2.0` von der CI erzeugt; vor dem ersten Release läuft nur die
> Portainer-/Standalone-Variante.

> **Bluetooth-Dongle-Sharing:** Das Add-on läuft mit `host_dbus: true` und
> spricht das **Host-BlueZ** direkt über D-Bus an. Es startet keinen eigenen
> `bluetoothd` und belegt den Dongle nicht exklusiv — die
> HA-Bluetooth-Integration (z.B. für eine BLE-Waage) und das visomat-Gateway
> können denselben USB-Dongle parallel nutzen. So kann der Dongle vom
> Portainer-Server (192.168.178.102) auf die Home-Assistant-VM
> (192.168.178.105) umziehen.

### Konfiguration (Add-on-Optionen)

| Option | Bedeutung |
|---|---|
| `visomat.ble.mac` | MAC (`DD:67:E2:1E:C0:93`), `""` leer für Name-Scan |
| `visomat.ble.name` | Name-Substring (`comfort soft`), falls keine MAC |
| `visomat.ble.adapter` | BlueZ-Adapter (`hci0`) |
| `visomat.ble.scan_timeout_sec` | Scan-Zeitfenster pro Versuch |
| `visomat.ble.scan_interval_sec` | Rescan, wenn Gerät nicht erreichbar |
| `visomat.ble.reconnect_delay_sec` | Pause zwischen Reconnect-Versuchen |
| `visomat.ble.timeout_sec` | Connect/GATT-Timeout |
| `visomat.ble.watchdog_max_failures` | Neustart nach N Connect-Fehlern (BlueZ-Stuck-Discovery); `0` = aus |
| `visomat.mqtt.host` | Broker (HA-Add-on: `core-mosquitto`) |
| `visomat.mqtt.*` | Broker-Port/Zugang, `base_topic` + Discovery-Prefix |
| `garmin_sync.enabled` | Garmin-Connect-Sync aktivieren (siehe unten) |
| `garmin_sync.garmin.email/password` | Garmin-Konto für den Sync |

Hinweis: Nach jeder Änderung *Speichern* und das Add-on neu starten
(Tab *Info* → *Neu starten*).

### Garmin-MFA-Login (einmalig)

Wenn `garmin_sync.enabled: true` gesetzt ist, wird einmalig ein interaktiver
MFA-Login benötigt. Im Add-on-Container per `docker exec` auf dem Home-Assistant-Host:

```bash
docker exec -it addon_visomat python -m garmin_sync.main --login
# MFA-Code am Prompt eingeben; Tokens landen persistent unter /data/garminconnect
```

Die Tokens bleiben über Add-on-Updates und Neustarts erhalten (`/data`-Volume).

## Betriebsmodell: visomat + BLE-Waage auf einem Dongle

Wenn die **BLE-Waage** und das visomat-Gateway denselben USB-Dongle nutzen,
gilt: **zwei unabhängige BLE-Add-ons auf einem Adapter koexistieren nicht
zuverlässig.** Der Dauerbetrieb des Scale-Add-ons wedged die fragile
GATT-Auflösung des visomat (bekannter BlueZ-„stuck discovery"-Bug, siehe
[BLE Scale Sync Troubleshooting](https://blescalesync.dev/troubleshooting)).
Erprobter Betriebsweg:

- **visomat** läuft dauerhaft (Best-Effort). Ein **Watchdog**
  (`visomat.ble.watchdog_max_failures`, Default 8, 0 = aus) beendet den Prozess
  nach N aufeinanderfolgenden Connect-/Discovery-Fehlern; der Supervisor
  startet das Add-on frisch (sauberer BlueZ-Zustand). Das Gerät puffert
  Messungen und liefert sie beim nächsten erfolgreichen Connect nach — es geht
  nichts verloren, nur verzögert.
- **Waage (BLE Scale Sync)** läuft im **Einmal-Modus**
  (`runtime.continuous_mode: false`): einmal wiegen, dann beendet sich das
  Add-on selbst. Gestartet wird es manuell über den Supervisor-Switch
  `switch.ble_scale_sync` (Einstellungen → Geräte & Dienste → in ein
  Dashboard legen): **Switch AN** → auf die Waage steigen → Messung →
  Add-on beendet sich → Switch geht automatisch auf AUS.
- Eine kleine Automation hält das visomat nach einer Waagen-Sitzung gesund
  (die Waage kann eine Verbindung im BlueZ hinterlassen, die den visomat
  wedged):

  ```yaml
  trigger:
    - platform: state
      entity_id: switch.ble_scale_sync
      to: "off"
  action:
    - service: hassio.addon_restart
      data:
        addon: 789c84b3_visomat
  ```

**Hinweis:** Bei dauerhaftem Parallelbetrieb beider Add-ons ist ein **zweiter
BLE-Adapter** oder ein **ESP32-BLE-Proxy** für die Waage die sauberere Lösung
(empfohlen in der BLE-Scale-Sync-Doku).

## Konfiguration (Standalone / Legacy-Docker)
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

## Produktiv-Deployment (ghcr.io + Portainer) — Legacy

> **Hinweis:** Seit Version 0.2.0 ist das Home Assistant Add-on der primäre
> Weg. Der Portainer-Stack wird nur noch für Umgebungen ohne HA-Supervisor
> verwendet und belegt den BLE-Dongle **exklusiv**.

### 1. GitHub Actions baut das Image automatisch
Bei jedem Push auf `main` (oder Tag `v*`) baut der Workflow
`.github/workflows/build-push-ghcr.yml` das Image (amd64 + arm64) und pusht es
nach `ghcr.io/bopp77/visomat-home-assistant` (`:latest`, `:main`, bzw. `:vX.Y.Z`).

### 2. Portainer-Stack auf dem Produktiv-Host
Auf `192.168.178.102` (Portainer-Web-UI → **Stacks → Add stack**):

- **Voraussetzungen auf dem Host:**
  - USB-BLE-Dongle durchgereicht (z.B. Realtek RTL8761BU); für Realtek-
    Dongles die Firmware `rtl8761bu_fw.bin` + `rtl8761bu_config.bin` nach
    `/lib/firmware/rtl_bt/` auf dem Host kopieren (Debian: `firmware-realtek`),
    sonst bleibt hci0 ohne Adresse.
  - Gerät einmalig als trusted markieren (im Container):
    `docker compose exec visomat-bt bluetoothctl trust DD:67:E2:1E:C0:93`
  - Konfiguration nach `/opt/visomat/config.yaml` legen
    (Vorlage: `config.prod.example.yaml`; Sektionen `visomat:` + `garmin_sync:`)
- **Stack-YAML:** `docker-compose.prod.yml` aus diesem Repo verwenden
  (image-basiert von ghcr.io, `privileged: true` + `/dev:/dev`-Mount für den
  HCI-/rfkill-Zugriff; BlueZ/D-Bus läuft im Container, der Host braucht kein
  BlueZ).
- Nach dem Anlegen einmalig den Garmin-MFA-Login ausführen:
  ```bash
  docker compose -f /opt/visomat/docker-compose.prod.yml run --rm garmin-sync python -m garmin_sync.main --login
  ```
  (Tokens landen persistent im Volume `garmin-tokens`.)

### 3. Update des Stacks
Push auf `main` → ghcr-Image `:latest` neu → in Portainer **Stack → Update**
(Image neu pullen / Stack neu deployen).

### 4. Ablösung durch das Add-on (Migration 192.168.178.102 → 192.168.178.105)

Der Portainer-Stack wird durch das HA-Add-on ersetzt, damit der USB-BLE-Dongle
vom Host-BlueZ der HA-VM verwaltet und mit der Bluetooth-Integration geteilt
werden kann. Ablauf:

1. **Dongle umstecken** vom Portainer-Server auf die HA-VM und dort als `hci0`
   verifizieren (Realtek-Firmware liegt HAOS üblicherweise bei).
2. **MQTT-User `visomat`** im HA-Mosquitto anlegen (Add-on → Mosquitto →
   Configuration → Users) und im Add-on als `username`/`password` eintragen.
3. **Add-on installieren** (siehe oben), BLE-/Garmin-Optionen setzen, starten,
   Gerät als trusted markieren, Garmin-MFA-Login ausführen.
4. **Verifikation**: Messung auslösen → Entitäten in HA + Garmin-Eintrag,
   BLE-Waage läuft parallel weiter (Dongle-Sharing bestätigt).
5. **Portainer-Stack `visomat` stoppen**; erst nach Abnahme löschen und
   `/opt/visomat` sowie das Volume `garmin-tokens` entfernen.


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
ruff check visomat_bt/ garmin_sync/ visomat_addon/
pytest -q
```

## Garmin-Sync (visomat-Messwerte → Garmin Connect)

Der optionale Dienst `garmin-sync` abonniert die MQTT-Topics des Gateways und
lädt jede neue Messung (Systole/Diastole/Puls + Messzeitpunkt) nach Garmin
Connect hoch. Die Messungen erscheinen dort als manuell erfasste
Blutdruckwerte.

**Hinweis:** Der Dienst nutzt die inoffizielle Garmin-Connect-API
(`garminconnect`). Bei MFA-aktivem Konto ist einmalig ein interaktiver Login
nötig; die Tokens werden danach persistent gespeichert. Im Add-on unter
`/data/garminconnect`, im Docker-Betrieb unter `~/.garminconnect`.

### Konfiguration (Add-on-Optionen / config.yaml)
```yaml
garmin_sync:
  enabled: true
  mqtt:
    host: "core-mosquitto"           # Add-on: core-mosquitto; Standalone: 192.168.178.105
    port: 1883
    username: "bopp"
    password: ""
    topic_base: "visomat_bt"
  garmin:
    email: "mein.garmin@example.com"
    password: "..."               # einmalig für --login nötig
    timezone: "Europe/Berlin"
    token_path: "/data/garminconnect"   # Add-on; Standalone: "~/.garminconnect"
```

### Einmaliger Garmin-Login (MFA)
Add-on:
```bash
docker exec -it addon_visomat python -m garmin_sync.main --login
```
Docker-Compose:
```bash
docker compose run --rm garmin-sync python -m garmin_sync.main --login
```
MFA-Code am Prompt eingeben; Tokens werden im Add-on-/garmin-tokens-Volume gespeichert.

### Start
Add-on: *Info* → *Starten*. Docker-Compose: `docker compose up -d --build`.

Deduplizierung: Eine Messung wird nur dann hochgeladen, wenn
`measurementTimestampGMT` noch nicht in Garmin vorhanden ist — damit werden
wiederholte Zustellungen des Geräts (Offline-Sync beim Connect) nicht
doppelt übertragen.

## Inbetriebnahme (Add-on)
1. Add-on installieren/starten (siehe oben), Gerät einmalig als trusted markieren:
   `docker exec -it addon_visomat bluetoothctl trust DD:67:E2:1E:C0:93`
2. Messung am Gerät starten → Log prüfen (`connected to comfort soft BT`,
   `published measurement: ...`), Werte gegen
   Geräte-Display plausibilisieren.

## Projektstruktur
```
visomat/                # Home Assistant Add-on (Repository-Root ist der Add-on-Store)
└── config.yaml         # Add-on-Manifest (image, Optionen + Schema)
                        # (Image wird per CI gebaut; kein lokaler Dockerfile-Build)

visomat_addon/          # Add-on-Orchestrator: Gateway + optionaler Garmin-Sync
├── main.py             # Supervised Entrypoint (liest /data/options.json)
└── tests/

visomat_bt/
├── protocol.py      # BLS-Parser: Flags, IEEE-11073 SFLOAT, Timestamp, Status, Feature
├── transport.py     # BleTransport (bleak): Connect, Subscribe 0x2A35/0x2A19, Device-Info
├── listener.py      # Kontinuierlicher Scanner + Reconnect-Watchdog
├── publisher.py     # MQTT-Discovery + State-Publishing
├── config.py        # config.yaml / /data/options.json (Sektion `visomat:`)
├── main.py          # Entrypoint
└── tests/           # Parser- und Publisher-Tests gegen Hex-Vektoren

garmin_sync/
├── mqtt_listener.py # Abonniert visomat-Topics, assembliert Messungen
├── garmin_uploader.py # Garmin-Auth, set_blood_pressure, Dedupe
├── syncer.py        # Verknüpft Listener + Uploader
├── config.py        # config.yaml / /data/options.json (Sektion `garmin_sync:`)
├── main.py          # Entrypoint (+ --login für MFA)
└── tests/           # Assemblierung, Dedupe, Validierung
```
