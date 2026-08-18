FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

# BlueZ + D-Bus für BLE im Container. Der Host stellt nur den HCI-Adapter
# (hci0) bereit; bluetoothd läuft im Container.
RUN apt-get update && apt-get install -y --no-install-recommends \
        bluez \
        dbus \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY visomat_bt ./visomat_bt
COPY garmin_sync ./garmin_sync
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY config.example.yaml ./config.yaml

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "visomat_bt.main"]
