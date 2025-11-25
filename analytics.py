import schedule
import time
import threading
import logging
import random
from datetime import datetime, timedelta

from tiktok_api import TikTokAPI
from database_sqlite import SQLiteDatabase as Database
from config import RAPIDAPI_DAILY_LIMIT
from utils import format_number

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация клиентов
tiktok_api = TikTokAPI()
db = Database()

def update_link_analytics(link):
    """Обновляет аналитику для одной ссылки"""
    try:
        # Проверяем лимиты API
        today_usage = db.get_api_usage_today()
        
        if today_usage and int(today_usage.get('total', 0)) >= RAPIDAPI_DAILY_LIMIT:
            logger.warning(f"Достигнут дневной лимит API запросов: {RAPIDAPI_DAILY_LIMIT}")
            return False
        
        logger.info(f"Обновление данных для {link['url']}")
        
        # Получаем данные через API
        stats = tiktok_api.get_tiktok_data(link['url'])
        
        # Определяем тип эндпоинта для отслеживания использования
        endpoint = "profile_info" if stats.get("type") == "profile" else "video_info"
        
        # Отслеживаем использование API
        db.track_api_usage(endpoint)
        
        # Сохраняем полученные данные в базу
        db.save_analytics(link["id"], stats)
        
        logger.info(f"Статистика для {link['url']} обновлена успешно")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении статистики для {link['url']}: {e}")
        return False

def update_analytics_batch():
    """Обновляет статистику для всех активных ссылок партиями"""
    logger.info("Запуск обновления аналитики...")
    
    # Получаем все активные ссылки
    links = db.get_all_active_links()
    total_links = len(links)
    logger.info(f"Найдено {total_links} активных ссылок для обновления")
    
    if not total_links:
        logger.info("Нет ссылок для обновления")
        return
    
    # Проверяем ограничения API
    today_usage = db.get_api_usage_today()
    available_calls = RAPIDAPI_DAILY_LIMIT - (int(today_usage.get('total', 0)) if today_usage else 0)
    
    if available_calls <= 0:
        logger.warning("Дневной лимит API исчерпан. Обновление отложено.")
        return
    
    # Если доступных вызовов меньше, чем ссылок, выбираем случайную выборку
    if available_calls < total_links:
        logger.info(f"Доступно только {available_calls} API вызовов. Выбираем {available_calls} ссылок случайным образом.")
        links = random.sample(links, available_calls)
    
    # Обработка ссылок с задержкой между запросами
    success_count = 0
    
    for i, link in enumerate(links):
        success = update_link_analytics(link)
        if success:
            success_count += 1
        
        # Прогресс выполнения
        logger.info(f"Прогресс: {i+1}/{len(links)} ({(i+1)/len(links)*100:.1f}%)")
        
        # Делаем паузу между запросами, чтобы не перегружать API
        if i < len(links) - 1:  # Не делаем паузу после последней ссылки
            delay = random.uniform(2, 5)  # 2-5 секунд между запросами
            logger.info(f"Пауза {delay:.1f} секунд перед следующим запросом...")
            time.sleep(delay)
    
    logger.info(f"Обновление аналитики завершено. Успешно: {success_count}/{len(links)}")

def update_priority_links():
    """Обновляет только приоритетные ссылки (недавно добавленные или популярные)"""
    logger.info("Запуск обновления приоритетных ссылок...")
    
    # Получаем все активные ссылки
    all_links = db.get_all_active_links()
    
    if not all_links:
        logger.info("Нет ссылок для обновления")
        return
    
    # Фильтруем ссылки, добавленные за последние 24 часа
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    one_day_ago_str = one_day_ago.isoformat()
    
    new_links = []
    for link in all_links:
        if link.get('created_at') and link.get('created_at') > one_day_ago_str:
            new_links.append(link)
    
    # Проверяем лимиты API
    today_usage = db.get_api_usage_today()
    available_calls = RAPIDAPI_DAILY_LIMIT - (int(today_usage.get('total', 0)) if today_usage else 0)
    
    if available_calls <= 0:
        logger.warning("Дневной лимит API исчерпан. Обновление отложено.")
        return
    
    # Определяем количество ссылок для обновления
    num_links_to_update = min(10, available_calls)  # Не более 10 ссылок за раз
    
    # Если новых ссылок меньше, чем нам нужно, добавляем случайные ссылки из оставшихся
    links_to_update = new_links[:num_links_to_update]
    
    if len(links_to_update) < num_links_to_update:
        # Исключаем уже выбранные ссылки
        remaining_links = [link for link in all_links if link not in links_to_update]
        # Выбираем случайные ссылки из оставшихся
        if remaining_links:
            additional_links = random.sample(
                remaining_links,
                min(num_links_to_update - len(links_to_update), len(remaining_links))
            )
            links_to_update.extend(additional_links)
    
    logger.info(f"Обновление {len(links_to_update)} приоритетных ссылок")
    
    # Обновляем выбранные ссылки
    for i, link in enumerate(links_to_update):
        update_link_analytics(link)
        
        # Делаем паузу между запросами
        if i < len(links_to_update) - 1:  # Не делаем паузу после последней ссылки
            time.sleep(random.uniform(2, 5))  # 2-5 секунд между запросами
    
    logger.info("Обновление приоритетных ссылок завершено")

def run_scheduler():
    """Запускает планировщик заданий"""
    # Полное обновление всех ссылок два раза в день
    schedule.every(12).hours.do(update_analytics_batch)
    
    # Обновление приоритетных ссылок чаще
    schedule.every(2).hours.do(update_priority_links)
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверяем расписание каждую минуту

def start_scheduler():
    """Запускает планировщик в отдельном потоке"""
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

def generate_report(user_id=None):
    """Генерирует отчет об аналитике за указанный период"""
    summary = db.get_analytics_summary(user_id)
    
    if not summary:
        return "Нет данных для отчета"
    
    report = "📊 Отчет по аналитике TikTok\n\n"
    
    # Группируем данные по типу (профили и видео)
    profiles = [item for item in summary if item.get('type') == 'profile']
    videos = [item for item in summary if item.get('type') == 'video']
    
    # Добавляем информацию о профилях
    if profiles:
        report += "👤 ПРОФИЛИ:\n"
        for profile in profiles:
            stats = profile.get('stats', {})
            username = profile.get('username') or "Неизвестный"
            report += f"@{username}: {format_number(stats.get('followers', 0))} подписчиков, "
            report += f"{format_number(stats.get('likes', 0))} лайков\n"
        report += "\n"
    
    # Добавляем информацию о видео
    if videos:
        report += "🎬 ВИДЕО:\n"
        for video in videos:
            stats = video.get('stats', {})
            author = stats.get('author') or "Неизвестный"
            views = format_number(stats.get('views', 0))
            likes = format_number(stats.get('likes', 0))
            title = (stats.get('title') or "")[:30] + ("..." if len(stats.get('title', "")) > 30 else "")
            report += f"@{author} - {title}\n"
            report += f"👁 {views} просмотров, ❤️ {likes} лайков\n\n"
    
    # Добавляем информацию об использовании API
    today_usage = db.get_api_usage_today()
    if today_usage:
        used = today_usage.get('total', 0)
        limit = RAPIDAPI_DAILY_LIMIT
        report += f"\n🔄 Использовано API сегодня: {used}/{limit} запросов\n"
    
    return report

if __name__ == "__main__":
    # Запускаем обновление приоритетных ссылок сразу
    try:
        logger.info("Запуск модуля аналитики...")
        update_priority_links()
        
        # Запускаем планировщик
        logger.info("Запуск планировщика обновлений...")
        start_scheduler()
        
        logger.info("Планировщик запущен успешно!")
        
        # Держим скрипт запущенным
        while True:
            time.sleep(3600)  # Проверка каждый час
            logger.info("Планировщик активен...")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске модуля аналитики: {e}")
