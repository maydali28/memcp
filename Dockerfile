FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md CHANGELOG.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "memcp"]
