"""
History Logger - Логирование исторических данных в SQLite
Сохраняет снапшоты статистики навсегда
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os


class HistoryLogger:
    """Логгер для сохранения исторических данных"""
    
    def __init__(self, db_path: str = "dashboard_history.db"):
        """
        Инициализация БД истории
        
        Args:
            db_path: Путь к файлу БД
        """
        self.db_path = db_path
        self.conn = None
        self._init_db()
    
    def _init_db(self):
        """Инициализация структуры БД"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        cursor = self.conn.cursor()
        
        # Таблица ежедневных снапшотов по платформам
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                platform TEXT NOT NULL,
                total_profiles INTEGER DEFAULT 0,
                total_followers INTEGER DEFAULT 0,
                total_views INTEGER DEFAULT 0,
                total_videos INTEGER DEFAULT 0,
                new_profiles INTEGER DEFAULT 0,
                old_profiles INTEGER DEFAULT 0,
                ban_profiles INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, platform)
            )
        """)
        
        # Таблица снапшотов по тематикам
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                topic TEXT NOT NULL,
                profiles INTEGER DEFAULT 0,
                followers INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                videos INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, topic)
            )
        """)
        
        # Таблица общей статистики
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_users INTEGER DEFAULT 0,
                total_profiles INTEGER DEFAULT 0,
                total_topics INTEGER DEFAULT 0,
                total_followers INTEGER DEFAULT 0,
                total_views INTEGER DEFAULT 0,
                total_videos INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Индексы для быстрого поиска
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_topics_date ON daily_topics(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_summary_date ON daily_summary(date)")
        
        self.conn.commit()
        print(f"✓ История: БД инициализирована ({self.db_path})")
    
    def save_daily_snapshot(self, date: str, summary: Dict):
        """
        Сохранить ежедневный снапшот
        
        Args:
            date: Дата в формате YYYY-MM-DD
            summary: Словарь с данными
        """
        cursor = self.conn.cursor()
        
        try:
            # Сохраняем общую статистику
            cursor.execute("""
                INSERT OR REPLACE INTO daily_summary 
                (date, total_users, total_profiles, total_topics, total_followers, total_views, total_videos)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                date,
                summary.get('total_users', 0),
                summary.get('total_profiles', 0),
                summary.get('total_topics', 0),
                summary.get('total_followers', 0),
                summary.get('total_views', 0),
                summary.get('total_videos', 0)
            ))
            
            # Сохраняем статистику по платформам
            platforms = summary.get('platforms', {})
            for platform_name, platform_data in platforms.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_stats 
                    (date, platform, total_profiles, total_followers, total_views, total_videos, 
                     new_profiles, old_profiles, ban_profiles)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    platform_name,
                    platform_data.get('total', 0),
                    platform_data.get('followers', 0),
                    platform_data.get('views', 0),
                    platform_data.get('videos', 0),
                    platform_data.get('new', 0),
                    platform_data.get('old', 0),
                    platform_data.get('ban', 0)
                ))
            
            # Сохраняем статистику по тематикам
            topics = summary.get('topics', {})
            for topic_name, topic_data in topics.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_topics 
                    (date, topic, profiles, followers, views, videos)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    topic_name,
                    topic_data.get('profiles', 0),
                    topic_data.get('followers', 0),
                    topic_data.get('views', 0),
                    topic_data.get('videos', 0)
                ))
            
            self.conn.commit()
            print(f"✓ Снапшот сохранен: {date}")
            return True
            
        except Exception as e:
            print(f"✗ Ошибка сохранения снапшота: {e}")
            self.conn.rollback()
            return False
    
    def get_views_by_period(self, start_date: str, end_date: str) -> Dict:
        """
        Получить просмотры за период
        
        Args:
            start_date: Начальная дата (YYYY-MM-DD)
            end_date: Конечная дата (YYYY-MM-DD)
            
        Returns:
            Словарь с датами и просмотрами
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT date, total_views 
            FROM daily_summary 
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC
        """, (start_date, end_date))
        
        results = cursor.fetchall()
        
        return {
            'dates': [row[0] for row in results],
            'views': [row[1] for row in results]
        }
    
    def get_stats_by_period(self, start_date: str, end_date: str) -> Dict:
        """
        Получить полную статистику за период
        
        Args:
            start_date: Начальная дата (YYYY-MM-DD)
            end_date: Конечная дата (YYYY-MM-DD)
            
        Returns:
            Словарь со статистикой
        """
        cursor = self.conn.cursor()
        
        # Получаем данные за период
        cursor.execute("""
            SELECT date, total_views, total_profiles, total_users, total_topics
            FROM daily_summary 
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC
        """, (start_date, end_date))
        
        results = cursor.fetchall()
        
        if not results:
            return {
                'dates': [],
                'views': [],
                'profiles': [],
                'users': [],
                'topics': [],
                'growth': {
                    'views': 0,
                    'profiles': 0
                }
            }
        
        dates = [row[0] for row in results]
        views = [row[1] for row in results]
        profiles = [row[2] for row in results]
        users = [row[3] for row in results]
        topics = [row[4] for row in results]
        
        # Рассчитываем прирост
        growth_views = views[-1] - views[0] if len(views) > 1 else 0
        growth_profiles = profiles[-1] - profiles[0] if len(profiles) > 1 else 0
        
        return {
            'dates': dates,
            'views': views,
            'profiles': profiles,
            'users': users,
            'topics': topics,
            'growth': {
                'views': growth_views,
                'profiles': growth_profiles
            },
            'start': {
                'views': views[0] if views else 0,
                'profiles': profiles[0] if profiles else 0
            },
            'end': {
                'views': views[-1] if views else 0,
                'profiles': profiles[-1] if profiles else 0
            }
        }
    
    def get_available_dates(self) -> List[str]:
        """Получить список доступных дат"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT date FROM daily_summary ORDER BY date DESC")
        return [row[0] for row in cursor.fetchall()]
    
    def get_date_range(self) -> Dict[str, str]:
        """Получить диапазон доступных дат"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT MIN(date), MAX(date) FROM daily_summary")
        result = cursor.fetchone()
        
        return {
            'min_date': result[0] if result[0] else datetime.now().strftime('%Y-%m-%d'),
            'max_date': result[1] if result[1] else datetime.now().strftime('%Y-%m-%d')
        }
    
    def cleanup_old_data(self, days_to_keep: int = 365):
        """
        Очистить старые данные (опционально, если нужно)
        
        Args:
            days_to_keep: Сколько дней хранить (по умолчанию 365)
        """
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        cursor = self.conn.cursor()
        
        cursor.execute("DELETE FROM daily_stats WHERE date < ?", (cutoff_date,))
        cursor.execute("DELETE FROM daily_topics WHERE date < ?", (cutoff_date,))
        cursor.execute("DELETE FROM daily_summary WHERE date < ?", (cutoff_date,))
        
        self.conn.commit()
        print(f"✓ Удалены данные старше {cutoff_date}")
    
    def close(self):
        """Закрыть соединение с БД"""
        if self.conn:
            self.conn.close()


if __name__ == "__main__":
    # Тест
    logger = HistoryLogger()
    
    # Проверяем диапазон
    date_range = logger.get_date_range()
    print(f"Диапазон: {date_range['min_date']} - {date_range['max_date']}")
    
    # Получаем доступные даты
    dates = logger.get_available_dates()
    print(f"Доступно дат: {len(dates)}")
    
    logger.close()
