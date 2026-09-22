FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# БД и логи переживают передеплой, только если завязаны на volume.
# Для «честного» 24/7 с SQLite лучше использовать systemd на VPS (deploy/systemd/).
EXPOSE 8080

CMD ["python", "bot.py"]