import requests
import re
import json
import logging
import time
from datetime import datetime
from config import FACEBOOK_RAPIDAPI_KEY, FACEBOOK_RAPIDAPI_HOST, FACEBOOK_APP_ID, FACEBOOK_URL_PATTERN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class FacebookAPI:
    """Клиент для работы с Facebook Reels API через RapidAPI"""

    def __init__(self, api_key=FACEBOOK_RAPIDAPI_KEY, api_host=FACEBOOK_RAPIDAPI_HOST, app_id=FACEBOOK_APP_ID):
        self.api_key = api_key
        self.api_host = api_host
        self.app_id = app_id
        self.base_url = f"https://{api_host}"
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.api_host
        }

    def is_valid_facebook_url(self, url):
        """Проверка валидности Facebook URL"""
        return bool(re.match(FACEBOOK_URL_PATTERN, url))

    def extract_page_from_url(self, url):
        """Извлекает имя страницы из Facebook URL"""
        # Паттерны для Facebook URL:
        # https://facebook.com/pagename
        # https://www.facebook.com/pagename
        # https://facebook.com/profile.php?id=123456789

        match = re.search(r'facebook\.com/([^/\?]+)', url)
        if match:
            page_name = match.group(1)
            if page_name not in ['profile.php', 'watch', 'reel', 'reels', 'stories', 'pages']:
                logger.info(f"✅ Извлечено имя страницы: {page_name}")
                return page_name

        # Проверка на profile.php?id=
        match = re.search(r'facebook\.com/profile\.php\?id=(\d+)', url)
        if match:
            profile_id = match.group(1)
            logger.info(f"✅ Извлечён profile ID: {profile_id}")
            return profile_id

        logger.error(f"❌ Не удалось извлечь имя страницы из URL: {url}")
        raise ValueError("Не удалось извлечь имя страницы из URL")

    def parse_date(self, date_string):
        """Парсинг даты из различных форматов"""
        try:
            # Попытка парсить ISO формат: 2025-12-09T10:30:00Z
            if 'T' in date_string:
                dt = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
                return dt

            # Попытка парсить простой формат: 2025-12-09
            dt = datetime.strptime(date_string[:10], '%Y-%m-%d')
            return dt
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга даты '{date_string}': {e}")
            return None

    def get_page_reels(self, page_url, kpi_views=0, date_from=None, date_to=None, max_videos=500):
        """
        Получение всех Reels со страницы Facebook с пагинацией

        Args:
            page_url: URL страницы Facebook
            kpi_views: минимальное количество просмотров для учета видео (0 = все видео)
            date_from: Дата начала периода (YYYY-MM-DD)
            date_to: Дата окончания периода (YYYY-MM-DD)
            max_videos: максимальное количество видео для загрузки (по умолчанию 500)

        Returns:
            dict с видео и статистикой
        """
        try:
            page_name = self.extract_page_from_url(page_url)

            logger.info(f"\n{'='*60}")
            logger.info(f"📥 ПОЛУЧЕНИЕ ВСЕХ REELS ДЛЯ СТРАНИЦЫ: {page_name}")
            logger.info(f"📊 Фильтры: KPI >= {kpi_views} просмотров")
            if date_from:
                logger.info(f"📅 Период: с {date_from} по {date_to}")
            logger.info(f"📦 Лимит: {max_videos} видео")
            logger.info(f"{'='*60}\n")

            # Парсинг дат для фильтрации
            date_from_dt = self.parse_date(date_from) if date_from else None
            date_to_dt = self.parse_date(date_to) if date_to else None

            all_videos = []
            cursor = None
            page_number = 1
            total_fetched = 0

            # Endpoint для получения Reels
            endpoint = f"{self.base_url}/fba/facebook-lookup-reels"

            while total_fetched < max_videos:
                # Параметры запроса
                params = {
                    "url": page_url  # Передаем полный URL страницы
                }

                # Добавляем cursor для пагинации
                if cursor:
                    params["cursor"] = cursor

                logger.info(f"📄 Страница {page_number}...")
                logger.info(f"📤 Запрос: {endpoint}")
                logger.info(f"📦 Параметры: url={page_url}" +
                           (f", cursor=..." if cursor else ""))

                try:
                    response = requests.get(
                        endpoint,
                        headers=self.headers,
                        params=params,
                        timeout=15
                    )
                    logger.info(f"📨 Статус: {response.status_code}")
                except requests.Timeout:
                    logger.error(f"⏱️ Timeout на странице {page_number}, завершаем")
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка запроса на странице {page_number}: {e}")
                    break

                if response.status_code == 200:
                    try:
                        data = response.json()

                        # Проверяем статус ответа
                        response_status = data.get("responseStatus", "")
                        if response_status != "PRODUCT_FOUND_RESPONSE":
                            logger.warning(f"⚠️ Неожиданный статус: {response_status}")
                            break

                        # Получаем видео из ответа (details - это массив видео)
                        details = data.get("details", [])
                        # Если details - dict, конвертируем в list
                        if isinstance(details, dict):
                            videos = list(details.values())
                        else:
                            videos = details

                        count_posts = data.get("countPosts", 0)
                        has_next_page = data.get("hasNextPage", False)
                        cursor = data.get("cursor", None)

                        logger.info(f"📊 Получено видео: {count_posts}")
                        logger.info(f"📑 Есть следующая страница: {has_next_page}")

                        # Обрабатываем каждое видео
                        for video in videos:
                            # Извлекаем данные видео
                            video_url = video.get("url", "")
                            video_views = video.get("videoViewCount", 0)
                            video_date_str = video.get("date", "")
                            likers_count = video.get("likersCount", 0)
                            comment_count = video.get("commentCount", 0)

                            # Парсим дату видео
                            video_date = self.parse_date(video_date_str) if video_date_str else None

                            # Фильтрация по дате
                            if date_from_dt and video_date:
                                if video_date < date_from_dt:
                                    logger.info(f"⏭️ Видео старше {date_from}, пропускаем")
                                    continue

                            if date_to_dt and video_date:
                                if video_date > date_to_dt:
                                    logger.info(f"⏭️ Видео новее {date_to}, пропускаем")
                                    continue

                            # Фильтрация по KPI
                            if video_views < kpi_views:
                                logger.info(f"⏭️ Видео с {video_views} просмотрами меньше KPI ({kpi_views}), пропускаем")
                                continue

                            # Добавляем видео в список
                            all_videos.append({
                                "url": video_url,
                                "views": video_views,
                                "date": video_date_str,
                                "likes": likers_count,
                                "comments": comment_count
                            })

                            total_fetched += 1
                            logger.info(f"✅ Видео #{total_fetched}: {video_views} просмотров, {likers_count} лайков")

                            # Проверяем лимит
                            if total_fetched >= max_videos:
                                logger.info(f"🛑 Достигнут лимит в {max_videos} видео")
                                break

                        # Проверяем есть ли следующая страница
                        if not has_next_page or not cursor:
                            logger.info("✅ Больше страниц нет, завершаем")
                            break

                        # Задержка между запросами
                        time.sleep(1)
                        page_number += 1

                    except json.JSONDecodeError as e:
                        logger.error(f"❌ Ошибка парсинга JSON: {e}")
                        logger.error(f"Response text: {response.text[:500]}")
                        break
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки данных: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        break
                else:
                    logger.error(f"❌ Ошибка API: {response.status_code}")
                    logger.error(f"Response: {response.text[:500]}")
                    break

            # Подсчет статистики
            total_views = sum(v["views"] for v in all_videos)
            total_likes = sum(v["likes"] for v in all_videos)
            total_comments = sum(v["comments"] for v in all_videos)

            logger.info(f"\n{'='*60}")
            logger.info(f"📊 ИТОГОВАЯ СТАТИСТИКА")
            logger.info(f"{'='*60}")
            logger.info(f"🎬 Всего видео: {len(all_videos)}")
            logger.info(f"👁️ Всего просмотров: {total_views:,}")
            logger.info(f"❤️ Всего лайков: {total_likes:,}")
            logger.info(f"💬 Всего комментариев: {total_comments:,}")
            logger.info(f"{'='*60}\n")

            return {
                "success": True,
                "total_videos": len(all_videos),
                "total_views": total_views,
                "total_likes": total_likes,
                "total_comments": total_comments,
                "videos": all_videos,
                "page_name": page_name
            }

        except Exception as e:
            logger.error(f"❌ Критическая ошибка при получении Reels: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "total_views": 0,
                "total_videos": 0
            }


# Тестирование (если запускается напрямую)
if __name__ == "__main__":
    api = FacebookAPI()

    # Пример URL
    test_url = "https://facebook.com/examplepage"

    # Тестирование парсинга страницы
    try:
        page_name = api.extract_page_from_url(test_url)
        print(f"✅ Page name: {page_name}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Тестирование получения Reels
    # result = api.get_page_reels(test_url, kpi_views=1000, date_from="2025-12-01", date_to="2025-12-09")
    # print(json.dumps(result, indent=2, ensure_ascii=False))
