# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Copy dependency file(s) first to leverage Docker layer caching
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY bot.py ./

# Run the bot
CMD ["python", "-u", "bot.py"]