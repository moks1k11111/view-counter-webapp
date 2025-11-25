import logging
from database_sqlite import SQLiteDatabase as Database
from database_sheets import SheetsDatabase
from config import GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEETS_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sync_to_google_sheets():
    """Синхронизирует данные из SQLite в Google Sheets"""
    try:
        logger.info("Начало синхронизации с Google Sheets...")
        
        # Подключаемся к обеим базам
        sqlite_db = Database()
        sheets_db = SheetsDatabase(GOOGLE_SHEETS_CREDENTIALS, GOOGLE_SHEETS_NAME)
        
        # Получаем все активные ссылки из SQLite
        links = sqlite_db.get_all_active_links()
        
        logger.info(f"Найдено {len(links)} активных ссылок")
        
        for link in links:
            # Получаем последнюю аналитику для каждой ссылки
            analytics = sqlite_db.get_analytics_for_link(link['id'], limit=1)
            
            if analytics:
                stats = analytics[0]['stats']
                
                # Добавляем ссылку в Google Sheets (если ещё нет)
                sheets_link = sheets_db.add_link(
                    user_id=link['user_id'],
                    url=link['url'],
                    link_type=link['type'],
                    username=link.get('username'),
                    video_id=link.get('video_id'),
                    sec_uid=link.get('sec_uid')
                )
                
                # Сохраняем статистику
                sheets_db.save_analytics(sheets_link['id'], stats)
                
                logger.info(f"Синхронизирована ссылка: {link['url'][:50]}...")
        
        logger.info("✅ Синхронизация завершена успешно!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка синхронизации: {e}")
        return False

if __name__ == "__main__":
    sync_to_google_sheets()
