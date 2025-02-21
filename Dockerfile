# Use an official Python runtime as a parent image
FROM python:3.10

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app/

# Install required Python packages
RUN pip install -r requirements.txt

# Set environment variables
ENV PORT=8080

# Expose the port
EXPOSE 8080

# Command to run the bot
CMD ["python", "bot.py"]
