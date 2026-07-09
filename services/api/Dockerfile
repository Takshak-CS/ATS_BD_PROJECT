FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/api /app/services/api

RUN python -m pip install --upgrade pip \
    && python -m pip install /app/services/api

EXPOSE 8000

CMD ["python", "-m", "ats_api", "--host", "0.0.0.0", "--port", "8000"]
