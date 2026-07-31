# docker-compose up

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Poetry
RUN pip install poetry

# cache our requirements
COPY poetry.lock pyproject.toml ./

# Docker is already isolated
RUN poetry config virtualenvs.create false 

RUN poetry install --no-root

# Copy application code
COPY . .

# Expose API port
EXPOSE 5000

CMD ["python", "main.py"]