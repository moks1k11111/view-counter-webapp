import os
import json

# ============ TELEGRAM BOT ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8325383993:AAEwrvCl13DEGuxyiFkVR74Nff-F3P25Jkw")
ADMIN_IDS = json.loads(os.getenv("ADMIN_IDS", "[873564841]"))

# ============ TIKTOK API ============
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "0789149b93msh06026dfc8f10553p1e22d9jsn3a9694ecc1b0")
RAPIDAPI_HOST = "tiktok-api23.p.rapidapi.com"
RAPIDAPI_BASE_URL = "https://tiktok-api23.p.rapidapi.com"
RAPIDAPI_DAILY_LIMIT = 1000

# ============ INSTAGRAM API ============
INSTAGRAM_RAPIDAPI_KEY = os.getenv("INSTAGRAM_RAPIDAPI_KEY", "0789149b93msh06026dfc8f10553p1e22d9jsn3a9694ecc1b0")
INSTAGRAM_RAPIDAPI_HOST = "instagram-scraper-stable-api.p.rapidapi.com"
INSTAGRAM_BASE_URL = "https://instagram-scraper-stable-api.p.rapidapi.com"

# ============ GOOGLE SHEETS ============
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "service_account.json")
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
# Дефолтная таблица для тестирования (старая TikTok Analytics переименована)
DEFAULT_GOOGLE_SHEETS_NAME = os.getenv("GOOGLE_SHEETS_NAME", "SuperGra")

# ============ URL PATTERNS ============
TIKTOK_URL_PATTERN = r'(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com)/.+'
INSTAGRAM_URL_PATTERN = r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+'
FACEBOOK_URL_PATTERN = r'(https?://)?(www\.)?facebook\.com/.+'
YOUTUBE_URL_PATTERN = r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'
