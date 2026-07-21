# DocNow.NG backend — FastAPI on Railway.
# All deps ship manylinux wheels, so no compiler/build stage is needed.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Railway injects $PORT at runtime; default for local `docker run`.
ENV PORT=5001
EXPOSE 5001

# Shell form so ${PORT} expands. Bind 0.0.0.0 so the platform can reach it.
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
