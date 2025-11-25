"""
TikTok Video Downloader с использованием RapidAPI
"""
import requests
import logging
from datetime import datetime, timedelta
import sqlite3

logger = logging.getLogger(__name__)

class TikTokDownloader:
    def __init__(self, rapidapi_key, db_path="bot_data.db"):
        self.rapidapi_key = rapidapi_key
        self.db_path = db_path
        self.headers = {
            'x-rapidapi-key': rapidapi_key,
            'x-rapidapi-host': 'tiktok-api23.p.rapidapi.com'
        }
        self.init_db()
    
    def init_db(self):
        """Инициализация таблицы для отслеживания скачиваний"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS video_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_url TEXT NOT NULL,
                download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def get_daily_downloads(self, user_id):
        """Получает количество скачиваний пользователя за сегодня"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        cursor.execute('''
            SELECT COUNT(*) FROM video_downloads 
            WHERE user_id = ? 
            AND download_date >= ? 
            AND download_date < ?
        ''', (user_id, today, tomorrow))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    
    def can_download(self, user_id, limit=6):
        """Проверяет может ли пользователь скачать видео"""
        count = self.get_daily_downloads(user_id)
        return count < limit
    
    def add_download(self, user_id, video_url):
        """Добавляет запись о скачивании"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO video_downloads (user_id, video_url)
            VALUES (?, ?)
        ''', (user_id, video_url))
        conn.commit()
        conn.close()
    
    def download_video(self, video_url):
        """
        Скачивает TikTok видео через RapidAPI
        
        Args:
            video_url: Ссылка на TikTok видео
            
        Returns:
            dict с информацией о видео и ссылкой на скачивание
        """
        try:
            logger.info(f"🎬 Скачивание видео: {video_url}")
            
            endpoint = "https://tiktok-api23.p.rapidapi.com/api/download/video"
            
            params = {
                "url": video_url
            }
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=30
            )
            
            logger.info(f"📨 Статус ответа: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Логируем полный ответ для отладки
                logger.info(f"📦 Ответ API: {data}")
                
                # Пробуем разные варианты получения ссылки
                # Приоритет: play (без watermark) > download > play_watermark
                download_url = (
                    data.get("play", "") or
                    data.get("data", {}).get("play", "") or
                    data.get("data", {}).get("download", "") or
                    data.get("play_watermark", "") or
                    data.get("data", {}).get("wmplay", "") or
                    data.get("data", {}).get("hdplay", "") or
                    ""
                )
                
                # Извлекаем данные
                video_data = {
                    "success": True,
                    "download_url": download_url,
                    "title": data.get("data", {}).get("title", data.get("title", "TikTok Video")),
                    "author": data.get("data", {}).get("author", {}).get("nickname", data.get("author", {}).get("nickname", "Unknown")),
                    "play_count": data.get("data", {}).get("play_count", data.get("play_count", 0)),
                    "thumbnail": data.get("data", {}).get("cover", data.get("cover", "")),
                    "raw_data": data  # Сохраняем для отладки
                }
                
                logger.info(f"✅ Видео получено: {video_data['title']}")
                logger.info(f"🔗 Download URL: {download_url}")
                return video_data
            
            else:
                logger.error(f"❌ Ошибка API: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return {
                    "success": False,
                    "error": f"API error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка скачивания: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    def download_video_file(self, download_url):
        """
        Скачивает видео файл по ссылке
        
        Args:
            download_url: Прямая ссылка на видео
            
        Returns:
            bytes с содержимым видео или None
        """
        try:
            logger.info(f"📥 Скачиваю файл: {download_url}")
            
            response = requests.get(download_url, timeout=60, stream=True)
            
            if response.status_code == 200:
                logger.info(f"✅ Файл скачан, размер: {len(response.content)} байт")
                return response.content
            else:
                logger.error(f"❌ Ошибка скачивания файла: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return None
