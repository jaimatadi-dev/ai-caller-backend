FROM python:3.11-slim

# Prevent Python from writing pyc files to disk and ensure output is unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies including espeak-ng
RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Ensure the output directory for audio exists
RUN mkdir -p audio_files

# Expose Render's default web service port
EXPOSE 10000

# Command to run the application
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
