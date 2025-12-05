import requests
import re
import json
import logging
import time
from urllib.parse import urlparse, parse_qs
from config import RAPIDAPI_KEY, RAPIDAPI_HOST, RAPIDAPI_BASE_URL, TIKTOK_URL_PATTERN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class TikTokAPI:
    """Исправленный клиент для работы с TikTok API через RapidAPI"""
    
    def __init__(self, api_key=RAPIDAPI_KEY, api_host=RAPIDAPI_HOST, base_url=RAPIDAPI_BASE_URL):
        self.api_key = api_key
        self.api_host = api_host
        self.base_url = base_url
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.api_host
        }
    
    def is_valid_tiktok_url(self, url):
        """Проверка валидности URL TikTok"""
        return bool(re.match(TIKTOK_URL_PATTERN, url))
    
    def normalize_tiktok_url(self, url):
        """Нормализация URL TikTok (для обработки коротких URL)"""
        if 'vm.tiktok.com' in url:
            try:
                response = requests.head(url, allow_redirects=True, timeout=10)
                logger.info(f"Нормализованный URL: {response.url}")
                return response.url
            except Exception as e:
                logger.error(f"Ошибка при нормализации URL: {e}")
                return url
        return url
    
    def extract_user_info(self, url):
        """Извлекает информацию о пользователе из URL TikTok"""
        normalized_url = self.normalize_tiktok_url(url)
        logger.info(f"Извлечение информации из URL: {normalized_url}")
        
        # Шаблон для аккаунта: tiktok.com/@username
        account_match = re.search(r'tiktok\.com/@([^/\?]+)', normalized_url)
        if account_match:
            username = account_match.group(1)
            logger.info(f"Найден профиль: @{username}")
            return {"type": "profile", "username": username}
        
        # Шаблон для видео: tiktok.com/@username/video/1234567890
        video_match = re.search(r'tiktok\.com/@([^/]+)/video/(\d+)', normalized_url)
        if video_match:
            username = video_match.group(1)
            video_id = video_match.group(2)
            logger.info(f"Найдено видео: ID={video_id}, автор=@{username}")
            return {"type": "video", "username": username, "video_id": video_id}
        
        logger.error(f"Не удалось распознать URL: {normalized_url}")
        raise ValueError("Не удалось извлечь информацию о пользователе из URL")
    
    def get_user_info(self, username):
        """Получение информации о пользователе по username"""
        endpoint = f"{self.base_url}/api/user/info"
        querystring = {"uniqueId": username}
        
        try:
            logger.info(f"=== ЗАПРОС ИНФОРМАЦИИ О ПОЛЬЗОВАТЕЛЕ ===")
            logger.info(f"Endpoint: {endpoint}")
            logger.info(f"Username: @{username}")
            logger.info(f"Headers: {self.headers}")

            response = requests.get(endpoint, headers=self.headers, params=querystring, timeout=30)
            logger.info(f"Статус код: {response.status_code}")

            # Логируем тело ответа даже при ошибке
            try:
                response_text = response.text
                logger.info(f"Response body: {response_text[:500]}")  # Первые 500 символов
            except:
                pass

            response.raise_for_status()

            data = response.json()
            
            if data.get("statusCode") == 0:
                user_info = data.get("userInfo", {})
                user = user_info.get("user", {})
                stats = user_info.get("stats", {})
                
                result = {
                    "username": user.get("uniqueId"),
                    "nickname": user.get("nickname"),
                    "secUid": user.get("secUid"),
                    "followerCount": stats.get("followerCount", 0),
                    "followingCount": stats.get("followingCount", 0),
                    "heartCount": stats.get("heartCount", 0),
                    "videoCount": stats.get("videoCount", 0),
                    "verified": user.get("verified", False),
                    "privateAccount": user.get("privateAccount", False),
                    "signature": user.get("signature", ""),
                    "avatarLarger": user.get("avatarLarger", "")
                }
                
                logger.info(f"✅ Получена информация о @{result['username']}")
                logger.info(f"   secUid: {result['secUid'][:30]}...")
                logger.info(f"   Подписчиков: {result['followerCount']:,}")
                logger.info(f"   Видео: {result['videoCount']}")
                
                return result
            else:
                error_msg = data.get("status_msg", "Неизвестная ошибка")
                logger.error(f"API вернул ошибку: {error_msg}")
                raise Exception(f"Ошибка API: {error_msg}")
                
        except Exception as e:
            logger.error(f"Ошибка запроса: {e}")
            raise
    
    def get_user_posts_with_full_pagination(self, sec_uid, max_videos=500, max_retries=10):
        """
        🔥 УЛУЧШЕННАЯ ВЕРСИЯ: Получение ВСЕХ постов с расширенной пагинацией
        
        Добавлено:
        - Увеличенный лимит запросов (max_retries)
        - Проверка на дубликаты видео
        - Более агрессивная пагинация
        """
        endpoint = f"{self.base_url}/api/user/posts"
        
        logger.info(f"\n{'='*70}")
        logger.info(f"🎬 ПОЛУЧЕНИЕ ВСЕХ ВИДЕО С РАСШИРЕННОЙ ПАГИНАЦИЕЙ")
        logger.info(f"{'='*70}")
        
        all_items = []
        seen_video_ids = set()  # Для отслеживания дубликатов
        cursor = 0
        has_more = True
        page = 1
        retry_count = 0
        
        while has_more and len(all_items) < max_videos and retry_count < max_retries:
            try:
                querystring = {
                    "secUid": sec_uid,
                    "count": "35",  # Максимум за раз
                    "cursor": str(cursor)
                }
                
                logger.info(f"\n📄 Страница {page} (cursor: {cursor})...")

                response = requests.get(endpoint, headers=self.headers, params=querystring, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                if "data" in data:
                    data_obj = data.get("data", {})
                    item_list = data_obj.get("itemList", [])
                    has_more = data_obj.get("hasMore", False)
                    new_cursor = data_obj.get("cursor", cursor)
                    
                    # Фильтруем дубликаты
                    new_items = []
                    for item in item_list:
                        video_id = item.get("id")
                        if video_id and video_id not in seen_video_ids:
                            seen_video_ids.add(video_id)
                            new_items.append(item)
                    
                    logger.info(f"   ✓ Получено видео: {len(item_list)} (новых: {len(new_items)})")
                    logger.info(f"   ✓ Есть еще: {'Да' if has_more else 'Нет'}")
                    logger.info(f"   ✓ Всего собрано: {len(all_items) + len(new_items)}")
                    
                    all_items.extend(new_items)
                    
                    # Если cursor не изменился, пробуем увеличить вручную
                    if new_cursor == cursor and has_more:
                        logger.warning(f"   ⚠️ Cursor не изменился, попытка #{retry_count + 1}")
                        cursor = cursor + 1  # Инкремент
                        retry_count += 1
                    else:
                        cursor = new_cursor
                        retry_count = 0  # Сбрасываем счетчик
                    
                    page += 1
                    
                    # Если получили 0 новых видео, но hasMore=True - что-то не так
                    if len(new_items) == 0 and has_more:
                        logger.warning(f"   ⚠️ Получено 0 новых видео, но API говорит hasMore=True")
                        retry_count += 1
                    
                    # Задержка между запросами (уменьшили с 2 до 1 сек)
                    if has_more:
                        time.sleep(1)
                else:
                    logger.error("   ❌ Нет данных в ответе")
                    break
                    
            except Exception as e:
                logger.error(f"   ❌ Ошибка: {e}")
                break
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 ИТОГО ПОЛУЧЕНО УНИКАЛЬНЫХ ВИДЕО: {len(all_items)}")
        logger.info(f"{'='*70}")
        
        return all_items
    
    def get_user_profile_with_total_views(self, username, use_extended_pagination=True):
        """
        🔥 УЛУЧШЕННАЯ ВЕРСИЯ: Получение полной статистики профиля
        
        Параметры:
        - use_extended_pagination: если True, использует расширенную пагинацию
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"ПОЛУЧЕНИЕ ПОЛНОЙ СТАТИСТИКИ ДЛЯ @{username}")
            logger.info(f"{'='*60}\n")
            
            # Шаг 1: Получаем информацию о пользователе и secUid
            user_info = self.get_user_info(username)
            sec_uid = user_info.get("secUid")
            
            if not sec_uid:
                raise Exception("Не удалось получить secUid пользователя")
            
            # Шаг 2: Получаем все посты с расширенной пагинацией (макс 500 видео)
            time.sleep(2)
            if use_extended_pagination:
                items = self.get_user_posts_with_full_pagination(sec_uid, max_videos=500)
            else:
                # Старый метод (оставлен для совместимости)
                items = self._get_user_posts_old(sec_uid)
            
            # Шаг 3: Суммируем просмотры по всем видео
            total_views = 0
            total_likes = 0
            total_comments = 0
            total_shares = 0
            
            for item in items:
                stats = item.get("stats", {})
                total_views += stats.get("playCount", 0)
                total_likes += stats.get("diggCount", 0)
                total_comments += stats.get("commentCount", 0)
                total_shares += stats.get("shareCount", 0)
            
            # Формируем финальный результат
            result = {
                "type": "profile",
                "url": f"https://www.tiktok.com/@{username}",
                "username": user_info.get("username"),
                "nickname": user_info.get("nickname"),
                "followers": user_info.get("followerCount", 0),
                "following": user_info.get("followingCount", 0),
                "likes": user_info.get("heartCount", 0),  # Из API профиля (общее количество)
                "videos": len(items),  # 🔥 РЕАЛЬНОЕ количество полученных видео (видимых)
                "total_views": total_views,  # 🔥 Сумма просмотров по ПОЛУЧЕННЫМ видео
                "verified": user_info.get("verified", False),
                "private": user_info.get("privateAccount", False),
                "bio": user_info.get("signature", ""),
                "avatar": user_info.get("avatarLarger", ""),
                "timestamp": time.time()
            }
            
            logger.info(f"\n{'='*60}")
            logger.info(f"✅ ИТОГОВАЯ СТАТИСТИКА @{username}:")
            logger.info(f"{'='*60}")
            logger.info(f"👥 Подписчиков: {result['followers']:,}")
            logger.info(f"👣 Подписок: {result['following']:,}")
            logger.info(f"🎬 Видео (видимых): {result['videos']}")
            logger.info(f"👁 Всего просмотров: {result['total_views']:,}")
            logger.info(f"❤️ Лайков (общее): {result['likes']:,}")
            logger.info(f"{'='*60}\n")
            
            return result
            
        except KeyError as e:
            logger.error(f"❌ Ошибка: отсутствует ключ {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка при получении статистики профиля: {e}")
            raise
    
    def _get_user_posts_old(self, sec_uid, count=35, cursor=0):
        """Старый метод получения постов (для совместимости)"""
        endpoint = f"{self.base_url}/api/user/posts"
        
        querystring = {
            "secUid": sec_uid,
            "count": str(count),
            "cursor": str(cursor)
        }
        
        try:
            response = requests.get(endpoint, headers=self.headers, params=querystring, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if "data" in data:
                data_obj = data.get("data", {})
                item_list = data_obj.get("itemList", [])
                return item_list
            else:
                return []
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return []
    
    def get_video_info(self, video_id):
        """Получение информации о конкретном видео"""
        endpoint = f"{self.base_url}/api/video/info"
        querystring = {"video_id": video_id}
        
        try:
            logger.info(f"=== ЗАПРОС ИНФОРМАЦИИ О ВИДЕО ===")
            logger.info(f"Video ID: {video_id}")
            
            response = requests.get(endpoint, headers=self.headers, params=querystring, timeout=30)
            logger.info(f"Статус код: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status_code") == 0:
                video_data = data.get("data", {})
                stats = video_data.get("stats", {})
                author = video_data.get("author", {})
                
                result = {
                    "type": "video",
                    "url": f"https://www.tiktok.com/@{author.get('uniqueId')}/video/{video_id}",
                    "video_id": video_id,
                    "author": author.get("uniqueId"),
                    "title": video_data.get("desc", ""),
                    "views": stats.get("playCount", 0),
                    "likes": stats.get("diggCount", 0),
                    "comments": stats.get("commentCount", 0),
                    "shares": stats.get("shareCount", 0),
                    "timestamp": time.time()
                }
                
                logger.info(f"✅ Получена информация о видео {video_id}")
                logger.info(f"   Просмотров: {result['views']:,}")
                logger.info(f"   Лайков: {result['likes']:,}")
                
                return result
            else:
                error_msg = data.get("status_msg", "Неизвестная ошибка")
                logger.error(f"API вернул ошибку: {error_msg}")
                raise Exception(f"Ошибка API: {error_msg}")
                
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            raise
    
    def get_tiktok_data(self, url):
        """Основной метод для получения данных TikTok по URL"""
        logger.info(f"Получение данных TikTok для URL: {url}")
        
        if not self.is_valid_tiktok_url(url):
            raise ValueError("Неверный URL TikTok")
        
        # Извлекаем информацию о пользователе/видео из URL
        info = self.extract_user_info(url)
        
        # В зависимости от типа URL вызываем соответствующий метод
        if info["type"] == "profile":
            return self.get_user_profile_with_total_views(info["username"], use_extended_pagination=True)
        elif info["type"] == "video":
            return self.get_video_info(info["video_id"])
        
        raise ValueError("Неподдерживаемый тип URL TikTok")


# Тестирование
if __name__ == "__main__":
    api = TikTokAPI()
    
    try:
        print("\n=== ТЕСТ: Получение статистики профиля ===")
        profile_url = "https://www.tiktok.com/@stb_ua_holostyak"
        data = api.get_tiktok_data(profile_url)
        print(f"\n✅ Успех! Получены данные:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
