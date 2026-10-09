FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY dashboard/requirements.txt /tmp/dashboard-requirements.txt
COPY dashboard/requirements.lock /tmp/dashboard-requirements.lock
RUN pip install -r /tmp/dashboard-requirements.txt -c /tmp/dashboard-requirements.lock

COPY dashboard ./dashboard
RUN python dashboard/patch_streamlit_branding.py
COPY data/processed ./data/processed
COPY data/external/player_identity_crosswalk.csv ./data/external/player_identity_crosswalk.csv
COPY .streamlit/config.toml ./.streamlit/config.toml
RUN python dashboard/check_release_assets.py

EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10000/_stcore/health', timeout=3)"

CMD ["sh", "-c", "streamlit run dashboard/app.py --server.address=0.0.0.0 --server.port=${PORT:-10000} --server.headless=true"]
