# Email Farm - Примеры использования

## 📥 Массовая загрузка почт (Admin)

### Формат данных

Подготовь файл с почтами в формате:
```
email:password:proxy
```

Пример `emails.txt`:
```
account1@outlook.com:Pass123!:socks5://user:pass@192.168.1.1:1080
account2@outlook.com:Pass456!:socks5://user:pass@192.168.1.2:1080
account3@outlook.com:Pass789!:
```

### Python скрипт для загрузки

```python
import requests
import json

# Конфигурация
API_URL = "https://your-render-app.onrender.com"
TELEGRAM_INIT_DATA = "your_telegram_init_data_here"  # Получи из WebApp

# Читаем файл с почтами
accounts = []
with open('emails.txt', 'r') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        parts = line.split(':')
        email = parts[0]
        password = parts[1]
        proxy = parts[2] if len(parts) > 2 and parts[2] else None

        accounts.append({
            "email": email,
            "password": password,
            "proxy": proxy
        })

# Отправляем на сервер
response = requests.post(
    f"{API_URL}/api/admin/emails/bulk_upload",
    headers={
        "x-telegram-init-data": TELEGRAM_INIT_DATA,
        "Content-Type": "application/json"
    },
    json={"accounts": accounts}
)

result = response.json()
print(f"✅ Успешно: {result['success']}")
print(f"❌ Ошибок: {result['failed']}")
if result['errors']:
    print("\nОшибки:")
    for error in result['errors']:
        print(f"  - {error}")
```

## 👤 Использование (User)

### 1. Получить список моих почт

```python
import requests

API_URL = "https://your-render-app.onrender.com"
TELEGRAM_INIT_DATA = "..."

response = requests.get(
    f"{API_URL}/api/emails/my_list",
    headers={"x-telegram-init-data": TELEGRAM_INIT_DATA}
)

data = response.json()
print(f"У меня {len(data['emails'])} почт")
print(f"Лимит: {data['limit']['max_active_emails']}")

for email in data['emails']:
    print(f"  📧 {email['email']} - {email['status']}")
```

### 2. Взять новую почту

```python
response = requests.post(
    f"{API_URL}/api/emails/allocate",
    headers={"x-telegram-init-data": TELEGRAM_INIT_DATA}
)

if response.status_code == 200:
    data = response.json()
    print(f"✅ Получил почту: {data['email']}")
    print(f"Email ID: {data['email_id']}")
    print(f"Активных: {data['active_count']}/{data['max_allowed']}")
else:
    print(f"❌ Ошибка: {response.json()['detail']}")
```

### 3. Проверить код в почте

```python
email_id = 1  # ID почты из предыдущего шага

response = requests.post(
    f"{API_URL}/api/emails/{email_id}/check_code",
    headers={"x-telegram-init-data": TELEGRAM_INIT_DATA}
)

data = response.json()

if data.get('is_safe'):
    print(f"✅ Письмо безопасно")
    print(f"📋 Код: {data['verification_code']}")
    print(f"📨 Тема: {data['subject']}")
    print(f"👤 От: {data['from']}")
else:
    print(f"⚠️ ВНИМАНИЕ! Подозрительное письмо!")
    print(f"Причина: {data['reason']}")
    print(f"Тема: {data['subject']}")
    print("🚨 Алерт отправлен администраторам")
```

### 4. Пометить почту как забаненную

```python
email_id = 1

response = requests.post(
    f"{API_URL}/api/emails/{email_id}/mark_banned",
    headers={"x-telegram-init-data": TELEGRAM_INIT_DATA}
)

if response.status_code == 200:
    print("✅ Почта помечена как забаненная")
```

## 🔧 Admin функции

### Установить лимит пользователю

```python
response = requests.post(
    f"{API_URL}/api/admin/emails/set_limit",
    headers={
        "x-telegram-init-data": TELEGRAM_INIT_DATA,
        "Content-Type": "application/json"
    },
    json={
        "user_id": 123456789,  # Telegram ID пользователя
        "max_emails": 10,       # Максимум активных почт
        "can_access": True      # Разрешить доступ
    }
)

print(response.json())
```

### Получить статистику

```python
response = requests.get(
    f"{API_URL}/api/admin/emails/stats",
    headers={"x-telegram-init-data": TELEGRAM_INIT_DATA}
)

stats = response.json()
print(f"📊 Статистика Email Farm:")
print(f"  Всего почт: {stats['total_emails']}")
print(f"  Свободных: {stats['free']}")
print(f"  Активных: {stats['active']}")
print(f"  Забанено: {stats['banned']}")
print(f"  Пользователей с доступом: {stats['users_with_access']}")
```

## 🔒 Безопасность - Что блокирует фильтр

Фильтр автоматически определяет попытки кражи аккаунта:

**Блокируется (EN):**
- change email, change e-mail
- reset password, change password
- unlink account, remove account
- verify new email, confirm new email
- primary email changed

**Блокируется (RU):**
- смена почты, изменить почту
- сброс пароля, смена пароля
- отвязать, удалить аккаунт
- новая почта, резервная почта

**Блокируется (UA):**
- зміна пошти, змінити пошту
- скидання паролю, зміна паролю
- відв'язати, видалити акаунт

При обнаружении этих фраз:
1. ❌ Код НЕ возвращается пользователю
2. 🚨 Алерт отправляется в LOG_CHANNEL_ID
3. 📝 Действие логируется в базу

## 📱 Интеграция в Telegram WebApp

```javascript
// В твоем frontend (Telegram WebApp)

// Получить init data
const initData = window.Telegram.WebApp.initData;

// Запрос к API
async function allocateEmail() {
    const response = await fetch('https://your-app.onrender.com/api/emails/allocate', {
        method: 'POST',
        headers: {
            'x-telegram-init-data': initData
        }
    });

    const data = await response.json();

    if (response.ok) {
        console.log('Получена почта:', data.email);
        return data;
    } else {
        console.error('Ошибка:', data.detail);
    }
}

// Проверить код
async function checkCode(emailId) {
    const response = await fetch(`https://your-app.onrender.com/api/emails/${emailId}/check_code`, {
        method: 'POST',
        headers: {
            'x-telegram-init-data': initData
        }
    });

    const data = await response.json();

    if (data.is_safe && data.verification_code) {
        alert(`Код: ${data.verification_code}`);
    } else {
        alert('Подозрительное письмо! Проверь с админом.');
    }
}
```

## 🧪 Тестирование локально

Перед деплоем на Render можно протестировать локально:

1. Создай `.env`:
```bash
DB_ENCRYPTION_KEY=ваш_сгенерированный_ключ
LOG_CHANNEL_ID=-1001234567890
TELEGRAM_TOKEN=ваш_токен
```

2. Запусти:
```bash
cd webapp/backend
uvicorn main:app --reload
```

3. Тестируй через Postman:
- `http://localhost:8000/api/admin/emails/upload`
- `http://localhost:8000/api/emails/allocate`

---

✅ Все готово к использованию!
