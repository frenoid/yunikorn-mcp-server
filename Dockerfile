# Build stage
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS build

RUN apt-get update -y && apt-get upgrade -y

COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "main.py"]