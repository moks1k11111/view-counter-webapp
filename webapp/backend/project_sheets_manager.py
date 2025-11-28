import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
from typing import Optional, Dict, List
import json
import os
import base64

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


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

    def create_project_sheet(self, project_name: str) -> bool:
        """
        Создание листа для проекта

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
                cols=11
            )

            # Добавляем заголовки
            headers = [
                "@Username",
                "Link",
                "Followers",
                "Likes",
                "Comments",
                "Videos",
                "Views",
                "Last Update",
                "Status",
                "Тематика",
                "Platform"
            ]
            worksheet.append_row(headers)

            # Форматируем заголовки
            worksheet.format('A1:K1', {
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

    def add_account_to_sheet(self, project_name: str, account_data: Dict) -> bool:
        """
        Добавление аккаунта в лист проекта

        :param project_name: Название проекта
        :param account_data: Данные аккаунта
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)

            # Подготавливаем данные
            row = [
                account_data.get('username', ''),
                account_data.get('profile_link', ''),
                account_data.get('followers', 0),
                account_data.get('likes', 0),
                account_data.get('comments', 0),
                account_data.get('videos', 0),
                account_data.get('views', 0),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                account_data.get('status', 'NEW'),
                account_data.get('topic', ''),
                account_data.get('platform', 'tiktok').upper()
            ]

            worksheet.append_row(row)
            logger.info(f"✅ Аккаунт {account_data.get('username')} добавлен в {project_name}")
            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка добавления аккаунта: {e}")
            return False

    def update_account_stats(self, project_name: str, username: str,
                            stats: Dict) -> bool:
        """
        Обновление статистики аккаунта в листе

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
            updates = []
            if 'followers' in stats:
                updates.append(gspread.Cell(row_number, 3, stats['followers']))
            if 'likes' in stats:
                updates.append(gspread.Cell(row_number, 4, stats['likes']))
            if 'comments' in stats:
                updates.append(gspread.Cell(row_number, 5, stats['comments']))
            if 'videos' in stats:
                updates.append(gspread.Cell(row_number, 6, stats['videos']))
            if 'views' in stats:
                updates.append(gspread.Cell(row_number, 7, stats['views']))

            # Обновляем время
            updates.append(gspread.Cell(
                row_number, 8,
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

    def delete_project_sheet(self, project_name: str) -> bool:
        """
        Удаление листа проекта

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
        except Exception as e:
            logger.error(f"❌ Ошибка удаления листа: {e}")
            return False

    def remove_account_from_sheet(self, project_name: str, username: str) -> bool:
        """
        Удаление аккаунта из листа проекта

        :param project_name: Название проекта
        :param username: Username аккаунта
        :return: True если успешно
        """
        try:
            worksheet = self.spreadsheet.worksheet(project_name)

            # Находим строку с аккаунтом
            cell = worksheet.find(username)
            if not cell:
                logger.warning(f"⚠️ Аккаунт {username} не найден в {project_name}")
                return False

            # Удаляем строку
            worksheet.delete_rows(cell.row)
            logger.info(f"✅ Аккаунт {username} удален из {project_name}")
            return True

        except gspread.exceptions.WorksheetNotFound:
            logger.error(f"❌ Лист {project_name} не найден")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка удаления аккаунта: {e}")
            return False
