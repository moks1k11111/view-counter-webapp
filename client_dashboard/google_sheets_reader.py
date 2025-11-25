import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Dict, List
import re
import os

class GoogleSheetsReader:
    SPREADSHEET_ID = "15dcxBXd9kMy-jsgUkOtOB6F8QV-8Q6-k4zNceAjUb-k"
    SHEET_NAMES = {'tiktok': 'TikTok', 'instagram': 'Instagram', 'facebook': 'Facebook', 'youtube': 'YouTube'}

    def __init__(self, credentials_file: str = "credentials.json"):
        self.credentials_file = credentials_file
        self.client = None
        self.spreadsheet = None
        self.is_connected = False
        self._connect()

    def _connect(self):
        try:
            if not os.path.exists(self.credentials_file):
                print(f"✗ Файл {self.credentials_file} не найден")
                return
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_file, scope)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(self.SPREADSHEET_ID)
            self.is_connected = True
            print(f"✓ Google Sheets: Подключено к таблице: {self.spreadsheet.title}")
        except Exception as e:
            print(f"✗ Google Sheets: Ошибка подключения: {e}")

    def _parse_number(self, value) -> int:
        if not value: return 0
        try:
            return int(float(str(value).replace(' ', '').replace(',', '')))
        except (ValueError, TypeError): return 0

    def _extract_username_from_url(self, url: str, platform: str) -> str:
        if not url: return "unknown"
        try:
            if platform == 'tiktok':
                match = re.search(r'@([^/?]+)', url)
                return match.group(1) if match else "unknown_tiktok"
            elif platform == 'instagram':
                match = re.search(r'instagram\.com/([^/?]+)', url)
                return match.group(1).strip('/') if match else "unknown_ig"
            return url
        except Exception: return url

    def read_sheet(self, platform: str) -> List[Dict]:
        if not self.is_connected: return []
        try:
            worksheet = self.spreadsheet.worksheet(self.SHEET_NAMES.get(platform.lower()))
            records = worksheet.get_all_values()
            if len(records) < 2: return []

            headers = [h.lower().strip() for h in records[0]]
            
            try:
                owner_col_variants = ['@username', 'username', 'telegram user']
                owner_idx = next(i for i, h in enumerate(headers) if h in owner_col_variants)
                
                link_col_variants = ['link', 'youtube url']
                link_idx = next(i for i, h in enumerate(headers) if h in link_col_variants)
            except StopIteration:
                print(f"✗ Не найдены обязательные колонки '@username' или 'link' в листе '{platform}'")
                return []

            def get_col_idx(keys):
                for key in keys:
                    if key in headers:
                        return headers.index(key)
                return None

            followers_idx = get_col_idx(['followers', 'подписчики'])
            likes_idx = get_col_idx(['likes', 'лайки'])
            videos_idx = get_col_idx(['videos', 'видео', 'reels'])
            views_idx = get_col_idx(['views', 'просмотры'])
            status_idx = get_col_idx(['status', 'статус'])
            topic_idx = get_col_idx(['topic', 'тематика'])

            profiles = []
            for row in records[1:]:
                if not row or not any(row): continue
                
                link = row[link_idx] if link_idx < len(row) else ''
                if not link or not link.startswith('http'): continue

                owner_username = row[owner_idx] if owner_idx < len(row) else ''
                account_username = self._extract_username_from_url(link, platform)
                
                profiles.append({
                    'platform': platform.lower(),
                    'username': account_username,
                    'telegram_user': owner_username,
                    'url': link,
                    'stats': {
                        'followers': self._parse_number(row[followers_idx] if followers_idx is not None and followers_idx < len(row) else 0),
                        'likes': self._parse_number(row[likes_idx] if likes_idx is not None and likes_idx < len(row) else 0),
                        'videos': self._parse_number(row[videos_idx] if videos_idx is not None and videos_idx < len(row) else 0),
                        'views': self._parse_number(row[views_idx] if views_idx is not None and views_idx < len(row) else 0),
                        'reels': 0, 'total_views': 0
                    },
                    'status': row[status_idx] if status_idx is not None and status_idx < len(row) else 'NEW',
                    'topic': row[topic_idx] if topic_idx is not None and topic_idx < len(row) else ''
                })
            print(f"  ✓ {platform.capitalize()}: Прочитано {len(profiles)} профилей")
            return profiles
        except gspread.exceptions.WorksheetNotFound:
            print(f"⚠️  Лист для платформы '{platform}' не найден.")
            return []
        except Exception as e:
            print(f"✗ Ошибка чтения листа {platform}: {e}")
            return []

    def read_all_platforms(self) -> List[Dict]:
        if not self.is_connected: return []
        all_profiles = []
        for platform in self.SHEET_NAMES.keys():
            all_profiles.extend(self.read_sheet(platform))
        print(f"✓ Всего прочитано: {len(all_profiles)} профилей")
        return all_profiles
