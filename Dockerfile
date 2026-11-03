FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglu1-mesa libxrender1 libxext6 libsm6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY voxfigure ./voxfigure
COPY assets ./assets
COPY templates ./templates
COPY static ./static
RUN useradd --create-home app && mkdir /cache && chown app:app /cache
USER app
ENV VOXFIGURE_CACHE=/cache
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "900", "app:app"]
