FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# Set work directory
WORKDIR /app

# Ensure Playwright knows where to find browsers in this official image
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure data directory exists and is writable
RUN mkdir -p /app/data && chmod -R 777 /app/data

# Start the application using gunicorn with uvicorn workers for production stability
CMD ["sh", "-c", "gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app --bind 0.0.0.0:${PORT:-8000} --timeout 120"]
