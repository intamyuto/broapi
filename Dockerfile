# Use an official Python runtime as a parent image
FROM python:3.12-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies and Python dependencies
COPY requirements.txt /app/
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

FROM python:3.12-slim AS runner

WORKDIR /app

# Install system dependencies and Python dependencies
COPY --from=builder /app/wheels /app/wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir /app/wheels/* \
    && pip install --no-cache-dir uvicorn

# Copy project
COPY . /app/

# Expose the port the app runs in
EXPOSE 8001

# Define the command to start the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]