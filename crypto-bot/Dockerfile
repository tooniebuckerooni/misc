FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dashboard]"

# Persistent data (SQLite pipelines) lives here — mount a volume at /app/data in production.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

COPY docker/entrypoint.sh /app/entrypoint.sh
# Strip any CRLF (Windows) line endings so the shebang works, then make executable.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8501
ENTRYPOINT ["/app/entrypoint.sh"]
