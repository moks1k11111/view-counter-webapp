from fastapi import FastAPI, HTTPException, Depends, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import sys
import os
import hmac
import hashlib
import json
import asyncio
import logging
from urllib.parse import parse_qsl
from collections import defaultdict

# Telegram Bot Imports
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Добавляем путь к родительской директории
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database_sheets import SheetsDatabase
from database_sqlite import SQLiteDatabase
from project_manager import ProjectManager
from project_sheets_manager import ProjectSheetsManager
from cache import (
    cache, TTL_PROJECT_ANALYTICS, TTL_USER_ANALYTICS, TTL_FINISHED_PROJECT,
    get_project_analytics_key, get_user_analytics_key
)
from config import (
    TELEGRAM_TOKEN, DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS,
    GOOGLE_SHEETS_CREDENTIALS_JSON, ADMIN_IDS,
    RAPIDAPI_KEY, RAPIDAPI_HOST, RAPIDAPI_BASE_URL,
    INSTAGRAM_RAPIDAPI_KEY, INSTAGRAM_RAPIDAPI_HOST, INSTAGRAM_BASE_URL,
    FACEBOOK_RAPIDAPI_KEY, FACEBOOK_RAPIDAPI_HOST, FACEBOOK_APP_ID,
    DB_ENCRYPTION_KEY, LOG_CHANNEL_ID
)
from tiktok_api import TikTokAPI
from instagram_api import InstagramAPI
from facebook_parser import FacebookAPI

# Email Farm imports
from email_farm_models import EmailFarmDatabase
from email_encryption import EmailEncryption, get_encryption
from email_imap_client import OutlookIMAPClient
from email_oauth2_client import OutlookOAuth2IMAPClient
from email_smart_filter import EmailSmartFilter
from email_sheets_manager import EmailSheetsManager

# Logging (initialize BEFORE using logger)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# WebApp Config
WEBAPP_URL = "https://moks1k11111.github.io/view-counter-webapp/index.html"

# Celery tasks (background processing)
try:
    from tasks import sync_account_to_sheets, sync_project_to_sheets
    CELERY_AVAILABLE = True
    logger.info("✅ Celery tasks imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ Celery not available: {e}. Background tasks disabled.")
    CELERY_AVAILABLE = False

app = FastAPI(title="View Counter WebApp API")

# CORS настройки для Telegram WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретный домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация баз данных
db = SQLiteDatabase()

# Используем GOOGLE_SHEETS_CREDENTIALS_JSON если доступна (Railway), иначе файл (локально)
try:
    sheets_db = SheetsDatabase(GOOGLE_SHEETS_CREDENTIALS, DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS_JSON)
except Exception as e:
    print(f"⚠️  Google Sheets не подключен: {e}")
    print("✅ Приложение продолжает работу с SQLite базой данных")
    sheets_db = None

project_manager = ProjectManager(db)

# Глобальное хранилище прогресса обновления статистики
# Формат: {project_id: {platform: {total, processed, updated, failed}}}
refresh_progress = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'processed': 0, 'updated': 0, 'failed': 0}))

# Инициализация Google Sheets для проектов
try:
    project_sheets = ProjectSheetsManager(GOOGLE_SHEETS_CREDENTIALS, "MainBD", GOOGLE_SHEETS_CREDENTIALS_JSON)
except Exception as e:
    print(f"⚠️  Project Sheets Manager не подключен: {e}")
    project_sheets = None

# Инициализация API клиентов для обновления статистики
try:
    tiktok_api = TikTokAPI(api_key=RAPIDAPI_KEY, api_host=RAPIDAPI_HOST, base_url=RAPIDAPI_BASE_URL)
    instagram_api = InstagramAPI(api_key=INSTAGRAM_RAPIDAPI_KEY, api_host=INSTAGRAM_RAPIDAPI_HOST, base_url=INSTAGRAM_BASE_URL)
    facebook_api = FacebookAPI(api_key=FACEBOOK_RAPIDAPI_KEY, api_host=FACEBOOK_RAPIDAPI_HOST, app_id=FACEBOOK_APP_ID)
    logger.info("✅ TikTok, Instagram and Facebook API clients initialized")
except Exception as e:
    logger.error(f"⚠️  Failed to initialize API clients: {e}")
    tiktok_api = None
    instagram_api = None
    facebook_api = None

# Инициализация Email Farm
try:
    email_farm_db = EmailFarmDatabase(db_path="tiktok_analytics.db")
    email_encryption = get_encryption()
    email_filter = EmailSmartFilter()
    logger.info("✅ Email Farm system initialized")
except Exception as e:
    logger.error(f"⚠️  Failed to initialize Email Farm: {e}")
    email_farm_db = None
    email_encryption = None
    email_filter = None

# Инициализация Email Sheets Manager для Email Farm
try:
    json_creds_preview = GOOGLE_SHEETS_CREDENTIALS_JSON[:50] + "..." if GOOGLE_SHEETS_CREDENTIALS_JSON else "None"
    logger.info(f"📊 Initializing Email Sheets Manager:")
    logger.info(f"   credentials_file={GOOGLE_SHEETS_CREDENTIALS}")
    logger.info(f"   has_json_creds={bool(GOOGLE_SHEETS_CREDENTIALS_JSON)}")
    logger.info(f"   json_creds_length={len(GOOGLE_SHEETS_CREDENTIALS_JSON) if GOOGLE_SHEETS_CREDENTIALS_JSON else 0}")
    logger.info(f"   json_creds_preview={json_creds_preview}")

    email_sheets = EmailSheetsManager(GOOGLE_SHEETS_CREDENTIALS, "PostBD", GOOGLE_SHEETS_CREDENTIALS_JSON)
    logger.info("✅ Email Sheets Manager (PostBD) initialized successfully")
    logger.info(f"   Spreadsheet: {email_sheets.spreadsheet.title}")
except Exception as e:
    logger.error(f"❌ Failed to initialize Email Sheets Manager: {e}")
    import traceback
    logger.error(traceback.format_exc())
    logger.error("⚠️ Email Farm will work WITHOUT Google Sheets persistence - emails will be lost on restart!")
    email_sheets = None

# ============ TELEGRAM BOT LOGIC ============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command"""
    logger.info(f"Received /start from {update.effective_user.id}")

    try:
        user = update.effective_user

        # Register user in database
        try:
            print(f"🔍 DEBUG: Saving user to DB - ID: {user.id}, Username: {user.username}, Name: {user.first_name} {user.last_name}")
            db.add_user(user.id, user.username, user.first_name, user.last_name)
            print(f"✅ User {user.id} (@{user.username}) saved/updated in persistent DB")
        except Exception as e:
            print(f"⚠️ Error saving user: {e}")
            import traceback
            traceback.print_exc()

        keyboard = [
            [KeyboardButton(
                text="📊 Открыть Аналитику",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            "Сервер Render работает ✅\n"
            "Нажми кнопку ниже, чтобы открыть панель аналитики:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in start_command: {e}")

async def run_telegram_bot():
    """Background task to run the Telegram bot"""
    if not TELEGRAM_TOKEN:
        logger.error("❌ No TELEGRAM_TOKEN found")
        return

    logger.info("🚀 Starting Telegram Bot in background...")
    try:
        bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
        bot_app.add_handler(CommandHandler("start", start_command))

        # ВАЖНО: Удаляем webhook перед polling
        logger.info("Deleting webhook...")
        await bot_app.bot.delete_webhook(drop_pending_updates=True)

        # Start polling
        logger.info("Starting polling...")
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()

        logger.info("✅ Bot polling started successfully on Render")

        # Keep running
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"❌ Bot failed to start: {e}")

async def sync_emails_from_sheets():
    """
    Load all emails from Google Sheets and sync them to SQLite on startup.
    This ensures emails persist across Render restarts.
    """
    if not email_sheets or not email_farm_db or not email_encryption:
        logger.warning("⚠️ Email Sheets or Email Farm DB not initialized - skipping sync")
        return

    try:
        logger.info("📥 Syncing emails from Google Sheets to SQLite...")

        # Get all emails from PostBD sheet
        all_emails = email_sheets.get_all_emails_for_sheet("Post")
        logger.info(f"   Found {len(all_emails)} emails in Google Sheets")

        synced_count = 0
        skipped_count = 0

        for sheet_email in all_emails:
            email_address = sheet_email['email']

            # Check if email already exists in SQLite
            existing = email_farm_db.get_email_by_address(email_address)

            if existing:
                # Email already exists, just update status if needed
                skipped_count += 1
                continue

            # Email doesn't exist, add it
            try:
                # Use empty password as placeholder since passwords are not stored in sheets
                # The real encrypted password is in SQLite, but we lost it on restart
                # Admin will need to re-upload with passwords if needed
                placeholder_password = email_encryption.encrypt("")

                email_id = email_farm_db.add_email_account(
                    email=email_address,
                    password_encrypted=placeholder_password,
                    proxy_string=None,  # Proxy info not stored in sheets
                    project_id=None
                )

                if email_id:
                    synced_count += 1

                    # Restore status and assignment from sheets if email was allocated
                    if sheet_email['status'] == 'active' and sheet_email['user_id']:
                        try:
                            user_id = int(sheet_email['user_id'])
                            email_farm_db.allocate_email_to_user(email_id, user_id)

                            # Restore is_completed status
                            if sheet_email.get('is_completed') == '1':
                                email_farm_db.mark_email_completed(email_id)

                            logger.info(f"   ✅ Synced: {email_address} (user: {user_id}, completed: {sheet_email.get('is_completed') == '1'})")
                        except Exception as e:
                            logger.warning(f"   ⚠️ Could not restore status for {email_address}: {e}")
                    else:
                        logger.info(f"   ✅ Synced: {email_address} (free)")

            except Exception as e:
                logger.warning(f"   ⚠️ Could not sync {email_address}: {e}")
                skipped_count += 1

        logger.info(f"✅ Email sync complete: {synced_count} synced, {skipped_count} skipped")

    except Exception as e:
        logger.error(f"❌ Error syncing emails from sheets: {e}")
        import traceback
        logger.error(traceback.format_exc())


@app.on_event("startup")
async def startup_event():
    """Start bot when FastAPI starts"""
    print("🚀 SERVER VERSION: 4.2 (ADDED GOOGLE SHEETS SYNC ON STARTUP)")
    logger.info("🚀 SERVER VERSION: 4.2 (ADDED GOOGLE SHEETS SYNC ON STARTUP)")
    logger.info("🚀 FastAPI starting up...")

    # Sync emails from Google Sheets to SQLite
    await sync_emails_from_sheets()

    # Start bot in background (won't crash API if bot fails)
    try:
        asyncio.create_task(run_telegram_bot())
        logger.info("✅ Bot task created successfully")
    except Exception as e:
        logger.error(f"⚠️ Failed to create bot task: {e}")
        logger.info("✅ API will continue without bot")

# ============ Модели данных ============

class UserAuth(BaseModel):
    telegram_init_data: str

class BonusCreate(BaseModel):
    project_id: str
    amount: float
    description: str

class ProjectStats(BaseModel):
    project_id: str
    platform: Optional[str] = None  # tiktok, instagram, или None для всех

class ProjectCreate(BaseModel):
    name: str
    target_views: int
    kpi_views: int = 1000
    deadline: str  # YYYY-MM-DD
    geo: str = ""
    allowed_platforms: Dict[str, bool] = {}

class SocialAccountCreate(BaseModel):
    platform: str  # tiktok, instagram, youtube, facebook
    username: str
    profile_link: str
    status: str = "NEW"  # NEW, OLD, Ban
    topic: str = ""
    telegram_user: Optional[str] = None  # Worker's Telegram username from frontend

class SocialAccountUpdate(BaseModel):
    status: Optional[str] = None
    topic: Optional[str] = None
    username: Optional[str] = None
    profile_link: Optional[str] = None

class AccountSnapshot(BaseModel):
    followers: int = 0
    likes: int = 0
    comments: int = 0
    videos: int = 0
    views: int = 0

class AddUserToProject(BaseModel):
    username: str

class RefreshStatsRequest(BaseModel):
    platforms: Dict[str, bool]  # {"tiktok": True, "instagram": True, ...}
    date_from: Optional[str] = None  # Дата начала периода (YYYY-MM-DD)
    date_to: Optional[str] = None  # Дата окончания периода (YYYY-MM-DD)

# ============ Email Farm Models ============

class EmailAccountUpload(BaseModel):
    email: str
    password: str
    proxy: Optional[str] = None  # socks5://user:pass@ip:port
    project_id: Optional[int] = None
    refresh_token: Optional[str] = None  # OAuth2 refresh token
    client_id: Optional[str] = None  # OAuth2 client ID
    auth_type: str = 'password'  # 'password' or 'oauth2'

class EmailAccountBulkUpload(BaseModel):
    accounts: List[EmailAccountUpload]

class SetUserEmailLimit(BaseModel):
    user_id: int
    max_emails: int
    can_access: bool = True

class CheckEmailCodeRequest(BaseModel):
    email_id: int

# ============ Email Farm Helper Functions ============

async def send_security_alert(user_id: int, email: str, subject: str, reason: str):
    """Send security alert to admin channel"""
    if not LOG_CHANNEL_ID:
        logger.warning("⚠️ LOG_CHANNEL_ID not configured, skipping security alert")
        return

    try:
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)

        message = (
            f"🚨 <b>Security Alert - Email Farm</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"📧 Email: <code>{email}</code>\n"
            f"📝 Subject: <i>{subject}</i>\n\n"
            f"⚠️ <b>Reason:</b> {reason}\n\n"
            f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        await bot.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=message,
            parse_mode='HTML'
        )
        logger.info(f"✅ Security alert sent to channel {LOG_CHANNEL_ID}")

    except Exception as e:
        logger.error(f"❌ Failed to send security alert: {e}")

# ============ Telegram WebApp Аутентификация ============

def validate_telegram_init_data(init_data: str) -> dict:
    """Проверяет подлинность данных от Telegram WebApp"""
    try:
        parsed_data = dict(parse_qsl(init_data))

        # Получаем hash из данных
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            raise HTTPException(status_code=401, detail="Missing hash")

        # Создаем строку для проверки
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])

        # Создаем секретный ключ
        secret_key = hmac.new(
            b"WebAppData",
            TELEGRAM_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        # Проверяем hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            raise HTTPException(status_code=401, detail="Invalid hash")

        # Парсим user данные
        user_data = json.loads(parsed_data.get('user', '{}'))
        return user_data

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")

async def get_current_user(x_telegram_init_data: str = Header(None)) -> dict:
    """Dependency для получения текущего пользователя"""
    print(f"🔍 Auth attempt - initData present: {bool(x_telegram_init_data)}, length: {len(x_telegram_init_data) if x_telegram_init_data else 0}")
    if not x_telegram_init_data:
        print("❌ Auth failed: No init data")
        raise HTTPException(status_code=401, detail="Telegram init data required")
    try:
        user = validate_telegram_init_data(x_telegram_init_data)
        print(f"✅ Auth success: user_id={user.get('id')}")
        return user
    except HTTPException as e:
        print(f"❌ Auth failed: {e.detail}")
        raise

# ============ API Endpoints ============

@app.get("/")
async def root():
    return {"message": "View Counter WebApp API + Telegram Bot", "version": "2.0", "bot_enabled": bool(TELEGRAM_TOKEN)}

@app.get("/api/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Получить информацию о текущем пользователе"""
    user_id = str(user.get('id'))

    # Получаем проекты пользователя
    projects = project_manager.get_user_projects(user_id)

    # Получаем текущий проект
    current_project_id = project_manager.get_user_current_project(user_id)

    return {
        "user": user,
        "projects": projects,
        "current_project_id": current_project_id
    }

@app.get("/api/projects")
async def get_projects(user: dict = Depends(get_current_user)):
    """Получить все проекты с проверкой доступа для пользователя"""
    user_id = str(user.get('id'))
    logger.info(f"📋 User {user_id} requesting all projects")
    # Используем новый метод для получения всех проектов с маскированием данных для недоступных
    projects = project_manager.get_all_projects_with_access(user_id)
    logger.info(f"📋 Found {len(projects)} projects for user {user_id}")

    # Логируем access для каждого проекта
    for p in projects:
        logger.info(f"  - Project '{p.get('name')}': has_access={p.get('has_access')}")

    return {"projects": projects}

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    """Получить детальную информацию о проекте"""
    user_id = str(user.get('id'))

    # Проверяем доступ к проекту
    user_projects = project_manager.get_user_projects(user_id)
    if not any(p['id'] == project_id for p in user_projects):
        raise HTTPException(status_code=403, detail="Access denied")

    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Получаем участников проекта
    users = project_manager.get_project_users(project_id)

    return {
        "project": project,
        "users": users
    }

@app.post("/api/projects/{project_id}/users")
async def add_user_to_project_endpoint(
    project_id: str,
    data: AddUserToProject,
    user: dict = Depends(get_current_user)
):
    """Добавить пользователя в проект по username"""
    # Проверяем доступ к проекту
    user_id = str(user.get('id'))
    user_projects = project_manager.get_user_projects(user_id)
    if not any(p['id'] == project_id for p in user_projects):
        raise HTTPException(status_code=403, detail="Access denied")

    # Strip @ from username if present
    username = data.username.strip().lstrip('@')

    # Look up user by username in the database (case-insensitive)
    try:
        print(f"🔍 DEBUG: Looking up user with username: '{username}' (case-insensitive)")
        db.cursor.execute(
            "SELECT user_id, first_name FROM users WHERE LOWER(username) = LOWER(?)",
            (username,)
        )
        result = db.cursor.fetchone()

        if not result:
            print(f"❌ User '{username}' not found in database")
            raise HTTPException(
                status_code=404,
                detail="User not found. Please ask them to /start the bot first."
            )

        print(f"✅ User found: {result[0]} (first_name: {result[1]})")

        target_user_id = result[0]

        # Check if user is already in the project
        db.cursor.execute(
            "SELECT COUNT(*) FROM project_users WHERE project_id = ? AND user_id = ?",
            (project_id, target_user_id)
        )
        already_exists = db.cursor.fetchone()[0] > 0

        if already_exists:
            raise HTTPException(status_code=400, detail="User is already in this project")

        # Add user to project
        success = project_manager.add_user_to_project(project_id, target_user_id)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to add user to project")

        return {"success": True, "message": f"User @{username} added to project"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding user to project: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/projects")
async def create_project(
    project: ProjectCreate,
    user: dict = Depends(get_current_user)
):
    """Создать новый проект (только для админов)"""
    user_id = str(user.get('id'))

    # Проверка прав администратора
    if user_id not in [str(admin_id) for admin_id in ADMIN_IDS]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Создаем проект
    new_project = project_manager.create_project(
        name=project.name,
        google_sheet_name=DEFAULT_GOOGLE_SHEETS_NAME,  # Используем дефолтную таблицу
        start_date=datetime.now().strftime("%Y-%m-%d"),
        end_date=project.deadline,
        target_views=project.target_views,
        geo=project.geo,
        kpi_views=project.kpi_views,
        allowed_platforms=project.allowed_platforms
    )

    # Добавляем создателя (админа) в проект
    project_manager.add_user_to_project(new_project['id'], user_id)

    # Создаем лист в Google Sheets, если project_sheets доступен
    if project_sheets:
        try:
            project_sheets.create_project_sheet(project.name)  # project - это Pydantic модель!
            logger.info(f"✅ Лист '{project.name}' создан в Google Sheets")
        except Exception as e:
            logger.error(f"⚠️ Ошибка создания листа в Google Sheets: {e}")
            import traceback
            traceback.print_exc()

    return {"success": True, "project": new_project}

async def sync_project_from_sheets(project_id: str, project: dict):
    """
    Автоматическая синхронизация с использованием SmartSyncService

    Применяет:
    - Safe number parsing (formatted numbers "1 000 000")
    - Platform-specific merge strategy (MAX for TikTok/Instagram, Sheets priority for FB/YT)
    - Protection for manual Facebook/YouTube edits
    """
    try:
        # 🚀 Используем SmartSyncService вместо ручного копирования
        from smart_sync import SmartSyncService

        sync_service = SmartSyncService(project_manager, project_sheets)
        result = sync_service.sync_project(project_id)

        if result.get('success'):
            logger.info(f"✅ Auto-sync '{project['name']}': {result.get('snapshot_count', 0)} обновлено")

    except Exception as e:
        logger.warning(f"⚠️ Auto-sync error for '{project['name']}': {e}")

@app.get("/api/projects/{project_id}/analytics")
async def get_project_analytics(
    project_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    platform: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Получить аналитику по проекту с историей (with Redis caching + background sync)"""
    user_id = str(user.get('id'))

    # Проверяем доступ
    user_projects = project_manager.get_user_projects(user_id)
    if not any(p['id'] == project_id for p in user_projects):
        raise HTTPException(status_code=403, detail="Access denied")

    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 🚀 REDIS CACHE: Check cache first
    cache_key = get_project_analytics_key(project_id)
    cached_data = cache.get(cache_key)
    if cached_data:
        # Validate cache: reject if shows 0 views but has profiles (data race/stale cache)
        total_views = cached_data.get('total_views', 0)
        total_profiles = cached_data.get('total_profiles', 0)

        if total_views == 0 and total_profiles > 0:
            logger.warning(f"⚠️ Invalid cache for project {project_id}: 0 views with {total_profiles} profiles - forcing sync")
            cache.delete(cache_key)  # Invalidate stale cache
        else:
            logger.info(f"🎯 Cache HIT for project {project_id} (valid data)")
            return cached_data

    # 🔄 ФОНОВАЯ СИНХРОНИЗАЦИЯ: Google Sheets → SQLite (НЕ блокирует ответ!)
    # Запускаем синхронизацию В ФОНЕ - пользователь получит ответ мгновенно!
    # Данные обновятся через 1-2 сек в фоне, следующий запрос покажет свежие данные
    if project_sheets:
        background_tasks.add_task(sync_project_from_sheets, project_id, project)
        logger.info(f"🔄 [Background] Sync task scheduled for project {project_id}")

    # 🚀 ЧИТАЕМ ДАННЫЕ ТОЛЬКО ИЗ SQLite SNAPSHOTS (мгновенно!)
    # Google Sheets синхронизируется в фоне (auto-sync выше), а мы читаем из базы
    all_profiles = []

    logger.info(f"📊 Loading analytics from SQLite snapshots for project '{project['name']}'")
    try:
        # Получаем социальные аккаунты из SQLite
        sqlite_accounts = project_manager.get_project_social_accounts(project_id, platform)

        for account in sqlite_accounts:
            # Получаем последний snapshot для каждого аккаунта
            snapshots = project_manager.get_account_snapshots(account['id'], limit=1)
            latest_snapshot = snapshots[0] if snapshots else {}

            # Извлекаем username из URL (так же как для Sheets)
            url = account.get('profile_link', '').strip()
            username = None

            if '/@' in url:
                username = url.split('/@')[1].split('?')[0].split('/')[0]
            elif 'facebook.com' in url.lower() or 'fb.com' in url.lower():
                # Facebook: проверяем формат profile.php?id=...
                url_lower_local = url.lower()
                if 'profile.php?id=' in url_lower_local:
                    try:
                        import urllib.parse
                        parsed = urllib.parse.urlparse(url)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'id' in params:
                            username = params['id'][0]
                    except:
                        pass
                else:
                    # Обычный формат
                    clean_url = url.rstrip('/').split('?')[0]
                    # Убираем пустые части после split
                    parts = [p for p in clean_url.split('/') if p]

                    if 'share' in parts:
                        idx = parts.index('share')
                        if idx + 1 < len(parts):
                            username = parts[idx + 1]
                    elif len(parts) > 0:
                        for part in reversed(parts):
                            if part and part not in ['facebook.com', 'www.facebook.com', 'fb.com', 'https:', 'http:']:
                                username = part
                                break

            # Fallback на username из базы или telegram_user
            if not username:
                username = account.get('username') or account.get('telegram_user') or 'Unknown'
                # Убираем @ если есть
                if username and username.startswith('@'):
                    username = username[1:]

            # Используем total_videos_fetched если > 0, иначе fallback на videos
            total_vids = latest_snapshot.get('total_videos_fetched', 0)
            videos_count = total_vids if total_vids > 0 else latest_snapshot.get('videos', 0)

            # Форматируем время последнего обновления в относительном формате
            last_update = "Не обновлялось"
            if latest_snapshot and latest_snapshot.get('snapshot_time'):
                try:
                    snapshot_time = latest_snapshot.get('snapshot_time')

                    # Парсим ISO формат и убираем timezone info для корректного сравнения
                    # SQLite хранит в UTC без timezone, поэтому парсим как naive datetime
                    if 'T' in snapshot_time:
                        # Формат: "2025-12-08T22:14:44" или "2025-12-08T22:14:44.123456"
                        dt_str = snapshot_time.split('.')[0]  # Убираем микросекунды если есть
                        dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
                    else:
                        # Формат: "2025-12-08 22:14:44"
                        dt = datetime.strptime(snapshot_time.split('.')[0], '%Y-%m-%d %H:%M:%S')

                    # Вычисляем разницу с текущим временем (оба naive datetime)
                    now = datetime.now()
                    diff = now - dt
                    total_seconds = int(diff.total_seconds())

                    # Форматируем относительно с детальным временем
                    if total_seconds < 0:
                        # Время в будущем (ошибка часов)
                        last_update = "Только что"
                    elif total_seconds < 60:
                        # Меньше минуты
                        last_update = "Только что"
                    elif total_seconds < 3600:  # Меньше 1 часа (до 59 минут)
                        minutes = total_seconds // 60
                        last_update = f"{minutes} мин. назад"
                    elif total_seconds < 86400:  # От 1 часа до 24 часов
                        hours = total_seconds // 3600
                        # Показываем каждый час: "1 ч. назад", "2 ч. назад", "23 ч. назад"
                        last_update = f"{hours} ч. назад"
                    else:  # Больше суток - показываем дату
                        last_update = dt.strftime('%d.%m.%Y')

                except Exception as e:
                    logger.warning(f"⚠️ Failed to parse snapshot_time '{snapshot_time}' for account {account.get('id')}: {e}")
                    last_update = "Не обновлялось"

            all_profiles.append({
                'telegram_user': account.get('telegram_user', 'Unknown'),
                'username': username,  # Username из соц сети
                'url': url,
                'followers': latest_snapshot.get('followers', 0),
                'likes': latest_snapshot.get('likes', 0),
                'comments': latest_snapshot.get('comments', 0),
                'videos': videos_count,  # Все видео (используем total_videos_fetched если есть)
                'total_views': latest_snapshot.get('views', 0),
                'platform': account.get('platform', 'tiktok').lower(),
                'topic': account.get('topic', 'Не указано'),
                'last_update': last_update  # Время последнего обновления
            })

        logger.info(f"✅ Loaded {len(all_profiles)} profiles from SQLite for project '{project['name']}'")
    except Exception as e:
        logger.warning(f"⚠️ Could not load accounts from SQLite: {e}")
        import traceback
        traceback.print_exc()

    # Группируем по пользователям
    users_stats = {}
    platform_stats = {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0}
    topic_stats = {}
    total_views = 0
    total_videos = 0
    total_profiles = len(all_profiles)

    for profile in all_profiles:
        telegram_user = profile['telegram_user']
        views = int(profile.get('total_views', 0) or 0)
        videos = int(profile.get('videos', 0) or 0)
        plat = profile['platform']
        topic = profile.get('topic', 'Не указано')

        # Считаем ВСЕ просмотры/видео
        total_views += views
        total_videos += videos

        # Статистика по пользователям
        if telegram_user not in users_stats:
            users_stats[telegram_user] = {
                "total_views": 0,
                "platforms": {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0},
                "topics": {},
                "profiles_count": 0
            }

        users_stats[telegram_user]["total_views"] += views
        users_stats[telegram_user]["platforms"][plat] += views
        users_stats[telegram_user]["profiles_count"] += 1

        if topic:
            users_stats[telegram_user]["topics"][topic] = \
                users_stats[telegram_user]["topics"].get(topic, 0) + views

        # Общая статистика по платформам
        platform_stats[plat] += views

        # Общая статистика по тематикам
        if topic:
            topic_stats[topic] = topic_stats.get(topic, 0) + views

    logger.info(f"🎯 FINAL ANALYTICS: total_views={total_views}, total_videos={total_videos}, total_profiles={total_profiles}")

    # Устанавливаем start_date и end_date если они не заданы
    if not start_date:
        # Пытаемся взять из проекта
        start_date = project.get('start_date')
        # Если и в проекте нет, используем 30 дней назад
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            logger.warning(f"⚠️ Project {project_id} has no start_date, using 30 days ago: {start_date}")

    if not end_date:
        end_date = project.get('end_date') or datetime.now().strftime('%Y-%m-%d')

    # Получаем историю просмотров проекта из SQLite
    daily_history = project_manager.get_project_daily_history(project_id, start_date, end_date)

    # Если нет истории в SQLite, создаем точки для периода проекта
    history = daily_history.get("history", [])
    growth_24h = daily_history.get("growth_24h", 0)
    today = datetime.now().strftime('%Y-%m-%d')

    if len(history) == 0 and total_views > 0:
        # Нет исторических данных - показываем только текущую точку
        history = [{
            "date": today,
            "views": total_views
        }]
        growth_24h = 0

        logger.warning(f"⚠️ No historical data available. Showing only current point: {today} with {total_views} views")
        logger.info(f"💡 To enable historical chart, add daily snapshots using POST /api/accounts/{{account_id}}/snapshot")
    else:
        # Есть историческая data из snapshots
        logger.info(f"📊 Loaded real history: {len(history)} days, growth_24h: {growth_24h}")

        # Если последняя точка НЕ сегодня - добавляем сегодняшнюю динамическую точку из Google Sheets
        if history and history[-1]['date'] != today and total_views > 0:
            # Вычисляем прирост за 24ч как разницу между сегодня и последней точкой
            last_day_views = history[-1]['views']
            growth_24h = total_views - last_day_views

            history.append({
                "date": today,
                "views": total_views  # Динамические данные из Google Sheets!
            })

            logger.info(f"📊 Added today's dynamic point: {today} with {total_views} views (growth: +{growth_24h})")

    # График показывает кумулятивные (накопительные) значения для страницы проекта
    # chart_data = history (формат: [{date, views}, ...] где views - это накопительная сумма)
    logger.info(f"📊 Chart data prepared: {len(history)} days (cumulative values)")

    # DEBUG: Log all_profiles before returning
    logger.info(f"🔍 DEBUG FINAL all_profiles count: {len(all_profiles)}")
    for idx, prof in enumerate(all_profiles):
        logger.info(f"🔍 DEBUG PROFILE[{idx}]: username='{prof.get('username')}', url='{prof.get('url')}', views={prof.get('total_views')}, platform='{prof.get('platform')}'")

    # Prepare response data
    response_data = {
        "project": project,
        "total_views": total_views,
        "total_videos": total_videos,
        "total_profiles": total_profiles,
        "platform_stats": platform_stats,
        "topic_stats": topic_stats,
        "users_stats": users_stats,
        "profiles": all_profiles,  # Список всех профилей для диаграммы аккаунтов
        "target_views": project['target_views'],
        "progress_percent": min(100, round((total_views / project['target_views'] * 100), 2)) if project['target_views'] > 0 else 0,
        "history": history,  # Кумулятивные значения (накопительная сумма)
        "chart_data": history,  # Кумулятивные значения для графика (накопительная сумма)
        "growth_24h": growth_24h,
        "backend_version": "v2.1_redis_cache"  # Для отладки версии бэкенда
    }

    # 🚀 REDIS CACHE: Save to cache
    # Use longer TTL for finished projects (they don't change)
    is_finished = project.get('is_active') == 0 or project.get('is_active') == False
    ttl = TTL_FINISHED_PROJECT if is_finished else TTL_PROJECT_ANALYTICS
    cache.set(cache_key, response_data, ttl)
    logger.info(f"💾 Cached project analytics for {project_id} (TTL: {ttl}s, finished: {is_finished})")

    return response_data

@app.get("/api/my-analytics")
async def get_my_analytics(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    project_id: Optional[str] = None
):
    """Получить личную аналитику пользователя (with Redis caching + background sync)"""
    user_id = str(user.get('id'))
    username = user.get('username', '')
    telegram_user = f"@{username}" if username else user.get('first_name', 'Неизвестно')

    # 🚀 REDIS CACHE: Check cache first (if project_id specified)
    if project_id:
        cache_key = get_user_analytics_key(user_id, project_id)
        cached_data = cache.get(cache_key)
        if cached_data:
            # Validate cache: reject if shows 0 views but has profiles
            total_views = cached_data.get('total_views', 0)
            total_profiles = len(cached_data.get('profiles', []))

            if total_views == 0 and total_profiles > 0:
                logger.warning(f"⚠️ Invalid cache for user {user_id} in project {project_id}: 0 views with {total_profiles} profiles - forcing sync")
                cache.delete(cache_key)  # Invalidate stale cache
            else:
                logger.info(f"🎯 Cache HIT for user {user_id} analytics in project {project_id} (valid data)")
                return cached_data

    # Если указан проект, фильтруем по нему
    project_name = None
    if project_id:
        project = project_manager.get_project(project_id)
        if project:
            project_name = project['name']

            # 🔄 ФОНОВАЯ СИНХРОНИЗАЦИЯ (НЕ блокирует ответ!)
            if project_sheets:
                background_tasks.add_task(sync_project_from_sheets, project_id, project)
                logger.info(f"🔄 [Background] Sync task scheduled for user {user_id} analytics")

    # 🚀 ЧИТАЕМ ПРОФИЛИ ИЗ SQLite SNAPSHOTS (так же как в /api/projects/{project_id}/analytics)
    # Это гарантирует консистентность данных между "Все проекты" и "Мои проекты"
    profiles = []
    if project_id:
        try:
            # Получаем социальные аккаунты пользователя из SQLite
            sqlite_accounts = project_manager.get_project_social_accounts(project_id, platform=None)

            # Нормализуем telegram_user для сравнения (убираем @ если есть)
            normalized_telegram_user = telegram_user.lstrip('@')

            logger.info(f"🔍 [MyAnalytics] Looking for user: '{normalized_telegram_user}' in project {project_id}")
            logger.info(f"🔍 [MyAnalytics] Found {len(sqlite_accounts)} total accounts in project")

            # Фильтруем по текущему пользователю
            for account in sqlite_accounts:
                # Нормализуем telegram_user из базы (убираем @ если есть)
                account_telegram_user = account.get('telegram_user', '').lstrip('@')

                logger.debug(f"🔍 [MyAnalytics] Comparing: '{account_telegram_user}' == '{normalized_telegram_user}'")

                if account_telegram_user == normalized_telegram_user:
                    # Получаем последний snapshot для каждого аккаунта
                    snapshots = project_manager.get_account_snapshots(account['id'], limit=1)
                    latest_snapshot = snapshots[0] if snapshots else {}

                    # Извлекаем username из URL (так же как для Sheets)
                    url = account.get('profile_link', '').strip()
                    username = None

                    if '/@' in url:
                        username = url.split('/@')[1].split('?')[0].split('/')[0]
                    elif 'facebook.com' in url.lower() or 'fb.com' in url.lower():
                        # Facebook: проверяем формат profile.php?id=...
                        url_lower_local = url.lower()
                        if 'profile.php?id=' in url_lower_local:
                            try:
                                import urllib.parse
                                parsed = urllib.parse.urlparse(url)
                                params = urllib.parse.parse_qs(parsed.query)
                                if 'id' in params:
                                    username = params['id'][0]
                            except:
                                pass
                        else:
                            # Обычный формат
                            clean_url = url.rstrip('/').split('?')[0]
                            parts = [p for p in clean_url.split('/') if p]

                            if 'share' in parts:
                                idx = parts.index('share')
                                if idx + 1 < len(parts):
                                    username = parts[idx + 1]
                            elif len(parts) > 0:
                                for part in reversed(parts):
                                    if part and part not in ['facebook.com', 'www.facebook.com', 'fb.com', 'https:', 'http:']:
                                        username = part
                                        break

                    # Fallback на username из базы или telegram_user
                    if not username:
                        username = account.get('username') or account.get('telegram_user') or 'Unknown'
                        if username and username.startswith('@'):
                            username = username[1:]

                    # Используем total_videos_fetched если > 0, иначе fallback на videos
                    total_vids = latest_snapshot.get('total_videos_fetched', 0)
                    videos_count = total_vids if total_vids > 0 else latest_snapshot.get('videos', 0)

                    profiles.append({
                        'telegram_user': account.get('telegram_user', 'Unknown'),
                        'username': username,
                        'url': url,
                        'followers': latest_snapshot.get('followers', 0),
                        'likes': latest_snapshot.get('likes', 0),
                        'comments': latest_snapshot.get('comments', 0),
                        'videos': videos_count,
                        'total_views': latest_snapshot.get('views', 0),
                        'platform': account.get('platform', 'tiktok').lower(),
                        'topic': account.get('topic', 'Не указано')
                    })

            logger.info(f"✅ [MyAnalytics] Found {len(profiles)} profiles for user '{normalized_telegram_user}'")
        except Exception as e:
            logger.error(f"❌ [MyAnalytics] Could not load user profiles from SQLite for project {project_id}: {e}")
            import traceback
            traceback.print_exc()

    # Статистика
    platform_stats = {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0, "threads": 0}
    topic_stats = {}
    total_views = 0
    total_videos = 0

    for profile in profiles:
        views = int(profile.get('total_views', 0) or 0)
        videos = int(profile.get('videos', 0) or 0)
        plat = profile['platform']
        topic = profile.get('topic', 'Не указано')

        total_views += views
        total_videos += videos
        if plat in platform_stats:
            platform_stats[plat] += views

        if topic:
            topic_stats[topic] = topic_stats.get(topic, 0) + views

    # Если передан project_id, возвращаем полный формат как в /api/projects/{project_id}/analytics
    if project_id and project:
        # Создаем users_stats только для текущего пользователя
        users_stats = {
            telegram_user: {
                "total_views": total_views,
                "total_videos": total_videos,
                "profiles_count": len(profiles)
            }
        }

        # Получаем историю просмотров КОНКРЕТНОГО ПОЛЬЗОВАТЕЛЯ (не всего проекта!)
        daily_history = project_manager.get_user_daily_history(project_id, telegram_user)

        # Если нет истории в SQLite, показываем только текущую точку
        history = daily_history.get("history", [])
        growth_24h = daily_history.get("growth_24h", 0)
        today = datetime.now().strftime('%Y-%m-%d')

        if len(history) == 0 and total_views > 0:
            # Показываем только сегодняшнюю точку с реальными данными
            history = [{"date": today, "views": total_views}]
            growth_24h = 0  # Нет истории = нет прироста
        else:
            # Если последняя точка НЕ сегодня - добавляем сегодняшнюю динамическую точку
            if history and history[-1]['date'] != today and total_views > 0:
                last_day_views = history[-1]['views']
                growth_24h = total_views - last_day_views

                history.append({
                    "date": today,
                    "views": total_views  # Динамические данные из Google Sheets!
                })

                logger.info(f"📊 [My Analytics] Added today's dynamic point: {today} with {total_views} views")

        # Вычисляем ежедневный прирост для графика на карточках (столбики)
        daily_growth = []
        for i, day in enumerate(history):
            if i == 0:
                # Первый день - прирост = значение первого дня
                growth = day['views']
            else:
                # Остальные дни - разница с предыдущим днем
                growth = day['views'] - history[i-1]['views']

            daily_growth.append({
                "date": day['date'],
                "growth": max(0, growth)  # Не показываем отрицательный прирост
            })

        logger.info(f"📊 [My Analytics] Daily growth calculated: {len(daily_growth)} days for chart")

        response_data = {
            "project": project,
            "total_views": total_views,
            "total_videos": total_videos,
            "total_profiles": len(profiles),
            "platform_stats": platform_stats,
            "topic_stats": topic_stats,
            "users_stats": users_stats,
            "profiles": profiles,  # Список всех профилей для диаграммы аккаунтов
            "target_views": project['target_views'],
            "progress_percent": min(100, round((total_views / project['target_views'] * 100), 2)) if project['target_views'] > 0 else 0,
            "history": history,  # Кумулятивные значения (для обратной совместимости)
            "chart_data": daily_growth,  # Ежедневный прирост для столбиков на карточках проектов
            "growth_24h": growth_24h,
            "backend_version": "v2.1_redis_cache"  # Для отладки версии бэкенда
        }

        # 🚀 REDIS CACHE: Save user analytics to cache
        cache.set(cache_key, response_data, TTL_USER_ANALYTICS)
        logger.info(f"💾 Cached user analytics for user {user_id} in project {project_id} (TTL: {TTL_USER_ANALYTICS}s)")

        return response_data

    # Иначе возвращаем упрощенный формат (для общей статистики)
    return {
        "total_views": total_views,
        "platform_stats": platform_stats,
        "topic_stats": topic_stats,
        "profiles_count": len(profiles)
    }

# ============ Административные функции ============

@app.post("/api/admin/projects/{project_id}/bonus")
async def add_bonus(
    project_id: str,
    bonus: BonusCreate,
    user: dict = Depends(get_current_user)
):
    """Добавить бонус в проект (только для админов)"""
    user_id = user.get('id')

    # TODO: Проверка на админа
    # if user_id not in ADMIN_IDS:
    #     raise HTTPException(status_code=403, detail="Admin access required")

    # TODO: Реализовать систему бонусов в БД
    # Пока возвращаем заглушку
    return {
        "success": True,
        "message": "Bonus added successfully",
        "bonus": bonus.dict()
    }

@app.post("/api/admin/projects/{project_id}/update-timestamp")
async def update_project_timestamp(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Обновить timestamp последнего нажатия кнопки 'Данные обновлены' (только для админов)

    Сохраняет текущее время в поле last_admin_update для синхронизации между устройствами.
    """
    user_id = user.get('id')

    # Проверка на админа
    if user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        logger.info(f"🔄 [Timestamp] Начинаем обновление timestamp для проекта {project_id}, админ {user_id}")

        # Обновляем timestamp в базе данных
        success = project_manager.update_project_admin_timestamp(project_id)

        logger.info(f"🔍 [Timestamp] Результат update_project_admin_timestamp: {success}")

        if not success:
            logger.error(f"❌ [Timestamp] update_project_admin_timestamp вернул False для проекта {project_id}")
            raise HTTPException(status_code=500, detail="Failed to update timestamp in database")

        # Инвалидируем кеш проекта
        cache.invalidate_project(project_id)

        logger.info(f"✅ [Timestamp] Timestamp обновлен для проекта {project_id} админом {user_id}")

        return {
            "success": True,
            "message": "Timestamp updated successfully",
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [Timestamp] Исключение при обновлении timestamp для проекта {project_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Exception: {str(e)}")

@app.post("/api/admin/clear-snapshots")
async def clear_all_snapshots(
    user: dict = Depends(get_current_user)
):
    """Очистить все snapshots из базы данных (только для админов)"""
    user_id = user.get('id')

    # Проверка на админа
    if user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Удаляем все snapshots и daily stats
        project_manager.db.cursor.execute('DELETE FROM account_snapshots')
        deleted_snapshots = project_manager.db.cursor.rowcount

        project_manager.db.cursor.execute('DELETE FROM account_daily_stats')
        deleted_daily_stats = project_manager.db.cursor.rowcount

        project_manager.db.conn.commit()

        logger.info(f"🗑️ Cleared {deleted_snapshots} snapshots and {deleted_daily_stats} daily stats by admin user {user_id}")

        return {
            "success": True,
            "message": f"Cleared {deleted_snapshots} snapshots and {deleted_daily_stats} daily stats",
            "deleted_snapshots": deleted_snapshots,
            "deleted_daily_stats": deleted_daily_stats
        }
    except Exception as e:
        logger.error(f"❌ Error clearing snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ API для управления социальными аккаунтами ============

@app.post("/api/projects/{project_id}/accounts")
async def add_social_account(
    project_id: str,
    account: SocialAccountCreate,
    user: dict = Depends(get_current_user)
):
    """Добавить социальный аккаунт в проект"""

    logger.info("🚀 MAIN.PY add_social_account called!")

    # Получаем данные проекта
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Проверяем, разрешена ли эта платформа в проекте
    allowed_platforms = project.get('allowed_platforms', {})
    if not allowed_platforms.get(account.platform.lower(), False):
        logger.warning(f"⚠️ Platform {account.platform} not allowed in project {project_id}")
        raise HTTPException(
            status_code=400,
            detail=f"Добавьте платформу из списка доступных"
        )

    # Проверка на дубликаты - проверяем существует ли уже аккаунт с такой ссылкой
    existing_accounts = project_manager.get_project_social_accounts(project_id)
    for existing in existing_accounts:
        if existing.get('profile_link', '').strip() == account.profile_link.strip():
            logger.warning(f"⚠️ Duplicate account detected: {account.profile_link}")
            raise HTTPException(
                status_code=400,
                detail=f"Этот аккаунт уже добавлен в проект"
            )

    # Safely get telegram_user (may not be present)
    telegram_user_from_frontend = getattr(account, 'telegram_user', None)
    logger.info(f"🔍 account.telegram_user = {repr(telegram_user_from_frontend)}")

    # Extract display name from frontend OR initData
    if telegram_user_from_frontend and telegram_user_from_frontend.strip():
        display_name = telegram_user_from_frontend.strip()
        logger.info(f"✅ Using telegram_user from FRONTEND: '{display_name}'")
    else:
        # Fallback to initData
        tg_username = user.get('username')
        first_name = user.get('first_name', '')
        last_name = user.get('last_name', '')

        if tg_username:
            display_name = f"@{tg_username}"
        elif first_name or last_name:
            display_name = f"{first_name} {last_name}".strip()
        else:
            display_name = f"ID:{user.get('id')}"

        logger.info(f"⚠️ Frontend value empty, using initData: '{display_name}'")

    logger.info(f"✅ FINAL USER: {display_name}")

    # Добавляем аккаунт в БД
    result = project_manager.add_social_account_to_project(
        project_id=project_id,
        platform=account.platform,
        username=account.username,
        profile_link=account.profile_link,
        status=account.status,
        topic=account.topic,
        telegram_user=display_name
    )

    if not result:
        raise HTTPException(status_code=400, detail="Failed to add account")

    # Добавляем в Google Sheets (если включено)
    if project_sheets:
        try:
            # Создаем лист проекта если не существует
            project_sheets.create_project_sheet(project['name'])

            # Парсим username из URL используя функцию из project_sheets_manager
            parsed_username = project_sheets._parse_username_from_url(account.profile_link)
            logger.info(f"📊 Parsed username from URL: '{parsed_username}' (original: '{account.username}')")

            # Добавляем аккаунт в лист С TELEGRAM USERNAME!
            logger.info(f"📊 Sending to Sheets: telegram_user = '{display_name}'")
            project_sheets.add_account_to_sheet(project['name'], {
                'username': parsed_username,  # ← ИСПРАВЛЕНО: используем спарсенный username
                'profile_link': account.profile_link,
                'followers': 0,
                'likes': 0,
                'comments': 0,
                'videos': 0,
                'views': 0,
                'status': account.status,
                'topic': account.topic,
                'platform': account.platform,
                'telegram_user': display_name
            })
            logger.info(f"✅ Added to Sheets: {parsed_username} by {display_name}")
        except Exception as e:
            logger.error(f"⚠️  Ошибка добавления в Google Sheets: {e}")

    return {"success": True, "account": result}

@app.get("/api/projects/{project_id}/accounts")
async def get_project_accounts(
    project_id: str,
    platform: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Получить все социальные аккаунты проекта с метриками (видео/просмотры)"""
    accounts = project_manager.get_project_social_accounts(project_id, platform)

    # Получаем проект для доступа к Google Sheets
    project = project_manager.get_project(project_id)

    # Обогащаем данные аккаунтов метриками из Google Sheets или SQLite
    enriched_accounts = []

    # Пытаемся загрузить данные из Google Sheets
    sheets_data = {}
    if project and project_sheets:
        try:
            accounts_data = project_sheets.get_project_accounts(project['name'])
            # Создаем словарь по ссылкам для быстрого поиска
            for acc_data in accounts_data:
                link = acc_data.get('Link', '')
                sheets_data[link] = {
                    'videos': int(acc_data.get('Videos', 0) or 0),
                    'views': int(acc_data.get('Views', 0) or 0)
                }
        except Exception as e:
            logger.warning(f"⚠️ Could not load metrics from sheets: {e}")

    # Обогащаем каждый аккаунт
    for account in accounts:
        # Пытаемся найти метрики в Google Sheets
        profile_link = account.get('profile_link', '')
        metrics = sheets_data.get(profile_link)

        # Если нет в Sheets, загружаем из последнего snapshot
        if not metrics:
            snapshots = project_manager.get_account_snapshots(account['id'], limit=1)
            latest_snapshot = snapshots[0] if snapshots else {}
            metrics = {
                'videos': latest_snapshot.get('videos', 0),
                'views': latest_snapshot.get('views', 0)
            }

        # Добавляем метрики к аккаунту
        enriched_account = {**account, **metrics}
        enriched_accounts.append(enriched_account)

    return {"success": True, "accounts": enriched_accounts}

@app.post("/api/projects/{project_id}/import_from_sheets")
async def import_from_sheets(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Импорт данных из Google Sheets (Sheets как Master DB)"""
    logger.info(f"🔄 Starting import from Sheets for project {project_id}")

    # Get project
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    try:
        # Read data from Google Sheets
        sheet_records = project_sheets.read_project_sheet(project['name'])
        logger.info(f"📊 Found {len(sheet_records)} records in Google Sheets")

        # Get all project accounts from SQLite
        sqlite_accounts = project_manager.get_project_social_accounts(project_id)

        # Create username -> account_id mapping
        username_to_id = {acc['username']: acc['id'] for acc in sqlite_accounts}

        updated_count = 0
        skipped_count = 0

        for record in sheet_records:
            # Extract data from Sheet record
            # Headers: @Username, Link, Followers, Likes, Following, Videos, Views, Last Update, Status, Тематика
            username = record.get('Link', '').split('@')[-1].split('?')[0].strip('/')
            if not username:
                username = record.get('@Username', '').strip('@')

            followers = int(record.get('Followers', 0) or 0)
            likes = int(record.get('Likes', 0) or 0)
            videos = int(record.get('Videos', 0) or 0)
            views = int(record.get('Views', 0) or 0)

            # Find account in SQLite
            account_id = username_to_id.get(username)

            if account_id:
                # Create snapshot with metrics from Sheets
                success = project_manager.add_account_snapshot(
                    account_id=account_id,
                    followers=followers,
                    likes=likes,
                    comments=0,  # Not in Sheets
                    videos=videos,
                    views=views
                )
                if success:
                    updated_count += 1
                    logger.info(f"✅ Updated {username}: {followers} followers, {views} views")
            else:
                skipped_count += 1
                logger.info(f"⚠️ Account {username} not found in SQLite, skipping")

        logger.info(f"✅ Import completed: {updated_count} updated, {skipped_count} skipped")

        return {
            "success": True,
            "updated": updated_count,
            "skipped": skipped_count,
            "total": len(sheet_records)
        }

    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@app.get("/api/projects/{project_id}/refresh_stats/stream")
async def refresh_stats_stream(
    project_id: str,
    init_data: str = None
):
    """SSE endpoint для стриминга прогресса обновления статистики"""

    # Проверяем авторизацию через query параметр (EventSource не поддерживает headers)
    if not init_data:
        raise HTTPException(status_code=401, detail="init_data required")

    try:
        user = validate_telegram_init_data(init_data)
        logger.info(f"📡 Client connected to progress stream for project {project_id} (user: {user.get('id')})")
    except HTTPException:
        raise HTTPException(status_code=401, detail="Invalid init_data")

    async def event_generator():
        """Генератор событий прогресса"""
        try:
            last_progress = None
            iteration = 0
            while True:
                iteration += 1
                # Получаем текущий прогресс
                current_progress = dict(refresh_progress.get(project_id, {}))

                logger.info(f"📡 SSE iteration {iteration}: current_progress = {current_progress}")

                # Отправляем обновление только если прогресс изменился
                if current_progress != last_progress:
                    data = json.dumps(current_progress)
                    logger.info(f"📤 Sending SSE update: {data}")
                    yield f"data: {data}\n\n"
                    last_progress = current_progress.copy()

                    # Проверяем завершение - все платформы обработаны
                    all_done = all(
                        stats['processed'] >= stats['total']
                        for stats in current_progress.values()
                        if stats['total'] > 0
                    )

                    logger.info(f"🔍 All done check: {all_done}, platforms: {len(current_progress)}")

                    if all_done and len(current_progress) > 0:
                        # Отправляем финальное событие
                        logger.info(f"📤 Sending completion event")
                        yield f"data: {json.dumps({'status': 'completed'})}\n\n"
                        logger.info(f"✅ Progress stream completed for project {project_id}")
                        break

                # Ждем перед следующей проверкой
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"❌ Client disconnected from progress stream for project {project_id}")
            # Очищаем прогресс при отключении
            if project_id in refresh_progress:
                del refresh_progress[project_id]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Отключаем буферизацию для Nginx
        }
    )

@app.get("/api/projects/{project_id}/refresh_progress")
async def get_refresh_progress(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Получить текущий прогресс обновления статистики"""
    progress = dict(refresh_progress.get(project_id, {}))
    logger.info(f"📊 Get progress for project {project_id}: {progress}")
    return {
        "success": True,
        "progress": progress
    }

@app.post("/api/projects/{project_id}/refresh_stats")
async def refresh_project_stats(
    project_id: str,
    request: RefreshStatsRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Обновить статистику для выбранных платформ через API"""
    logger.info(f"🔄 Starting stats refresh for project {project_id}, platforms: {request.platforms}")

    # Проверка что пользователь - админ
    if user['id'] not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Only admins can refresh stats")

    # 🧹 REDIS CACHE: Invalidate cache for this project (stats will be updated)
    cache.invalidate_project(project_id)
    logger.info(f"🧹 Invalidated cache for project {project_id} before refresh")

    # НЕМЕДЛЕННАЯ инициализация прогресса (до любых медленных операций!)
    try:
        # Получаем все аккаунты проекта
        accounts = project_manager.get_project_social_accounts(project_id)
        logger.info(f"📊 Found {len(accounts)} accounts in project")

        # Подсчитываем количество аккаунтов по платформам для прогресс-бара
        platform_stats = {}
        for platform in request.platforms:
            if request.platforms[platform]:
                count = sum(1 for acc in accounts if acc.get('platform', 'tiktok').lower() == platform)
                platform_stats[platform] = {'total': count, 'processed': 0, 'updated': 0, 'failed': 0}

        # Инициализируем прогресс в глобальном хранилище СРАЗУ
        refresh_progress[project_id] = platform_stats.copy()
        logger.info(f"🔧 IMMEDIATELY initialized refresh_progress[{project_id}] = {refresh_progress[project_id]}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize progress: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize progress: {str(e)}")

    # Теперь делаем остальные проверки
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    if not tiktok_api and not instagram_api and not facebook_api:
        raise HTTPException(status_code=503, detail="Stats API clients not available")

    # Получаем KPI проекта
    kpi_views = project.get('kpi_views', 1000)
    logger.info(f"📊 Project KPI: >= {kpi_views:,} просмотров на видео")

    # Запускаем обработку в фоне
    background_tasks.add_task(
        process_accounts_background,
        project_id=project_id,
        project=project,
        accounts=accounts,
        platforms=request.platforms,
        platform_stats=platform_stats,
        kpi_views=kpi_views,
        date_from=request.date_from,
        date_to=request.date_to
    )

    logger.info(f"✅ Background task started for project {project_id}")

    # Возвращаем успех СРАЗУ, чтобы polling мог начать получать прогресс
    return {
        "success": True,
        "message": "Stats refresh started in background",
        "total_accounts": len(accounts)
    }


def process_accounts_background(
    project_id: str,
    project: dict,
    accounts: list,
    platforms: dict,
    platform_stats: dict,
    kpi_views: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """
    Фоновая обработка аккаунтов с обновлением прогресса

    :param date_from: Дата начала периода (YYYY-MM-DD) - учитываются только видео после этой даты
    :param date_to: Дата окончания периода (YYYY-MM-DD) - учитываются только видео до этой даты
    """
    import time

    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 BACKGROUND TASK STARTED FOR PROJECT {project_id}")
    logger.info(f"📊 ПРОГРЕСС-БАР ОБНОВЛЕНИЯ СТАТИСТИКИ")
    logger.info(f"{'='*70}")
    for platform, stats in platform_stats.items():
        logger.info(f"   {platform.upper()}: 0/{stats['total']} аккаунтов")
    if date_from or date_to:
        logger.info(f"📅 Фильтр по датам: с {date_from or 'начала'} по {date_to or 'сегодня'}")
    logger.info(f"{'='*70}\n")

    updated_count = 0
    failed_count = 0
    errors = []

    for account in accounts:
        platform = account.get('platform', 'tiktok').lower()
        profile_link = account.get('profile_link', '')
        username = account.get('username', '')
        status = account.get('status', '').upper()

        # Пропускаем если платформа не выбрана для обновления
        if not platforms.get(platform, False):
            logger.info(f"⏭️ Skipping {platform} account {username} (platform not selected)")
            continue

        # Пропускаем аккаунты со статусом OLD
        if status == 'OLD':
            logger.info(f"⏭️ Skipping {platform} account {username} (status: OLD)")
            # Обновляем счетчик processed для прогресс-бара
            if platform in platform_stats:
                platform_stats[platform]['processed'] += 1
                refresh_progress[project_id][platform] = platform_stats[platform].copy()
            continue

        logger.info(f"🔄 Updating {platform} account: {username}")

        try:
            stats = None

            # Получаем статистику в зависимости от платформы (с KPI и датами фильтрации)
            if platform == 'tiktok' and tiktok_api:
                stats = tiktok_api.get_tiktok_data(profile_link, kpi_views=kpi_views, date_from=date_from, date_to=date_to)
            elif platform == 'instagram' and instagram_api:
                stats = instagram_api.get_instagram_data(profile_link, kpi_views=kpi_views, date_from=date_from, date_to=date_to)
            elif platform == 'facebook' and facebook_api:
                # Facebook использует другую структуру данных (Reels API)
                result = facebook_api.get_page_reels(profile_link, kpi_views=kpi_views, date_from=date_from, date_to=date_to)
                if result.get('success'):
                    # Преобразуем результат Facebook в общий формат
                    stats = {
                        'total_views': result.get('total_views', 0),
                        'total_likes': result.get('total_likes', 0),
                        'videos': result.get('total_videos', 0),
                        'reels': result.get('total_videos', 0),
                        'total_videos_fetched': result.get('total_videos', 0),
                        'total_reels_fetched': result.get('total_videos', 0),
                        'followers': 0,  # Facebook API не возвращает followers в Reels API
                        'likes': result.get('total_likes', 0)
                    }
                else:
                    stats = None
                    logger.error(f"❌ Facebook API error: {result.get('error', 'Unknown error')}")
            else:
                logger.warning(f"⚠️ Platform {platform} not supported yet")
                if platform in platform_stats:
                    platform_stats[platform]['processed'] += 1
                    platform_stats[platform]['failed'] += 1
                    # Обновляем глобальный прогресс
                    refresh_progress[project_id][platform] = platform_stats[platform].copy()
                continue

            if stats:
                # Обновляем в Google Sheets
                stats_dict = {
                    'followers': stats.get('followers', 0),
                    'likes': stats.get('likes', stats.get('total_likes', 0)),
                    'videos': stats.get('videos', stats.get('reels', 0)),
                    'views': stats.get('total_views', 0),
                    'comments': 0  # Не все API возвращают комментарии
                }
                project_sheets.update_account_stats(
                    project_name=project['name'],
                    username=username,
                    stats=stats_dict,
                    profile_link=profile_link  # Передаем URL для точного поиска в Sheets
                )

                # Создаем snapshot в SQLite
                project_manager.add_account_snapshot(
                    account_id=account['id'],
                    followers=stats.get('followers', 0),
                    likes=stats.get('likes', stats.get('total_likes', 0)),
                    comments=0,
                    videos=stats.get('videos', stats.get('reels', 0)),  # Видео прошедшие KPI
                    views=stats.get('total_views', 0),
                    total_videos_fetched=stats.get('total_videos_fetched', stats.get('total_reels_fetched', 0))  # Все видео
                )

                updated_count += 1

                # Обновляем прогресс-бар
                if platform in platform_stats:
                    platform_stats[platform]['processed'] += 1
                    platform_stats[platform]['updated'] += 1
                    # Обновляем глобальный прогресс
                    refresh_progress[project_id][platform] = platform_stats[platform].copy()
                    logger.info(f"🔄 Updated refresh_progress[{project_id}][{platform}] = {refresh_progress[project_id][platform]}")

                logger.info(f"✅ Updated {username}: {stats.get('total_views', 0)} views")

                # Логируем прогресс-бар после каждого обновления
                logger.info(f"\n{'='*70}")
                logger.info(f"📊 ПРОГРЕСС ОБНОВЛЕНИЯ:")
                logger.info(f"{'='*70}")
                for plt, pstats in platform_stats.items():
                    progress_percent = (pstats['processed'] / pstats['total'] * 100) if pstats['total'] > 0 else 0
                    logger.info(f"   {plt.upper()}: {pstats['processed']}/{pstats['total']} ({progress_percent:.0f}%) | ✅ {pstats['updated']} | ❌ {pstats['failed']}")
                logger.info(f"{'='*70}\n")

                # Задержка между аккаунтами (уменьшили с 2 до 1 сек)
                time.sleep(1)

        except Exception as e:
            failed_count += 1

            # Обновляем прогресс-бар
            if platform in platform_stats:
                platform_stats[platform]['processed'] += 1
                platform_stats[platform]['failed'] += 1
                # Обновляем глобальный прогресс
                refresh_progress[project_id][platform] = platform_stats[platform].copy()

            error_msg = f"Failed to update {username}: {str(e)}"
            errors.append(error_msg)
            logger.error(f"❌ {error_msg}")

            # Логируем прогресс-бар после ошибки
            logger.info(f"\n{'='*70}")
            logger.info(f"📊 ПРОГРЕСС ОБНОВЛЕНИЯ:")
            logger.info(f"{'='*70}")
            for plt, pstats in platform_stats.items():
                progress_percent = (pstats['processed'] / pstats['total'] * 100) if pstats['total'] > 0 else 0
                logger.info(f"   {plt.upper()}: {pstats['processed']}/{pstats['total']} ({progress_percent:.0f}%) | ✅ {pstats['updated']} | ❌ {pstats['failed']}")
            logger.info(f"{'='*70}\n")

            continue

    logger.info(f"✅ Stats refresh completed: {updated_count} updated, {failed_count} failed")

    # Финальный прогресс-бар
    logger.info(f"\n{'='*70}")
    logger.info(f"📊 ИТОГОВЫЙ ПРОГРЕСС:")
    logger.info(f"{'='*70}")
    for plt, pstats in platform_stats.items():
        logger.info(f"   {plt.upper()}: {pstats['total']} аккаунтов | ✅ {pstats['updated']} успешно | ❌ {pstats['failed']} ошибок")
    logger.info(f"{'='*70}\n")

    logger.info(f"🏁 BACKGROUND TASK COMPLETED FOR PROJECT {project_id}")

@app.post("/api/projects/{project_id}/migrate_platform_column")
async def migrate_platform_column(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Добавить колонку Platform в существующий Google Sheet и заполнить на основе URL"""
    logger.info(f"🔄 Starting platform column migration for project {project_id}")

    # Get project
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    try:
        import gspread
        worksheet = project_sheets.spreadsheet.worksheet(project['name'])

        # Проверяем есть ли уже колонка Platform
        headers = worksheet.row_values(1)
        logger.info(f"📊 Current headers: {headers}")

        if 'Platform' in headers:
            logger.info("✅ Platform column already exists")
            return {"success": True, "message": "Platform column already exists"}

        # Вставляем колонку Platform после Link (позиция C)
        worksheet.insert_cols([[]], col=3, value_input_option='RAW')

        # Обновляем заголовок
        worksheet.update_cell(1, 3, 'Platform')

        # Получаем все строки с данными
        all_rows = worksheet.get_all_values()

        updated_count = 0
        # Начинаем со 2-й строки (пропускаем заголовки)
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if len(row) < 2:  # Нет Link
                continue

            url = row[1].strip().lower()  # Link в колонке B
            platform = 'tiktok'  # Default

            # Определяем платформу по URL
            if 'tiktok.com' in url:
                platform = 'tiktok'
            elif 'instagram.com' in url:
                platform = 'instagram'
            elif 'facebook.com' in url or 'fb.com' in url:
                platform = 'facebook'
            elif 'youtube.com' in url or 'youtu.be' in url:
                platform = 'youtube'
            elif 'threads.net' in url:
                platform = 'threads'

            # Записываем платформу в колонку C
            worksheet.update_cell(row_idx, 3, platform)
            updated_count += 1
            logger.info(f"✅ Row {row_idx}: {url[:50]} -> {platform}")

        logger.info(f"✅ Migration completed: updated {updated_count} rows")

        return {
            "success": True,
            "updated": updated_count,
            "message": f"Platform column added and {updated_count} rows updated"
        }

    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"Worksheet {project['name']} not found")
    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@app.post("/api/projects/{project_id}/migrate_username_column")
async def migrate_username_column(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Добавить колонку Username в существующий Google Sheet и заполнить парсингом из Link"""
    logger.info(f"🔄 Starting username column migration for project {project_id}")

    # Get project
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    try:
        success = project_sheets.migrate_username_column(project['name'])

        if success:
            return {
                "success": True,
                "message": f"Username column migration completed for project {project['name']}"
            }
        else:
            raise HTTPException(status_code=500, detail="Migration failed")

    except Exception as e:
        logger.error(f"❌ Username migration error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Username migration failed: {str(e)}")

@app.post("/api/migrate_all_usernames")
async def migrate_all_usernames():
    """Мигрировать колонку Username для ВСЕХ проектов (без авторизации, для одноразового запуска)"""
    logger.info("🔄 Starting migration for ALL projects")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    # Получаем все листы в таблице
    try:
        all_sheets = project_sheets.spreadsheet.worksheets()
        results = []

        for sheet in all_sheets:
            project_name = sheet.title
            logger.info(f"🔄 Migrating project: {project_name}")

            try:
                success = project_sheets.migrate_username_column(project_name)
                results.append({
                    "project": project_name,
                    "success": success,
                    "message": "Migration completed" if success else "Migration failed"
                })
            except Exception as e:
                logger.error(f"❌ Error migrating {project_name}: {e}")
                results.append({
                    "project": project_name,
                    "success": False,
                    "error": str(e)
                })

        logger.info(f"✅ Migration completed for {len(results)} projects")

        return {
            "success": True,
            "total_projects": len(results),
            "results": results
        }

    except Exception as e:
        logger.error(f"❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@app.post("/api/save_daily_snapshots")
@app.post("/api/save_hourly_snapshots")  # Alias для часового обновления
async def save_daily_snapshots(cron_secret: Optional[str] = None):
    """
    Сохранить снимки статистики для всех аккаунтов из Google Sheets
    Вызывается каждый час через внешний cron (cron-job.org, uptimerobot и т.д.)

    Optional: добавь ?cron_secret=YOUR_SECRET для дополнительной защиты
    """
    logger.info("📊 Starting hourly snapshots save...")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    results = {
        "total_projects": 0,
        "total_accounts": 0,
        "saved_snapshots": 0,
        "errors": []
    }

    try:
        # Получаем все проекты
        all_projects = project_manager.get_all_projects()
        results["total_projects"] = len(all_projects)

        for project in all_projects:
            project_id = project['id']
            project_name = project['name']

            logger.info(f"📊 Processing project: {project_name}")

            try:
                # Получаем данные из Google Sheets
                accounts_data = project_sheets.get_project_accounts(project_name)

                for account_data in accounts_data:
                    results["total_accounts"] += 1

                    # Извлекаем данные
                    profile_link = account_data.get('Link', '').strip()
                    if not profile_link:
                        continue

                    # Находим аккаунт в SQLite по profile_link
                    sqlite_accounts = project_manager.get_project_social_accounts(project_id)
                    matching_account = next((acc for acc in sqlite_accounts if acc['profile_link'] == profile_link), None)

                    if not matching_account:
                        logger.warning(f"⚠️ Account not found in SQLite: {profile_link}")
                        continue

                    # Сохраняем snapshot
                    success = project_manager.add_account_snapshot(
                        account_id=matching_account['id'],
                        followers=int(account_data.get('Followers', 0) or 0),
                        likes=int(account_data.get('Likes', 0) or 0),
                        comments=0,  # Нет в Sheets
                        videos=int(account_data.get('Videos', 0) or 0),
                        views=int(account_data.get('Views', 0) or 0)
                    )

                    if success:
                        results["saved_snapshots"] += 1
                    else:
                        results["errors"].append(f"Failed to save snapshot for {profile_link}")

            except Exception as e:
                error_msg = f"Error processing project {project_name}: {str(e)}"
                logger.error(f"❌ {error_msg}")
                results["errors"].append(error_msg)

        logger.info(f"✅ Hourly snapshots saved: {results['saved_snapshots']}/{results['total_accounts']}")

        return {
            "success": True,
            "message": f"Saved {results['saved_snapshots']} snapshots for {results['total_accounts']} accounts across {results['total_projects']} projects",
            "timestamp": datetime.now().isoformat(),
            **results
        }

    except Exception as e:
        logger.error(f"❌ Hourly snapshots error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Hourly snapshots failed: {str(e)}")

@app.get("/api/list_all_projects")
async def list_all_projects():
    """Показать все проекты с ID (без авторизации, для дебага)"""
    projects = project_manager.get_all_projects()

    result = []
    for project in projects:
        result.append({
            "id": project['id'],
            "name": project['name'],
            "is_active": project.get('is_active', True),
            "is_finished": project.get('is_finished', False)
        })

    return {"success": True, "projects": result}

@app.post("/api/projects/{project_id}/generate_test_history")
async def generate_test_history(
    project_id: str,
    days: int = 14
):
    """
    Генерация тестовых исторических данных для проекта (для демо/тестирования)

    :param project_id: ID проекта
    :param days: Количество дней истории (по умолчанию 14)
    """
    logger.info(f"📊 Generating test history for project {project_id} ({days} days)")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets not available")

    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        import random

        # Получаем текущие данные из Google Sheets
        accounts_data = project_sheets.get_project_accounts(project['name'])

        results = {
            "project": project['name'],
            "days_generated": days,
            "accounts_processed": 0,
            "snapshots_created": 0
        }

        # Получаем аккаунты из SQLite
        sqlite_accounts = project_manager.get_project_social_accounts(project_id)

        for account_data in accounts_data:
            profile_link = account_data.get('Link', '').strip()
            if not profile_link:
                continue

            # Находим соответствующий аккаунт в SQLite
            matching_account = next((acc for acc in sqlite_accounts if acc['profile_link'] == profile_link), None)
            if not matching_account:
                continue

            results["accounts_processed"] += 1

            # Текущие значения из Sheets
            current_followers = int(account_data.get('Followers', 0) or 0)
            current_likes = int(account_data.get('Likes', 0) or 0)
            current_videos = int(account_data.get('Videos', 0) or 0)
            current_views = int(account_data.get('Views', 0) or 0)

            # Генерируем историю от (days) дней назад до сегодня
            for day_offset in range(days, -1, -1):
                snapshot_date = datetime.now() - timedelta(days=day_offset)

                # Рассчитываем значения для этого дня (симуляция роста)
                # Чем дальше в прошлое, тем меньше значения
                progress = 1 - (day_offset / days)  # 0 в начале, 1 сегодня

                # Добавляем случайность для реалистичности (±10%)
                random_factor = 1 + random.uniform(-0.1, 0.1)

                day_followers = int(current_followers * progress * random_factor)
                day_likes = int(current_likes * progress * random_factor)
                day_videos = int(current_videos * progress * random_factor)
                day_views = int(current_views * progress * random_factor)

                # Сохраняем snapshot
                success = project_manager.add_account_snapshot(
                    account_id=matching_account['id'],
                    followers=day_followers,
                    likes=day_likes,
                    comments=0,
                    videos=day_videos,
                    views=day_views
                )

                if success:
                    results["snapshots_created"] += 1
                    # Обновляем время snapshot в базе на правильную дату
                    project_manager.db.cursor.execute('''
                        UPDATE account_snapshots
                        SET snapshot_time = ?
                        WHERE account_id = ? AND snapshot_time = (
                            SELECT MAX(snapshot_time) FROM account_snapshots WHERE account_id = ?
                        )
                    ''', (snapshot_date.isoformat(), matching_account['id'], matching_account['id']))
                    project_manager.db.conn.commit()

        logger.info(f"✅ Test history generated: {results['snapshots_created']} snapshots for {results['accounts_processed']} accounts")

        return {
            "success": True,
            "message": f"Generated {results['snapshots_created']} test snapshots across {days} days for {results['accounts_processed']} accounts",
            **results
        }

    except Exception as e:
        logger.error(f"❌ Test history generation error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Test history generation failed: {str(e)}")

@app.get("/api/projects/{project_id}/debug_snapshots")
async def debug_project_snapshots(project_id: str):
    """Debug endpoint to check snapshots and dates for a project"""
    try:
        # Get project info
        project = project_manager.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get accounts for this project
        project_manager.db.cursor.execute('''
            SELECT id, username, profile_link, platform
            FROM project_social_accounts
            WHERE project_id = ? AND is_active = 1
        ''', (project_id,))
        accounts = [{'id': row[0], 'username': row[1], 'link': row[2], 'platform': row[3]}
                   for row in project_manager.db.cursor.fetchall()]

        # Get snapshot date range for each account
        snapshot_info = []
        for account in accounts:
            project_manager.db.cursor.execute('''
                SELECT
                    MIN(DATE(snapshot_time)) as first_date,
                    MAX(DATE(snapshot_time)) as last_date,
                    COUNT(*) as snapshot_count
                FROM account_snapshots
                WHERE account_id = ?
            ''', (account['id'],))
            result = project_manager.db.cursor.fetchone()
            snapshot_info.append({
                'account': account['username'],
                'platform': account['platform'],
                'first_snapshot': result[0] if result else None,
                'last_snapshot': result[1] if result else None,
                'snapshot_count': result[2] if result else 0
            })

        return {
            "project": {
                "id": project['id'],
                "name": project['name'],
                "start_date": project.get('start_date'),
                "end_date": project.get('end_date'),
                "target_views": project.get('target_views', 0),
                "kpi_views": project.get('kpi_views', 1000)
            },
            "accounts": snapshot_info,
            "total_accounts": len(accounts)
        }

    except Exception as e:
        logger.error(f"❌ Debug endpoint error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/fix_dates_for_test_data")
async def fix_project_dates_for_test_data(project_id: str):
    """Update project start_date to match the earliest snapshot (for test data)"""
    try:
        # Get project info
        project = project_manager.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get accounts for this project
        project_manager.db.cursor.execute('''
            SELECT id FROM project_social_accounts
            WHERE project_id = ? AND is_active = 1
        ''', (project_id,))
        account_ids = [row[0] for row in project_manager.db.cursor.fetchall()]

        if not account_ids:
            raise HTTPException(status_code=400, detail="No accounts found for project")

        # Find the earliest snapshot date
        placeholders = ','.join('?' * len(account_ids))
        project_manager.db.cursor.execute(f'''
            SELECT MIN(DATE(snapshot_time)) as earliest_date
            FROM account_snapshots
            WHERE account_id IN ({placeholders})
        ''', account_ids)
        result = project_manager.db.cursor.fetchone()
        earliest_date = result[0] if result and result[0] else None

        if not earliest_date:
            raise HTTPException(status_code=400, detail="No snapshots found for project")

        # Update project start_date
        old_start_date = project.get('start_date')
        project_manager.db.cursor.execute('''
            UPDATE projects
            SET start_date = ?
            WHERE id = ?
        ''', (earliest_date, project_id))
        project_manager.db.conn.commit()

        return {
            "success": True,
            "message": f"Updated project start_date from {old_start_date} to {earliest_date}",
            "old_start_date": old_start_date,
            "new_start_date": earliest_date
        }

    except Exception as e:
        logger.error(f"❌ Fix dates error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/update_target_views")
async def update_project_target_views(project_id: str, target_views: int):
    """Update project target_views"""
    try:
        # Get project info
        project = project_manager.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Update target_views
        old_target = project.get('target_views', 0)
        project_manager.db.cursor.execute('''
            UPDATE projects
            SET target_views = ?
            WHERE id = ?
        ''', (target_views, project_id))
        project_manager.db.conn.commit()

        return {
            "success": True,
            "message": f"Updated target_views from {old_target} to {target_views}",
            "old_target_views": old_target,
            "new_target_views": target_views
        }

    except Exception as e:
        logger.error(f"❌ Update target_views error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/clear_snapshots")
async def clear_project_snapshots(project_id: str, keep_last_n: int = 0):
    """Clear snapshots for a project, optionally keeping last N snapshots per account"""
    try:
        # Get project info
        project = project_manager.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get accounts for this project
        project_manager.db.cursor.execute('''
            SELECT id FROM project_social_accounts
            WHERE project_id = ? AND is_active = 1
        ''', (project_id,))
        account_ids = [row[0] for row in project_manager.db.cursor.fetchall()]

        if not account_ids:
            raise HTTPException(status_code=400, detail="No accounts found for project")

        total_deleted = 0

        if keep_last_n == 0:
            # Delete all snapshots for these accounts
            placeholders = ','.join('?' * len(account_ids))
            project_manager.db.cursor.execute(f'''
                DELETE FROM account_snapshots
                WHERE account_id IN ({placeholders})
            ''', account_ids)
            total_deleted = project_manager.db.cursor.rowcount
        else:
            # Keep last N snapshots per account
            for account_id in account_ids:
                # Get IDs to keep
                project_manager.db.cursor.execute(f'''
                    SELECT id FROM account_snapshots
                    WHERE account_id = ?
                    ORDER BY snapshot_time DESC
                    LIMIT {keep_last_n}
                ''', (account_id,))
                keep_ids = [row[0] for row in project_manager.db.cursor.fetchall()]

                if keep_ids:
                    keep_placeholders = ','.join('?' * len(keep_ids))
                    project_manager.db.cursor.execute(f'''
                        DELETE FROM account_snapshots
                        WHERE account_id = ? AND id NOT IN ({keep_placeholders})
                    ''', [account_id] + keep_ids)
                else:
                    # No snapshots to keep, delete all
                    project_manager.db.cursor.execute('''
                        DELETE FROM account_snapshots
                        WHERE account_id = ?
                    ''', (account_id,))

                total_deleted += project_manager.db.cursor.rowcount

        project_manager.db.conn.commit()

        return {
            "success": True,
            "message": f"Deleted {total_deleted} snapshots for project {project['name']}",
            "project_id": project_id,
            "project_name": project['name'],
            "snapshots_deleted": total_deleted,
            "kept_per_account": keep_last_n
        }

    except Exception as e:
        logger.error(f"❌ Clear snapshots error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Полное удаление проекта (только для администраторов)"""
    user_id = str(user.get('id'))

    # Проверка прав администратора
    if user_id not in [str(admin_id) for admin_id in ADMIN_IDS]:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Проверяем, существует ли проект
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # STEP 1: Пытаемся удалить лист из Google Sheets ПЕРЕД удалением из БД
    # (чтобы избежать orphan sheets если БД удалена, но sheet остался)
    sheet_deletion_failed = False
    if project_sheets:
        try:
            logger.info(f"🔄 Attempting to delete Google Sheet for project '{project['name']}'...")
            project_sheets.delete_project_sheet(project['name'])
            logger.info(f"✅ Google Sheet '{project['name']}' deleted successfully")
        except Exception as e:
            sheet_deletion_failed = True
            logger.error(
                f"{'='*80}\n"
                f"⚠️⚠️⚠️ CRITICAL WARNING ⚠️⚠️⚠️\n"
                f"Failed to delete Google Sheet '{project['name']}' after retries!\n"
                f"Error: {e}\n"
                f"The project will still be deleted from the database to prevent phantom projects.\n"
                f"MANUAL ACTION REQUIRED: Delete the orphan Google Sheet '{project['name']}' manually!\n"
                f"{'='*80}"
            )
            # Continue with DB deletion despite sheet deletion failure

    # STEP 2: Удаляем проект из БД (даже если Google Sheet не удалился)
    success = project_manager.delete_project_fully(project_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete project from database")

    # Log final status
    if sheet_deletion_failed:
        logger.warning(
            f"⚠️ Project {project_id} deleted from DB by admin {user_id}, "
            f"but Google Sheet '{project['name']}' may still exist!"
        )
    else:
        logger.info(f"✅ Project {project_id} fully deleted (DB + Sheet) by admin {user_id}")

    return {"success": True, "message": "Project deleted successfully"}

@app.post("/api/projects/{project_id}/finish")
async def finish_project(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Завершение проекта (только для администраторов)"""
    user_id = str(user.get('id'))

    # Проверка прав администратора
    if user_id not in [str(admin_id) for admin_id in ADMIN_IDS]:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Проверяем, существует ли проект
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Завершаем проект (is_active = 0)
    success = project_manager.finish_project(project_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to finish project")

    logger.info(f"✅ Project {project_id} finished by admin {user_id}")
    return {"success": True, "message": "Project finished successfully"}

@app.get("/api/accounts/{account_id}")
async def get_social_account(
    account_id: str,
    user: dict = Depends(get_current_user)
):
    """Получить данные социального аккаунта"""
    account = project_manager.get_social_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"success": True, "account": account}

@app.put("/api/accounts/{account_id}")
async def update_social_account(
    account_id: str,
    updates: SocialAccountUpdate,
    user: dict = Depends(get_current_user)
):
    """Обновить данные социального аккаунта"""
    # Получаем текущие данные аккаунта
    account = project_manager.get_social_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Обновляем в БД
    update_data = {k: v for k, v in updates.dict().items() if v is not None}
    success = project_manager.update_social_account(account_id, **update_data)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update account")

    return {"success": True, "message": "Account updated successfully"}

@app.delete("/api/accounts/{account_id}")
async def delete_social_account(
    account_id: str,
    user: dict = Depends(get_current_user)
):
    """Удалить социальный аккаунт из проекта"""
    # Получаем данные аккаунта и проекта
    account = project_manager.get_social_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    project = project_manager.get_project(account['project_id'])

    # Удаляем из БД
    success = project_manager.remove_social_account_from_project(account_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete account")

    # Удаляем из Google Sheets (если включено)
    if project_sheets and project:
        try:
            # Используем profile_link для точного поиска в колонке Link
            project_sheets.remove_account_from_sheet(project['name'], account['profile_link'])
            logger.info(f"✅ Аккаунт {account['profile_link']} удален из Google Sheets")
        except Exception as e:
            logger.error(f"⚠️ Ошибка удаления из Google Sheets: {e}")

    return {"success": True, "message": "Account deleted successfully"}

@app.post("/api/accounts/{account_id}/snapshot")
async def add_account_snapshot(
    account_id: str,
    snapshot: AccountSnapshot,
    user: dict = Depends(get_current_user)
):
    """Добавить снимок статистики аккаунта"""
    # Получаем данные аккаунта
    account = project_manager.get_social_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Добавляем снимок в БД
    success = project_manager.add_account_snapshot(
        account_id=account_id,
        followers=snapshot.followers,
        likes=snapshot.likes,
        comments=snapshot.comments,
        videos=snapshot.videos,
        views=snapshot.views
    )

    if not success:
        raise HTTPException(status_code=400, detail="Failed to add snapshot")

    # Обновляем в Google Sheets (если включено)
    if project_sheets:
        try:
            project = project_manager.get_project(account['project_id'])
            if project:
                project_sheets.update_account_stats(
                    project['name'],
                    account['username'],
                    snapshot.dict()
                )
        except Exception as e:
            print(f"⚠️  Ошибка обновления Google Sheets: {e}")

    return {"success": True, "message": "Snapshot added successfully"}

@app.get("/api/accounts/{account_id}/snapshots")
async def get_account_snapshots(
    account_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user)
):
    """Получить снимки статистики аккаунта"""
    snapshots = project_manager.get_account_snapshots(
        account_id, start_date, end_date, limit
    )
    return {"success": True, "snapshots": snapshots}

@app.get("/api/accounts/{account_id}/daily-stats")
async def get_account_daily_stats(
    account_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Получить ежедневную статистику аккаунта с приростом"""
    stats = project_manager.get_account_daily_stats(
        account_id, start_date, end_date
    )
    return {"success": True, "stats": stats}

@app.post("/api/projects/{project_id}/import_from_sheets")
async def import_from_sheets(
    project_id: str,
    user: dict = Depends(get_current_user)
):
    """Импортировать данные из Google Sheets в БД (Reverse Sync)"""
    # Проверяем доступ к проекту
    user_id = str(user.get('id'))
    user_projects = project_manager.get_user_projects(user_id)
    if not any(p['id'] == project_id for p in user_projects):
        raise HTTPException(status_code=403, detail="Access denied")

    # Получаем проект
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project_sheets:
        raise HTTPException(status_code=503, detail="Google Sheets integration not available")

    try:
        # Читаем данные из Google Sheet
        sheet_data = project_sheets.read_project_sheet(project['name'])

        if not sheet_data:
            return {
                "success": True,
                "message": "No data found in Google Sheet",
                "imported_count": 0,
                "updated_count": 0
            }

        imported_count = 0
        updated_count = 0

        for row in sheet_data:
            try:
                username = row.get('@Username', '').strip()
                link = row.get('Link', '').strip()

                if not username and not link:
                    continue

                # Пытаемся найти аккаунт в БД по username или link
                accounts = project_manager.get_project_social_accounts(project_id)
                matching_account = None

                for acc in accounts:
                    if (username and acc.get('username') == username) or \
                       (link and acc.get('profile_link') == link):
                        matching_account = acc
                        break

                if matching_account:
                    # Обновляем существующий аккаунт через snapshot
                    followers = int(row.get('Followers', 0) or 0)
                    likes = int(row.get('Likes', 0) or 0)
                    comments = int(row.get('Comments', 0) or 0)
                    videos = int(row.get('Videos', 0) or 0)
                    views = int(row.get('Views', 0) or 0)

                    # Добавляем snapshot
                    success = project_manager.add_account_snapshot(
                        account_id=matching_account['id'],
                        followers=followers,
                        likes=likes,
                        comments=comments,
                        videos=videos,
                        views=views
                    )

                    if success:
                        updated_count += 1
                        logger.info(f"Updated account {username or link} from Sheets")
                else:
                    # Аккаунт не найден - можно создать новый (опционально)
                    logger.warning(f"Account {username or link} not found in DB, skipping")

            except Exception as e:
                logger.error(f"Error importing row: {e}")
                continue

        return {
            "success": True,
            "message": f"Import completed: {updated_count} accounts updated",
            "imported_count": imported_count,
            "updated_count": updated_count
        }

    except Exception as e:
        logger.error(f"Error importing from sheets: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@app.post("/api/admin/force_migration")
async def force_database_migration():
    """
    Force database migration to add missing columns (ADMIN ONLY)

    This endpoint manually adds the total_videos_fetched column to account_snapshots
    if it's missing. Useful for fixing production databases.
    """
    try:
        logger.info("🔧 [ADMIN] Force migration requested")

        # Check if table exists
        db.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='account_snapshots'"
        )

        if not db.cursor.fetchone():
            return {
                "success": False,
                "message": "Table account_snapshots does not exist"
            }

        # Check current columns
        db.cursor.execute("PRAGMA table_info(account_snapshots)")
        columns = [column[1] for column in db.cursor.fetchall()]
        logger.info(f"🔍 Current columns in account_snapshots: {columns}")

        # Check if migration needed
        if 'total_videos_fetched' in columns:
            return {
                "success": True,
                "message": "Column total_videos_fetched already exists",
                "columns": columns
            }

        # Add the column
        logger.info("➕ Adding column total_videos_fetched to account_snapshots...")
        db.cursor.execute('ALTER TABLE account_snapshots ADD COLUMN total_videos_fetched INTEGER DEFAULT 0')
        db.conn.commit()
        logger.info("✅ Column total_videos_fetched added successfully")

        # Verify
        db.cursor.execute("PRAGMA table_info(account_snapshots)")
        new_columns = [column[1] for column in db.cursor.fetchall()]

        return {
            "success": True,
            "message": "Migration completed successfully",
            "columns_before": columns,
            "columns_after": new_columns
        }

    except Exception as e:
        logger.error(f"❌ Force migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")


@app.post("/api/admin/smart_sync")
async def trigger_smart_sync(project_id: Optional[str] = None):
    """
    Trigger smart sync manually or via cron job

    This endpoint can be called:
    - Manually for testing
    - By Render Cron Jobs (free tier alternative to Celery Beat)
    - By any external scheduler

    Query params:
        project_id (optional): Sync specific project, or all projects if not provided

    Returns:
        Sync results with statistics
    """
    try:
        logger.info(f"🔄 [ADMIN] Smart sync triggered via HTTP (project_id={project_id})")

        from config import DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS_JSON
        from smart_sync import sync_all_projects_standalone, sync_single_project_standalone

        if project_id:
            # Sync single project
            result = sync_single_project_standalone(
                db=db,
                sheets_credentials=GOOGLE_SHEETS_CREDENTIALS_JSON,
                sheets_name=DEFAULT_GOOGLE_SHEETS_NAME,
                project_id=project_id
            )
            logger.info(f"✅ [ADMIN] Smart sync completed for project {project_id}")
        else:
            # Sync all projects
            result = sync_all_projects_standalone(
                db=db,
                sheets_credentials=GOOGLE_SHEETS_CREDENTIALS_JSON,
                sheets_name=DEFAULT_GOOGLE_SHEETS_NAME
            )
            logger.info(f"✅ [ADMIN] Smart sync completed for all projects")

        return result

    except Exception as e:
        logger.error(f"❌ Smart sync failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Smart sync failed: {str(e)}")


@app.get("/api/admin/sync_status")
async def get_sync_status():
    """
    Get sync status and statistics

    Returns information about:
    - Total projects
    - Active projects
    - Last sync time (if available)
    - Cache status

    Useful for monitoring and debugging
    """
    try:
        from project_manager import ProjectManager

        pm = ProjectManager(db)

        # Get project counts
        all_projects = pm.get_all_projects()
        active_projects = [p for p in all_projects if p.get('is_active', 1) == 1]

        # Check cache status
        from cache import cache

        return {
            "success": True,
            "total_projects": len(all_projects),
            "active_projects": len(active_projects),
            "cache_enabled": cache.enabled,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Failed to get sync status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


# ============ EMAIL FARM ENDPOINTS ============

@app.post("/api/admin/emails/upload")
async def admin_upload_email_account(
    data: EmailAccountUpload,
    x_telegram_init_data: str = Header(None)
):
    """
    [ADMIN ONLY] Upload single email account to farm

    Body:
    - email: Email address
    - password: Plain password (will be encrypted)
    - proxy: Optional proxy string (socks5://user:pass@ip:port)
    - project_id: Optional project ID
    """
    if not email_farm_db or not email_encryption:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    # Check admin
    if user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        # Encrypt password
        encrypted_password = email_encryption.encrypt(data.password)

        # Save to database
        email_id = email_farm_db.add_email_account(
            email=data.email,
            password_encrypted=encrypted_password,
            proxy_string=data.proxy,
            project_id=data.project_id
        )

        if not email_id:
            raise HTTPException(status_code=400, detail="Email already exists")

        logger.info(f"✅ [ADMIN {user_id}] Added email: {data.email}")

        return {
            "success": True,
            "email_id": email_id,
            "email": data.email,
            "status": "free"
        }

    except Exception as e:
        logger.error(f"❌ Failed to upload email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/emails/bulk_upload")
async def admin_bulk_upload_emails(
    data: EmailAccountBulkUpload,
    x_telegram_init_data: str = Header(None)
):
    """
    [ADMIN ONLY] Bulk upload email accounts

    Accepts text format:
    email:password:proxy
    or
    email:password

    Example:
    accounts: [
        {email: "test1@outlook.com", password: "pass123", proxy: "socks5://user:pass@ip:port"},
        {email: "test2@outlook.com", password: "pass456"}
    ]
    """
    if not email_farm_db or not email_encryption:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    # Check admin
    if user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    results = {
        "success": 0,
        "failed": 0,
        "errors": []
    }

    for account in data.accounts:
        try:
            # Encrypt password (for password auth or as placeholder)
            encrypted_password = email_encryption.encrypt(account.password) if account.password else ""

            # Encrypt OAuth2 tokens if provided
            encrypted_refresh_token = None
            if account.refresh_token:
                encrypted_refresh_token = email_encryption.encrypt(account.refresh_token)

            # Save to database
            email_id = email_farm_db.add_email_account(
                email=account.email,
                password_encrypted=encrypted_password,
                proxy_string=account.proxy,
                project_id=account.project_id,
                refresh_token_encrypted=encrypted_refresh_token,
                client_id=account.client_id,
                auth_type=account.auth_type
            )

            if email_id:
                results["success"] += 1
                logger.info(f"✅ [BULK] Added: {account.email} (auth_type: {account.auth_type})")

                # Log to Google Sheets (PostBD) - новая почта в статусе free
                if email_sheets:
                    try:
                        email_sheets.log_new_email(
                            sheet_name="Post",
                            email=account.email,
                            has_proxy=bool(account.proxy)
                        )
                        # Небольшая задержка между API вызовами для избежания rate limit
                        await asyncio.sleep(0.3)
                    except Exception as sheet_error:
                        logger.warning(f"⚠️ Failed to log bulk upload to PostBD: {sheet_error}")
            else:
                results["failed"] += 1
                results["errors"].append(f"{account.email}: Already exists")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{account.email}: {str(e)}")
            logger.error(f"❌ Failed to add {account.email}: {e}")

    logger.info(f"✅ [ADMIN {user_id}] Bulk upload: {results['success']} success, {results['failed']} failed")

    return results


@app.post("/api/admin/emails/set_limit")
async def admin_set_user_email_limit(
    data: SetUserEmailLimit,
    x_telegram_init_data: str = Header(None)
):
    """
    [ADMIN ONLY] Set user email access limit

    Body:
    - user_id: Telegram user ID
    - max_emails: Maximum active emails allowed
    - can_access: Whether user can access emails
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate admin
    user_data = validate_telegram_init_data(x_telegram_init_data)
    admin_id = user_data['id']

    if admin_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        success = email_farm_db.set_user_limit(
            user_id=data.user_id,
            max_emails=data.max_emails,
            can_access=data.can_access
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to set limit")

        logger.info(f"✅ [ADMIN {admin_id}] Set limit for user {data.user_id}: {data.max_emails} emails")

        return {
            "success": True,
            "user_id": data.user_id,
            "max_emails": data.max_emails,
            "can_access": data.can_access
        }

    except Exception as e:
        logger.error(f"❌ Failed to set user limit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/emails/stats")
async def admin_get_email_stats(x_telegram_init_data: str = Header(None)):
    """
    [ADMIN ONLY] Get email farm statistics

    Returns:
    - total_emails
    - free
    - active
    - banned
    - archived
    - users_with_access
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate admin
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    if user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        stats = email_farm_db.get_stats()
        logger.info(f"📊 [ADMIN {user_id}] Requested email stats")
        return stats

    except Exception as e:
        logger.error(f"❌ Failed to get email stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/emails/clear_all")
async def admin_clear_all_emails(x_telegram_init_data: str = Header(None)):
    """
    [ADMIN ONLY] Clear all emails from Email Farm database

    Deletes:
    - All email accounts
    - All email history records

    Returns:
    - deleted_emails: number of deleted email accounts
    - deleted_history: number of deleted history records
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate admin
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    if user_id not in ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        cursor = email_farm_db.conn.cursor()

        # Delete all email history
        cursor.execute("DELETE FROM email_history")
        deleted_history = cursor.rowcount

        # Delete all email accounts
        cursor.execute("DELETE FROM email_accounts")
        deleted_emails = cursor.rowcount

        email_farm_db.conn.commit()

        logger.warning(f"🗑️ [ADMIN {user_id}] CLEARED ALL EMAIL FARM DATA: {deleted_emails} emails, {deleted_history} history records")

        return {
            "success": True,
            "deleted_emails": deleted_emails,
            "deleted_history": deleted_history
        }

    except Exception as e:
        logger.error(f"❌ Failed to clear emails: {e}")
        email_farm_db.conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============ USER EMAIL FARM ENDPOINTS ============

@app.get("/api/emails/my_list")
async def get_my_emails(x_telegram_init_data: str = Header(None)):
    """
    Get list of emails assigned to current user

    Returns list of emails with:
    - id
    - email
    - status
    - assigned_at
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    try:
        # Check user access
        limit_info = email_farm_db.get_user_limit(user_id)
        if not limit_info.get('can_access_emails'):
            raise HTTPException(status_code=403, detail="Email access disabled for this user")

        # Get user's emails
        emails = email_farm_db.get_user_emails(user_id)

        # Hide proxy info from response
        for email in emails:
            email.pop('proxy_string', None)

        logger.info(f"📋 User {user_id} has {len(emails)} emails")

        return {
            "success": True,
            "emails": emails,
            "limit": limit_info
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get user emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/emails/allocate")
async def allocate_email_to_me(x_telegram_init_data: str = Header(None)):
    """
    Allocate free email to current user

    Checks user limits before allocation
    Returns allocated email info (without password)
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    try:
        # Check if user is participant in at least one ACTIVE (not finished) project
        user_projects = project_manager.get_user_projects(str(user_id))
        has_active_project = any(
            project.get('is_active') and not project.get('is_finished')
            for project in user_projects
        )

        if not has_active_project:
            logger.warning(f"⚠️ User {user_id} tried to allocate email but has no active projects")
            raise HTTPException(
                status_code=403,
                detail="Вы можете запросить почту только если являетесь участником активного проекта"
            )

        # Check user access
        limit_info = email_farm_db.get_user_limit(user_id)
        if not limit_info.get('can_access_emails'):
            raise HTTPException(status_code=403, detail="Email access disabled")

        # Check if user reached limit
        active_count = email_farm_db.get_user_active_count(user_id)
        max_allowed = limit_info.get('max_active_emails', 5)

        if active_count >= max_allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Email limit reached ({active_count}/{max_allowed})"
            )

        # Get free email
        free_email = email_farm_db.get_free_email()
        if not free_email:
            raise HTTPException(status_code=404, detail="No free emails available")

        # Allocate to user
        success = email_farm_db.allocate_email_to_user(free_email['id'], user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to allocate email")

        logger.info(f"✅ User {user_id} allocated email: {free_email['email']}")

        # Log to Google Sheets (PostBD)
        if email_sheets:
            try:
                # Получаем username пользователя
                username = user_data.get('username', f"user_{user_id}")

                logger.info(f"📊 Logging allocation to PostBD: {free_email['email']} for user {username}")

                # Логируем выделение почты (лист = название листа MainBD или Post)
                # Используем "Post" как название листа
                email_sheets.log_email_allocation(
                    sheet_name="Post",
                    email=free_email['email'],
                    user_id=user_id,
                    username=username,
                    has_proxy=bool(free_email.get('proxy_string'))
                )
                logger.info(f"✅ PostBD logging successful for {free_email['email']}")
            except Exception as sheet_error:
                logger.error(f"❌ Failed to log email allocation to PostBD: {sheet_error}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.warning("⚠️ Email Sheets Manager not initialized - skipping PostBD logging")

        # Return without password/proxy
        return {
            "success": True,
            "email_id": free_email['id'],
            "email": free_email['email'],
            "status": "active",
            "active_count": active_count + 1,
            "max_allowed": max_allowed
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to allocate email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/emails/{email_id}/check_code")
async def check_email_for_code(
    email_id: int,
    x_telegram_init_data: str = Header(None)
):
    """
    Check latest email and extract verification code

    Connects to Outlook via IMAP (through proxy)
    Runs smart filter for security
    Returns extracted code if safe
    """
    if not email_farm_db or not email_encryption or not email_filter:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    try:
        # Get email account
        email_account = email_farm_db.get_email_by_id(email_id)
        if not email_account:
            raise HTTPException(status_code=404, detail="Email not found")

        # Verify ownership
        if email_account['assigned_user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Email not assigned to you")

        # Check status
        if email_account['status'] != 'active':
            raise HTTPException(status_code=400, detail=f"Email status: {email_account['status']}")

        # Выбираем правильный IMAP клиент в зависимости от auth_type
        auth_type = email_account.get('auth_type', 'password')

        if auth_type == 'oauth2':
            # OAuth2 аутентификация
            if not email_account.get('refresh_token_encrypted') or not email_account.get('client_id'):
                raise HTTPException(status_code=400, detail="OAuth2 credentials missing")

            # Расшифровываем refresh token
            refresh_token = email_encryption.decrypt(email_account['refresh_token_encrypted'])

            # Создаем OAuth2 IMAP клиент
            imap_client = OutlookOAuth2IMAPClient(
                email=email_account['email'],
                refresh_token=refresh_token,
                client_id=email_account['client_id'],
                proxy_string=email_account.get('proxy_string')
            )
        else:
            # Обычная password аутентификация
            plain_password = email_encryption.decrypt(email_account['password_encrypted'])

            imap_client = OutlookIMAPClient(
                email=email_account['email'],
                password=plain_password,
                proxy_string=email_account.get('proxy_string')
            )

        # Fetch latest emails
        # Для OAuth2: используем Outlook REST API (работает лучше с прокси)
        # Для password: используем IMAP
        if email_account['auth_type'] == 'oauth2':
            logger.info(f"📨 Используем Outlook REST API v2.0 для получения писем (OAuth2)")
            emails = await imap_client.get_latest_emails_graph_api(limit=5)
        else:
            # Подключаемся к IMAP для password auth
            logger.info(f"📨 Используем IMAP для получения писем (password)")
            connected = await imap_client.connect()
            if not connected:
                raise HTTPException(status_code=500, detail="Failed to connect to email")

            emails = await imap_client.get_latest_emails(limit=5)
            await imap_client.disconnect()

        if not emails:
            # Log to Google Sheets (PostBD) - no emails
            if email_sheets:
                try:
                    email_sheets.log_email_check(
                        sheet_name="Post",
                        email=email_account['email'],
                        found_code=False,
                        is_safe=True,
                        subject="📭 No new emails"
                    )
                except Exception as sheet_error:
                    logger.warning(f"⚠️ Failed to log 'no emails' to PostBD: {sheet_error}")

            return {
                "success": True,
                "found_emails": False,
                "message": "No new emails"
            }

        # Analyze latest email
        latest = emails[0]
        analysis = email_filter.analyze_email(latest['subject'], latest['body'])

        # Log action
        email_farm_db.log_action(
            user_id=user_id,
            email_id=email_id,
            action='checked_code',
            details=f"Subject: {latest['subject']}"
        )

        # If unsafe, send security alert
        if not analysis['is_safe']:
            await send_security_alert(
                user_id=user_id,
                email=email_account['email'],
                subject=latest['subject'],
                reason=analysis['unsafe_reason']
            )

            logger.warning(f"⚠️ User {user_id} - Unsafe email detected: {analysis['unsafe_reason']}")

            # Log unsafe email to Google Sheets (PostBD)
            if email_sheets:
                try:
                    email_sheets.log_email_check(
                        sheet_name="Post",
                        email=email_account['email'],
                        found_code=False,
                        is_safe=False,
                        subject=f"⚠️ {latest['subject']} - {analysis['unsafe_reason']}"
                    )
                except Exception as sheet_error:
                    logger.warning(f"⚠️ Failed to log unsafe email to PostBD: {sheet_error}")

            return {
                "success": False,
                "is_safe": False,
                "reason": analysis['unsafe_reason'],
                "subject": latest['subject']
            }

        # Return safe result with code
        logger.info(f"✅ User {user_id} - Code check safe: {email_account['email']}")

        # Log to Google Sheets (PostBD)
        if email_sheets:
            try:
                email_sheets.log_email_check(
                    sheet_name="Post",
                    email=email_account['email'],
                    found_code=bool(analysis['verification_code']),
                    is_safe=analysis['is_safe'],
                    subject=latest['subject'],
                    code=analysis['verification_code'] or ""
                )
            except Exception as sheet_error:
                logger.warning(f"⚠️ Failed to log email check to PostBD: {sheet_error}")

        return {
            "success": True,
            "is_safe": True,
            "verification_code": analysis['verification_code'],
            "all_codes": analysis['all_codes'],
            "subject": latest['subject'],
            "from": latest['from'],
            "date": latest['date']
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to check email code: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/emails/{email_id}/mark_banned")
async def mark_email_as_banned(
    email_id: int,
    x_telegram_init_data: str = Header(None)
):
    """
    Mark email as banned (user reported it as invalid/blocked)
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    try:
        # Get email account
        email_account = email_farm_db.get_email_by_id(email_id)
        if not email_account:
            raise HTTPException(status_code=404, detail="Email not found")

        # Verify ownership
        if email_account['assigned_user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Email not assigned to you")

        # Mark as banned
        success = email_farm_db.mark_email_banned(
            email_id=email_id,
            user_id=user_id,
            reason="User reported as banned/invalid"
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to mark as banned")

        logger.info(f"✅ User {user_id} marked email {email_id} as banned")

        # Log to Google Sheets (PostBD)
        if email_sheets:
            try:
                email_sheets.log_email_ban(
                    sheet_name="Post",
                    email=email_account['email'],
                    ban_reason="User reported as banned/invalid"
                )
            except Exception as sheet_error:
                logger.warning(f"⚠️ Failed to log email ban to PostBD: {sheet_error}")

        return {
            "success": True,
            "email_id": email_id,
            "status": "banned"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to mark email as banned: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/emails/{email_id}/complete")
async def complete_email_registration(
    email_id: int,
    x_telegram_init_data: str = Header(None)
):
    """
    Mark email registration as completed (move from Registration to My Emails)
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    try:
        # Get email account
        email_account = email_farm_db.get_email_by_id(email_id)
        if not email_account:
            raise HTTPException(status_code=404, detail="Email not found")

        # Verify ownership
        if email_account['assigned_user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Email not assigned to you")

        # Mark as completed
        success = email_farm_db.mark_email_completed(email_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to complete registration")

        # Update Google Sheets
        if email_sheets:
            try:
                email_sheets.update_email_completed_status(
                    sheet_name="Post",
                    email=email_account['email'],
                    is_completed=True
                )
            except Exception as sheet_error:
                logger.warning(f"⚠️ Failed to update completed status in PostBD: {sheet_error}")

        logger.info(f"✅ User {user_id} completed registration for email {email_id}")

        return {
            "success": True,
            "email_id": email_id,
            "is_completed": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to complete email registration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/emails/{email_id}/reopen")
async def reopen_email_registration(
    email_id: int,
    x_telegram_init_data: str = Header(None)
):
    """
    Reopen email registration (move from My Emails back to Registration)
    """
    if not email_farm_db:
        raise HTTPException(status_code=503, detail="Email Farm not initialized")

    # Validate user
    user_data = validate_telegram_init_data(x_telegram_init_data)
    user_id = user_data['id']

    try:
        # Get email account
        email_account = email_farm_db.get_email_by_id(email_id)
        if not email_account:
            raise HTTPException(status_code=404, detail="Email not found")

        # Verify ownership
        if email_account['assigned_user_id'] != user_id:
            raise HTTPException(status_code=403, detail="Email not assigned to you")

        # Reopen registration
        success = email_farm_db.reopen_email_registration(email_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to reopen registration")

        # Update Google Sheets
        if email_sheets:
            try:
                email_sheets.update_email_completed_status(
                    sheet_name="Post",
                    email=email_account['email'],
                    is_completed=False
                )
            except Exception as sheet_error:
                logger.warning(f"⚠️ Failed to update completed status in PostBD: {sheet_error}")

        logger.info(f"✅ User {user_id} reopened email {email_id} for additional code")

        return {
            "success": True,
            "email_id": email_id,
            "is_completed": False
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to reopen email registration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
