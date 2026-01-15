FROM python:3.13-slim-bullseye AS system

### ENVIRONMENT VARIABLES ###
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy
ENV UV_NO_CACHE=1

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

FROM system AS libraries

### PREPARE BUILD WITH NECESSARY FILES AND FOLDERS ###
WORKDIR /app

COPY ./pyproject.toml ./uv.lock ./LICENSE ./

### INSTALL CORE DEPENDENCIES ###
RUN pip install -U pip && \
    pip install uv && \
    uv sync --frozen --no-install-project

FROM libraries AS build-dev

COPY ./cat ./cat
COPY ./data ./data
COPY ./migrations ./migrations

### INSTALL PLUGIN DEPENDENCIES ###
RUN find /app/cat/core_plugins -name requirements.txt -exec uv pip install --no-cache -r {} \; && \
    uv cache clean && \
    find /app | grep -E "(/__pycache__$|\.pyc$|\.pyo$)" | xargs sudo rm -rf && \
    pip cache purge

### FINISH ###
CMD ["uv", "run", "python", "-m", "cat.main"]

FROM libraries AS build-prod

COPY ./cat ./cat
COPY ./data ./data
COPY ./migrations ./migrations

### FINISH ###
CMD ["uv", "run", "python", "-m", "cat.main"]