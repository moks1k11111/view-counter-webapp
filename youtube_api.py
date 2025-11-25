import re
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# YouTube URL patterns
YOUTUBE_URL_PATTERN = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'

class YouTubeAPI:
    """Минимальный класс для работы с YouTube URL"""
    
    def __init__(self):
        pass
    
    def is_valid_youtube_url(self, url):
        """Проверка валидности YouTube URL"""
        return bool(re.match(YOUTUBE_URL_PATTERN, url))
    
    def extract_channel_info_from_url(self, url):
        """
        Извлекает channel ID или username из YouTube URL
        
        Примеры URL:
        - https://www.youtube.com/@username
        - https://www.youtube.com/channel/UCxxxxx
        - https://www.youtube.com/c/channelname
        - https://www.youtube.com/user/username
        """
        # Убираем параметры и trailing slash
        url = url.split('?')[0].rstrip('/')
        
        # Паттерн для @username (новый формат)
        match = re.search(r'youtube\.com/@([^/\?]+)', url)
        if match:
            username = match.group(1)
            logger.info(f"✅ Извлечён YouTube username: @{username}")
            return {"type": "username", "value": username}
        
        # Паттерн для /channel/ID
        match = re.search(r'youtube\.com/channel/([^/\?]+)', url)
        if match:
            channel_id = match.group(1)
            logger.info(f"✅ Извлечён YouTube channel ID: {channel_id}")
            return {"type": "channel_id", "value": channel_id}
        
        # Паттерн для /c/channelname
        match = re.search(r'youtube\.com/c/([^/\?]+)', url)
        if match:
            channel_name = match.group(1)
            logger.info(f"✅ Извлечён YouTube channel name: {channel_name}")
            return {"type": "channel_name", "value": channel_name}
        
        # Паттерн для /user/username
        match = re.search(r'youtube\.com/user/([^/\?]+)', url)
        if match:
            username = match.group(1)
            logger.info(f"✅ Извлечён YouTube user: {username}")
            return {"type": "user", "value": username}
        
        logger.error(f"❌ Не удалось извлечь информацию из YouTube URL: {url}")
        raise ValueError("Не удалось извлечь информацию о канале из YouTube URL")
    
    def normalize_url(self, url):
        """Нормализует YouTube URL"""
        try:
            info = self.extract_channel_info_from_url(url)
            if info["type"] == "username":
                return f"https://www.youtube.com/@{info['value']}"
            elif info["type"] == "channel_id":
                return f"https://www.youtube.com/channel/{info['value']}"
            elif info["type"] == "channel_name":
                return f"https://www.youtube.com/c/{info['value']}"
            elif info["type"] == "user":
                return f"https://www.youtube.com/user/{info['value']}"
            return url
        except:
            return url
    
    def get_display_name(self, url):
        """Получает имя для отображения"""
        try:
            info = self.extract_channel_info_from_url(url)
            if info["type"] == "username":
                return f"@{info['value']}"
            return info['value']
        except:
            return "Unknown"


# Тестирование
if __name__ == "__main__":
    api = YouTubeAPI()
    
    test_urls = [
        "https://www.youtube.com/@MrBeast",
        "https://www.youtube.com/channel/UCX6OQ3DkcsbYNE6H8uQQuVA",
        "https://www.youtube.com/c/Google",
        "https://www.youtube.com/user/pewdiepie",
    ]
    
    for url in test_urls:
        try:
            print(f"\n📌 Тест URL: {url}")
            info = api.extract_channel_info_from_url(url)
            print(f"✅ Type: {info['type']}, Value: {info['value']}")
            normalized = api.normalize_url(url)
            print(f"✅ Normalized: {normalized}")
            display = api.get_display_name(url)
            print(f"✅ Display: {display}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
