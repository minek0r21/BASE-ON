# 적재 스크립트 이미지. 실행은 BASEON 폴더에서: docker compose run --rm etl etl/<스크립트> [옵션]
FROM python:3.11-slim

WORKDIR /srv
COPY etl/requirements.txt etl/requirements.txt
RUN pip install --no-cache-dir -r etl/requirements.txt
COPY shared shared
RUN pip install --no-cache-dir ./shared
COPY etl etl

ENTRYPOINT ["python"]
CMD ["etl/03_check.py"]
