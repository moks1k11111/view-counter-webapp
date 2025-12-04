# View Counter WebApp

Telegram WebApp для отслеживания просмотров и статистики социальных сетей (TikTok, Instagram, Facebook, YouTube, Threads).

## 📁 Структура проекта

```
view_counter_webapp/
├── webapp/
│   └── backend/
│       ├── main.py                      # Основной FastAPI сервер
│       ├── api.py                       # Дополнительные API endpoints
│       ├── database_sqlite.py           # SQLite база данных
│       ├── project_manager.py           # Управление проектами и аккаунтами
│       ├── project_sheets_manager.py    # Интеграция с Google Sheets
│       └── requirements.txt             # Python зависимости
├── app.js                               # Основной frontend (Telegram WebApp)
├── index.html                           # HTML страница WebApp
├── config.json                          # Конфигурация (Google Sheets credentials)
└── view_counter.db                      # SQLite база данных
```

## 🏗️ Архитектура

### Backend (Python/FastAPI)

**Основные компоненты:**

1. **main.py** - Главный сервер FastAPI
   - API endpoints для проектов, аккаунтов, аналитики
   - Интеграция с Telegram WebApp (валидация initData)
   - Синхронизация с Google Sheets

2. **project_manager.py** - Бизнес-логика
   - CRUD операции для проектов
   - Управление социальными аккаунтами
   - Работа со снапшотами статистики
   - Генерация аналитики

3. **project_sheets_manager.py** - Google Sheets
   - Создание листов для проектов
   - Синхронизация аккаунтов
   - Обновление статистики
   - Используется как Master DB

4. **database_sqlite.py** - SQLite ORM
   - Управление таблицами
   - Миграции схемы
   - Кэширование данных из Sheets

### Frontend (Vanilla JS)

**app.js** - Single Page Application:
- Telegram WebApp интеграция
- Роли: Admin / User
- Разделы: Главная, Проекты, Аналитика, Профиль
- Режимы просмотра: Admin mode / User mode

## 🗄️ База данных

### SQLite таблицы

#### `projects`
```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    google_sheet_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    target_views INTEGER DEFAULT 0,
    geo TEXT DEFAULT "",
    kpi_views INTEGER DEFAULT 1000,
    created_at TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    is_finished BOOLEAN DEFAULT 0,
    allowed_platforms TEXT  -- JSON: {"tiktok": true, "instagram": true, ...}
)
```

#### `project_users`
```sql
CREATE TABLE project_users (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE(project_id, user_id)
)
```

#### `project_social_accounts`
```sql
CREATE TABLE project_social_accounts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    platform TEXT NOT NULL,  -- tiktok/instagram/facebook/youtube/threads
    username TEXT NOT NULL,
    profile_link TEXT NOT NULL,
    status TEXT DEFAULT 'NEW',  -- NEW/OLD/Ban
    topic TEXT DEFAULT '',
    telegram_user TEXT DEFAULT '',  -- Кто добавил аккаунт
    added_at TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    UNIQUE(project_id, profile_link)  -- Уникальность по ссылке, не по username!
)
```

#### `account_snapshots`
```sql
CREATE TABLE account_snapshots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    followers INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    videos INTEGER DEFAULT 0,
    views INTEGER DEFAULT 0,
    snapshot_time TEXT NOT NULL
)
```

#### `account_daily_stats`
```sql
CREATE TABLE account_daily_stats (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    followers_start INTEGER,
    followers_end INTEGER,
    followers_growth INTEGER,
    likes_start INTEGER,
    likes_end INTEGER,
    likes_growth INTEGER,
    videos_start INTEGER,
    videos_end INTEGER,
    videos_growth INTEGER,
    views_start INTEGER,
    views_end INTEGER,
    views_growth INTEGER,
    UNIQUE(account_id, date)
)
```

#### `user_context`
```sql
CREATE TABLE user_context (
    user_id TEXT PRIMARY KEY,
    current_project_id TEXT,
    last_updated TEXT NOT NULL
)
```

### Google Sheets структура

Каждый проект = отдельный лист со структурой:

| @Username | Link | Platform | Username | Followers | Likes | Following | Videos | Views | Last Update | Status | Тематика |
|-----------|------|----------|----------|-----------|-------|-----------|--------|-------|-------------|--------|----------|

**Колонки:**
- **@Username** - Telegram username пользователя (кто добавил аккаунт)
- **Link** - URL профиля соц сети
- **Platform** - Платформа (tiktok/instagram/facebook/youtube/threads)
- **Username** - Username соц сети (парсится из Link)
- **Followers/Likes/Following/Videos/Views** - Метрики
- **Last Update** - Дата последнего обновления
- **Status** - Статус аккаунта (NEW/OLD/Ban)
- **Тематика** - Категория контента

**Google Sheets как Master DB:**
- Основной источник данных для аналитики
- SQLite используется как кэш и для истории
- При добавлении аккаунта пишется в оба места
- Username парсится из URL автоматически

## 🔑 API Endpoints

### Проекты

- `GET /api/projects` - Получить все проекты
- `POST /api/projects` - Создать проект
- `GET /api/projects/{id}` - Получить проект
- `PUT /api/projects/{id}` - Обновить проект
- `DELETE /api/projects/{id}` - Удалить проект (admin only)
- `POST /api/projects/{id}/set_current` - Установить текущий проект
- `POST /api/projects/{id}/finish` - Завершить проект
- `POST /api/projects/{id}/add_user` - Добавить пользователя в проект
- `POST /api/projects/{id}/remove_user` - Удалить пользователя из проекта

### Аккаунты

- `GET /api/projects/{id}/accounts` - Получить аккаунты проекта (с метриками)
- `POST /api/projects/{id}/add_account` - Добавить аккаунт
- `DELETE /api/projects/{project_id}/accounts/{account_id}` - Удалить аккаунт
- `POST /api/projects/{id}/import_from_sheets` - Импорт из Google Sheets
- `POST /api/projects/{id}/migrate_platform_column` - Миграция: добавить колонку Platform
- `POST /api/projects/{id}/migrate_username_column` - Миграция: добавить колонку Username

### Аналитика

- `GET /api/projects/{id}/analytics` - Аналитика проекта (admin/user)
- `GET /api/my-analytics` - Личная аналитика пользователя
- `POST /api/account_snapshots` - Добавить снапшот

### Пользователи

- `GET /api/me` - Информация о текущем пользователе

## 🎨 Frontend структура

### Глобальные переменные

```javascript
let currentUser = null;           // Telegram user объект
let currentProjectId = null;      // ID текущего проекта
let currentProjectMode = 'user';  // 'user' или 'admin'
const ADMIN_IDS = [1234567890];   // Telegram IDs администраторов
```

### Основные функции

**Навигация:**
- `showSection(sectionName)` - Показать раздел
- `initSwiper()` - Инициализация свайпера для графиков

**Проекты:**
- `loadProjects()` - Загрузка списка проектов
- `setCurrentProject(projectId)` - Установить текущий проект
- `createProject(data)` - Создать новый проект
- `finishProject(projectId)` - Завершить проект

**Аккаунты:**
- `loadProjectSocialAccounts(projectId, mode)` - Загрузка аккаунтов
- `renderProjectSocialAccountsList(accounts, mode)` - Рендер списка
- `addSocialAccountToProject(data)` - Добавить аккаунт
- `deleteSocialAccount(accountId)` - Удалить аккаунт

**Аналитика:**
- `loadAnalytics(projectId)` - Загрузка аналитики
- `renderAllCharts(analytics)` - Рендер всех графиков
- `createDailyChart(history)` - График просмотров по дням
- `createPlatformsChart(platformStats)` - Распределение по платформам
- `createProfilesChart(profiles)` - Топ-10 аккаунтов
- `createTopicsChart(topicStats)` - Распределение по тематикам

## 🔐 Авторизация

**Telegram WebApp initData:**
```javascript
window.Telegram.WebApp.initData
```

Отправляется в заголовке:
```
X-Telegram-Init-Data: <initData>
```

Backend валидация:
```python
def validate_telegram_init_data(init_data: str) -> dict:
    # Проверка подписи HMAC-SHA256
    # Возвращает user объект
```

## 🎯 Роли и права

### Admin
- Видит все проекты
- Может добавлять/удалять пользователей
- Может удалять любые аккаунты
- Видит статистику всех пользователей

### User
- Видит только свои проекты
- Видит только свои аккаунты в проекте
- Может добавлять аккаунты
- Не может удалять аккаунты (кнопка скрыта)
- Видит только свою статистику

Проверка роли:
```javascript
const isAdmin = currentUser && ADMIN_IDS.includes(currentUser.id);
```

## 📊 Логика определения платформы

**По URL (case-insensitive):**
```javascript
if (url.includes('tiktok.com')) -> 'tiktok'
if (url.includes('instagram.com')) -> 'instagram'
if (url.includes('facebook.com') || url.includes('fb.com')) -> 'facebook'
if (url.includes('youtube.com') || url.includes('youtu.be')) -> 'youtube'
if (url.includes('threads.net')) -> 'threads'
default -> 'tiktok'
```

**Извлечение username:**
- TikTok/Instagram/YouTube: `/@username`
- Facebook: `/share/ID` или последняя часть URL

## 🚀 Запуск проекта

### Требования

- Python 3.8+
- Node.js (для разработки)
- Google Cloud Project с включенным Google Sheets API

### Backend

```bash
cd webapp/backend
pip install -r requirements.txt

# Создать config.json с credentials от Google Sheets
python main.py
```

Переменные окружения:
```
TELEGRAM_TOKEN=<bot_token>
ADMIN_IDS=<comma_separated_ids>
```

### Frontend

Просто открыть `index.html` или развернуть на статическом хостинге.

**Для Telegram WebApp:**
1. Создать бота через @BotFather
2. Установить Web App URL: `/setmenubutton` -> WebApp URL
3. URL должен вести на `index.html`

## 🔄 Workflow добавления аккаунта

1. User нажимает "Добавить аккаунт" в WebApp
2. Заполняет форму: Platform, Username, Link, Status, Topic
3. Frontend отправляет `POST /api/projects/{id}/add_account`
4. Backend:
   - Определяет платформу по URL
   - Извлекает username из URL
   - Сохраняет в SQLite с `telegram_user`
   - Добавляет строку в Google Sheets с Platform
5. Frontend обновляет список аккаунтов

## 📈 Аналитика

### Метрики проекта

```javascript
{
  "total_views": 1234567,
  "total_videos": 123,
  "total_profiles": 8,
  "target_views": 5000000,
  "progress_percent": 24.69,
  "growth_24h": 0,  // Требует исторических данных
  "platform_stats": {
    "tiktok": 900000,
    "instagram": 0,
    "facebook": 334567,
    "youtube": 0,
    "threads": 0
  },
  "topic_stats": {
    "Познавательное": 500000,
    "Гемблинг": 734567
  },
  "history": [
    {"date": "2025-12-04", "views": 1234567}
  ],
  "profiles": [...] // Для топ-10
}
```

### История (требует доработки)

**Текущая проблема:**
- `growth_24h` всегда 0
- `history` содержит только текущую точку

**Решение:**
Нужен cron job который каждый день:
1. Читает Google Sheets
2. Сохраняет snapshot в `account_daily_stats`
3. Рассчитывает прирост за 24 часа

## 🐛 Известные проблемы

1. **Платформы показывают только TikTok**
   - ✅ ИСПРАВЛЕНО: Добавлена колонка Platform в Google Sheets
   - Для старых проектов: запустить `/api/projects/{id}/migrate_platform_column`

2. **Unknown usernames в аналитике**
   - ✅ ИСПРАВЛЕНО: Добавлена колонка Username в Google Sheets
   - Для старых проектов: запустить `/api/projects/{id}/migrate_username_column`
   - Username теперь парсится из URL при добавлении аккаунта

3. **Instagram usernames не извлекались**
   - ✅ ИСПРАВЛЕНО: Улучшен парсинг для instagram.com/username/
   - Поддержка всех платформ: TikTok, Instagram, Facebook, YouTube, Threads

4. **История и прирост 24ч**
   - ❌ НЕ РЕАЛИЗОВАНО: Требуется daily cron job

## 🔧 Конфигурация

### config.json (Google Sheets)

```json
{
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "...@....iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "spreadsheet_id": "your_spreadsheet_id"
}
```

### Переменные окружения

```bash
# .env
TELEGRAM_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_IDS=123456789,987654321
PORT=8000
```

## 📝 TODO / Улучшения

- [ ] Добавить daily cron для сохранения истории
- [ ] Улучшить парсинг Facebook URLs
- [ ] Добавить экспорт аналитики в CSV/Excel
- [ ] Webhook от Telegram для уведомлений
- [ ] Графики с zoom и детализацией
- [ ] Сравнение проектов
- [ ] Мобильная оптимизация
- [ ] Dark/Light theme

## 🤝 Contributing

При разработке учитывать:
1. **Google Sheets как Master DB** - основной источник данных
2. **SQLite как кэш** - для быстрого доступа и истории
3. **Telegram WebApp** - использовать стандарты TG WebApp API
4. **Роли Admin/User** - проверять права на backend и frontend
5. **Platform detection** - всегда из URL, колонка Platform в Sheets

## 📄 License

Private project - All rights reserved
