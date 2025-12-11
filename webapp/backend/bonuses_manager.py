"""
Bonuses Manager
Управление бонусами пользователей через Google Sheets (MainBD -> Bonuses)
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import logging
import json
import os
import base64
import uuid

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


class BonusesManager:
    """Менеджер для работы с бонусами в Google Sheets"""

    def __init__(self, credentials_file, spreadsheet_name, credentials_json=""):
        """
        Инициализация подключения к Google Sheets (MainBD)

        Args:
            credentials_file: путь к файлу credentials (для локальной разработки)
            spreadsheet_name: название Google Sheets (MainBD)
            credentials_json: JSON-строка с credentials (для Render)
        """
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]

        try:
            # Пробуем использовать JSON-строку (Render)
            if credentials_json:
                try:
                    decoded_json = base64.b64decode(credentials_json).decode('utf-8')
                except Exception:
                    decoded_json = credentials_json
                    decoded_json = decoded_json.replace('\\n', '\n')

                creds_dict = json.loads(decoded_json)
                credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
            # Иначе используем файл (локальная разработка)
            elif os.path.exists(credentials_file):
                credentials = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, self.scope)
            else:
                raise FileNotFoundError(f"No credentials found: neither JSON string nor file {credentials_file}")

            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open(spreadsheet_name)
            logger.info(f"✅ Bonuses Manager: Подключено к таблице {spreadsheet_name}")

            # Инициализируем лист Bonuses
            self._init_bonuses_sheet()

        except Exception as e:
            logger.error(f"❌ Bonuses Manager: Ошибка подключения к Google Sheets: {e}")
            raise

    def _init_bonuses_sheet(self):
        """Инициализация листа Bonuses"""
        sheet_names = [sheet.title for sheet in self.spreadsheet.worksheets()]

        if "Bonuses" not in sheet_names:
            # Создаем новый лист
            self.bonuses_sheet = self.spreadsheet.add_worksheet(title="Bonuses", rows=1000, cols=6)
            logger.info("✅ Создан новый лист Bonuses")
        else:
            self.bonuses_sheet = self.spreadsheet.worksheet("Bonuses")
            logger.info("✅ Найден существующий лист Bonuses")

        # Проверяем наличие заголовков
        if len(self.bonuses_sheet.get_all_values()) == 0:
            headers = [
                "User ID",
                "Username",
                "Date",
                "Amount ($)",
                "Assigned By",
                "Paid"
            ]
            self.bonuses_sheet.append_row(headers)
            self.bonuses_sheet.format('A1:F1', {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
                "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.8}
            })
            logger.info("✅ Добавлены заголовки в лист Bonuses")

    def add_bonus(self, user_id: str, username: str, amount: float, assigned_by_username: str, reason: str = ""):
        """
        Добавить бонус пользователю

        Args:
            user_id: Telegram ID пользователя
            username: Telegram username пользователя
            amount: Сумма бонуса в $
            assigned_by_username: Username админа который назначил бонус
            reason: Причина бонуса (опционально)

        Returns:
            bool: True если успешно
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Форматируем username с @
            formatted_username = f"@{username}" if not username.startswith('@') else username
            formatted_assigned_by = f"@{assigned_by_username}" if not assigned_by_username.startswith('@') else assigned_by_username

            row_data = [
                user_id,
                formatted_username,
                timestamp,
                amount,
                formatted_assigned_by,
                "Нет"  # По умолчанию не оплачено
            ]

            self.bonuses_sheet.append_row(row_data)
            logger.info(f"✅ Bonuses: Добавлен бонус ${amount} для {formatted_username} от {formatted_assigned_by}")
            return True

        except Exception as e:
            logger.error(f"❌ Bonuses: Ошибка добавления бонуса: {e}")
            return False

    def get_user_bonuses(self, user_id: str):
        """
        Получить все бонусы пользователя

        Args:
            user_id: Telegram ID пользователя

        Returns:
            dict: {
                "total": float,  # Общая сумма всех бонусов
                "total_paid": float,  # Сумма оплаченных бонусов
                "total_unpaid": float,  # Сумма неоплаченных бонусов
                "bonuses": [...]  # Список бонусов
            }
        """
        try:
            all_rows = self.bonuses_sheet.get_all_values()

            if len(all_rows) <= 1:
                return {
                    "total": 0,
                    "total_paid": 0,
                    "total_unpaid": 0,
                    "bonuses": []
                }

            # Пропускаем заголовок
            data_rows = all_rows[1:]

            bonuses = []
            total = 0
            total_paid = 0
            total_unpaid = 0

            for row in data_rows:
                if len(row) < 6:
                    continue

                row_user_id = row[0]

                if row_user_id == str(user_id):
                    try:
                        amount = float(row[3]) if row[3] else 0
                        is_paid = row[5].lower() in ['да', 'yes', 'оплачено', 'paid']

                        bonuses.append({
                            "username": row[1],
                            "date": row[2],
                            "amount": amount,
                            "assigned_by": row[4],
                            "paid": is_paid
                        })

                        total += amount
                        if is_paid:
                            total_paid += amount
                        else:
                            total_unpaid += amount

                    except (ValueError, IndexError) as e:
                        logger.warning(f"⚠️ Bonuses: Ошибка парсинга строки: {row}, ошибка: {e}")
                        continue

            logger.info(f"📊 Bonuses: User {user_id} имеет {len(bonuses)} бонусов на сумму ${total}")

            return {
                "total": round(total, 2),
                "total_paid": round(total_paid, 2),
                "total_unpaid": round(total_unpaid, 2),
                "bonuses": bonuses
            }

        except Exception as e:
            logger.error(f"❌ Bonuses: Ошибка получения бонусов: {e}")
            return {
                "total": 0,
                "total_paid": 0,
                "total_unpaid": 0,
                "bonuses": []
            }

    def get_all_bonuses(self):
        """
        Получить все бонусы (для админа)

        Returns:
            list: Список всех бонусов
        """
        try:
            all_rows = self.bonuses_sheet.get_all_values()

            if len(all_rows) <= 1:
                return []

            # Пропускаем заголовок
            data_rows = all_rows[1:]

            bonuses = []

            for row in data_rows:
                if len(row) < 6:
                    continue

                try:
                    amount = float(row[3]) if row[3] else 0
                    is_paid = row[5].lower() in ['да', 'yes', 'оплачено', 'paid']

                    bonuses.append({
                        "user_id": row[0],
                        "username": row[1],
                        "date": row[2],
                        "amount": amount,
                        "assigned_by": row[4],
                        "paid": is_paid
                    })

                except (ValueError, IndexError) as e:
                    logger.warning(f"⚠️ Bonuses: Ошибка парсинга строки: {row}, ошибка: {e}")
                    continue

            logger.info(f"📊 Bonuses: Всего {len(bonuses)} бонусов в системе")
            return bonuses

        except Exception as e:
            logger.error(f"❌ Bonuses: Ошибка получения всех бонусов: {e}")
            return []


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    # Используйте ваши реальные credentials для теста
    # manager = BonusesManager("credentials.json", "MainBD")
    # manager.add_bonus("123456", "testuser", 50.0, "admin", "За отличную работу")
    # bonuses = manager.get_user_bonuses("123456")
    # print(bonuses)

    print("✅ Bonuses Manager module loaded successfully")
