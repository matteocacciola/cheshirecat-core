FROM python:3.11-slim-bullseye

### ENVIRONMENT VARIABLES ###
ENV PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

### SYSTEM SETUP ###
# Install system dependencies in a single layer with cleanup
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        build-essential \
        libmagic1 \
        libmagic-dev \
        poppler-utils \
        tesseract-ocr \
        libgl1 \
        mime-support && \
    apt-get clean

### PREPARE BUILD WITH NECESSARY FILES AND FOLDERS ###
WORKDIR /app

COPY ./pyproject.toml ./uv.lock ./LICENSE ./
COPY ./cat/core_plugins ./cat/core_plugins

### INSTALL DEPENDENCIES (CORE + CORE PLUGINS) ###
RUN pip install -U pip uv && \
    uv sync --frozen --no-install-project --no-upgrade --no-cache && \
    find ./cat/core_plugins -name requirements.txt | sed 's/^/-r /' | xargs uv pip install --no-cache --no-upgrade && \
    rm -rf *.egg-info && \
    uv cache clean && \
    find ./ -type d -name __pycache__ -exec rm -rf {} + && \
    rm -rf /root/.cache/pip && \
    rm -rf /tmp/* /var/tmp/*

### REMOVE BUILD TOOLS (IMPORTANT) ###
RUN apt-get purge -y build-essential && \
    apt-get autoremove --purge -y && \
    rm -rf /var/lib/apt/lists/*

COPY ./cat ./cat
COPY ./data ./data
COPY ./migrations ./migrations

### FINISH ###
CMD ["uv", "run", "python", "-m", "cat.main"]