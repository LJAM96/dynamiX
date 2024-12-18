# Use an official Python runtime as a parent image
FROM python:3.8


# Install required tools and libraries
RUN apt-get update && apt-get install -y \
    xvfb \
    python3-tk \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container
COPY . .

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Define the default command to run the application
CMD ["xvfb-run", "-a", "python", "dynamiXMain.py"]
