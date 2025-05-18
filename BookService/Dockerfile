# Use an official Python runtime as a base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the application files into the container
COPY . /app

# Install the required dependencies
RUN pip install -r requirements.txt

# Expose port 5006
EXPOSE 5006

# Command to run the service
CMD ["python", "main.py"]
