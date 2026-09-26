# For running on your own server (e.g. a VM in a Korean cloud region) instead of GitHub Actions.
#   docker build -t getjob .
#   docker run --rm --env-file .env -v "$PWD/data:/app/data" getjob doctor
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config

VOLUME ["/app/data"]
ENTRYPOINT ["getjob"]
CMD ["doctor"]
