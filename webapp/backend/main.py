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
from config import (
    TELEGRAM_TOKEN, DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS,
    GOOGLE_SHEETS_CREDENTIALS_JSON, ADMIN_IDS,
    RAPIDAPI_KEY, RAPIDAPI_HOST, RAPIDAPI_BASE_URL,
    INSTAGRAM_RAPIDAPI_KEY, INSTAGRAM_RAPIDAPI_HOST, INSTAGRAM_BASE_URL
)
from tiktok_api import TikTokAPI
from instagram_api import InstagramAPI

# WebApp Config
WEBAPP_URL = "https://moks1k11111.github.io/view-counter-webapp/index.html"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
    logger.info("✅ TikTok and Instagram API clients initialized")
except Exception as e:
    logger.error(f"⚠️  Failed to initialize API clients: {e}")
    tiktok_api = None
    instagram_api = None

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

@app.on_event("startup")
async def startup_event():
    """Start bot when FastAPI starts"""
    print("🚀 SERVER VERSION: 4.1 (ADDED telegram_user TO PYDANTIC MODEL)")
    logger.info("🚀 SERVER VERSION: 4.1 (ADDED telegram_user TO PYDANTIC MODEL)")
    logger.info("🚀 FastAPI starting up...")
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
            project_sheets.create_project_sheet(project.name)
        except Exception as e:
            print(f"⚠️ Ошибка создания листа в Google Sheets: {e}")

    return {"success": True, "project": new_project}

@app.get("/api/projects/{project_id}/analytics")
async def get_project_analytics(
    project_id: str,
    user: dict = Depends(get_current_user),
    platform: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Получить аналитику по проекту с историей"""
    user_id = str(user.get('id'))

    # Проверяем доступ
    user_projects = project_manager.get_user_projects(user_id)
    if not any(p['id'] == project_id for p in user_projects):
        raise HTTPException(status_code=403, detail="Access denied")

    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Получаем все профили проекта из листа проекта с fallback на SQLite
    all_profiles = []

    # Пытаемся загрузить из Google Sheets
    if project_sheets:
        try:
            accounts_data = project_sheets.get_project_accounts(project['name'])
            logger.info(f"🔍 DEBUG: Raw accounts_data from Sheets: {accounts_data[:1] if accounts_data else 'empty'}")

            # Конвертируем в нужный формат
            for account in accounts_data:
                videos_value = account.get('Videos', 0)
                logger.info(f"🔍 DEBUG: Videos field = {repr(videos_value)} (type: {type(videos_value).__name__})")

                # Извлекаем username и определяем платформу из URL
                url = account.get('Link', '').strip()  # Убираем пробелы
                url_lower = url.lower()  # Для проверки без учета регистра
                username = None
                platform = account.get('Platform', '').lower() if account.get('Platform') else None

                logger.info(f"🔍 Processing account: url='{url}', platform_from_sheets='{platform}'")

                # Определяем платформу и username из URL (без учета регистра)
                if 'tiktok.com' in url_lower:
                    platform = platform or 'tiktok'
                    if '/@' in url:
                        username = url.split('/@')[1].split('?')[0].split('/')[0]
                elif 'instagram.com' in url_lower:
                    platform = platform or 'instagram'
                    # Instagram URLs: instagram.com/username/ или instagram.com/@username/
                    clean_url = url.rstrip('/').split('?')[0]
                    parts = clean_url.split('/')
                    logger.info(f"🔍 Instagram URL parts: {parts}")
                    # Ищем часть после instagram.com
                    for i, part in enumerate(parts):
                        logger.info(f"🔍 Checking part {i}: '{part}', contains instagram.com: {'instagram.com' in part}")
                        if 'instagram.com' in part and i + 1 < len(parts):
                            username_part = parts[i + 1]
                            logger.info(f"🔍 Found username_part: '{username_part}'")
                            # Убираем @ если есть
                            username = username_part.lstrip('@')
                            logger.info(f"🔍 Extracted Instagram username: '{username}'")
                            break
                elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
                    platform = platform or 'facebook'
                    # Facebook: проверяем формат profile.php?id=...
                    if 'profile.php?id=' in url_lower:
                        # Извлекаем ID из параметра
                        try:
                            import urllib.parse
                            parsed = urllib.parse.urlparse(url)
                            params = urllib.parse.parse_qs(parsed.query)
                            if 'id' in params:
                                username = params['id'][0]
                        except:
                            pass
                    else:
                        # Обычный формат facebook.com/share/ID или facebook.com/username
                        clean_url = url.rstrip('/').split('?')[0]
                        # Убираем пустые части после split
                        parts = [p for p in clean_url.split('/') if p]

                        if 'share' in parts:
                            idx = parts.index('share')
                            if idx + 1 < len(parts):
                                username = parts[idx + 1]
                        elif len(parts) > 0:
                            # Берем последнюю непустую часть URL, кроме доменов
                            for part in reversed(parts):
                                if part and part not in ['facebook.com', 'www.facebook.com', 'fb.com', 'https:', 'http:']:
                                    username = part
                                    break
                elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
                    platform = platform or 'youtube'
                    # YouTube URLs: youtube.com/@username или youtube.com/c/username
                    if '/@' in url:
                        username = url.split('/@')[1].split('?')[0].split('/')[0]
                    elif '/c/' in url_lower:
                        username = url.split('/c/')[1].split('?')[0].split('/')[0]
                    elif '/channel/' in url_lower:
                        username = url.split('/channel/')[1].split('?')[0].split('/')[0]
                elif 'threads.net' in url_lower:
                    platform = platform or 'threads'
                    # Threads URLs: threads.net/@username
                    if '/@' in url:
                        username = url.split('/@')[1].split('?')[0].split('/')[0]
                    else:
                        clean_url = url.rstrip('/').split('?')[0]
                        parts = clean_url.split('/')
                        for i, part in enumerate(parts):
                            if 'threads.net' in part and i + 1 < len(parts):
                                username = parts[i + 1].lstrip('@')
                                break

                # Fallback на Username из Google Sheets (это username соц сети, не telegram)
                if not username:
                    sheets_username = account.get('Username', '').strip()
                    if sheets_username:
                        username = sheets_username
                    else:
                        # Последний fallback на @Username (telegram user)
                        telegram_username = account.get('@Username', '').strip()
                        if telegram_username and not telegram_username.startswith('@'):
                            username = telegram_username
                        elif telegram_username:
                            username = telegram_username[1:]  # Убираем @

                # Финальный fallback
                if not username:
                    username = 'Unknown'

                # Fallback если платформа не определена
                if not platform:
                    platform = 'tiktok'
                    logger.warning(f"⚠️ Platform not detected from URL '{url}', defaulting to tiktok")

                logger.info(f"✅ Final: username='{username}', platform='{platform}'")

                all_profiles.append({
                    'telegram_user': account.get('@Username', ''),
                    'username': username,  # Username из соц сети
                    'url': url,
                    'followers': int(account.get('Followers', 0) or 0),
                    'likes': int(account.get('Likes', 0) or 0),
                    'comments': int(account.get('Comments', 0) or 0),
                    'videos': int(videos_value or 0),
                    'total_views': int(account.get('Views', 0) or 0),
                    'platform': platform,
                    'topic': account.get('Тематика', 'Не указано')
                })
            logger.info(f"✅ Loaded {len(all_profiles)} profiles from Google Sheets for project '{project['name']}'")
        except Exception as e:
            logger.warning(f"⚠️ Could not load accounts from sheets for project {project['name']}: {e}")

    # FALLBACK: Если Google Sheets пустой или недоступен, загружаем из SQLite
    if len(all_profiles) == 0:
        logger.info(f"📊 Google Sheets empty, loading from SQLite for project '{project['name']}'")
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
                    'topic': account.get('topic', 'Не указано')
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

        total_views += views
        total_videos += videos
        logger.info(f"🔍 DEBUG: Profile videos={videos}, total_videos now={total_videos}")

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

    return {
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
        "history": history,
        "growth_24h": growth_24h,
        "backend_version": "v2.0_progress_fix"  # Для отладки версии бэкенда
    }

@app.get("/api/my-analytics")
async def get_my_analytics(
    user: dict = Depends(get_current_user),
    project_id: Optional[str] = None
):
    """Получить личную аналитику пользователя"""
    user_id = str(user.get('id'))
    username = user.get('username', '')
    telegram_user = f"@{username}" if username else user.get('first_name', 'Неизвестно')

    # Если указан проект, фильтруем по нему
    project_name = None
    if project_id:
        project = project_manager.get_project(project_id)
        if project:
            project_name = project['name']

    # Получаем профили пользователя из листа проекта
    profiles = []
    if project_sheets and project_name:
        try:
            accounts_data = project_sheets.get_project_accounts(project_name)
            # Конвертируем и фильтруем по пользователю
            for account in accounts_data:
                if account.get('@Username', '') == telegram_user:
                    # Извлекаем username из URL
                    url = account.get('Link', '')
                    username = 'Unknown'
                    if '/@' in url:
                        # TikTok, Instagram: https://www.tiktok.com/@username
                        username = url.split('/@')[1].split('?')[0].split('/')[0]
                    elif 'facebook.com/share/' in url or 'facebook.com/' in url:
                        # Facebook: извлекаем ID или username
                        parts = url.split('/')
                        if 'share' in parts:
                            idx = parts.index('share')
                            if idx + 1 < len(parts):
                                username = parts[idx + 1].split('?')[0]
                        else:
                            username = parts[-1].split('?')[0] if parts[-1] else parts[-2]

                    profiles.append({
                        'telegram_user': account.get('@Username', ''),
                        'username': username,  # Username из соц сети
                        'url': url,
                        'followers': int(account.get('Followers', 0) or 0),
                        'likes': int(account.get('Likes', 0) or 0),
                        'comments': int(account.get('Comments', 0) or 0),
                        'videos': int(account.get('Videos', 0) or 0),
                        'total_views': int(account.get('Views', 0) or 0),
                        'platform': account.get('Platform', 'tiktok').lower(),
                        'topic': account.get('Тематика', 'Не указано')
                    })
        except Exception as e:
            logger.warning(f"⚠️ Could not load user profiles from sheets for project {project_name}: {e}")

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

        # Получаем историю просмотров проекта
        daily_history = project_manager.get_project_daily_history(project_id)

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

        return {
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
            "history": history,
            "growth_24h": growth_24h,
            "backend_version": "v2.0_progress_fix"  # Для отладки версии бэкенда
        }

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

    if not tiktok_api and not instagram_api:
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
        kpi_views=kpi_views
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
    kpi_views: int
):
    """
    Фоновая обработка аккаунтов с обновлением прогресса
    """
    import time

    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 BACKGROUND TASK STARTED FOR PROJECT {project_id}")
    logger.info(f"📊 ПРОГРЕСС-БАР ОБНОВЛЕНИЯ СТАТИСТИКИ")
    logger.info(f"{'='*70}")
    for platform, stats in platform_stats.items():
        logger.info(f"   {platform.upper()}: 0/{stats['total']} аккаунтов")
    logger.info(f"{'='*70}\n")

    updated_count = 0
    failed_count = 0
    errors = []

    for account in accounts:
        platform = account.get('platform', 'tiktok').lower()
        profile_link = account.get('profile_link', '')
        username = account.get('username', '')

        # Пропускаем если платформа не выбрана для обновления
        if not platforms.get(platform, False):
            logger.info(f"⏭️ Skipping {platform} account {username} (platform not selected)")
            continue

        logger.info(f"🔄 Updating {platform} account: {username}")

        try:
            stats = None

            # Получаем статистику в зависимости от платформы (с KPI фильтрацией)
            if platform == 'tiktok' and tiktok_api:
                stats = tiktok_api.get_tiktok_data(profile_link, kpi_views=kpi_views)
            elif platform == 'instagram' and instagram_api:
                stats = instagram_api.get_instagram_data(profile_link, kpi_views=kpi_views)
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
                    stats=stats_dict
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
            project_sheets.remove_account_from_sheet(project['name'], account['username'])
        except Exception as e:
            print(f"⚠️  Ошибка удаления из Google Sheets: {e}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
