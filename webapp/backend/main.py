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
from config import TELEGRAM_TOKEN, DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEETS_CREDENTIALS_JSON

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
        # DEV MODE: возвращаем тестового пользователя
        return {
            "id": 873564841,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser"
        }
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

    # Получаем все профили проекта
    if sheets_db:
        all_profiles = sheets_db.get_all_profiles(
            platform=platform,
            project_name=project['name']
        )
    else:
        all_profiles = []

    # Группируем по пользователям
    users_stats = {}
    platform_stats = {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0}
    topic_stats = {}
    total_views = 0

    for profile in all_profiles:
        telegram_user = profile['telegram_user']
        views = int(profile.get('total_views', 0) or 0)
        plat = profile['platform']
        topic = profile.get('topic', 'Не указано')

        total_views += views

        # Статистика по пользователям
        if telegram_user not in users_stats:
            users_stats[telegram_user] = {
                "total_views": 0,
                "platforms": {"tiktok": 0, "instagram": 0, "facebook": 0, "youtube": 0},
                "topics": {}
            }

        users_stats[telegram_user]["total_views"] += views
        users_stats[telegram_user]["platforms"][plat] += views

        if topic:
            users_stats[telegram_user]["topics"][topic] = \
                users_stats[telegram_user]["topics"].get(topic, 0) + views

        # Общая статистика по платформам
        platform_stats[plat] += views

        # Общая статистика по тематикам
        if topic:
            topic_stats[topic] = topic_stats.get(topic, 0) + views

    return {
        "project": project,
        "total_views": total_views,
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

    # Получаем профили пользователя
    if sheets_db:
        profiles = sheets_db.get_user_profiles(telegram_user, project_name=project_name)
    else:
        profiles = []

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
