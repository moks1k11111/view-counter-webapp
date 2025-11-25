"""
Google Sheets Logger - Синхронизация истории с Google Таблицами
Backup всех данных в облако
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from typing import Dict, List, Optional
import json


class GoogleSheetsLogger:
    """Логгер для сохранения данных в Google Sheets"""
    
    def __init__(self, credentials_file: str = "credentials.json", spreadsheet_name: str = "TikTok Analytics History"):
        """
        Инициализация Google Sheets Logger
        
        Args:
            credentials_file: Путь к файлу с credentials от Google
            spreadsheet_name: Название таблицы в Google Sheets
        """
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name
        self.client = None
        self.spreadsheet = None
        self.is_connected = False
        
        self._connect()
    
    def _connect(self):
        """Подключение к Google Sheets"""
        try:
            # Проверяем наличие файла credentials
            import os
            if not os.path.exists(self.credentials_file):
                print(f"⚠️  Файл {self.credentials_file} не найден")
                print("   Инструкция по настройке:")
                print("   1. Перейдите на https://console.cloud.google.com/")
                print("   2. Создайте проект и включите Google Sheets API")
                print("   3. Создайте Service Account и скачайте JSON ключ")
                print("   4. Переименуйте файл в credentials.json")
                print("   5. Положите его в папку web_dashboard/")
                self.is_connected = False
                return
            
            # Авторизация
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file,
                scope
            )
            
            self.client = gspread.authorize(creds)
            
            # Открываем или создаем таблицу
            try:
                self.spreadsheet = self.client.open(self.spreadsheet_name)
                print(f"✓ Подключено к таблице: {self.spreadsheet_name}")
            except gspread.SpreadsheetNotFound:
                self.spreadsheet = self.client.create(self.spreadsheet_name)
                print(f"✓ Создана новая таблица: {self.spreadsheet_name}")
            
            # Инициализируем листы
            self._init_sheets()
            
            self.is_connected = True
            
        except Exception as e:
            print(f"✗ Ошибка подключения к Google Sheets: {e}")
            self.is_connected = False
    
    def _init_sheets(self):
        """Инициализация листов в таблице"""
        try:
            # Лист 1: История профилей
            try:
                self.profiles_sheet = self.spreadsheet.worksheet("Profile History")
            except gspread.WorksheetNotFound:
                self.profiles_sheet = self.spreadsheet.add_worksheet(
                    title="Profile History",
                    rows=10000,
                    cols=12
                )
                # Заголовки
                headers = [
                    "Дата", "Время", "Платформа", "Профиль", "Username",
                    "Telegram User", "Подписчики", "Просмотры", "Видео", "Статус"
                ]
                self.profiles_sheet.append_row(headers)
                print("  ✓ Создан лист: Profile History")
            
            # Лист 2: Общая статистика по дням
            try:
                self.daily_sheet = self.spreadsheet.worksheet("Daily Summary")
            except gspread.WorksheetNotFound:
                self.daily_sheet = self.spreadsheet.add_worksheet(
                    title="Daily Summary",
                    rows=1000,
                    cols=20
                )
                # Заголовки
                headers = [
                    "Дата", "Пользователей", "Профилей", "Подписчиков", "Просмотров", "Видео",
                    "TikTok Профили", "TikTok Подписчики", "TikTok Просмотры",
                    "Instagram Профили", "Instagram Подписчики", "Instagram Просмотры",
                    "Facebook Профили", "Facebook Подписчики", "Facebook Просмотры",
                    "YouTube Профили", "YouTube Подписчики", "YouTube Просмотры"
                ]
                self.daily_sheet.append_row(headers)
                print("  ✓ Создан лист: Daily Summary")
            
            # Лист 3: Лог событий
            try:
                self.log_sheet = self.spreadsheet.worksheet("Event Log")
            except gspread.WorksheetNotFound:
                self.log_sheet = self.spreadsheet.add_worksheet(
                    title="Event Log",
                    rows=5000,
                    cols=5
                )
                headers = ["Timestamp", "Event", "Status", "Details"]
                self.log_sheet.append_row(headers)
                print("  ✓ Создан лист: Event Log")
            
        except Exception as e:
            print(f"✗ Ошибка инициализации листов: {e}")
    
    def log_profile_snapshot(
        self,
        platform: str,
        profile_url: str,
        stats: Dict,
        telegram_user: str = "",
        status: str = "NEW"
    ) -> bool:
        """
        Записать snapshot профиля в Google Sheets
        
        Args:
            platform: Платформа
            profile_url: URL профиля
            stats: Статистика
            telegram_user: Telegram пользователь
            status: Статус
        
        Returns:
            True если успешно
        """
        if not self.is_connected:
            return False
        
        try:
            now = datetime.now()
            date = now.strftime("%Y-%m-%d")
            time = now.strftime("%H:%M:%S")
            
            # Извлекаем username
            if '@' in profile_url:
                username = profile_url.split('@')[1].split('/')[0]
            else:
                username = profile_url.split('/')[-2] if profile_url.endswith('/') else profile_url.split('/')[-1]
            
            # Формируем строку
            row = [
                date,
                time,
                platform,
                profile_url,
                username,
                telegram_user,
                stats.get('followers', 0),
                stats.get('views', 0) + stats.get('total_views', 0),
                stats.get('videos', 0) + stats.get('reels', 0),
                status
            ]
            
            # Добавляем в таблицу
            self.profiles_sheet.append_row(row)
            
            # Логируем событие
            self._log_event("Profile Snapshot", "Success", f"{platform} - {username}")
            
            return True
            
        except Exception as e:
            print(f"✗ Ошибка записи в Google Sheets: {e}")
            self._log_event("Profile Snapshot", "Error", str(e))
            return False
    
    def log_daily_summary(self, summary_data: Dict) -> bool:
        """
        Записать общую статистику за день
        
        Args:
            summary_data: Словарь со статистикой
        
        Returns:
            True если успешно
        """
        if not self.is_connected:
            return False
        
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            
            # Проверяем, есть ли уже запись за сегодня
            cell = self.daily_sheet.find(date)
            
            row = [
                date,
                summary_data.get('total_users', 0),
                summary_data.get('total_profiles', 0),
                summary_data.get('total_followers', 0),
                summary_data.get('total_views', 0),
                summary_data.get('total_videos', 0),
                summary_data.get('tiktok_profiles', 0),
                summary_data.get('tiktok_followers', 0),
                summary_data.get('tiktok_views', 0),
                summary_data.get('instagram_profiles', 0),
                summary_data.get('instagram_followers', 0),
                summary_data.get('instagram_views', 0),
                summary_data.get('facebook_profiles', 0),
                summary_data.get('facebook_followers', 0),
                summary_data.get('facebook_views', 0),
                summary_data.get('youtube_profiles', 0),
                summary_data.get('youtube_followers', 0),
                summary_data.get('youtube_views', 0)
            ]
            
            if cell:
                # Обновляем существующую строку
                row_num = cell.row
                self.daily_sheet.delete_rows(row_num)
                self.daily_sheet.insert_row(row, row_num)
            else:
                # Добавляем новую строку
                self.daily_sheet.append_row(row)
            
            self._log_event("Daily Summary", "Success", f"Date: {date}")
            
            return True
            
        except Exception as e:
            print(f"✗ Ошибка записи daily summary: {e}")
            self._log_event("Daily Summary", "Error", str(e))
            return False
    
    def _log_event(self, event: str, status: str, details: str = ""):
        """Записать событие в лог"""
        try:
            if not self.is_connected:
                return
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp, event, status, details]
            self.log_sheet.append_row(row)
            
        except Exception as e:
            print(f"✗ Ошибка записи лога: {e}")
    
    def get_spreadsheet_url(self) -> Optional[str]:
        """Получить URL таблицы"""
        if self.spreadsheet:
            return self.spreadsheet.url
        return None
    
    def test_connection(self) -> bool:
        """Проверить подключение"""
        return self.is_connected


# Пример использования
if __name__ == "__main__":
    print("=" * 50)
    print("Тестирование Google Sheets Logger")
    print("=" * 50)
    
    # Создаем логгер
    logger = GoogleSheetsLogger()
    
    if logger.is_connected:
        print("\n✓ Подключение успешно!")
        print(f"  URL таблицы: {logger.get_spreadsheet_url()}")
        
        # Тест записи
        print("\nТест записи snapshot...")
        success = logger.log_profile_snapshot(
            platform="tiktok",
            profile_url="https://tiktok.com/@testuser",
            stats={'followers': 1000, 'views': 50000, 'videos': 20},
            telegram_user="test_user",
            status="NEW"
        )
        print(f"  {'✓' if success else '✗'} Snapshot записан")
        
        # Тест daily summary
        print("\nТест записи daily summary...")
        summary = {
            'total_users': 10,
            'total_profiles': 5,
            'total_followers': 5000,
            'total_views': 250000,
            'tiktok_profiles': 5,
            'tiktok_followers': 5000,
            'tiktok_views': 250000
        }
        success = logger.log_daily_summary(summary)
        print(f"  {'✓' if success else '✗'} Summary записан")
        
    else:
        print("\n✗ Не удалось подключиться")
        print("  Следуйте инструкции выше для настройки Google Sheets API")
    
    print("\n" + "=" * 50)
