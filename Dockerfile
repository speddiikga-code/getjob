# For running on your own server (e.g. a VM in a Korean cloud region) instead of GitHub Actions.
#   docker build -t getjob .
#   docker run --rm --env-file .env -v "$PWD/data:/app/data" getjob doctor
#   docker run --rm --env-file .env -v "$PWD/data:/app/data" \
#     -v "$PWD/config/experience.yaml:/app/config/experience.yaml:ro" getjob run --send
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ai]"
COPY config ./config

VOLUME ["/app/data"]
ENTRYPOINT ["getjob"]
CMD ["doctor"]
