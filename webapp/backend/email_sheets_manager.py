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


class EmailSheetsManager:
    """Класс для работы с Google Sheets для Email Farm"""

    def __init__(self, credentials_file: str, spreadsheet_name: str = "PostBD", credentials_json: str = ""):
        """
        Инициализация подключения к Google Sheets для Email Farm

        :param credentials_file: Путь к JSON файлу с credentials (для локальной разработки)
        :param spreadsheet_name: Название таблицы для Email Farm (по умолчанию PostBD)
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
                logger.info(f"✅ Email Farm: Подключено к таблице {spreadsheet_name}")
            except gspread.exceptions.SpreadsheetNotFound:
                self.spreadsheet = self.client.create(spreadsheet_name)
                logger.info(f"✅ Email Farm: Создана новая таблица {spreadsheet_name}")

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка подключения к Google Sheets: {e}")
            raise

    @retry_on_quota_error(max_retries=3, delay=5)
    def get_or_create_sheet(self, sheet_name: str):
        """
        Получить лист или создать новый, если не существует

        :param sheet_name: Название листа
        :return: Объект листа
        """
        try:
            sheet = self.spreadsheet.worksheet(sheet_name)
            logger.info(f"📄 Email Farm: Найден лист {sheet_name}")
            return sheet
        except gspread.exceptions.WorksheetNotFound:
            sheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            logger.info(f"📄 Email Farm: Создан новый лист {sheet_name}")

            # Создаем заголовки для Email Farm
            headers = [
                "Email", "Status", "User ID", "Username",
                "Allocated At", "Last Checked", "Ban Reason",
                "Total Checks", "Has Proxy", "Notes"
            ]
            sheet.update('A1:J1', [headers])

            # Форматируем заголовки
            sheet.format('A1:J1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2}
            })

            return sheet

    @retry_on_quota_error(max_retries=3, delay=5)
    def log_email_allocation(
        self,
        sheet_name: str,
        email: str,
        user_id: int,
        username: str,
        has_proxy: bool = False
    ):
        """
        Записать выделение почты пользователю

        :param sheet_name: Название листа (обычно название листа из основной таблицы)
        :param email: Email адрес
        :param user_id: Telegram User ID
        :param username: Telegram Username
        :param has_proxy: Есть ли прокси у этой почты
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Проверяем, есть ли уже запись для этого email
            all_values = sheet.get_all_values()
            email_row = None

            for idx, row in enumerate(all_values[1:], start=2):  # Пропускаем заголовок
                if row[0] == email:
                    email_row = idx
                    break

            row_data = [
                email,
                "active",
                str(user_id),
                username,
                now,
                "",
                "",
                "0",
                "Да" if has_proxy else "Нет",
                ""
            ]

            if email_row:
                # Обновляем существующую запись
                sheet.update(f'A{email_row}:J{email_row}', [row_data])
                logger.info(f"✅ Email Farm: Обновлена запись для {email} на листе {sheet_name}")
            else:
                # Добавляем новую запись
                sheet.append_row(row_data)
                logger.info(f"✅ Email Farm: Добавлена новая запись для {email} на листе {sheet_name}")

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка записи allocation для {email}: {e}")

    @retry_on_quota_error(max_retries=3, delay=5)
    def log_new_email(
        self,
        sheet_name: str,
        email: str,
        has_proxy: bool = False
    ):
        """
        Записать новую почту в статусе free (при bulk upload)

        :param sheet_name: Название листа
        :param email: Email адрес
        :param has_proxy: Есть ли прокси у этой почты
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Проверяем, есть ли уже запись для этого email
            all_values = sheet.get_all_values()
            email_exists = any(row[0] == email for row in all_values[1:])

            if email_exists:
                logger.info(f"⚠️ Email Farm: Почта {email} уже существует на листе {sheet_name}")
                return

            row_data = [
                email,
                "free",
                "",
                "[ADMIN_UPLOAD]",
                now,
                "",
                "",
                "0",
                "Да" if has_proxy else "Нет",
                f"📤 Загружена админом ({now})"
            ]

            # Добавляем новую запись
            sheet.append_row(row_data)
            logger.info(f"✅ Email Farm: Добавлена новая free почта {email} на листе {sheet_name}")

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка записи new email для {email}: {e}")

    @retry_on_quota_error(max_retries=3, delay=5)
    def log_email_check(
        self,
        sheet_name: str,
        email: str,
        found_code: bool = False,
        is_safe: bool = True,
        subject: str = ""
    ):
        """
        Записать проверку почты на код

        :param sheet_name: Название листа
        :param email: Email адрес
        :param found_code: Найден ли код верификации
        :param is_safe: Безопасно ли письмо
        :param subject: Тема письма
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Ищем строку с этим email
            all_values = sheet.get_all_values()
            email_row = None

            for idx, row in enumerate(all_values[1:], start=2):
                if row[0] == email:
                    email_row = idx
                    break

            if email_row:
                # Обновляем Last Checked и Total Checks
                current_checks = int(row[7]) if row[7].isdigit() else 0
                new_checks = current_checks + 1

                notes = ""
                if found_code:
                    notes = f"✅ Код найден: {subject}"
                elif not is_safe:
                    notes = f"⚠️ ПОДОЗРИТЕЛЬНО: {subject}"
                else:
                    notes = f"📭 Нет писем или нет кода: {subject}"

                sheet.update(f'F{email_row}', now)  # Last Checked
                sheet.update(f'H{email_row}', str(new_checks))  # Total Checks
                sheet.update(f'J{email_row}', notes)  # Notes

                logger.info(f"✅ Email Farm: Обновлена проверка для {email} на листе {sheet_name}")
            else:
                logger.warning(f"⚠️ Email Farm: Не найдена запись для {email} на листе {sheet_name}")

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка записи check для {email}: {e}")

    @retry_on_quota_error(max_retries=3, delay=5)
    def log_email_ban(
        self,
        sheet_name: str,
        email: str,
        ban_reason: str = "User marked as banned"
    ):
        """
        Записать бан почты

        :param sheet_name: Название листа
        :param email: Email адрес
        :param ban_reason: Причина бана
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Ищем строку с этим email
            all_values = sheet.get_all_values()
            email_row = None

            for idx, row in enumerate(all_values[1:], start=2):
                if row[0] == email:
                    email_row = idx
                    break

            if email_row:
                sheet.update(f'B{email_row}', "banned")  # Status
                sheet.update(f'G{email_row}', f"{ban_reason} ({now})")  # Ban Reason
                sheet.update(f'J{email_row}', f"🚫 Забанена: {ban_reason}")  # Notes

                logger.info(f"✅ Email Farm: Помечена как banned {email} на листе {sheet_name}")
            else:
                logger.warning(f"⚠️ Email Farm: Не найдена запись для {email} на листе {sheet_name}")

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка записи ban для {email}: {e}")

    @retry_on_quota_error(max_retries=3, delay=5)
    def log_email_release(
        self,
        sheet_name: str,
        email: str
    ):
        """
        Записать освобождение почты (возврат в free)

        :param sheet_name: Название листа
        :param email: Email адрес
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Ищем строку с этим email
            all_values = sheet.get_all_values()
            email_row = None

            for idx, row in enumerate(all_values[1:], start=2):
                if row[0] == email:
                    email_row = idx
                    break

            if email_row:
                sheet.update(f'B{email_row}', "free")  # Status
                sheet.update(f'C{email_row}', "")  # User ID
                sheet.update(f'D{email_row}', "")  # Username
                sheet.update(f'J{email_row}', f"🔄 Освобождена ({now})")  # Notes

                logger.info(f"✅ Email Farm: Освобождена почта {email} на листе {sheet_name}")
            else:
                logger.warning(f"⚠️ Email Farm: Не найдена запись для {email} на листе {sheet_name}")

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка освобождения {email}: {e}")

    @retry_on_quota_error(max_retries=3, delay=5)
    def get_email_status(self, sheet_name: str, email: str) -> Optional[Dict]:
        """
        Получить статус почты из таблицы

        :param sheet_name: Название листа
        :param email: Email адрес
        :return: Словарь с данными или None
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            all_values = sheet.get_all_values()

            for row in all_values[1:]:  # Пропускаем заголовок
                if row[0] == email:
                    return {
                        "email": row[0],
                        "status": row[1],
                        "user_id": row[2],
                        "username": row[3],
                        "allocated_at": row[4],
                        "last_checked": row[5],
                        "ban_reason": row[6],
                        "total_checks": row[7],
                        "has_proxy": row[8],
                        "notes": row[9]
                    }

            return None

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка получения статуса {email}: {e}")
            return None

    @retry_on_quota_error(max_retries=3, delay=5)
    def get_all_emails_for_sheet(self, sheet_name: str) -> List[Dict]:
        """
        Получить все email записи для определенного листа

        :param sheet_name: Название листа
        :return: Список словарей с данными
        """
        try:
            sheet = self.get_or_create_sheet(sheet_name)

            all_values = sheet.get_all_values()
            emails = []

            for row in all_values[1:]:  # Пропускаем заголовок
                if row[0]:  # Если есть email
                    emails.append({
                        "email": row[0],
                        "status": row[1],
                        "user_id": row[2],
                        "username": row[3],
                        "allocated_at": row[4],
                        "last_checked": row[5],
                        "ban_reason": row[6],
                        "total_checks": row[7],
                        "has_proxy": row[8],
                        "notes": row[9]
                    })

            return emails

        except Exception as e:
            logger.error(f"❌ Email Farm: Ошибка получения всех emails для листа {sheet_name}: {e}")
            return []
