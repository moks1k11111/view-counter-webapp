import requests
import re
import json
import logging
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Instagram URL patterns
INSTAGRAM_URL_PATTERN = r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+'

class InstagramAPI:
    """Клиент для работы с Instagram Scraper Stable API через RapidAPI"""
    
    def __init__(self, api_key, api_host="instagram-scraper-stable-api.p.rapidapi.com", base_url="https://instagram-scraper-stable-api.p.rapidapi.com"):
        self.api_key = api_key
        self.api_host = api_host
        self.base_url = base_url
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.api_host,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    def is_valid_instagram_url(self, url):
        """Проверка валидности Instagram URL"""
        return bool(re.match(INSTAGRAM_URL_PATTERN, url))
    
    def extract_username_from_url(self, url):
        """Извлекает username из Instagram URL"""
        match = re.search(r'instagram\.com/([^/\?]+)', url)
        if match:
            username = match.group(1)
            if username not in ['p', 'reel', 'reels', 'tv', 'stories', 'explore']:
                logger.info(f"✅ Извлечён username: @{username}")
                return username
        
        logger.error(f"❌ Не удалось извлечь username из URL: {url}")
        raise ValueError("Не удалось извлечь username из URL")
    
    def get_user_reels(self, username, amount=100, max_pages=5):
        """
        Получение reels пользователя с пагинацией
        
        Args:
            username: Instagram username (без @)
            amount: количество reels за один запрос
            max_pages: максимальное количество страниц пагинации
        
        Returns:
            dict с reels и статистикой
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"📥 ПОЛУЧЕНИЕ ВСЕХ REELS ДЛЯ @{username}")
            logger.info(f"{'='*60}\n")
            
            endpoint = f"{self.base_url}/get_ig_user_reels.php"
            
            all_reels = []
            pagination_token = None
            page = 1
            
            while page <= max_pages:
                payload = {
                    "username_or_url": username,
                    "amount": amount
                }
                
                # Добавляем токен пагинации если есть
                if pagination_token:
                    payload["pagination_token"] = pagination_token
                
                logger.info(f"📄 Страница {page}...")
                logger.info(f"📤 Запрос: {endpoint}")
                logger.info(f"📦 Параметры: username={username}, amount={amount}" +
                           (f", pagination_token=..." if pagination_token else ""))

                try:
                    response = requests.post(
                        endpoint,
                        headers=self.headers,
                        data=payload,
                        timeout=15  # Уменьшили timeout с 30 до 15 секунд
                    )
                    logger.info(f"📨 Статус: {response.status_code}")
                except requests.Timeout:
                    logger.error(f"⏱️ Timeout на странице {page}, пропускаем")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка запроса на странице {page}: {e}")
                    break
                
                if response.status_code == 200:
                    data = response.json()
                    
                    reels_list = data.get("reels", [])
                    logger.info(f"✅ Получено {len(reels_list)} reels на странице {page}")
                    
                    if not reels_list:
                        logger.info("⭐ Больше reels нет, останавливаем")
                        break
                    
                    all_reels.extend(reels_list)
                    
                    # Проверяем есть ли следующая страница
                    pagination_token = data.get("pagination_token")
                    if not pagination_token:
                        logger.info("✅ Все страницы загружены (нет pagination_token)")
                        break
                    
                    page += 1
                    
                    # Задержка между запросами (уменьшили с 1 до 0.5 сек)
                    if page <= max_pages:
                        import time
                        time.sleep(0.5)
                
                else:
                    logger.error(f"❌ Ошибка API: {response.status_code}")
                    logger.error(f"Response: {response.text}")
                    break
            
            # Подсчитываем статистику
            total_views = 0
            total_likes = 0
            total_comments = 0
            
            for i, reel_item in enumerate(all_reels, 1):
                node = reel_item.get("node", {})
                media = node.get("media", {})
                
                play_count = media.get("play_count", 0)
                like_count = media.get("like_count", 0)
                comment_count = media.get("comment_count", 0)
                
                total_views += play_count
                total_likes += like_count
                total_comments += comment_count
                
                if i <= 5 or i > len(all_reels) - 5:  # Показываем первые и последние 5
                    logger.info(f"  Reel {i}: 👁 {play_count:,} просмотров, ❤️ {like_count} лайков")
                elif i == 6:
                    logger.info(f"  ... (reels 6-{len(all_reels)-5}) ...")
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 ИТОГОВАЯ СТАТИСТИКА:")
            logger.info(f"{'='*60}")
            logger.info(f"🎬 Всего reels: {len(all_reels)}")
            logger.info(f"👁 Всего просмотров: {total_views:,}")
            logger.info(f"❤️ Всего лайков: {total_likes:,}")
            logger.info(f"💬 Всего комментариев: {total_comments:,}")
            logger.info(f"{'='*60}\n")
            
            return {
                "success": True,
                "username": username,
                "reels_count": len(all_reels),
                "total_views": total_views,
                "total_likes": total_likes,
                "total_comments": total_comments,
                "reels": all_reels
            }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения reels: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_profile_with_reels_stats(self, username):
        """
        Получение полной статистики профиля
        
        Возвращает:
        - username
        - количество reels
        - общие просмотры
        - лайки
        - комментарии
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"🔍 ПОЛУЧЕНИЕ СТАТИСТИКИ @{username}")
            logger.info(f"{'='*60}\n")
            
            # Получаем reels (максимум 100 за запрос, 5 страниц = ~500 reels)
            reels_data = self.get_user_reels(username, amount=100)
            
            if not reels_data.get("success"):
                raise Exception(reels_data.get("error", "Failed to get reels"))
            
            result = {
                "type": "profile",
                "platform": "instagram",
                "url": f"https://www.instagram.com/{username}/",
                "username": username,
                "reels": reels_data["reels_count"],
                "total_views": reels_data["total_views"],
                "total_likes": reels_data["total_likes"],
                "total_comments": reels_data["total_comments"],
                "followers": 0,  # Нужен отдельный endpoint для подписчиков
                "timestamp": time.time()
            }
            
            logger.info(f"✅ Статистика получена успешно")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            raise
    
    def get_instagram_data(self, url):
        """Получение данных по Instagram URL"""
        try:
            username = self.extract_username_from_url(url)
            return self.get_profile_with_reels_stats(username)
        except Exception as e:
            logger.error(f"❌ Ошибка обработки URL: {e}")
            raise


# Тест
if __name__ == "__main__":
    # Замени на свой ключ
    API_KEY = "YOUR_RAPIDAPI_KEY"
    
    api = InstagramAPI(API_KEY)
    
    # Тест
    username = "reddit.kr"
    result = api.get_profile_with_reels_stats(username)
    
    print(f"\n✅ Результат:")
    print(f"Username: {result['username']}")
    print(f"Reels: {result['reels']}")
    print(f"Просмотров: {result['total_views']:,}")
    print(f"Лайков: {result['total_likes']:,}")
