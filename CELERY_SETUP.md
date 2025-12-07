# 🚀 Celery Background Tasks Setup

## Что было добавлено

Celery фоновые задачи для синхронизации с Google Sheets **без блокировки** пользовательского интерфейса!

### Файлы:
- `webapp/backend/tasks.py` - Celery задачи
- `Dockerfile` - Docker образ для приложения
- `docker-compose.yml` - Оркестрация всех сервисов
- `.env.example` - обновлён с Redis настройками

## 📦 Установка (БЕЗ Docker - для разработки)

### 1. Убедитесь что Redis запущен:
```bash
# macOS:
brew services start redis

# Linux:
sudo systemctl start redis

# Проверка:
redis-cli ping  # Должно вывести: PONG
```

### 2. Запустить Celery Worker (в отдельном терминале):
```bash
cd webapp/backend
celery -A tasks worker --loglevel=info
```

Должны увидеть:
```
✅ Celery worker started
📡 Broker: redis://localhost:6379/1
💾 Backend: redis://localhost:6379/2

[tasks]
  . sync_account_to_sheets
  . sync_project_to_sheets
  . periodic_sync_all_projects
```

### 3. Запустить Celery Beat (периодические задачи, в третьем терминале):
```bash
cd webapp/backend
celery -A tasks beat --loglevel=info
```

### 4. Запустить FastAPI (в четвёртом терминале):
```bash
cd webapp/backend
uvicorn main:app --reload
```

### 5. (Опционально) Flower - мониторинг Celery:
```bash
cd webapp/backend
celery -A tasks flower --port=5555
```

Открыть в браузере: http://localhost:5555

## 🐳 Установка (С Docker - рекомендуется для продакшена)

### 1. Создать .env файл:
```bash
cp webapp/backend/.env.example webapp/backend/.env
# Заполнить все переменные окружения
```

### 2. Запустить все сервисы одной командой:
```bash
docker-compose up --build
```

Это запустит:
- ✅ Redis (port 6379)
- ✅ FastAPI API (port 8000)
- ✅ Celery Worker
- ✅ Celery Beat
- ✅ Flower (port 5555)

### 3. Остановить все:
```bash
docker-compose down
```

### 4. Просмотр логов:
```bash
# Все сервисы:
docker-compose logs -f

# Только Celery worker:
docker-compose logs -f celery_worker

# Только API:
docker-compose logs -f api
```

## 🧪 Тестирование фоновых задач

### Тест 1: Синхронизация проекта
```python
from tasks import sync_project_to_sheets

# Запустить задачу в фоне
task = sync_project_to_sheets.delay(
    project_id="123",
    project_name="Test Project",
    accounts_data=[{
        'username': 'testuser',
        'profile_link': 'https://tiktok.com/@testuser',
        'views': 10000,
        'videos': 50,
        'followers': 1000,
        'likes': 5000,
        'comments': 100
    }]
)

# Проверить статус
print(f"Task ID: {task.id}")
print(f"Task State: {task.state}")

# Дождаться результата (блокирует)
result = task.get(timeout=30)
print(f"Result: {result}")
```

### Тест 2: Мониторинг в Flower
1. Открыть http://localhost:5555
2. Перейти на вкладку "Tasks"
3. Запустить задачу через API или напрямую
4. Смотреть выполнение в реальном времени!

### Тест 3: Проверить периодические задачи
Celery Beat автоматически запускает `periodic_sync_all_projects` каждые 10 минут.

Проверить в логах Celery Beat:
```
[2025-01-07 12:00:00] Scheduler: Sending due task sync-all-projects-every-10-minutes
```

## 📊 Как это работает

### Старая схема (БЕЗ Celery):
```
Пользователь нажимает "Добавить аккаунт"
  ↓
FastAPI сохраняет в SQLite (0.1 сек) ✅
  ↓
FastAPI синхронизирует с Google Sheets (5-10 сек) ⏳
  ↓
Пользователь ждёт... 😴
  ↓
Возвращает ответ пользователю
```
**ИТОГО: 5-10 секунд ожидания!**

### Новая схема (С Celery):
```
Пользователь нажимает "Добавить аккаунт"
  ↓
FastAPI сохраняет в SQLite (0.1 сек) ✅
  ↓
FastAPI ставит задачу в очередь Celery (0.01 сек) ✅
  ↓
МГНОВЕННО возвращает ответ пользователю ⚡
  ↓
(В ФОНЕ) Celery Worker синхронизирует с Sheets (5-10 сек) 🔄
  ↓
(Опционально) Уведомление пользователю "Синхронизация завершена!"
```
**ИТОГО: 0.1 секунды ожидания! Ускорение в 50-100x!** 🚀

## 🔧 Конфигурация

### Настройки Celery (в tasks.py):
```python
task_time_limit = 600  # 10 минут макс на задачу
worker_prefetch_multiplier = 1  # Одна задача за раз
worker_max_tasks_per_child = 50  # Перезапуск после 50 задач
```

### Периодические задачи (в tasks.py):
```python
celery_app.conf.beat_schedule = {
    'sync-all-projects-every-10-minutes': {
        'task': 'periodic_sync_all_projects',
        'schedule': 600.0,  # 10 минут
    },
}
```

Изменить частоту:
- `300.0` - каждые 5 минут
- `1800.0` - каждые 30 минут
- `3600.0` - каждый час

## 🐛 Troubleshooting

### Celery worker не запускается:

```
Error: Unable to connect to Redis
```

**Решение:**
1. Проверить что Redis запущен: `redis-cli ping`
2. Проверить .env: `REDIS_HOST=localhost`, `REDIS_PORT=6379`

### Задачи не выполняются:

**Проверить что worker запущен:**
```bash
celery -A tasks inspect active
```

Должно показать активные задачи.

### Задачи висят в очереди:

**Очистить очередь:**
```bash
redis-cli
> FLUSHDB
```

**Или перезапустить worker:**
```bash
# Ctrl+C в терминале worker
celery -A tasks worker --loglevel=info
```

### Flower не подключается:

**Проверить порт:**
```bash
lsof -i :5555
```

**Или изменить порт:**
```bash
celery -A tasks flower --port=5556
```

## 📈 Мониторинг производительности

### Flower Dashboard (http://localhost:5555):
- **Tasks** - все задачи (успешные, failed, в процессе)
- **Workers** - статус workers
- **Broker** - Redis статистика
- **Monitor** - графики в реальном времени

### Логи:
```bash
# Уровень DEBUG для подробных логов:
celery -A tasks worker --loglevel=debug

# Только ошибки:
celery -A tasks worker --loglevel=error
```

## ✅ Чеклист готовности

- [ ] Redis установлен и запущен
- [ ] `pip install -r requirements.txt` выполнен
- [ ] Celery Worker запускается без ошибок
- [ ] Celery Beat запускается без ошибок
- [ ] В логах видно: `✅ Celery tasks imported successfully`
- [ ] Flower доступен на http://localhost:5555
- [ ] Тестовая задача выполняется успешно
- [ ] Периодические задачи запускаются каждые 10 минут

## 🚀 Деплой на Production

### Render (с managed Redis):

1. Добавить Redis addon в Render
2. Добавить Environment Variables:
   ```
   REDIS_HOST=<render-redis-host>
   REDIS_PORT=<render-redis-port>
   REDIS_PASSWORD=<render-redis-password>
   ```

3. Создать два сервиса в Render:
   - **Web Service**: `uvicorn main:app --host 0.0.0.0 --port 8000`
   - **Background Worker**: `celery -A tasks worker --loglevel=info`

### Heroku:

```bash
# Procfile
web: uvicorn main:app --host 0.0.0.0 --port $PORT
worker: celery -A tasks worker --loglevel=info
beat: celery -A tasks beat --loglevel=info
```

```bash
heroku addons:create heroku-redis:mini
git push heroku main
heroku ps:scale worker=1 beat=1
```

---

**Готово! Фоновые задачи настроены и работают!** 🎉

**Следующий шаг:** Протестировать вместе с Redis кэшированием = **100x общее ускорение!** 🚀
