"""
Web Dashboard для TikTok Analytics Bot
Запуск: python main.py
URL: http://localhost:8000
"""

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_sheets_reader import GoogleSheetsReader

app = FastAPI(
    title="TikTok Analytics Dashboard",
    description="Web интерфейс для просмотра аналитики",
    version="2.0.0"
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

sheets_reader = GoogleSheetsReader("credentials.json")

security = HTTPBasic()

VALID_CREDENTIALS = {
    "admin": "admin123"
}

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    username = credentials.username
    password = credentials.password
    
    if username not in VALID_CREDENTIALS:
        raise HTTPException(
            status_code=401,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    correct_password = VALID_CREDENTIALS[username]
    if not secrets.compare_digest(password, correct_password):
        raise HTTPException(
            status_code=401,
            detail="Неверные учетные данные",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return username


@app.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    username: str = Depends(verify_credentials)
):
    try:
        summary = sheets_reader.read_all_platforms()
        
        platforms_stats = {
            "tiktok": {"total": 0, "followers": 0, "views": 0, "videos": 0},
            "instagram": {"total": 0, "followers": 0, "views": 0, "videos": 0},
            "facebook": {"total": 0, "followers": 0, "views": 0, "videos": 0},
            "youtube": {"total": 0, "followers": 0, "views": 0, "videos": 0}
        }
        
        for item in summary:
            platform = item.get("platform", "tiktok")
            if platform in platforms_stats:
                platforms_stats[platform]["total"] += 1
                stats = item["stats"]
                platforms_stats[platform]["followers"] += stats.get("followers", 0)
                views = stats.get("views", 0) + stats.get("total_views", 0)
                platforms_stats[platform]["views"] += views
                platforms_stats[platform]["videos"] += stats.get("videos", 0)
        
        # Подсчет уникальных тематик
        unique_topics = set()
        for item in summary:
            topic = item.get("topic", "")
            if topic:
                # Нормализуем: первая буква заглавная, остальные строчные
                topic = topic.strip().capitalize()
                unique_topics.add(topic)
        
        total_users = len(set(p.get('telegram_user', '') for p in summary if p.get('telegram_user')))
        total_profiles = sum(p["total"] for p in platforms_stats.values())
        total_topics = len(unique_topics)
        total_views = sum(p["views"] for p in platforms_stats.values())
        total_content = sum(p["videos"] for p in platforms_stats.values())
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "username": username,
            "total_users": total_users,
            "total_profiles": total_profiles,
            "total_topics": total_topics,
            "total_views": total_views,
            "total_content": total_content,
            "platforms_stats": platforms_stats,
            "current_date": datetime.now().strftime("%d.%m.%Y"),
            "current_time": datetime.now().strftime("%H:%M")
        })
    
    except Exception as e:
        print(f"Ошибка на главной странице: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/profiles", response_class=HTMLResponse)
async def profiles_page(
    request: Request,
    username: str = Depends(verify_credentials)
):
    try:
        summary = sheets_reader.read_all_platforms()
        
        summary_sorted = sorted(
            summary,
            key=lambda x: x["stats"].get("views", 0) + x["stats"].get("total_views", 0),
            reverse=True
        )
        
        return templates.TemplateResponse("profiles.html", {
            "request": request,
            "username": username,
            "profiles": summary_sorted,
            "total_profiles": len(summary_sorted)
        })
    
    except Exception as e:
        print(f"Ошибка на странице профилей: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    username: str = Depends(verify_credentials)
):
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "username": username
    })


@app.get("/topics", response_class=HTMLResponse)
async def topics_page(
    request: Request,
    username: str = Depends(verify_credentials)
):
    """Страница аналитики тематик"""
    try:
        summary = sheets_reader.read_all_platforms()
        
        # Группируем по тематикам
        topic_stats = {}
        for profile in summary:
            topic = profile.get("topic", "Без тематики")
            if not topic:
                topic = "Без тематики"
            else:
                # Нормализуем: первая буква заглавная, остальные строчные
                topic = topic.strip().capitalize()
            
            if topic not in topic_stats:
                topic_stats[topic] = {
                    "topic": topic,
                    "profiles": 0,
                    "followers": 0,
                    "views": 0,
                    "videos": 0
                }
            
            stats = profile["stats"]
            topic_stats[topic]["profiles"] += 1
            topic_stats[topic]["followers"] += stats.get("followers", 0)
            topic_stats[topic]["views"] += stats.get("views", 0) + stats.get("total_views", 0)
            topic_stats[topic]["videos"] += stats.get("videos", 0)
        
        # Сортируем по просмотрам
        topics_sorted = sorted(
            topic_stats.values(),
            key=lambda x: x["views"],
            reverse=True
        )
        
        total_profiles = sum(t["profiles"] for t in topics_sorted)
        total_views = sum(t["views"] for t in topics_sorted)
        
        return templates.TemplateResponse("topics.html", {
            "request": request,
            "username": username,
            "topics": topics_sorted,
            "total_profiles": total_profiles,
            "total_views": total_views
        })
    
    except Exception as e:
        print(f"Ошибка на странице тематик: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats/overview")
async def get_stats_overview(username: str = Depends(verify_credentials)):
    try:
        summary = sheets_reader.read_all_platforms()
        
        total_users = len(set(p.get('telegram_user', '') for p in summary if p.get('telegram_user')))
        total_profiles = len(summary)
        total_followers = sum(item["stats"].get("followers", 0) for item in summary)
        total_views = sum(
            item["stats"].get("views", 0) + item["stats"].get("total_views", 0) 
            for item in summary
        )
        total_content = sum(
            item["stats"].get("videos", 0)
            for item in summary
        )
        
        return {
            "success": True,
            "data": {
                "total_users": total_users,
                "total_profiles": total_profiles,
                "total_followers": total_followers,
                "total_views": total_views,
                "total_content": total_content
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/stats/growth")
async def get_growth_stats(
    days: int = 7,
    username: str = Depends(verify_credentials)
):
    try:
        from history_logger import HistoryLogger
        
        try:
            history = HistoryLogger("dashboard_history.db")
            growth_data = history.get_growth_data(days)
            history.close()
            
            if growth_data['dates']:
                return {
                    "success": True,
                    "data": growth_data
                }
        except Exception as e:
            print(f"История не найдена, используем mock данные: {e}")
        
        dates = []
        views = []
        
        for i in range(days):
            date = (datetime.now() - timedelta(days=days-i-1)).strftime("%d.%m")
            dates.append(date)
            views.append(1000000 + i * 50000)
        
        return {
            "success": True,
            "data": {
                "dates": dates,
                "views": views
            }
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/stats/by-platform")
async def get_platform_stats(username: str = Depends(verify_credentials)):
    try:
        summary = sheets_reader.read_all_platforms()
        
        platforms_data = {
            "tiktok": {"profiles": 0, "views": 0, "followers": 0},
            "instagram": {"profiles": 0, "views": 0, "followers": 0},
            "facebook": {"profiles": 0, "views": 0, "followers": 0},
            "youtube": {"profiles": 0, "views": 0, "followers": 0}
        }
        
        for item in summary:
            platform = item.get("platform", "tiktok")
            if platform in platforms_data:
                platforms_data[platform]["profiles"] += 1
                views = item["stats"].get("views", 0) + item["stats"].get("total_views", 0)
                platforms_data[platform]["views"] += views
                platforms_data[platform]["followers"] += item["stats"].get("followers", 0)
        
        return {
            "success": True,
            "data": platforms_data
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/profiles/top")
async def get_top_profiles(
    limit: int = 10,
    sort_by: str = "views",
    username: str = Depends(verify_credentials)
):
    try:
        summary = sheets_reader.read_all_platforms()
        
        if sort_by == "views":
            sorted_profiles = sorted(
                summary, 
                key=lambda x: x["stats"].get("views", 0) + x["stats"].get("total_views", 0),
                reverse=True
            )
        elif sort_by == "followers":
            sorted_profiles = sorted(
                summary,
                key=lambda x: x["stats"].get("followers", 0),
                reverse=True
            )
        else:
            sorted_profiles = summary
        
        top_profiles = sorted_profiles[:limit]
        
        result = []
        for profile in top_profiles:
            result.append({
                "url": profile.get("url", ""),
                "username": profile.get("username", ""),
                "telegram_user": profile.get("telegram_user", ""),
                "platform": profile.get("platform", "tiktok"),
                "status": profile.get("status", "NEW"),
                "followers": profile["stats"].get("followers", 0),
                "views": profile["stats"].get("views", 0) + profile["stats"].get("total_views", 0),
                "videos": profile["stats"].get("videos", 0)
            })
        
        return {
            "success": True,
            "data": result
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/users/top_by_views")
async def get_top_users_by_views(
    limit: int = 10,
    username: str = Depends(verify_credentials)
):
    """API: ТОП пользователей по сумме просмотров всех их профилей"""
    try:
        profiles = sheets_reader.read_all_platforms()
        
        # Группируем по telegram_user
        user_stats = {}
        for profile in profiles:
            telegram_user = profile.get("telegram_user", "")
            if not telegram_user:
                continue
            
            views = profile["stats"].get("views", 0) + profile["stats"].get("total_views", 0)
            
            if telegram_user not in user_stats:
                user_stats[telegram_user] = {
                    "telegram_user": telegram_user,
                    "total_views": 0,
                    "profiles_count": 0
                }
            
            user_stats[telegram_user]["total_views"] += views
            user_stats[telegram_user]["profiles_count"] += 1
        
        # Сортируем по убыванию просмотров
        sorted_users = sorted(
            user_stats.values(),
            key=lambda x: x["total_views"],
            reverse=True
        )
        
        # Берем топ N
        top_users = sorted_users[:limit]
        
        return {
            "success": True,
            "data": top_users
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/stats/by_topic")
async def get_stats_by_topic(username: str = Depends(verify_credentials)):
    """API: Статистика по тематикам"""
    try:
        profiles = sheets_reader.read_all_platforms()
        
        # Группируем по тематикам
        topic_stats = {}
        for profile in profiles:
            topic = profile.get("topic", "Без тематики")
            if not topic:
                topic = "Без тематики"
            else:
                # Нормализуем: первая буква заглавная, остальные строчные
                topic = topic.strip().capitalize()
            
            if topic not in topic_stats:
                topic_stats[topic] = {
                    "topic": topic,
                    "profiles": 0,
                    "followers": 0,
                    "views": 0,
                    "videos": 0
                }
            
            stats = profile["stats"]
            topic_stats[topic]["profiles"] += 1
            topic_stats[topic]["followers"] += stats.get("followers", 0)
            topic_stats[topic]["views"] += stats.get("views", 0) + stats.get("total_views", 0)
            topic_stats[topic]["videos"] += stats.get("videos", 0)
        
        # Сортируем по количеству просмотров
        sorted_topics = sorted(
            topic_stats.values(),
            key=lambda x: x["views"],
            reverse=True
        )
        
        return {
            "success": True,
            "data": sorted_topics
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/history/period")
async def get_history_by_period(
    start_date: str,
    end_date: str,
    username: str = Depends(verify_credentials)
):
    """API: Получить историю за период"""
    try:
        from history_logger import HistoryLogger
        history = HistoryLogger("dashboard_history.db")
        
        stats = history.get_stats_by_period(start_date, end_date)
        history.close()
        
        return {
            "success": True,
            "data": stats
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/history/date_range")
async def get_history_date_range(username: str = Depends(verify_credentials)):
    """API: Получить доступный диапазон дат"""
    try:
        from history_logger import HistoryLogger
        history = HistoryLogger("dashboard_history.db")
        
        date_range = history.get_date_range()
        history.close()
        
        return {
            "success": True,
            "data": date_range
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    
    print("=" * 50)
    print("🚀 Запуск Web Dashboard...")
    print("=" * 50)
    print(f"URL: http://localhost:8002")
    print(f"Логин: admin")
    print(f"Пароль: admin123")
    print("=" * 50)
    print("⚠️  ВАЖНО: Измените пароль в main.py!")
    print("=" * 50)
    
    if not sheets_reader.is_connected:
        print("\n⚠️  ВНИМАНИЕ: Не удалось подключиться к Google Sheets!")
        print("Проверьте credentials.json и доступ к таблице")
        print("=" * 50)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
