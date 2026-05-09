# Use the official Playwright image for Python
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure /tmp is used for temp files
ENV TMPDIR=/tmp

# Railway uses PORT env var
EXPOSE 8000

# Start the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
