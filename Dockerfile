FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies that might be needed for python-whois
RUN apt-get update && apt-get install -y \
    whois \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY domain_monitor.py .
COPY src/ ./src/
COPY utils/ ./utils/

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data

# Copy example config
COPY config.yaml.example .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command - show help
CMD ["python", "domain_monitor.py", "--help"]