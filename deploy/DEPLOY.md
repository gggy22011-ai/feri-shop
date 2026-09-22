# Развёртывание Feri_shop на свободном сервере (24/7, работает и при выключенном ПК)

Рекомендуемый вариант: **Oracle Cloud Always Free** — бесплатный VPS навсегда.
SQLite и поллинг работают нормально: у VPS есть настоящий диск, в отличие от
бесплатных Render/Railway (там БД стирается при рестарте и инстанс «засыпает»).

В проекте два сервиса: **бот** (polling) и **сайт** (каталог + документы +
проверка покупок) — оба читают одну и ту же `bot.db`.

## 1. Получить сервер (бесплатно, ~15 минут)

1. https://cloud.oracle.com → Sign Up (нужна карта только для верификации, не списывают).
2. Создать Compute → VM (Always Free: 1 OCPU ARM + 1 GB RAM — достаточно).
   - Ubuntu 24.04.
   - Скачать SSH-ключ.
3. В Security List открыть **порт 80** (для сайта). Для бота открывать ничего не нужно —
   он ходит в Telegram исходящими запросами.

Запомни: IP сервера и путь к ключу `key.pem`.

## 2. Скопировать проект на сервер

Выполнять на **своём ПК** (замени IP):

```bash
scp -i key.pem -r "C:\Users\Admin\Documents\Default Project\feri_shop" ubuntu@IP:/opt/feri_shop
```

## 3. Настроить на сервере

```bash
ssh -i key.pem ubuntu@IP
sudo apt update && sudo apt install -y python3-venv
cd /opt/feri_shop
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# отредактировать .env (токен, ADMIN_IDS, каналы, пароль админки)
nano .env

# системный юзер (если не существует)
sudo useradd -r -m -d /opt/feri_shop feri 2>/dev/null || true
sudo chown -R feri:feri /opt/feri_shop

# бот
sudo cp deploy/systemd/feri-shop.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now feri-shop
sudo systemctl status feri-shop

# сайт на 127.0.0.1:8000 + nginx наружу
sudo cp deploy/systemd/feri-web.service /etc/systemd/system/
sudo systemctl enable --now feri-web
sudo apt install -y nginx
sudo tee /etc/nginx/sites-available/feri > /dev/null <<'NGX'
server {
    listen 80;
    server_name _;
    location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
}
NGX
sudo ln -sf /etc/nginx/sites-available/feri /etc/nginx/sites-enabled/feri
sudo nginx -t && sudo systemctl reload nginx
```

Логи бота: `journalctl -u feri-shop -f` · сайта: `journalctl -u feri-web -f`
Сайт откроется по http://IP (каталог, как купить, FAQ, поддержка,
пользовательское соглашение, политика конфиденциальности, проверка покупок).

## Проверка

- Бот должен быть **админом обоих каналов** (иначе гейт блокирует всех пользователей).
- После запуска в консоли/журнале будет видно «🚨 Бот НЕ админ канала …», если прав не хватает.

## Альтернатива: Docker (если есть свой VPS с docker)

```bash
cd /opt/feri_shop
sudo docker build -t feri-shop -f deploy/Dockerfile .
# пробросить volume для SQLite, иначе БД эфемерная:
sudo docker run -d --name feri-shop --restart always \
  -v /opt/feri_shop/data:/app \
  -e BOT_TOKEN=... -e ADMIN_IDS=... -e ADMIN_PASSWORD=... feri-shop
```

## Важно про «ПК выключен»

Бот ходит в Telegram **исходящими** запросами. Ему не нужен открытый порт/белый IP —
нужен только интернет. Пока запущен сервер (systemd перезапускает при падении) —
бот живёт 24/7 независимо от твоего ПК.