# Stage 1: Builder
FROM python:3.10.6-slim AS builder

WORKDIR /home/app

# Copy only the requirements file to leverage Docker cache more effectively
COPY requirements.txt .

# Install the dependencies in a virtual environment to keep the build clean
RUN python3 -m venv /venv && \
    /venv/bin/pip install --upgrade pip && \
    /venv/bin/pip install -r requirements.txt --progress-bar off

# Stage 2: Final Image
FROM python:3.10.6-slim

WORKDIR /home/app

# Copy the virtual environment from the builder stage
COPY --from=builder /venv /venv

# Copy only the necessary application files
COPY ./src /home/app/src
COPY ./models /home/app/models
COPY ./Datasets /home/app/Datasets

# Ensure the virtual environment's binaries are used
ENV PATH="/venv/bin:$PATH"

EXPOSE 8568

WORKDIR /home/app/src

CMD ["python3", "deploy_app.py"]
