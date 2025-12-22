FROM python:3.13-slim-bullseye AS system

### ENVIRONMENT VARIABLES ###
ENV PYTHONUNBUFFERED=1
ENV WATCHFILES_FORCE_POLLING=true
ENV UV_LINK_MODE=copy

### SYSTEM SETUP ###
# Install system dependencies in a single layer with cleanup
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        fastjar \
        libmagic-mgc \
        libmagic1 \
        libmagic-dev \
        poppler-utils \
        tesseract-ocr \
        libgl1-mesa-glx \
        mime-support && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

### INSTALL UV ###
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

FROM system AS libraries

### PREPARE BUILD WITH NECESSARY FILES AND FOLDERS ###
WORKDIR /app
COPY ./pyproject.toml ./uv.lock ./LICENSE ./

### COPY APPLICATION CODE ###
COPY ./data ./data
COPY ./cat ./cat

### INSTALL CORE DEPENDENCIES ###
# Copy and install dependencies in separate layers for better caching
RUN /root/.local/bin/uv sync --no-cache

FROM libraries AS build-dev

### INSTALL PLUGIN DEPENDENCIES ###
# Clean cache immediately after each installation
RUN find /app/cat/core_plugins -name requirements.txt -exec /root/.local/bin/uv pip install -r {} \; && \
    /root/.local/bin/uv cache clean || true && \
    rm -rf /root/.cache/uv 2>/dev/null || true && \
    find /app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

### FINISH ###
CMD ["/root/.local/bin/uv", "run", "python", "-m", "cat.main"]

FROM libraries AS build-prod

### FINISH ###
CMD ["/root/.local/bin/uv", "run", "python", "-m", "cat.main"]