FROM python:3.12-slim

WORKDIR /app/build

RUN pip install poetry==1.6.1

WORKDIR /app

RUN poetry config virtualenvs.create false

COPY [ "poetry.toml", "poetry.lock", "pyproject.toml", "./" ]

RUN poetry install --only main

COPY bot/ bot/
COPY main.py main.py

ENV PYTHONUNBUFFERED=1
ENTRYPOINT [ "python", "main.py" ]
