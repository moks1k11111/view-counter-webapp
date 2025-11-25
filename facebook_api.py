import re
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Facebook URL patterns
FACEBOOK_URL_PATTERN = r'(https?://)?(www\.)?(facebook\.com|fb\.com|fb\.me)/.+'

class FacebookAPI:
    """Минимальный класс для работы с Facebook URL"""
    
    def __init__(self):
        pass
    
    def is_valid_facebook_url(self, url):
        """Проверка валидности Facebook URL"""
        return bool(re.match(FACEBOOK_URL_PATTERN, url))
    
    def extract_username_from_url(self, url):
        """
        Извлекает username/page из Facebook URL
        
        Примеры ВАЛИДНЫХ URL (профили):
        - https://www.facebook.com/username
        - https://facebook.com/username/
        - https://www.facebook.com/pages/PageName/123456789
        - https://www.facebook.com/profile.php?id=100012345678
        - https://fb.com/username
        
        Примеры НЕВАЛИДНЫХ URL (НЕ профили):
        - https://www.facebook.com/share/p/... (посты)
        - https://www.facebook.com/share/r/... (REELS)
        - https://www.facebook.com/share/v/... (видео)
        - https://www.facebook.com/reel/... (reels)
        - https://www.facebook.com/watch/... (видео)
        
        Примеры ВАЛИДНЫХ (профили и группы):
        - https://www.facebook.com/share/g/... (группы - разрешены!)
        """
        
        # БЛОКИРУЕМ только reels, посты и видео (НЕ группы!)
        blocked_paths = [
            '/share/p/',    # Посты (share post)
            '/share/r/',    # Reels (share reel)
            '/share/v/',    # Видео (share video)
            '/reel/',       # Прямые reels
            '/watch/',      # Видео watch
            '/photo/',      # Отдельные фото
            '/video/',      # Отдельные видео
            '/posts/',      # Посты
        ]
        
        for blocked in blocked_paths:
            if blocked in url.lower():
                error_msg = f"❌ Это не профиль! Facebook {blocked.strip('/')} не поддерживаются. Отправьте ссылку на профиль или страницу."
                logger.error(error_msg)
                raise ValueError(error_msg)
        
        # Проверка на profile.php?id=
        if 'profile.php' in url:
            match = re.search(r'id=(\d+)', url)
            if match:
                user_id = match.group(1)
                logger.info(f"✅ Извлечён Facebook ID: {user_id}")
                return user_id
            else:
                logger.error(f"❌ Не удалось извлечь ID из profile.php URL: {url}")
                raise ValueError("Не удалось извлечь ID из Facebook profile.php URL")
        
        # Убираем параметры и trailing slash
        url = url.split('?')[0].rstrip('/')
        
        # Паттерны для разных форматов FB URL
        patterns = [
            r'facebook\.com/([^/\?]+)',  # facebook.com/username
            r'fb\.com/([^/\?]+)',         # fb.com/username
            r'fb\.me/([^/\?]+)',          # fb.me/username
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                username = match.group(1)
                # Исключаем служебные пути
                if username not in ['pages', 'people', 'groups', 'events', 'watch', 'gaming', 'marketplace']:
                    logger.info(f"✅ Извлечён Facebook username: {username}")
                    return username
        
        logger.error(f"❌ Не удалось извлечь username из Facebook URL: {url}")
        raise ValueError("Не удалось извлечь username из Facebook URL")
    
    def normalize_url(self, url):
        """Нормализует Facebook URL"""
        try:
            username = self.extract_username_from_url(url)
            return f"https://www.facebook.com/{username}/"
        except:
            return url


# Тестирование
if __name__ == "__main__":
    api = FacebookAPI()
    
    # Валидные URL (профили)
    valid_urls = [
        "https://www.facebook.com/zuck",
        "https://facebook.com/CocaCola/",
        "https://fb.com/nike",
        "https://www.facebook.com/profile.php?id=100012345678",
    ]
    
    # Невалидные URL (не профили)
    invalid_urls = [
        "https://www.facebook.com/share/p/abc123",
        "https://www.facebook.com/share/r/xyz789",
        "https://www.facebook.com/share/v/def456",
        "https://www.facebook.com/reel/123456789",
        "https://www.facebook.com/watch/?v=123456789",
    ]
    
    print("="*70)
    print("✅ ТЕСТ ВАЛИДНЫХ URL (ПРОФИЛИ)")
    print("="*70)
    for url in valid_urls:
        try:
            print(f"\n📌 Тест URL: {url}")
            username = api.extract_username_from_url(url)
            print(f"✅ Username: {username}")
            normalized = api.normalize_url(url)
            print(f"✅ Normalized: {normalized}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    print("\n" + "="*70)
    print("❌ ТЕСТ НЕВАЛИДНЫХ URL (НЕ ПРОФИЛИ)")
    print("="*70)
    for url in invalid_urls:
        try:
            print(f"\n📌 Тест URL: {url}")
            username = api.extract_username_from_url(url)
            print(f"⚠️ ОШИБКА: Не должно было пройти! Username: {username}")
        except ValueError as e:
            print(f"✅ Правильно отклонён: {e}")
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
