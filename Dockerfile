# Multi-stage build for optimization
FROM python:3.11-slim AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set up working directory
WORKDIR /app

FROM base AS dependencies

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM dependencies AS final

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/output /app/temp && \
    chown -R appuser:appuser /app

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8888

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8888/ || exit 1

# Set default environment variables
ENV DATABASE_PATH=/app/data/navidrome.db
ENV OUTPUT_DIR=/app/output
ENV DATA_DIR=/app/data
ENV FLASK_ENV=production

# Use entrypoint script
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "app.py"]
