# API 서버 이미지. 빌드는 BASEON 폴더에서: docker compose build api
FROM python:3.11-slim

WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY shared shared
RUN pip install --no-cache-dir ./shared
COPY backend backend

WORKDIR /srv/backend
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
