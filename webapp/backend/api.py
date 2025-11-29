from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import sys
import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl

# Добавляем путь к родительской директории
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from database_sheets import SheetsDatabase
from database_sqlite import SQLiteDatabase
from project_manager import ProjectManager
from project_sheets_manager import ProjectSheetsManager
from config import TELEGRAM_TOKEN, DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEETS_CREDENTIALS_JSON, ADMIN_IDS

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
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Telegram init data required")
    return validate_telegram_init_data(x_telegram_init_data)

# ============ API Endpoints ============

@app.get("/")
async def root():
    return {"message": "View Counter WebApp API", "version": "1.0"}

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
    """Получить все проекты пользователя"""
    user_id = str(user.get('id'))
    projects = project_manager.get_user_projects(user_id)

    return {"projects": projects}

@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, user: dict = Depends(get_current_user)):
    """Получить детальную информацию о проекте"""
    user_id = str(user.get('id'))

    # Проверяем доступ к проекту (админы имеют доступ ко всем проектам)
    is_admin = int(user_id) in ADMIN_IDS
    if not is_admin:
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
        kpi_views=project.kpi_views
    )

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

    # 1. Проверяем, является ли пользователь Админом
    # Приводим все ID к строке для надежного сравнения
    admin_ids_str = [str(admin_id) for admin_id in ADMIN_IDS]
    is_admin = user_id in admin_ids_str

    # 2. Проверяем, является ли пользователь участником проекта
    user_projects = project_manager.get_user_projects(user_id)
    is_member = any(p['id'] == project_id for p in user_projects)

    # 3. Если не Админ и не Участник -> Запрещаем доступ
    if not is_member and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied: You are not a member of this project")

    # Получаем проект
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Получаем ВСЕХ пользователей проекта из БД
    project_users = project_manager.get_project_users(project_id)

    # Получаем все аккаунты проекта из Project Sheets (новый подход)
    all_profiles = []
    if project_sheets:
        try:
            # Получаем аккаунты из листа проекта
            sheet_accounts = project_sheets.get_project_accounts(project['name'])

            # Преобразуем формат данных из Google Sheets в формат, ожидаемый analytics
            for account in sheet_accounts:
                # Маппинг полей Google Sheets -> analytics формат
                profile = {
                    'telegram_user': account.get('Telegram User', account.get('@Username', 'Manual')),
                    'total_views': account.get('Views', 0),
                    'platform': account.get('Platform', 'TIKTOK').lower(),
                    'topic': account.get('Тематика', 'Не указано'),
                    'username': account.get('@Username', ''),
                    'profile_link': account.get('Link', ''),
                    'followers': account.get('Followers', 0),
                    'likes': account.get('Likes', 0),
                    'comments': account.get('Comments', 0),
                    'videos': account.get('Videos', 0),
                    'status': account.get('Status', 'NEW')
                }
                all_profiles.append(profile)

            print(f"✅ Загружено {len(all_profiles)} аккаунтов из проектного листа '{project['name']}'")
        except Exception as e:
            print(f"⚠️ Ошибка получения аккаунтов из Project Sheets: {e}")
            import traceback
            traceback.print_exc()
            # Не падаем, просто возвращаем пустой список
            all_profiles = []

    # Инициализируем статистику для ВСЕХ пользователей проекта
    users_stats = {}
    for user in project_users:
        username = user.get('username', 'Unknown')
        users_stats[username] = {
            "total_views": 0,
            "platforms": {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0},
            "topics": {},
            "profiles_count": 0
        }

    # Группируем статистику
    platform_stats = {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0}
    topic_stats = {}
    total_views = 0
    total_videos = len(all_profiles)  # Общее количество профилей = количество видео

    for profile in all_profiles:
        telegram_user = profile.get('telegram_user', 'Unknown')

        # Безопасное преобразование данных в числа
        try:
            views = int(str(profile.get('total_views', 0)).replace(' ', ''))
        except (ValueError, TypeError):
            views = 0

        plat = profile.get('platform', 'tiktok')
        topic = profile.get('topic', 'Не указано')

        total_views += views

        # Статистика по пользователям
        if telegram_user not in users_stats:
            # Если пользователь не в проекте, но у него есть профили, добавляем его
            users_stats[telegram_user] = {
                "total_views": 0,
                "platforms": {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0},
                "topics": {},
                "profiles_count": 0
            }

        users_stats[telegram_user]["total_views"] += views
        users_stats[telegram_user]["profiles_count"] += 1  # Увеличиваем счетчик профилей

        if plat in users_stats[telegram_user]["platforms"]:
            users_stats[telegram_user]["platforms"][plat] += views

        if topic:
            current_topic_views = users_stats[telegram_user]["topics"].get(topic, 0)
            users_stats[telegram_user]["topics"][topic] = current_topic_views + views

        # Общая статистика по платформам
        if plat in platform_stats:
            platform_stats[plat] += views

        # Общая статистика по тематикам
        if topic:
            topic_stats[topic] = topic_stats.get(topic, 0) + views

    # Считаем прогресс
    progress = 0
    if project.get('target_views', 0) > 0:
        progress = round((total_views / project['target_views'] * 100), 2)

    return {
        "project": project,
        "total_views": total_views,
        "total_videos": total_videos,
        "platform_stats": platform_stats,
        "topic_stats": topic_stats,
        "users_stats": users_stats,
        "target_views": project.get('target_views', 0),
        "progress_percent": progress
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

    # Получаем профили пользователя
    profiles = sheets_db.get_user_profiles(telegram_user, project_name=project_name)

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

    # Получаем данные проекта для Google Sheets
    project = project_manager.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Добавляем в Google Sheets (если включено)
    if project_sheets:
        try:
            # Извлекаем Telegram username из user объекта
            telegram_username = user.get('username', '')
            if not telegram_username:
                telegram_username = user.get('first_name', 'Unknown')
            else:
                telegram_username = f"@{telegram_username}"

            # Создаем лист проекта если не существует
            project_sheets.create_project_sheet(project['name'])

            # Добавляем аккаунт в лист
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
                'telegram_user': telegram_username
            })
        except Exception as e:
            print(f"⚠️  Ошибка добавления в Google Sheets: {e}")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
