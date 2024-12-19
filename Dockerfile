# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install tzdata to configure timezone
RUN apt-get update && apt-get install -y tzdata

# Set the time zone (e.g., America/New_York)
ENV TZ=America/New_York

# Reconfigure the time zone
RUN ln -sf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install system dependencies for tkinter
RUN apt-get update && apt-get install -y \
    python3-tk \
    libx11-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the application port
EXPOSE 80

# Run the Python script
CMD ["python", "dynamiXHeadless.py"]
