from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import sys
import os
import hmac
import hashlib
import json
import asyncio
import logging
from urllib.parse import parse_qsl

# Telegram Bot Imports
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Добавляем путь к родительской директории
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database_sheets import SheetsDatabase
from database_sqlite import SQLiteDatabase
from project_manager import ProjectManager
from project_sheets_manager import ProjectSheetsManager
from config import TELEGRAM_TOKEN, DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEETS_CREDENTIALS_JSON, ADMIN_IDS

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

# Инициализация Google Sheets для проектов
try:
    project_sheets = ProjectSheetsManager(GOOGLE_SHEETS_CREDENTIALS, "MainBD", GOOGLE_SHEETS_CREDENTIALS_JSON)
except Exception as e:
    print(f"⚠️  Project Sheets Manager не подключен: {e}")
    project_sheets = None

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

    from datetime import datetime

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
    platform: Optional[str] = None
):
    """Получить аналитику по проекту"""
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

                all_profiles.append({
                    'telegram_user': account.get('@Username', ''),
                    'url': account.get('Link', ''),
                    'followers': int(account.get('Followers', 0) or 0),
                    'likes': int(account.get('Likes', 0) or 0),
                    'comments': int(account.get('Comments', 0) or 0),
                    'videos': int(videos_value or 0),
                    'total_views': int(account.get('Views', 0) or 0),
                    'platform': account.get('Platform', 'tiktok').lower(),
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

                all_profiles.append({
                    'telegram_user': account.get('username', 'Unknown'),
                    'url': account.get('profile_link', ''),
                    'followers': latest_snapshot.get('followers', 0),
                    'likes': latest_snapshot.get('likes', 0),
                    'comments': latest_snapshot.get('comments', 0),
                    'videos': latest_snapshot.get('videos', 0),
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

    return {
        "project": project,
        "total_views": total_views,
        "total_videos": total_videos,
        "total_profiles": total_profiles,
        "platform_stats": platform_stats,
        "topic_stats": topic_stats,
        "users_stats": users_stats,
        "target_views": project['target_views'],
        "progress_percent": round((total_views / project['target_views'] * 100), 2) if project['target_views'] > 0 else 0
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
                    profiles.append({
                        'telegram_user': account.get('@Username', ''),
                        'url': account.get('Link', ''),
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
    platform_stats = {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0}
    topic_stats = {}
    total_views = 0

    for profile in profiles:
        views = int(profile.get('total_views', 0) or 0)
        plat = profile['platform']
        topic = profile.get('topic', 'Не указано')

        total_views += views
        platform_stats[plat] += views

        if topic:
            topic_stats[topic] = topic_stats.get(topic, 0) + views

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
        topic=account.topic
    )

    if not result:
        raise HTTPException(status_code=400, detail="Failed to add account")

    # Добавляем в Google Sheets (если включено)
    if project_sheets:
        try:
            # Создаем лист проекта если не существует
            project_sheets.create_project_sheet(project['name'])

            # Добавляем аккаунт в лист С TELEGRAM USERNAME!
            logger.info(f"📊 Sending to Sheets: telegram_user = '{display_name}'")
            project_sheets.add_account_to_sheet(project['name'], {
                'username': account.username,
                'profile_link': account.profile_link,
                'followers': 0,
                'likes': 0,
                'comments': 0,
                'videos': 0,
                'views': 0,
                'status': account.status,
                'topic': account.topic,
                'platform': account.platform,
                'telegram_user': display_name  # ← ИСПРАВЛЕНО: ДОБАВЛЕН TELEGRAM USER!
            })
            logger.info(f"✅ Added to Sheets: {account.username} by {display_name}")
        except Exception as e:
            logger.error(f"⚠️  Ошибка добавления в Google Sheets: {e}")

    return {"success": True, "account": result}

@app.get("/api/projects/{project_id}/accounts")
async def get_project_accounts(
    project_id: str,
    platform: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Получить все социальные аккаунты проекта"""
    accounts = project_manager.get_project_social_accounts(project_id, platform)
    return {"success": True, "accounts": accounts}

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
