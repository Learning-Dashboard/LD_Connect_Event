# Use a lightweight Python base image
FROM python:3.10-slim

# Create and use the /app directory
WORKDIR /app

# Copy your requirements.txt in first so Docker can cache the pip install layer
COPY requirements.txt .

# Install your dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code into the container
COPY . .

# Expose port 5000 for your Flask/Gunicorn app to listen on
EXPOSE 5000

# Run gunicorn for  "app:create_app()" factory function
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:create_app()"]
