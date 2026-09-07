FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY src/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application source (includes shared/, modules, templates and static).
COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
