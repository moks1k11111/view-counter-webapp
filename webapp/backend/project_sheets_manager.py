import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
from typing import Optional, Dict, List
import json
import os
import base64
import time
from functools import wraps

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


def retry_on_quota_error(max_retries=3, delay=5):
    """
    Decorator to retry Google Sheets API calls on quota errors (429).

    :param max_retries: Maximum number of retry attempts (default 3)
    :param delay: Delay in seconds between retries (default 5)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except gspread.exceptions.APIError as e:
                    # Check if it's a quota/rate limit error (429)
                    if hasattr(e, 'response') and e.response.status_code == 429:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"⚠️ Google Sheets API Rate Limit hit (429). "
                                f"Retry {attempt + 1}/{max_retries - 1} in {delay}s... "
                                f"Function: {func.__name__}"
                            )
                            time.sleep(delay)
                            continue
                        else:
                            logger.error(
                                f"❌ Google Sheets API Rate Limit exceeded after {max_retries} attempts. "
                                f"Function: {func.__name__}"
                            )
                            raise
                    else:
                        # Not a quota error, raise immediately
                        raise
                except Exception as e:
                    # For non-API errors, raise immediately
                    raise
            # Should not reach here, but just in case
            return func(*args, **kwargs)
        return wrapper
    return decorator


class ProjectSheetsManager:
    """Класс для работы с Google Sheets для проектов"""

    def __init__(self, credentials_file: str, spreadsheet_name: str = "MainBD", credentials_json: str = ""):
        """
        Инициализация подключения к Google Sheets

        :param credentials_file: Путь к JSON файлу с credentials (для локальной разработки)
        :param spreadsheet_name: Название основной таблицы
        :param credentials_json: JSON-строка с credentials (для Render/Railway)
        """
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]

        try:
            # Пробуем использовать JSON-строку (Render/Railway)
            if credentials_json:
                # Декодируем base64, если это base64-закодированная строка
                try:
                    decoded_json = base64.b64decode(credentials_json).decode('utf-8')
                    # После base64 decode получаем готовый JSON - парсим напрямую
                except Exception:
                    # Если не base64, используем как есть
                    decoded_json = credentials_json
                    # Заменяем экранированные переносы строк на обычные
                    decoded_json = decoded_json.replace('\\n', '\n')

                creds_dict = json.loads(decoded_json)
                credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
            # Иначе используем файл (локальная разработка)
            elif os.path.exists(credentials_file):
                credentials = ServiceAccountCredentials.from_json_keyfile_name(
                    credentials_file, self.scope
                )
            else:
                raise FileNotFoundError(f"No credentials found: neither JSON string nor file {credentials_file}")

            self.client = gspread.authorize(credentials)

            try:
                self.spreadsheet = self.client.open(spreadsheet_name)
                logger.info(f"✅ Подключено к таблице {spreadsheet_name}")
            except gspread.exceptions.SpreadsheetNotFound:
                self.spreadsheet = self.client.create(spreadsheet_name)
                logger.info(f"✅ Создана новая таблица {spreadsheet_name}")

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к Google Sheets: {e}")
            raise

    @retry_on_quota_error(max_retries=3, delay=5)
    def create_project_sheet(self, project_name: str) -> bool:
        """
        Создание листа для проекта (с автоматическими повторами при quota errors)

        :param project_name: Название проекта
        :return: True если успешно
        """
        try:
            # Проверяем, существует ли уже лист
            sheet_names = [sheet.title for sheet in self.spreadsheet.worksheets()]

            if project_name in sheet_names:
                logger.info(f"⚠️ Лист {project_name} уже существует")
                return True

            # Создаем новый лист
            worksheet = self.spreadsheet.add_worksheet(
                title=project_name,
                rows=1000,
                cols=13
            )

            # Добавляем заголовки
            headers = [
                "@Username",      # Telegram username
                "Link",
                "Platform",
                "Username",       # Social media username (NEW)
                "Followers",
                "Likes",
                "Following",
                "Videos",
                "Views",
                "Last Update",
                "Status",
                "Тематика"
            ]
            worksheet.append_row(headers)

            # Форматируем заголовки
            worksheet.format('A1:L1', {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
                "backgroundColor": {
                    "red": 0.2,
                    "green": 0.2,
                    "blue": 0.2
                },
                "textFormat": {
                    "foregroundColor": {
                        "red": 1.0,
                        "green": 1.0,
                        "blue": 1.0
                    },
                    "bold": True
                }
            })

            logger.info(f"✅ Создан лист для проекта: {project_name}")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка создания листа проекта: {e}")
            return False

    @retry_on_quota_error(max_retries=3, delay=5)
    def add_account_to_sheet(self, project_name: str, account_data: Dict) -> bool:
        """
        Добавление аккаунта в лист проекта (с автоматическими повторами при quota errors)

        :param project_name: Название проекта
        :param account_data: Данные аккаунта
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)

            # DEBUG: Log what we received from api.py
            logger.info("=" * 80)
            logger.info(f"🔍 SHEETS MANAGER: Received account_data = {account_data}")
            logger.info(f"🔍 SHEETS MANAGER: account_data['telegram_user'] = {repr(account_data.get('telegram_user'))}")
            logger.info("=" * 80)

            # Get telegram_user with fallback
            telegram_user = account_data.get('telegram_user') or 'Unknown'
            logger.info(f"🔍 SHEETS MANAGER: After fallback, telegram_user = '{telegram_user}'")

            # Подготавливаем данные
            row = [
                telegram_user,                                # @Username - Telegram User
                account_data.get('profile_link', ''),         # Link
                account_data.get('platform', 'tiktok'),       # Platform
                account_data.get('username', 'Unknown'),      # Username - Social media username (NEW)
                account_data.get('followers', 0),             # Followers
                account_data.get('likes', 0),                 # Likes
                account_data.get('following', 0),             # Following
                account_data.get('videos', 0),                # Videos
                account_data.get('views', 0),                 # Views
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # Last Update
                account_data.get('status', 'NEW'),            # Status
                account_data.get('topic', '')                 # Тематика
            ]

            worksheet.append_row(row)
            logger.info(f"✅ Аккаунт {account_data.get('username')} добавлен в {project_name} (Telegram User: {telegram_user})")
            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка добавления аккаунта: {e}")
            return False

    @retry_on_quota_error(max_retries=3, delay=5)
    def update_account_stats(self, project_name: str, username: str,
                            stats: Dict) -> bool:
        """
        Обновление статистики аккаунта в листе (с автоматическими повторами при quota errors)

        :param project_name: Название проекта
        :param username: Username аккаунта
        :param stats: Статистика (followers, likes, comments, videos, views)
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)

            # Находим строку с аккаунтом
            cell = worksheet.find(username)
            if not cell:
                logger.warning(f"⚠️ Аккаунт {username} не найден в {project_name}")
                return False

            row_number = cell.row

            # Обновляем статистику
            # Структура: @Username | Link | Platform | Username | Followers | Likes | Following | Videos | Views | Last Update | Status | Тематика
            #            1          | 2    | 3        | 4        | 5         | 6     | 7         | 8      | 9     | 10          | 11     | 12
            updates = []
            if 'followers' in stats:
                updates.append(gspread.Cell(row_number, 5, stats['followers']))
            if 'likes' in stats:
                updates.append(gspread.Cell(row_number, 6, stats['likes']))
            if 'following' in stats:
                updates.append(gspread.Cell(row_number, 7, stats.get('following', 0)))
            if 'videos' in stats:
                updates.append(gspread.Cell(row_number, 8, stats['videos']))
            if 'views' in stats:
                updates.append(gspread.Cell(row_number, 9, stats['views']))

            # Обновляем время
            updates.append(gspread.Cell(
                row_number, 10,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))

            worksheet.update_cells(updates)
            logger.info(f"✅ Статистика {username} обновлена в {project_name}")
            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка обновления статистики: {e}")
            return False

    def get_project_accounts(self, project_name: str) -> List[Dict]:
        """
        Получение всех аккаунтов из листа проекта

        :param project_name: Название проекта
        :return: Список аккаунтов
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)
            records = worksheet.get_all_records()
            return records

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return []
        except Exception as e:
            logger.error(f"❌ Ошибка получения аккаунтов: {e}")
            return []

    def read_project_sheet(self, project_name: str) -> List[Dict]:
        """
        Чтение данных из листа проекта (алиас для get_project_accounts)

        :param project_name: Название проекта
        :return: Список записей из Google Sheet
        """
        return self.get_project_accounts(project_name)

    @retry_on_quota_error(max_retries=3, delay=5)
    def delete_project_sheet(self, project_name: str) -> bool:
        """
        Удаление листа проекта (с автоматическими повторами при quota errors)

        :param project_name: Название проекта
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)
            self.spreadsheet.del_worksheet(worksheet)
            logger.info(f"✅ Лист {project_name} удален")
            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.warning(f"⚠️ Лист {project_name} не найден")
            return False
        except gspread.exceptions.APIError as e:
            # APIError will be caught by retry decorator if it's a 429
            logger.error(f"❌ API ошибка удаления листа: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка удаления листа: {e}")
            return False

    @retry_on_quota_error(max_retries=3, delay=5)
    def remove_account_from_sheet(self, project_name: str, profile_link: str) -> bool:
        """
        Удаление аккаунта из листа проекта по ссылке (с автоматическими повторами при quota errors)

        :param project_name: Название проекта
        :param profile_link: Полная ссылка на профиль (Link)
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)

            # Получаем все данные
            all_values = worksheet.get_all_values()
            if len(all_values) < 2:  # Нет данных кроме заголовков
                logger.warning(f"⚠️ Нет данных в {project_name}")
                return False

            # Находим индекс колонки "Link"
            headers = all_values[0]
            try:
                link_col_index = headers.index('Link')
            except ValueError:
                logger.error(f"❌ Колонка 'Link' не найдена в {project_name}")
                return False

            # Ищем строку с этим profile_link
            row_to_delete = None
            for idx, row in enumerate(all_values[1:], start=2):  # Пропускаем заголовок, начинаем с 2
                if link_col_index < len(row):
                    if row[link_col_index].strip() == profile_link.strip():
                        row_to_delete = idx
                        break

            if not row_to_delete:
                logger.warning(f"⚠️ Аккаунт с ссылкой {profile_link} не найден в {project_name}")
                return False

            # Удаляем строку
            worksheet.delete_rows(row_to_delete)
            logger.info(f"✅ Аккаунт {profile_link} удален из {project_name} (строка {row_to_delete})")
            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка удаления аккаунта: {e}")
            import traceback
            traceback.print_exc()
            return False

    @retry_on_quota_error(max_retries=3, delay=5)
    def migrate_username_column(self, project_name: str) -> bool:
        """
        Добавляет колонку Username в существующий лист и заполняет её парсингом из Link

        :param project_name: Название проекта
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)

            # Получаем заголовки
            headers = worksheet.row_values(1)
            logger.info(f"🔍 Current headers: {headers}")

            # Проверяем, есть ли уже колонка Username
            if 'Username' in headers:
                logger.info(f"⚠️ Колонка Username уже существует в {project_name}")
                return True

            # Находим куда вставить колонку Username
            # Если есть Platform - вставляем после неё, иначе после Link
            if 'Platform' in headers:
                platform_index = headers.index('Platform') + 1
                username_col = platform_index + 1
            elif 'Link' in headers:
                link_index = headers.index('Link') + 1
                username_col = link_index + 1
            else:
                logger.error(f"❌ Не найдена ни колонка Platform, ни Link в {project_name}")
                return False

            # Вставляем новую колонку после Platform
            worksheet.insert_cols([[]], col=username_col)
            logger.info(f"✅ Вставлена новая колонка в позицию {username_col}")

            # Устанавливаем заголовок
            worksheet.update_cell(1, username_col, 'Username')
            logger.info(f"✅ Установлен заголовок Username в колонку {username_col}")

            # Получаем все данные
            all_data = worksheet.get_all_values()

            # Парсим username из Link для каждой строки
            updates = []
            for row_index, row in enumerate(all_data[1:], start=2):  # Пропускаем заголовок
                if len(row) < 2:  # Нет Link
                    continue

                link = row[1] if len(row) > 1 else ''  # Link в колонке B (index 1)
                if not link:
                    continue

                # Парсим username из URL
                username = self._parse_username_from_url(link)

                if username:
                    updates.append(gspread.Cell(row_index, username_col, username))

            # Обновляем все username'ы батчем
            if updates:
                worksheet.update_cells(updates)
                logger.info(f"✅ Обновлено {len(updates)} username'ов в {project_name}")

            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка миграции колонки Username: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _parse_username_from_url(self, url: str) -> str:
        """
        Парсит username из URL соц сети

        :param url: URL профиля
        :return: Username или 'Unknown'
        """
        url_lower = url.lower().strip()
        username = None

        try:
            if 'tiktok.com' in url_lower:
                if '/@' in url:
                    username = url.split('/@')[1].split('?')[0].split('/')[0]
            elif 'instagram.com' in url_lower:
                clean_url = url.rstrip('/').split('?')[0]
                parts = clean_url.split('/')
                for i, part in enumerate(parts):
                    if 'instagram.com' in part and i + 1 < len(parts):
                        username = parts[i + 1].lstrip('@')
                        break
            elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
                # Проверяем формат profile.php?id=...
                if 'profile.php?id=' in url_lower:
                    # Извлекаем ID из параметра
                    try:
                        import urllib.parse
                        parsed = urllib.parse.urlparse(url)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'id' in params:
                            username = params['id'][0]
                    except:
                        pass
                else:
                    clean_url = url.rstrip('/').split('?')[0]
                    # Убираем пустые части после split
                    parts = [p for p in clean_url.split('/') if p]

                    if 'share' in parts:
                        idx = parts.index('share')
                        if idx + 1 < len(parts):
                            username = parts[idx + 1]
                    elif len(parts) > 0:
                        # Берем последнюю непустую часть, кроме доменов
                        for part in reversed(parts):
                            if part and part not in ['facebook.com', 'www.facebook.com', 'fb.com', 'https:', 'http:']:
                                username = part
                                break
            elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
                if '/@' in url:
                    username = url.split('/@')[1].split('?')[0].split('/')[0]
                elif '/c/' in url_lower:
                    username = url.split('/c/')[1].split('?')[0].split('/')[0]
                elif '/channel/' in url_lower:
                    username = url.split('/channel/')[1].split('?')[0].split('/')[0]
            elif 'threads.net' in url_lower:
                if '/@' in url:
                    username = url.split('/@')[1].split('?')[0].split('/')[0]
                else:
                    clean_url = url.rstrip('/').split('?')[0]
                    parts = clean_url.split('/')
                    for i, part in enumerate(parts):
                        if 'threads.net' in part and i + 1 < len(parts):
                            username = parts[i + 1].lstrip('@')
                            break
        except Exception as e:
            logger.warning(f"⚠️ Ошибка парсинга username из URL {url}: {e}")

        return username or 'Unknown'
