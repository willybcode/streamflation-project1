# Streamflation dashboard — production image
# Build:  docker build -t streamflation .
# Run:    docker run -p 8050:8050 streamflation   ->  http://localhost:8050

FROM python:3.12-slim

WORKDIR /srv

# Dependencies first, so the (rarely changing) layer is cached
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Raw data + pipeline: data/processed is rebuilt at image build time,
# so the image always contains tables generated from exactly the raw files
# that were copied in with it.
COPY data/raw ./data/raw
COPY src ./src
RUN python src/data_prep.py

# Application code
COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8050/').status==200 else 1)"

# gunicorn serves the Dash/Flask server object exported by app/app.py
CMD ["gunicorn", "--chdir", "/srv/app", "--bind", "0.0.0.0:8050", "--workers", "2", "--timeout", "120", "app:server"]
