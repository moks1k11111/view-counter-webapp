"""
Data Collector - Ежедневный сбор статистики
Запускать по cron каждый день в 00:00
"""

import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from history_logger import HistoryLogger
from google_sheets_reader import GoogleSheetsReader


class DataCollector:
    """Сборщик данных для истории"""
    
    def __init__(self, credentials_path: str = "credentials.json"):
        self.sheets_reader = GoogleSheetsReader(credentials_path)
        self.history_logger = HistoryLogger("dashboard_history.db")
        
        if not self.sheets_reader.is_connected:
            print("✗ ОШИБКА: Google Sheets не подключен!")
    
    def collect_and_save(self, date: str = None):
        """Собрать и сохранить данные за день"""
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        print("\n" + "=" * 60)
        print(f"🔄 Сбор данных: {date}")
        print("=" * 60)
        
        try:
            # Читаем все профили
            profiles = self.sheets_reader.read_all_platforms()
            
            if not profiles:
                print("⚠️  Профили не найдены!")
                return False
            
            print(f"✓ Получено {len(profiles)} профилей")
            
            # Подсчитываем статистику
            summary = self._calculate_summary(profiles)
            
            # Сохраняем в БД
            success = self.history_logger.save_daily_snapshot(date, summary)
            
            if success:
                print("\n" + "=" * 60)
                print("✅ Данные сохранены!")
                print("=" * 60)
                print(f"👥 Пользователей: {summary['total_users']}")
                print(f"📊 Профилей: {summary['total_profiles']}")
                print(f"📌 Тематик: {summary['total_topics']}")
                print(f"👁️  Просмотров: {summary['total_views']:,}")
                print("=" * 60)
            
            return success
            
        except Exception as e:
            print(f"✗ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _calculate_summary(self, profiles: list) -> dict:
        """Подсчитать сводную статистику"""
        
        # Статистика по платформам
        platforms = {
            'tiktok': {'total': 0, 'new': 0, 'old': 0, 'ban': 0, 'followers': 0, 'views': 0, 'videos': 0},
            'instagram': {'total': 0, 'new': 0, 'old': 0, 'ban': 0, 'followers': 0, 'views': 0, 'videos': 0},
            'facebook': {'total': 0, 'new': 0, 'old': 0, 'ban': 0, 'followers': 0, 'views': 0, 'videos': 0},
            'youtube': {'total': 0, 'new': 0, 'old': 0, 'ban': 0, 'followers': 0, 'views': 0, 'videos': 0}
        }
        
        # Статистика по тематикам
        topics = {}
        
        # Уникальные пользователи
        unique_users = set()
        
        for profile in profiles:
            platform = profile.get('platform', 'tiktok')
            status = profile.get('status', 'NEW')
            topic = profile.get('topic', '')
            telegram_user = profile.get('telegram_user', '')
            
            # Нормализуем тематику
            if topic:
                topic = topic.strip().capitalize()
            else:
                topic = "Без тематики"
            
            # Подсчитываем по платформам
            if platform in platforms:
                platforms[platform]['total'] += 1
                
                if status == 'NEW':
                    platforms[platform]['new'] += 1
                elif status == 'OLD':
                    platforms[platform]['old'] += 1
                elif status == 'BAN':
                    platforms[platform]['ban'] += 1
                
                stats = profile.get('stats', {})
                platforms[platform]['followers'] += stats.get('followers', 0)
                platforms[platform]['views'] += stats.get('views', 0) + stats.get('total_views', 0)
                platforms[platform]['videos'] += stats.get('videos', 0)
            
            # Подсчитываем по тематикам
            if topic not in topics:
                topics[topic] = {
                    'profiles': 0,
                    'followers': 0,
                    'views': 0,
                    'videos': 0
                }
            
            topics[topic]['profiles'] += 1
            stats = profile.get('stats', {})
            topics[topic]['followers'] += stats.get('followers', 0)
            topics[topic]['views'] += stats.get('views', 0) + stats.get('total_views', 0)
            topics[topic]['videos'] += stats.get('videos', 0)
            
            # Считаем уникальных пользователей
            if telegram_user:
                unique_users.add(telegram_user)
        
        # Общая статистика
        total_profiles = sum(p['total'] for p in platforms.values())
        total_followers = sum(p['followers'] for p in platforms.values())
        total_views = sum(p['views'] for p in platforms.values())
        total_videos = sum(p['videos'] for p in platforms.values())
        
        return {
            'total_users': len(unique_users),
            'total_profiles': total_profiles,
            'total_topics': len(topics),
            'total_followers': total_followers,
            'total_views': total_views,
            'total_videos': total_videos,
            'platforms': platforms,
            'topics': topics
        }
    
    def show_history_stats(self):
        """Показать статистику истории"""
        date_range = self.history_logger.get_date_range()
        dates = self.history_logger.get_available_dates()
        
        print("\n" + "=" * 60)
        print("📊 Статистика истории")
        print("=" * 60)
        print(f"Период: {date_range['min_date']} - {date_range['max_date']}")
        print(f"Дней в истории: {len(dates)}")
        print("=" * 60)


def main():
    """Главная функция"""
    print("""
╔══════════════════════════════════════════════════════════╗
║                   DATA COLLECTOR                          ║
║       Ежедневный сбор статистики                         ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    # Создаем сборщик
    collector = DataCollector("credentials.json")
    
    # Собираем и сохраняем данные
    success = collector.collect_and_save()
    
    # Показываем статистику
    collector.show_history_stats()
    
    if success:
        print("✅ Готово!\n")
        return 0
    else:
        print("❌ Ошибка!\n")
        return 1


if __name__ == "__main__":
    exit(main())
