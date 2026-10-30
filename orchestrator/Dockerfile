FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml ./
COPY jarvis ./jarvis
RUN pip install --no-cache-dir ".[postgres]"

RUN useradd --create-home jarvis
USER jarvis

CMD ["jarvis", "telegram"]
