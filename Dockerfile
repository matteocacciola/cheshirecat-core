FROM python:3.11.11-slim-bullseye AS system

### ENVIRONMENT VARIABLES ###
ENV PYTHONUNBUFFERED=1
ENV WATCHFILES_FORCE_POLLING=true

### SYSTEM SETUP ###
# Install system dependencies for Unstructured document parsing
RUN apt-get update && \
    apt-get install -y \
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
    rm -rf /var/lib/apt/lists/*

FROM system AS libraries

### PREPARE BUILD WITH NECESSARY FILES AND FOLDERS ###
COPY ./pyproject.toml /app/pyproject.toml
COPY ./requirements.txt /app/requirements.txt

### INSTALL PYTHON DEPENDENCIES (Core) ###
WORKDIR /app
RUN pip install -U pip && \
    pip install --no-cache-dir -r requirements.txt

FROM libraries AS scaffold

COPY ./data /app/data

### COPY CAT CODE INSIDE THE CONTAINER (so it can be run standalone) ###
COPY ./cat /app/cat

FROM scaffold AS build-dev

### INSTALL PYTHON DEPENDENCIES (Plugins) ###
RUN find /app/cat/core_plugins -name requirements.txt -exec pip install -r {} \;
# RUN python3 -c "import nltk; nltk.download('punkt');nltk.download('averaged_perceptron_tagger');import tiktoken;tiktoken.get_encoding('cl100k_base')"

### FINISH ###
CMD python3 -m cat.main

FROM scaffold AS build-prod

### FINISH ###
CMD python3 -m cat.main