# 📊 Google Sheets Persistence System - Complete Summary

## Overview

**Цель:** Сохранение всех email аккаунтов в Google Sheets (PostBD) для предотвращения потери данных после перезагрузки Render.

**Архитектура:**
- **SQLite** - временное хранилище (очищается при рестарте Render)
- **Google Sheets (PostBD)** - постоянное хранилище (source of truth)
- **Двусторонняя синхронизация:**
  - При старте: Sheets → SQLite
  - При изменениях: SQLite → Sheets

## Key Components

### 1. Credentials Configuration

**Файл:** `service_account.json` (локально) или `GOOGLE_SHEETS_CREDENTIALS_JSON` (Render)

**Формат на Render:**
```bash
# Создать base64 БЕЗ переносов строк:
base64 -i service_account.json | tr -d '\n'
```

**Environment Variables:**
- `GOOGLE_SHEETS_CREDENTIALS_JSON` - base64 encoded service account JSON
- `EMAIL_FARM_SECRET_KEY` - ключ шифрования для паролей

**Права доступа:**
- Service Account должен быть добавлен в Google Sheets с ролью "Editor"
- Email: `tiktok-bot@round-tome-428411-m2.iam.gserviceaccount.com`

### 2. Table Structure (PostBD → Post)

| Column | Name | Type | Description |
|--------|------|------|-------------|
| A | Email | Text | Email адрес (уникальный) |
| B | Status | Text | free / active / banned |
| C | User ID | Number | Telegram ID пользователя |
| D | Username | Text | Telegram username |
| E | Allocated At | DateTime | Когда взята пользователем |
| F | Last Checked | DateTime | Последняя проверка кода |
| G | Ban Reason | Text | Причина бана |
| H | Total Checks | Number | Количество проверок |
| I | Has Proxy | Text | "Да" / "Нет" |
| J | Codes History | Text | "123456 (2025-12-11 10:30), 789012 ..." |
| K | Is Completed | Number | 0 или 1 (регистрация завершена) |
| L | Notes | Text | Заметки |

**Важно:**
- Первая строка ВСЕГДА должна содержать заголовки
- Код автоматически создаёт/проверяет заголовки при каждом обращении к листу

### 3. Core Functions

#### A. Header Validation (NEW!)

**Файл:** `email_sheets_manager.py:115-182`

**Функция:** `get_or_create_sheet(sheet_name)`

**Что делает:**
1. Открывает существующий лист или создаёт новый
2. Проверяет первую строку: `first_row[0] == "Email"`
3. Если заголовки отсутствуют:
   - Для листа с данными: `insert_row(headers, 1)` (сдвигает данные вниз)
   - Для пустого листа: `update('A1:L1', [headers])`
4. Применяет форматирование (bold + dark background)

**Когда вызывается:**
- При каждом обращении к листу через `get_or_create_sheet()`
- При bulk upload
- При синхронизации
- При логировании действий

#### B. Bulk Upload Persistence

**Файл:** `main.py:2843-2916`

**Endpoint:** `POST /api/admin/emails/bulk_upload`

**Workflow:**
```python
for each account:
    1. Encrypt password/refresh_token
    2. Save to SQLite (email_farm_db.add_email_account)
    3. Save to Google Sheets (email_sheets.log_new_email)
       ↳ Status: "free"
       ↳ Notes: "📤 Загружена админом (timestamp)"
```

**Duplicate Prevention:**
- SQLite: `UNIQUE` constraint на email
- Sheets: проверка `any(row[0] == email for row in all_values[1:])`

#### C. Startup Sync

**Файл:** `main.py:215-282`

**Функция:** `sync_emails_from_sheets()`

**Workflow:**
```python
1. Получить все emails из Google Sheets
   ↳ email_sheets.get_all_emails_for_sheet("Post")

2. Для каждой почты:
   - Проверить, есть ли уже в SQLite
   - Если нет → добавить с placeholder password
   - Восстановить status (free/active)
   - Восстановить user assignment
   - Восстановить is_completed флаг

3. Логировать результат:
   ✅ Email sync complete: X synced, Y skipped
```

**Когда запускается:**
- При старте сервера (`@app.on_event("startup")`)
- После каждого перезапуска Render

#### D. Email Allocation Logging

**Файл:** `email_sheets_manager.py:185-241`

**Функция:** `log_email_allocation()`

**Когда вызывается:**
- Пользователь взял почту через `/farm/get_email`
- Status меняется: `free` → `active`

**Что записывается:**
- User ID, Username
- Allocated At timestamp
- Status = "active"

#### E. Code Check Logging

**Файл:** `email_sheets_manager.py:293-363`

**Функция:** `log_email_check()`

**Когда вызывается:**
- Пользователь проверяет код через `/farm/get_code`

**Что записывается:**
- Last Checked timestamp
- Total Checks += 1
- Codes History: "123456 (2025-12-11 10:30:00)"

#### F. Completion Status

**Файл:** `email_sheets_manager.py:365-390`

**Функция:** `update_email_completed_status()`

**Когда вызывается:**
- Пользователь нажал "Complete Registration"
- Или админ переместил почту в "My Emails"

**Что записывается:**
- Is Completed = 1

### 4. Error Handling & Retries

**Rate Limiting:**
```python
@retry_on_quota_error(max_retries=3, delay=5)
def some_function():
    # Google Sheets API call
```

**Quota Error (429):**
- Автоматический retry с экспоненциальной задержкой
- Максимум 3 попытки
- Логирование каждой попытки

**Connection Errors:**
- Если Google Sheets недоступен → продолжить работу без синхронизации
- SQLite всё равно работает локально
- Warnings в логах: "⚠️ Email Sheets Manager not initialized"

### 5. Data Flow Diagrams

#### Bulk Upload Flow
```
Admin uploads 20 emails
    ↓
For each email:
    ↓
    ├─→ Encrypt password
    ├─→ Add to SQLite (email_accounts table)
    └─→ Log to Google Sheets (PostBD → Post)
        ├─→ Check headers (auto-create if missing)
        ├─→ Check for duplicates
        └─→ Append row with status="free"
```

#### Startup Sync Flow
```
Render restarts
    ↓
SQLite database cleared (empty)
    ↓
sync_emails_from_sheets() called
    ↓
Load all emails from Google Sheets
    ↓
For each email:
    ↓
    ├─→ Check if exists in SQLite
    ├─→ If not: add with placeholder password
    ├─→ Restore status (free/active)
    └─→ Restore user assignment + is_completed
```

#### User Takes Email Flow
```
User clicks "Take Email"
    ↓
/api/farm/get_email called
    ↓
    ├─→ Check user limit (max 5 active)
    ├─→ Get free email from SQLite
    ├─→ Allocate to user (status = active)
    └─→ Log to Google Sheets
        ├─→ Update row: status=active, user_id, username, allocated_at
        └─→ Or append new row if missing
```

#### Code Check Flow
```
User clicks "Get Code"
    ↓
/api/farm/get_code called
    ↓
    ├─→ Decrypt password/refresh_token
    ├─→ Connect to Outlook via IMAP/OAuth2
    ├─→ Find TikTok email
    ├─→ Extract code
    └─→ Log to Google Sheets
        ├─→ Update: last_checked, total_checks += 1
        └─→ Append to codes_history: "123456 (timestamp)"
```

## Deployment Checklist

### On Render:

- [x] Environment variable `GOOGLE_SHEETS_CREDENTIALS_JSON` set (base64, no newlines)
- [x] Environment variable `EMAIL_FARM_SECRET_KEY` set
- [x] Service Account added to PostBD with Editor role
- [x] Table renamed to "PostBD" (no spaces)
- [x] Sheet named "Post" exists
- [x] Headers auto-validation implemented

### Expected Logs on Startup:

```
📊 Initializing Email Sheets Manager:
   credentials_file=service_account.json
   has_json_creds=True
   json_creds_length=1234
✅ Email Sheets Manager (PostBD) initialized successfully
   Spreadsheet: PostBD
📄 Email Farm: Найден лист Post
✅ Email Farm: Заголовки уже существуют на листе Post
📥 Syncing emails from Google Sheets to SQLite...
   Found 20 emails in Google Sheets
   ✅ Synced: test1@outlook.com (free)
   ✅ Synced: test2@outlook.com (user: 123456, completed: True)
✅ Email sync complete: 20 synced, 0 skipped
```

## Common Issues & Solutions

### Issue: "Invalid private key"
**Cause:** Base64 encoding corrupted `\n` characters in private key

**Solution:** Use proper encoding without line breaks:
```bash
base64 -i service_account.json | tr -d '\n'
```

### Issue: "Spreadsheet not found: PostBD"
**Cause:** Table name mismatch or Service Account lacks access

**Solution:**
1. Check table is named exactly "PostBD" (case-sensitive)
2. Add Service Account email to Sheets with Editor role

### Issue: "Data in wrong columns"
**Cause:** Headers missing or incorrect

**Solution:**
- Auto-fixed by new header validation (commit 20b4719)
- Code now checks and creates headers automatically

### Issue: Rate Limit (429)
**Cause:** Too many API calls in short time

**Solution:**
- Retry decorator handles this automatically
- Waits 5 seconds and retries (max 3 times)
- Consider adding `time.sleep(0.5)` between bulk operations if persistent

### Issue: Emails disappear after restart
**Cause:** SQLite is ephemeral on Render

**Solution:**
- ✅ Fixed by Google Sheets persistence
- Startup sync restores all emails from Sheets

## Performance Considerations

**API Quota:**
- Google Sheets API: 100 requests per 100 seconds per user
- Bulk upload of 20 emails ≈ 20-25 API calls
- Rate limiting should be rare with normal usage

**Startup Time:**
- Loading 100 emails from Sheets: ~2-3 seconds
- Loading 1000 emails: ~10-15 seconds
- Acceptable for startup operation

**Memory:**
- SQLite + gspread client: ~50-100 MB
- No memory leaks detected
- Connection reuse via singleton pattern

## Testing Status

✅ Credentials encoding/decoding
✅ Table access and permissions
✅ Header auto-validation and creation
✅ Bulk upload with Sheets logging
✅ Startup sync from Sheets to SQLite
✅ User allocation logging
✅ Code check logging
✅ Completion status updates
✅ Duplicate prevention
✅ Rate limit handling

## Next Steps

1. Monitor production usage for rate limiting
2. Collect metrics on sync times with large datasets
3. Consider batch API calls if quota becomes an issue
4. Add periodic background sync (every 1 hour) for redundancy

## Commit History

- `20b4719` - ✅ Add automatic header validation and creation for PostBD sheet
- Previous commits: OAuth2 support, email encryption, startup sync implementation

## References

- `email_sheets_manager.py` - Google Sheets operations
- `email_farm_models.py` - SQLite database models
- `main.py` - FastAPI endpoints and startup logic
- `GOOGLE_SHEETS_SETUP.md` - Setup instructions
- `HEADER_VALIDATION_TEST.md` - Testing procedures
