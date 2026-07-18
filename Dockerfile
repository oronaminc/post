# 선택: 컨테이너로 실행하고 싶을 때
FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 (레이어 캐시)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# config.yaml 의 server.host 를 0.0.0.0 으로 바꾸거나 아래처럼 직접 지정
ENV APP_CONFIG=/app/config.yaml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
