# Build context: openshorts. CPU wheels avoid shipping NVIDIA CUDA packages to N100.
FROM python:3.11-slim AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade --no-cache-dir pip \
    && pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.11.0 torchvision==0.26.0 \
    && pip install --no-cache-dir -r requirements.txt \
    && pip check

FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-dejavu-core libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r appuser \
    && useradd -r -g appuser -d /app -s /sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

COPY --chown=appuser:appuser *.py ./
COPY --chown=appuser:appuser fonts/ ./fonts/
COPY --chown=appuser:appuser assets/fonts/ ./assets/fonts/
COPY --chown=appuser:appuser assets/music/ ./assets/music/
COPY LICENSE THIRD_PARTY_NOTICES.md ./

RUN mkdir -p /app/uploads /app/output /tmp/Ultralytics \
    && chown appuser:appuser /app /app/uploads /app/output /tmp/Ultralytics

USER appuser
RUN python -c "import torch; assert torch.version.cuda is None, 'CPU Torch required'; from ultralytics import YOLO; YOLO('yolov8n.pt')"

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
