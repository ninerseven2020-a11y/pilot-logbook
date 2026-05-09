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

# Railway uses PORT env var
ENV PORT=8000
EXPOSE 8000

# Start the application using sh -c to expand PORT
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
