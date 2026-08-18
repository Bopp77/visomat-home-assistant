FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY visomat_bt ./visomat_bt
COPY garmin_sync ./garmin_sync
COPY config.example.yaml ./config.yaml

CMD ["python", "-m", "visomat_bt.main"]
