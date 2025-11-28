import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
import time
import traceback
import asyncio
import json
import os
import base64

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class SheetsDatabase:
    """Класс для работы с Google Sheets в качестве базы данных"""

    def __init__(self, credentials_file, spreadsheet_name, credentials_json=""):
        """Инициализация подключения к Google Sheets

        Args:
            credentials_file: путь к файлу credentials (для локальной разработки)
            spreadsheet_name: название Google Sheets
            credentials_json: JSON-строка с credentials (для Railway)
        """
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]

        try:
            # Пробуем использовать JSON-строку (Railway/Render)
            if credentials_json:
                # Декодируем base64, если это base64-закодированная строка
                try:
                    decoded_json = base64.b64decode(credentials_json).decode('utf-8')
                except Exception:
                    # Если не base64, используем как есть
                    decoded_json = credentials_json

                # Заменяем экранированные переносы строк на обычные
                decoded_json = decoded_json.replace('\\n', '\n')
                creds_dict = json.loads(decoded_json)
                credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
            # Иначе используем файл (локальная разработка)
            elif os.path.exists(credentials_file):
                credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, self.scope)
            else:
                raise FileNotFoundError(f"No credentials found: neither JSON string nor file {credentials_file}")

            self.client = gspread.authorize(credentials)
            
            try:
                self.spreadsheet = self.client.open(spreadsheet_name)
                logger.info(f"Подключено к таблице {spreadsheet_name}")
            except gspread.exceptions.SpreadsheetNotFound:
                self.spreadsheet = self.client.create(spreadsheet_name)
                logger.info(f"Создана новая таблица {spreadsheet_name}")
            
            self._init_worksheets()
            
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}")
            raise
    
    def _init_worksheets(self):
        """Инициализация рабочих листов для TikTok, Instagram, Facebook и YouTube"""
        sheet_names = [sheet.title for sheet in self.spreadsheet.worksheets()]
        
        # ===== TIKTOK ЛИСТ =====
        if "TikTok" not in sheet_names:
            self.tiktok = self.spreadsheet.add_worksheet(title="TikTok", rows=1000, cols=10)
            logger.info("✅ Создан новый лист TikTok")
        else:
            self.tiktok = self.spreadsheet.worksheet("TikTok")
            logger.info("✅ Найден существующий лист TikTok")
        
        if len(self.tiktok.get_all_values()) == 0:
            headers = [
                "Telegram User",
                "TikTok URL",
                "Подписчики",
                "Лайки",
                "Подписки",
                "Видео",
                "Просмотры",
                "Last Update",
                "Статус",
                "Тематика",
                "Проект"
            ]
            self.tiktok.append_row(headers)
            self.tiktok.format('A1:K1', {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER"
            })
            logger.info("✅ Добавлены заголовки в лист TikTok")
        
        # ===== INSTAGRAM ЛИСТ =====
        if "Instagram" not in sheet_names:
            self.instagram = self.spreadsheet.add_worksheet(title="Instagram", rows=1000, cols=10)
            logger.info("✅ Создан новый лист Instagram")
        else:
            self.instagram = self.spreadsheet.worksheet("Instagram")
            logger.info("✅ Найден существующий лист Instagram")
        
        if len(self.instagram.get_all_values()) == 0:
            headers = [
                "Telegram User",
                "Instagram URL",
                "Подписчики",
                "Лайки",
                "Подписки",
                "Reels",
                "Просмотры",
                "Last Update",
                "Статус",
                "Тематика",
                "Проект"
            ]
            self.instagram.append_row(headers)
            self.instagram.format('A1:K1', {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER"
            })
            logger.info("✅ Добавлены заголовки в лист Instagram")
        
        # ===== FACEBOOK ЛИСТ =====
        if "Facebook" not in sheet_names:
            self.facebook = self.spreadsheet.add_worksheet(title="Facebook", rows=1000, cols=10)
            logger.info("✅ Создан новый лист Facebook")
        else:
            self.facebook = self.spreadsheet.worksheet("Facebook")
            logger.info("✅ Найден существующий лист Facebook")
        
        if len(self.facebook.get_all_values()) == 0:
            headers = [
                "Telegram User",
                "Facebook URL",
                "Подписчики",
                "Лайки",
                "Подписки",
                "Посты",
                "Просмотры",
                "Last Update",
                "Статус",
                "Тематика",
                "Проект"
            ]
            self.facebook.append_row(headers)
            self.facebook.format('A1:K1', {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER"
            })
            logger.info("✅ Добавлены заголовки в лист Facebook")
        
        # ===== YOUTUBE ЛИСТ =====
        if "YouTube" not in sheet_names:
            self.youtube = self.spreadsheet.add_worksheet(title="YouTube", rows=1000, cols=10)
            logger.info("✅ Создан новый лист YouTube")
        else:
            self.youtube = self.spreadsheet.worksheet("YouTube")
            logger.info("✅ Найден существующий лист YouTube")
        
        if len(self.youtube.get_all_values()) == 0:
            headers = [
                "Telegram User",
                "YouTube URL",
                "Подписчики",
                "Лайки",
                "Подписки",
                "Видео",
                "Просмотры",
                "Last Update",
                "Статус",
                "Тематика",
                "Проект"
            ]
            self.youtube.append_row(headers)
            self.youtube.format('A1:K1', {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER"
            })
            logger.info("✅ Добавлены заголовки в лист YouTube")
        
        # Удаляем старый лист links если есть
        if "links" in sheet_names:
            try:
                old_sheet = self.spreadsheet.worksheet("links")
                self.spreadsheet.del_worksheet(old_sheet)
                logger.info("🗑️ Удалён старый лист 'links'")
            except:
                pass

        # Добавляем колонку "Проект" в существующие листы, если её нет
        self._add_project_column_if_missing()

    def _add_project_column_if_missing(self):
        """Добавляет колонку 'Проект' в существующие листы, если её нет"""
        sheets_to_check = [
            (self.tiktok, "TikTok"),
            (self.instagram, "Instagram"),
            (self.facebook, "Facebook"),
            (self.youtube, "YouTube")
        ]

        for sheet, sheet_name in sheets_to_check:
            try:
                # Получаем первую строку (заголовки)
                headers = sheet.row_values(1)

                if not headers:
                    # Лист пуст, пропускаем
                    continue

                # Проверяем, есть ли колонка "Проект"
                if "Проект" not in headers:
                    # Добавляем колонку "Проект" в конец
                    col_index = len(headers) + 1

                    # Проверяем и расширяем лист, если нужно
                    current_cols = sheet.col_count
                    if col_index > current_cols:
                        sheet.resize(cols=col_index)
                        logger.info(f"📐 Расширен лист {sheet_name} до {col_index} колонок")

                    sheet.update_cell(1, col_index, "Проект")

                    # Форматируем заголовок
                    sheet.format(f'{chr(64 + col_index)}1', {
                        "textFormat": {"bold": True},
                        "horizontalAlignment": "CENTER"
                    })

                    logger.info(f"✅ Добавлена колонка 'Проект' в лист {sheet_name}")
                else:
                    logger.info(f"✓ Колонка 'Проект' уже существует в листе {sheet_name}")

            except Exception as e:
                logger.error(f"❌ Ошибка проверки/добавления колонки 'Проект' в {sheet_name}: {e}")

    def _get_sheet_by_platform(self, platform):
        """Возвращает нужный лист в зависимости от платформы"""
        if platform == "instagram":
            return self.instagram
        elif platform == "facebook":
            return self.facebook
        elif platform == "youtube":
            return self.youtube
        return self.tiktok
    
    def _normalize_url(self, url):
        """Нормализует URL для сравнения"""
        if not url:
            return ""
        url = url.split('?')[0].rstrip('/').lower()
        return url
    
    def _find_profile_row(self, url, platform="tiktok"):
        """Ищет строку с указанным URL в нужном листе"""
        try:
            sheet = self._get_sheet_by_platform(platform)
            urls_column = sheet.col_values(2)
            normalized_search_url = self._normalize_url(url)
            
            for i, cell_url in enumerate(urls_column[1:], start=2):
                if cell_url and self._normalize_url(cell_url) == normalized_search_url:
                    logger.info(f"✅ Найден профиль в строке {i}: {cell_url}")
                    return i
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске профиля: {e}")
            return None
    
    def check_profile_exists(self, url, platform="tiktok"):
        """Проверяет существует ли уже этот профиль в таблице"""
        return self._find_profile_row(url, platform) is not None
    
    def add_profile(self, telegram_user, url, status="NEW", platform="tiktok", topic="", project_name=""):
        """Добавляет новый профиль в таблицу"""
        try:
            if self.check_profile_exists(url, platform):
                logger.warning(f"⚠️ Профиль уже существует: {url}")
                return {"exists": True, "url": url}

            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            new_row = [
                telegram_user,
                url,
                0,
                0,
                0,
                0,
                0,
                timestamp,
                status,
                topic,
                project_name
            ]

            sheet = self._get_sheet_by_platform(platform)
            sheet.append_row(new_row)

            all_values = sheet.get_all_values()
            new_row_index = len(all_values)

            logger.info(f"✅ Добавлен {platform} профиль ({status}, {topic}, проект: {project_name}) в строку {new_row_index}: {url}")

            return {"exists": False, "row": new_row_index, "url": url, "status": status, "platform": platform, "topic": topic, "project_name": project_name}

        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении профиля: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def update_profile_stats(self, url, stats, platform="tiktok"):
        """Обновляет статистику профиля (только для статуса NEW)"""
        try:
            row_index = self._find_profile_row(url, platform)
            
            if not row_index:
                logger.warning(f"⚠️ Профиль не найден: {url}")
                return None
            
            sheet = self._get_sheet_by_platform(platform)
            status = sheet.cell(row_index, 9).value
            
            if status in ["OLD", "BAN"]:
                logger.info(f"⭐ Пропускаем {status} профиль: {url}")
                return {"skipped": True, "reason": f"{status} profile"}
            
            followers = stats.get("followers", 0)
            
            # Для Instagram: лайки и комменты из total_likes/total_comments
            if platform == "instagram":
                likes = stats.get("total_likes", 0)
                following = stats.get("total_comments", 0)  # Комментарии в столбец following
            else:
                likes = stats.get("likes", 0)
                following = stats.get("following", 0)
            
            videos = stats.get("videos", 0) if platform == "tiktok" else stats.get("reels", 0)
            total_views = stats.get("total_views", 0)
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            
            logger.info(f"🔄 Обновляем NEW {platform} профиль в строке {row_index}")
            
            updates = [
                {"range": f"C{row_index}", "values": [[followers]]},
                {"range": f"D{row_index}", "values": [[likes]]},
                {"range": f"E{row_index}", "values": [[following]]},
                {"range": f"F{row_index}", "values": [[videos]]},
                {"range": f"G{row_index}", "values": [[total_views]]},
                {"range": f"H{row_index}", "values": [[timestamp]]}
            ]
            
            sheet.batch_update(updates)
            content_type = "видео" if platform == "tiktok" else "reels"
            logger.info(f"✅ Обновлен профиль: {followers} подписчиков, {videos} {content_type}, {total_views} просмотров")
            
            return {"updated": True}
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def get_all_profiles(self, platform=None, project_name=None):
        """Получает все профили из таблицы с оптимизацией

        :param platform: Фильтр по платформе (tiktok, instagram, facebook, youtube)
        :param project_name: Фильтр по имени проекта
        """
        try:
            all_profiles = []

            platforms_to_get = []
            if platform == "tiktok":
                platforms_to_get = [("tiktok", self.tiktok)]
            elif platform == "instagram":
                platforms_to_get = [("instagram", self.instagram)]
            elif platform == "facebook":
                platforms_to_get = [("facebook", self.facebook)]
            elif platform == "youtube":
                platforms_to_get = [("youtube", self.youtube)]
            else:
                # Получаем все 4 платформы
                platforms_to_get = [
                    ("tiktok", self.tiktok),
                    ("instagram", self.instagram),
                    ("facebook", self.facebook),
                    ("youtube", self.youtube)
                ]

            for plat, sheet in platforms_to_get:
                # Используем batch_get вместо get_all_values для экономии квоты
                all_rows = sheet.get_all_values()[1:]

                # Добавляем задержку между листами
                time.sleep(0.5)

                for i, row in enumerate(all_rows, start=2):
                    if len(row) >= 2 and row[1]:
                        profile_project = row[10] if len(row) > 10 else ""

                        # Фильтруем по проекту, если указан
                        if project_name and profile_project != project_name:
                            continue

                        all_profiles.append({
                            "row": i,
                            "platform": plat,
                            "telegram_user": row[0] if len(row) > 0 else "",
                            "url": row[1] if len(row) > 1 else "",
                            "followers": row[2] if len(row) > 2 else 0,
                            "likes": row[3] if len(row) > 3 else 0,
                            "following": row[4] if len(row) > 4 else 0,
                            "videos": row[5] if len(row) > 5 else 0,
                            "total_views": row[6] if len(row) > 6 else 0,
                            "last_update": row[7] if len(row) > 7 else "",
                            "status": row[8] if len(row) > 8 else "NEW",
                            "topic": row[9] if len(row) > 9 else "",
                            "project_name": profile_project
                        })

            return all_profiles

        except Exception as e:
            logger.error(f"❌ Ошибка при получении профилей: {e}")
            return []
    
    def get_user_profiles(self, telegram_user, project_name=None):
        """Получает профили пользователя, опционально фильтруя по проекту"""
        all_profiles = self.get_all_profiles()

        # Нормализуем для сравнения (убираем @)
        normalized_user = telegram_user.lstrip('@')

        # Фильтруем профили - сравниваем с и без @
        user_profiles = [
            p for p in all_profiles
            if p["telegram_user"].lstrip('@') == normalized_user
        ]

        # Если указан проект - фильтруем по нему
        if project_name:
            user_profiles = [
                p for p in user_profiles
                if p.get("project_name", "") == project_name
            ]
            logger.info(f"📊 Найдено {len(user_profiles)} профилей для {telegram_user} в проекте {project_name}")
        else:
            logger.info(f"📊 Найдено {len(user_profiles)} профилей для {telegram_user}")

        logger.info(f"🔍 Проверено {len(all_profiles)} всего профилей")

        return user_profiles
    
    def update_all_profiles(self, tiktok_api, instagram_api, min_views=0, project_name=None):
        """Обновляет ТОЛЬКО NEW профили через API обеих платформ

        :param tiktok_api: TikTok API instance
        :param instagram_api: Instagram API instance
        :param min_views: Минимальное количество просмотров для учёта видео/reels (по умолчанию 0 - учитываются все)
        :param project_name: Имя проекта для фильтрации (если None - обновляются все проекты)
        """
        try:
            result = {
                "tiktok": {"updated": 0, "skipped": 0, "errors": 0, "filtered": 0},
                "instagram": {"updated": 0, "skipped": 0, "errors": 0, "filtered": 0}
            }

            tiktok_profiles = self.get_all_profiles(platform="tiktok", project_name=project_name)
            logger.info(f"🔄 Начинаем обновление {len(tiktok_profiles)} TikTok профилей...")
            
            for idx, profile in enumerate(tiktok_profiles, 1):
                url = profile["url"]
                status = profile.get("status", "NEW")
                
                logger.info(f"📍 Прогресс TikTok: {idx}/{len(tiktok_profiles)}")
                
                if not url or "tiktok.com" not in url.lower():
                    result["tiktok"]["skipped"] += 1
                    continue
                
                if status == "OLD":
                    logger.info(f"⭐ Пропускаем OLD: {url}")
                    result["tiktok"]["skipped"] += 1
                    continue
                
                try:
                    logger.info(f"📊 Обновление NEW: {url}")
                    stats = tiktok_api.get_tiktok_data(url)

                    if stats and stats.get("type") == "profile":
                        # Проверяем минимальное количество просмотров
                        total_views = stats.get("total_views", 0) or 0
                        if min_views > 0 and total_views < min_views:
                            logger.info(f"🔽 Пропускаем (мало просмотров): {url} - {total_views} < {min_views}")
                            result["tiktok"]["filtered"] += 1
                        else:
                            update_result = self.update_profile_stats(url, stats, platform="tiktok")
                            if update_result and update_result.get("updated"):
                                result["tiktok"]["updated"] += 1
                                logger.info(f"✅ Успешно обновлен #{result['tiktok']['updated']}")
                            else:
                                result["tiktok"]["errors"] += 1
                    else:
                        result["tiktok"]["errors"] += 1

                    time.sleep(3)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления TikTok {url}: {e}")
                    result["tiktok"]["errors"] += 1
                    continue

            instagram_profiles = self.get_all_profiles(platform="instagram", project_name=project_name)
            logger.info(f"🔄 Начинаем обновление {len(instagram_profiles)} Instagram профилей...")
            
            for idx, profile in enumerate(instagram_profiles, 1):
                url = profile["url"]
                status = profile.get("status", "NEW")
                
                logger.info(f"📍 Прогресс Instagram: {idx}/{len(instagram_profiles)}")
                
                if not url or "instagram.com" not in url.lower():
                    result["instagram"]["skipped"] += 1
                    continue
                
                if status == "OLD":
                    logger.info(f"⭐ Пропускаем OLD: {url}")
                    result["instagram"]["skipped"] += 1
                    continue
                
                try:
                    logger.info(f"📊 Обновление NEW: {url}")
                    stats = instagram_api.get_instagram_data(url)

                    if stats and stats.get("platform") == "instagram":
                        # Проверяем минимальное количество просмотров
                        total_views = stats.get("total_views", 0) or 0
                        if min_views > 0 and total_views < min_views:
                            logger.info(f"🔽 Пропускаем (мало просмотров): {url} - {total_views} < {min_views}")
                            result["instagram"]["filtered"] += 1
                        else:
                            update_result = self.update_profile_stats(url, stats, platform="instagram")
                            if update_result and update_result.get("updated"):
                                result["instagram"]["updated"] += 1
                                logger.info(f"✅ Успешно обновлен #{result['instagram']['updated']}")
                            else:
                                result["instagram"]["errors"] += 1
                    else:
                        result["instagram"]["errors"] += 1

                    time.sleep(3)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления Instagram {url}: {e}")
                    result["instagram"]["errors"] += 1
                    continue
            
            logger.info(f"🏁 Обновление завершено!")
            return result
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
            return result

    async def update_profile_async(self, url, api, platform, semaphore):
        """Асинхронное обновление одного профиля"""
        async with semaphore:
            try:
                logger.info(f"📊 Обновление {platform}: {url}")

                # Запускаем синхронный вызов API в executor, чтобы не блокировать event loop
                loop = asyncio.get_event_loop()
                if platform == "tiktok":
                    stats = await loop.run_in_executor(None, api.get_tiktok_data, url)
                else:  # instagram
                    stats = await loop.run_in_executor(None, api.get_instagram_data, url)

                if stats and stats.get("type") == "profile" if platform == "tiktok" else stats.get("platform") == "instagram":
                    update_result = self.update_profile_stats(url, stats, platform=platform)
                    await asyncio.sleep(3)  # Асинхронная задержка

                    if update_result and update_result.get("updated"):
                        logger.info(f"✅ Успешно обновлен: {url}")
                        return {"success": True, "url": url}
                    else:
                        return {"success": False, "url": url, "error": "Update failed"}
                else:
                    return {"success": False, "url": url, "error": "Invalid data"}

            except Exception as e:
                logger.error(f"❌ Ошибка обновления {platform} {url}: {e}")
                return {"success": False, "url": url, "error": str(e)}

    async def update_all_profiles_async(self, tiktok_api, instagram_api):
        """Асинхронное обновление ТОЛЬКО NEW профилей через API обеих платформ"""
        try:
            result = {
                "tiktok": {"updated": 0, "skipped": 0, "errors": 0},
                "instagram": {"updated": 0, "skipped": 0, "errors": 0}
            }

            # Ограничиваем до 5 одновременных запросов к API
            semaphore = asyncio.Semaphore(5)
            tasks = []

            # TikTok профили
            if tiktok_api:
                tiktok_profiles = self.get_all_profiles(platform="tiktok")
                logger.info(f"🔄 Начинаем обновление {len(tiktok_profiles)} TikTok профилей...")

                for profile in tiktok_profiles:
                    url = profile["url"]
                    status = profile.get("status", "NEW")

                    if not url or "tiktok.com" not in url.lower():
                        result["tiktok"]["skipped"] += 1
                        continue

                    if status == "OLD":
                        logger.info(f"⭐ Пропускаем OLD: {url}")
                        result["tiktok"]["skipped"] += 1
                        continue

                    task = asyncio.create_task(
                        self.update_profile_async(url, tiktok_api, "tiktok", semaphore)
                    )
                    tasks.append(("tiktok", task))

            # Instagram профили
            if instagram_api:
                instagram_profiles = self.get_all_profiles(platform="instagram")
                logger.info(f"🔄 Начинаем обновление {len(instagram_profiles)} Instagram профилей...")

                for profile in instagram_profiles:
                    url = profile["url"]
                    status = profile.get("status", "NEW")

                    if not url or "instagram.com" not in url.lower():
                        result["instagram"]["skipped"] += 1
                        continue

                    if status == "OLD":
                        logger.info(f"⭐ Пропускаем OLD: {url}")
                        result["instagram"]["skipped"] += 1
                        continue

                    task = asyncio.create_task(
                        self.update_profile_async(url, instagram_api, "instagram", semaphore)
                    )
                    tasks.append(("instagram", task))

            # Ждем завершения всех задач
            for platform, task in tasks:
                try:
                    task_result = await task
                    if task_result["success"]:
                        result[platform]["updated"] += 1
                    else:
                        result[platform]["errors"] += 1
                except Exception as e:
                    logger.error(f"Ошибка задачи {platform}: {e}")
                    result[platform]["errors"] += 1

            logger.info(f"🏁 Асинхронное обновление завершено!")
            return result

        except Exception as e:
            logger.error(f"❌ Критическая ошибка асинхронного обновления: {e}")
            return result

    def get_summary_stats(self, project_name=None):
        """Получает общую статистику по всем платформам

        :param project_name: Название проекта для фильтрации (если None - общая статистика)
        """
        try:
            all_profiles = self.get_all_profiles()

            # Фильтруем по проекту если указан
            if project_name:
                all_profiles = [p for p in all_profiles if p.get("project_name", "") == project_name]

            tiktok_stats = {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "videos": 0, "views": 0}
            instagram_stats = {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "videos": 0, "views": 0}
            facebook_stats = {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "videos": 0, "views": 0}
            youtube_stats = {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "videos": 0, "views": 0}

            for profile in all_profiles:
                platform = profile.get("platform", "tiktok")
                status = profile.get("status", "NEW")
                
                try:
                    followers = int(profile.get("followers", 0) or 0)
                    videos = int(profile.get("videos", 0) or 0)
                    views = int(profile.get("total_views", 0) or 0)
                    
                    if platform == "instagram":
                        instagram_stats["total"] += 1
                        instagram_stats["followers"] += followers
                        instagram_stats["videos"] += videos
                        instagram_stats["views"] += views
                        if status == "OLD":
                            instagram_stats["old"] += 1
                        elif status == "BAN":
                            instagram_stats["ban"] += 1
                        else:
                            instagram_stats["new"] += 1
                    elif platform == "facebook":
                        facebook_stats["total"] += 1
                        facebook_stats["followers"] += followers
                        facebook_stats["videos"] += videos
                        facebook_stats["views"] += views
                        if status == "OLD":
                            facebook_stats["old"] += 1
                        elif status == "BAN":
                            facebook_stats["ban"] += 1
                        else:
                            facebook_stats["new"] += 1
                    elif platform == "youtube":
                        youtube_stats["total"] += 1
                        youtube_stats["followers"] += followers
                        youtube_stats["videos"] += videos
                        youtube_stats["views"] += views
                        if status == "OLD":
                            youtube_stats["old"] += 1
                        elif status == "BAN":
                            youtube_stats["ban"] += 1
                        else:
                            youtube_stats["new"] += 1
                    else:  # tiktok
                        tiktok_stats["total"] += 1
                        tiktok_stats["followers"] += followers
                        tiktok_stats["videos"] += videos
                        tiktok_stats["views"] += views
                        if status == "OLD":
                            tiktok_stats["old"] += 1
                        elif status == "BAN":
                            tiktok_stats["ban"] += 1
                        else:
                            tiktok_stats["new"] += 1
                except:
                    continue
            
            return {
                "tiktok": tiktok_stats, 
                "instagram": instagram_stats,
                "facebook": facebook_stats,
                "youtube": youtube_stats
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return None
    
    def add_link(self, user_id, url, link_type, username=None, video_id=None, sec_uid=None):
        return {"id": "temp", "url": url, "type": link_type}
    
    def save_analytics(self, link_id, stats):
        url = stats.get("url")
        platform = stats.get("platform", "tiktok")
        if url:
            return self.update_profile_stats(url, stats, platform)
        return None
    
    def add_user(self, user_id, username, first_name, last_name=None):
        return {"id": str(user_id)}
    
    def get_user_links(self, user_id):
        return []
    
    def get_all_active_links(self):
        return []
    
    def update_link_status(self, link_id, is_active):
        pass
    
    def get_analytics_for_link(self, link_id, limit=10):
        return []
    
    def get_analytics_summary(self, user_id=None):
        return []
    
    def get_growth_stats(self, link_id, days=7):
        return {"not_enough_data": True, "message": "Недостаточно данных"}
    
    def track_api_usage(self, endpoint):
        pass
    
    def get_api_usage_today(self):
        return None
