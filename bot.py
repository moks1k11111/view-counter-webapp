import logging
import re
import requests
import io
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
# ParseMode удалён в v20+

from config import (
    TELEGRAM_TOKEN, ADMIN_IDS,
    TIKTOK_URL_PATTERN, INSTAGRAM_URL_PATTERN, FACEBOOK_URL_PATTERN, YOUTUBE_URL_PATTERN,
    GOOGLE_SHEETS_CREDENTIALS, DEFAULT_GOOGLE_SHEETS_NAME,
    RAPIDAPI_KEY, RAPIDAPI_HOST, RAPIDAPI_BASE_URL,
    INSTAGRAM_RAPIDAPI_KEY, INSTAGRAM_RAPIDAPI_HOST, INSTAGRAM_BASE_URL
)
from tiktok_api import TikTokAPI
from tiktok_downloader import TikTokDownloader
from instagram_api import InstagramAPI
from facebook_api import FacebookAPI
from youtube_api import YouTubeAPI
from database_sqlite import SQLiteDatabase as Database
from database_sheets import SheetsDatabase
from utils import format_number, format_growth_compact, format_growth_line
from project_manager import ProjectManager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def escape_markdown(text):
    """
    Экранирует специальные символы Markdown для Telegram
    
    Args:
        text: текст для экранирования
    
    Returns:
        текст с экранированными специальными символами
    """
    if not text:
        return text
    
    # Символы которые нужно экранировать в Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def format_username(username):
    """
    Форматирует username с экранированием для Markdown
    
    Args:
        username: никнейм пользователя (без @)
    
    Returns:
        отформатированный @username с экранированными символами
    """
    if not username:
        return "unknown"
    
    # Экранируем только подчеркивание для сохранения читаемости
    escaped = username.replace('_', '\\_')
    return f"@{escaped}"

def parse_instagram_username(url):
    """Извлекает username из Instagram URL"""
    url_clean = url.replace("https://", "").replace("http://", "")
    url_clean = url_clean.replace("www.", "")
    url_clean = url_clean.replace("instagram.com/", "").replace("instagr.am/", "")
    username = url_clean.split("/")[0].strip()
    return username if username else "unknown"

def parse_tiktok_username(url):
    """Извлекает username из TikTok URL"""
    if "@" in url:
        username = url.split("@")[-1].split("/")[0]
        return username if username else "unknown"
    return "unknown"

def parse_facebook_username(url):
    """Извлекает username из Facebook URL"""
    url_clean = url.replace("https://", "").replace("http://", "")
    url_clean = url_clean.replace("www.", "").replace("facebook.com/", "")
    username = url_clean.split("/")[0].strip()
    return username if username else "unknown"

def parse_youtube_username(url):
    """Извлекает название канала из YouTube URL"""
    if "@" in url:
        username = url.split("@")[-1].split("/")[0]
        return f"@{username}" if username else "unknown"
    else:
        url_clean = url.replace("https://", "").replace("http://", "")
        url_clean = url_clean.replace("www.", "").replace("youtube.com/", "").replace("youtu.be/", "")
        username = url_clean.split("/")[0].strip()
        return username if username else "unknown"

# Инициализация API клиентов
tiktok_api = TikTokAPI()
tiktok_downloader = TikTokDownloader(RAPIDAPI_KEY)
instagram_api = InstagramAPI(INSTAGRAM_RAPIDAPI_KEY, INSTAGRAM_RAPIDAPI_HOST, INSTAGRAM_BASE_URL)
facebook_api = FacebookAPI()
youtube_api = YouTubeAPI()
db = Database()
project_manager = ProjectManager(db)

try:
    sheets_db = SheetsDatabase(GOOGLE_SHEETS_CREDENTIALS, DEFAULT_GOOGLE_SHEETS_NAME)
    logger.info("✅ Google Sheets подключен успешно")
except Exception as e:
    sheets_db = None
    logger.warning(f"⚠️ Google Sheets не подключен: {e}")

# Временное хранилище для добавляемых профилей
user_context = {}
# Режим работы пользователя (download/normal)
user_mode = {}

def get_main_keyboard():
    """Создаёт постоянную клавиатуру главного меню"""
    keyboard = [
        [KeyboardButton("📥 Скачать видео"), KeyboardButton("📊 Моя статистика")],
        [KeyboardButton("📂 Мои проекты")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_action_menu():
    """Создаёт меню выбора действия после операции"""
    keyboard = [
        [KeyboardButton("📥 Скачать ещё видео"), KeyboardButton("➕ Добавить профиль")],
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("🏠 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_admin_keyboard():
    """Создаёт клавиатуру для админов"""
    keyboard = [
        [KeyboardButton("📥 Скачать видео"), KeyboardButton("📊 Моя статистика")],
        [KeyboardButton("📂 Мои проекты"), KeyboardButton("👑 Админ панель")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_project_keyboard(is_admin=False):
    """Создаёт клавиатуру для работы с проектом"""
    keyboard = [
        [KeyboardButton("📊 Моя статистика"), KeyboardButton("👤 Мои профили")],
        [KeyboardButton("➕ Добавить профиль"), KeyboardButton("📥 Скачать видео")],
        [KeyboardButton("🔄 Сменить проект"), KeyboardButton("ℹ️ Справка")]
    ]

    if is_admin:
        keyboard.append([KeyboardButton("👑 Админ панель")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def detect_platform(url):
    """Определяет платформу по URL"""
    if re.search(TIKTOK_URL_PATTERN, url):
        return "tiktok"
    elif re.search(INSTAGRAM_URL_PATTERN, url):
        return "instagram"
    elif re.search(FACEBOOK_URL_PATTERN, url):
        return "facebook"
    elif re.search(YOUTUBE_URL_PATTERN, url):
        return "youtube"
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)
    
    # Выбираем клавиатуру в зависимости от прав пользователя
    if user.id in ADMIN_IDS:
        keyboard = get_admin_keyboard()
    else:
        keyboard = get_main_keyboard()
    
    await update.message.reply_text(
        f'Привет, {user.first_name}! 👋\n\n'
        'Я помогу вам отслеживать статистику профилей в TikTok, Instagram, Facebook и YouTube.\n\n'
        '📝 *Отправьте мне ссылку на профиль:*\n'
        '  • TikTok: https://www.tiktok.com/@username\n'
        '  • Instagram: https://www.instagram.com/username/\n'
        '  • Facebook: https://www.facebook.com/username\n'
        '  • YouTube: https://www.youtube.com/@username\n\n'
        '📥 *Скачать видео:*\n'
        '  Нажмите "📥 Скачать видео" внизу или используйте\n'
        '  `/download <ссылка>` (лимит 6/день)\n\n'
        '💡 *Используйте кнопки внизу для быстрого доступа*',
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет текущую операцию и сбрасывает состояние"""
    user_id = update.effective_user.id
    
    if user_id in user_mode:
        del user_mode[user_id]
    if user_id in user_context:
        del user_context[user_id]
    
    if user_id in ADMIN_IDS:
        keyboard = get_admin_keyboard()
    else:
        keyboard = get_main_keyboard()
    
    await update.message.reply_text(
        '❌ *Операция отменена*\n\n'
        '💡 Выберите действие из меню ниже.',
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    user = update.effective_user
    
    help_text = (
        '📚 *Справка по командам*\n\n'
        '🔹 /start - Начать работу\n'
        '🔹 /help - Эта справка\n'
        '🔹 /cancel - Отменить текущую операцию\n'
        '🔹 /mystats - Моя статистика\n'
        '🔹 /links - Список моих профилей\n'
        '🔹 /download - Скачать TikTok видео (лимит 6/день)\n\n'
        '📝 *Как добавить профиль:*\n'
        'Просто отправьте ссылку на профиль TikTok, Instagram, Facebook или YouTube\n\n'
        '*TikTok:*\n'
        '  https://www.tiktok.com/@username\n\n'
        '*Instagram:*\n'
        '  https://www.instagram.com/username/\n\n'
        '*Facebook:*\n'
        '  https://www.facebook.com/username\n\n'
        '*YouTube:*\n'
        '  https://www.youtube.com/@username'
    )
    
    if user.id in ADMIN_IDS:
        help_text += (
            '\n\n👑 *Команды администратора:*\n'
            '/admin - Админ-панель\n'
            '/update - Обновить статистику\n'
            '/broadcast - Разослать статистику\n'
            '/stats - Общая статистика'
        )
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def handle_keyboard_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки постоянной клавиатуры"""
    text = update.message.text
    user = update.effective_user

    # ПРОВЕРКА: ждем ли мы ввод минимального количества просмотров для обновления
    if 'update_platform' in context.user_data:
        try:
            min_views = int(text.strip())
            if min_views < 0:
                await update.message.reply_text('❌ Количество просмотров не может быть отрицательным. Попробуйте еще раз:')
                return

            platform = context.user_data['update_platform']
            project_id = context.user_data.get('project_id_for_update')
            project_name = None

            # Если указан project_id, получаем имя проекта
            if project_id:
                project = project_manager.get_project(project_id)
                if project:
                    project_name = project['name']
                    await update.message.reply_text(
                        f'🔄 Обновляю проект *{project_name}* с минимальным порогом: {min_views:,} просмотров...',
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text('❌ Проект не найден!')
                    context.user_data.pop('update_platform', None)
                    context.user_data.pop('project_id_for_update', None)
                    return
            else:
                await update.message.reply_text(f'🔄 Обновляю с минимальным порогом: {min_views:,} просмотров...')

            try:
                if not sheets_db:
                    await update.message.reply_text('❌ Google Sheets не подключен!')
                    context.user_data.pop('update_platform', None)
                    context.user_data.pop('project_id_for_update', None)
                    return

                if platform == 'tiktok':
                    result = sheets_db.update_all_profiles(tiktok_api, None, min_views=min_views, project_name=project_name)
                    message = (
                        f'✅ *TikTok обновлён!*\n\n'
                        f'📊 Обновлено (NEW): {result["tiktok"]["updated"]}\n'
                        f'⭐ Пропущено (OLD): {result["tiktok"]["skipped"]}\n'
                        f'🔽 Пропущено (мало просмотров): {result["tiktok"].get("filtered", 0)}\n'
                        f'❌ Ошибок: {result["tiktok"]["errors"]}'
                    )
                elif platform == 'instagram':
                    result = sheets_db.update_all_profiles(None, instagram_api, min_views=min_views, project_name=project_name)
                    message = (
                        f'✅ *Instagram обновлён!*\n\n'
                        f'📊 Обновлено (NEW): {result["instagram"]["updated"]}\n'
                        f'⭐ Пропущено (OLD/BAN): {result["instagram"]["skipped"]}\n'
                        f'🔽 Пропущено (мало просмотров): {result["instagram"].get("filtered", 0)}\n'
                        f'❌ Ошибок: {result["instagram"]["errors"]}'
                    )
                else:  # both
                    result = sheets_db.update_all_profiles(tiktok_api, instagram_api, min_views=min_views, project_name=project_name)
                    message = (
                        f'✅ *Обновление завершено!*\n\n'
                        f'🎵 TikTok:\n'
                        f'  📊 Обновлено (NEW): {result["tiktok"]["updated"]}\n'
                        f'  ⭐ Пропущено (OLD): {result["tiktok"]["skipped"]}\n'
                        f'  🔽 Пропущено (мало просмотров): {result["tiktok"].get("filtered", 0)}\n'
                        f'  ❌ Ошибок: {result["tiktok"]["errors"]}\n\n'
                        f'📷 Instagram:\n'
                        f'  📊 Обновлено (NEW): {result["instagram"]["updated"]}\n'
                        f'  ⭐ Пропущено (OLD): {result["instagram"]["skipped"]}\n'
                        f'  🔽 Пропущено (мало просмотров): {result["instagram"].get("filtered", 0)}\n'
                        f'  ❌ Ошибок: {result["instagram"]["errors"]}'
                    )

                await update.message.reply_text(message, parse_mode="Markdown")

            except Exception as e:
                logger.error(f"Ошибка обновления: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await update.message.reply_text(f'❌ Ошибка: {str(e)}')
            finally:
                context.user_data.pop('update_platform', None)
                context.user_data.pop('project_id_for_update', None)
            return

        except ValueError:
            await update.message.reply_text('❌ Пожалуйста, введите число (например: 30000)')
            return

    # ПРОВЕРКА: ждем ли мы ввод тематики
    if user.id in user_context and user_context[user.id].get("awaiting_topic"):
        profile_data = user_context[user.id]
        topic = text.strip().capitalize()
        
        if not topic or len(topic) > 50:
            await update.message.reply_text('❌ Тематика должна быть от 1 до 50 символов. Попробуйте еще раз:')
            return
        
        status = profile_data.get("status", "NEW")
        platform = profile_data.get("platform", "tiktok")
        
        # Определяем emoji
        if platform == "tiktok":
            platform_emoji = "🎵"
        elif platform == "instagram":
            platform_emoji = "📷"
        elif platform == "facebook":
            platform_emoji = "👤"
        elif platform == "youtube":
            platform_emoji = "🎬"
        else:
            platform_emoji = "📱"
        
        logger.info(f"✅ Добавляем {platform} профиль: {status}, {topic}")

        # Получаем текущий проект пользователя
        current_project_id = project_manager.get_user_current_project(str(user.id))
        project_name = ""
        if current_project_id:
            project = project_manager.get_project(current_project_id)
            if project:
                project_name = project["name"]

        if sheets_db:
            try:
                result = sheets_db.add_profile(
                    telegram_user=profile_data["telegram_user"],
                    url=profile_data["url"],
                    status=status,
                    platform=platform,
                    topic=topic,
                    project_name=project_name
                )
                
                if result and not result.get("exists"):
                    if status == "NEW":
                        if platform in ["tiktok", "instagram"]:
                            message = (
                                f'{platform_emoji} ✅ Профиль добавлен!\n\n'
                                f'👤 {profile_data["username"]}\n'
                                f'📌 Тематика: {topic}\n'
                                f'📊 Статус: {status}\n\n'
                                f'Статистика будет автоматически обновляться.\n'
                                f'Используйте /mystats для просмотра.'
                            )
                        else:
                            message = (
                                f'{platform_emoji} ✅ Профиль добавлен!\n\n'
                                f'👤 {profile_data["username"]}\n'
                                f'📌 Тематика: {topic}\n'
                                f'📊 Статус: {status}\n\n'
                                f'⚠️ Статистика для {platform.upper()} обновляется вручную.\n'
                                f'Данные будут видны в /mystats после внесения.'
                            )
                    else:
                        message = (
                            f'{platform_emoji} ✅ Профиль добавлен!\n\n'
                            f'👤 {profile_data["username"]}\n'
                            f'📌 Тематика: {topic}\n'
                            f'📊 Статус: {status}\n\n'
                            f'⚠️ Этот профиль не будет обновляться автоматически.\n'
                            f'Статистика будет видна в /mystats после внесения данных.'
                        )
                    
                    await update.message.reply_text(message)
                    logger.info("✅ Профиль добавлен успешно")
                else:
                    await update.message.reply_text('❌ Ошибка при сохранении профиля.')
            except Exception as e:
                logger.error(f"❌ Ошибка: {e}")
                await update.message.reply_text(f'❌ Ошибка: {str(e)}')
        else:
            await update.message.reply_text('❌ Google Sheets не подключен')
        
        user_context.pop(user.id, None)
        return
    
    # АВТОМАТИЧЕСКИЙ СБРОС СОСТОЯНИЙ при нажатии кнопок главного меню
    main_menu_buttons = [
        "📊 Моя статистика", 
        "📋 Мои профили", 
        "📥 Скачать видео", 
        "📚 Справка",
        "🏠 Главное меню",
        "👑 Админ панель"
    ]
    
    if text in main_menu_buttons:
        user_id = user.id
        if user_id in user_mode:
            del user_mode[user_id]
        if user_id in user_context:
            del user_context[user_id]
    
    if text == "📊 Моя статистика":
        # Проверяем есть ли текущий проект
        current_project_id = project_manager.get_user_current_project(str(user.id))

        if current_project_id:
            # Если есть текущий проект, показываем статистику по нему
            await my_stats(update, context)
        else:
            # Если нет текущего проекта, показываем выбор проекта
            projects = project_manager.get_user_projects(str(user.id))

            if not projects:
                await update.message.reply_text(
                    '📂 У вас пока нет проектов.\n\n'
                    'Попросите администратора добавить вас в проект.',
                    parse_mode="Markdown"
                )
                return

            keyboard = []
            for project in projects:
                keyboard.append([InlineKeyboardButton(
                    f'{project["name"]} ({project["start_date"]} — {project["end_date"]})',
                    callback_data=f'select_stats_project_{project["id"]}'
                )])

            await update.message.reply_text(
                '📊 *Выберите проект для просмотра статистики:*',
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    
    elif text == "📋 Мои профили" or text == "👤 Мои профили":
        await show_links(update, context)

    elif text == "🔄 Сменить проект" or text == "📂 Мои проекты":
        # Вызываем команду my_projects
        await my_projects(update, context)

    elif text == "ℹ️ Справка":
        await help_command(update, context)

    elif text == "📥 Скачать видео" or text == "📥 Скачать ещё видео":
        # Проверяем лимит
        daily_count = tiktok_downloader.get_daily_downloads(user.id)
        remaining = 6 - daily_count
        
        if not tiktok_downloader.can_download(user.id):
            await update.message.reply_text(
                f'⚠️ *Лимит исчерпан!*\n\n'
                f'Вы уже скачали {daily_count}/6 видео сегодня.\n'
                f'Попробуйте завтра!',
                parse_mode="Markdown"
            )
            return
        
        # Включаем режим ожидания ссылки
        user_mode[user.id] = "download"
        
        await update.message.reply_text(
            f'📥 *Режим скачивания активирован*\n\n'
            f'Отправьте ссылку на TikTok видео:\n'
            f'Например: `https://www.tiktok.com/@user/video/123`\n\n'
            f'📊 Доступно сегодня: {remaining}/6',
            parse_mode="Markdown"
        )
    
    elif text == "➕ Добавить профиль":
        # Режим добавления профиля
        user_mode[user.id] = "add_profile"
        
        await update.message.reply_text(
            '➕ *Режим добавления профиля*\n\n'
            'Отправьте ссылку на профиль:\n'
            '  • TikTok: https://www.tiktok.com/@username\n'
            '  • Instagram: https://www.instagram.com/username/\n'
            '  • Facebook: https://www.facebook.com/username\n'
            '  • YouTube: https://www.youtube.com/@username',
            parse_mode="Markdown"
        )
    
    elif text == "🏠 Главное меню":
        # Возвращаем в обычный режим
        user_mode[user.id] = "normal"
        
        if user.id in ADMIN_IDS:
            keyboard = get_admin_keyboard()
        else:
            keyboard = get_main_keyboard()
        
        await update.message.reply_text(
            '🏠 Главное меню',
            reply_markup=keyboard
        )
    
    elif text == "📚 Справка":
        await help_command(update, context)
    
    elif text == "👑 Админ панель":
        if user.id in ADMIN_IDS:
            await admin_panel(update, context)
        else:
            await update.message.reply_text("❌ У вас нет доступа к админ-панели.")
    
    else:
        # Проверяем режим пользователя
        mode = user_mode.get(user.id, "normal")
        
        if mode == "download":
            # Обрабатываем как ссылку на видео для скачивания
            await handle_download_link(update, context)
        elif mode == "add_profile":
            # Обрабатываем как ссылку на профиль
            await process_link(update, context)
            # После добавления профиля показываем меню действий
            user_mode[user.id] = "normal"
        else:
            # Обычный режим - пытаемся определить что это
            if 'tiktok.com' in text.lower() and '/video/' in text.lower():
                # Похоже на ссылку на видео - предлагаем скачать
                keyboard = [
                    [InlineKeyboardButton("📥 Скачать видео", callback_data="quick_download")],
                    [InlineKeyboardButton("➕ Добавить профиль", callback_data="quick_profile")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Сохраняем ссылку
                user_context[user.id] = {"link": text}
                
                await update.message.reply_text(
                    '🤔 Что вы хотите сделать с этой ссылкой?',
                    reply_markup=reply_markup
                )
            else:
                # Обрабатываем как профиль
                await process_link(update, context)

async def handle_download_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ссылки на видео для скачивания"""
    user = update.effective_user
    video_url = update.message.text
    
    # Проверяем что это TikTok ссылка
    if 'tiktok.com' not in video_url.lower():
        await update.message.reply_text(
            '❌ Это не ссылка на TikTok видео!\n\n'
            'Отправьте ссылку вида:\n'
            'https://www.tiktok.com/@username/video/1234567890'
        )
        return
    
    # Проверяем лимит
    if not tiktok_downloader.can_download(user.id):
        daily_count = tiktok_downloader.get_daily_downloads(user.id)
        user_mode[user.id] = "normal"
        await update.message.reply_text(
            f'⚠️ *Лимит исчерпан!*\n\n'
            f'Вы уже скачали {daily_count}/6 видео сегодня.\n'
            f'Попробуйте завтра!',
            parse_mode="Markdown"
        )
        return
    
    # Скачиваем
    msg = await update.message.reply_text('⏳ Получаю видео...')
    
    try:
        result = tiktok_downloader.download_video(video_url)
        
        if result.get("success"):
            # Записываем скачивание
            tiktok_downloader.add_download(user.id, video_url)
            
            daily_count = tiktok_downloader.get_daily_downloads(user.id)
            remaining = 6 - daily_count
            
            download_url = result.get("download_url")
            title = result.get("title", "TikTok Video")
            author = result.get("author", "Unknown")
            
            # Проверяем что ссылка не пустая
            if not download_url:
                user_mode[user.id] = "normal"
                logger.error(f"❌ Пустая ссылка на видео! Raw data: {result.get('raw_data')}")
                await msg.edit_text(
                    f'❌ *Ошибка получения видео*\n\n'
                    f'API не вернул ссылку на скачивание.\n'
                    f'Попробуйте другое видео или повторите позже.\n\n'
                    f'📊 Скачано сегодня: {daily_count}/6',
                    parse_mode="Markdown"
                )
                return
            
            # Возвращаемся в обычный режим и показываем меню действий
            user_mode[user.id] = "normal"
            action_keyboard = get_action_menu()
            
            await msg.edit_text('📥 Скачиваю видео...')
            
            # Скачиваем видео файл
            try:
                video_response = requests.get(download_url, timeout=60)
                video_response.raise_for_status()
                
                video_file = io.BytesIO(video_response.content)
                video_file.name = f"{author}_{title[:30]}.mp4"
                
                await msg.edit_text('📤 Отправляю видео...')
                
                # Отправляем видео файлом
                await update.message.reply_video(
                    video=video_file,
                    caption=(
                        f'✅ *Видео готово!*\n\n'
                        f'👤 Автор: {author}\n'
                        f'📝 {title[:100]}\n\n'
                        f'📊 Скачано сегодня: {daily_count}/6\n'
                        f'Осталось: {remaining}'
                    ),
                    parse_mode="Markdown",
                    supports_streaming=True
                )
                
                await msg.delete()
                
                # Отправляем меню действий
                await update.message.reply_text(
                    '💡 Выберите действие:',
                    reply_markup=action_keyboard
                )
            except Exception as e:
                logger.error(f"Ошибка отправки видео: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                # Если не получилось отправить видео, даём ссылку
                await msg.edit_text(
                    f'✅ *Видео готово!*\n\n'
                    f'👤 Автор: {author}\n'
                    f'📝 {title[:100]}\n\n'
                    f'Видео слишком большое для отправки в Telegram.\n\n'
                    f'[📥 Скачать видео]({download_url})\n\n'
                    f'📊 Скачано сегодня: {daily_count}/6\n'
                    f'Осталось: {remaining}',
                    parse_mode="Markdown",
                    disable_web_page_preview=False
                )
                
                await update.message.reply_text(
                    '💡 Выберите действие:',
                    reply_markup=action_keyboard
                )
        else:
            user_mode[user.id] = "normal"
            error = result.get("error", "Неизвестная ошибка")
            await msg.edit_text(
                f'❌ Ошибка получения видео:\n{error}\n\n'
                f'Проверьте ссылку и попробуйте снова.'
            )
    
    except Exception as e:
        user_mode[user.id] = "normal"
        logger.error(f"Ошибка скачивания видео: {e}")
        await msg.edit_text(f'❌ Ошибка: {str(e)}')

async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ссылки на профиль TikTok, Instagram, Facebook или YouTube"""
    user = update.effective_user
    text = update.message.text
    
    # Определяем платформу
    platform = detect_platform(text)
    
    if not platform:
        return  # Не ссылка на поддерживаемые платформы
    
    processing_msg = await update.message.reply_text('🔍 Проверяю ссылку...')
    
    try:
        if platform == "tiktok":
            # TIKTOK ЛОГИКА
            url = tiktok_api.normalize_tiktok_url(text)
            info = tiktok_api.extract_user_info(url)
            link_type = info.get("type", "unknown")
            
            if link_type == "video":
                await processing_msg.delete()
                await update.message.reply_text(
                    '⚠️ Пожалуйста, отправьте ссылку на ПРОФИЛЬ, а не на видео.\n\n'
                    '✅ Правильно: https://www.tiktok.com/@username\n'
                    '❌ Неправильно: https://www.tiktok.com/@username/video/123456'
                )
                return
            
            username = info.get("username")
            display_name = f"@{username}"
            platform_emoji = "🎵"
            content_type = "видео"
            
        elif platform == "instagram":
            # INSTAGRAM ЛОГИКА
            username = instagram_api.extract_username_from_url(text)
            url = f"https://www.instagram.com/{username}/"
            display_name = f"@{username}"
            platform_emoji = "📷"
            content_type = "reels"
            
        elif platform == "facebook":
            # FACEBOOK ЛОГИКА
            username = facebook_api.extract_username_from_url(text)
            url = facebook_api.normalize_url(text)
            display_name = username
            platform_emoji = "👤"
            content_type = "посты"
            
        elif platform == "youtube":
            # YOUTUBE ЛОГИКА
            url = youtube_api.normalize_url(text)
            display_name = youtube_api.get_display_name(text)
            platform_emoji = "🎬"
            content_type = "видео"
        
        # Проверяем существование в sheets
        if sheets_db and sheets_db.check_profile_exists(url, platform):
            await processing_msg.delete()
            await update.message.reply_text(
                '⚠️ Этот профиль уже добавлен в систему!\n\n'
                'Используйте /mystats для просмотра статистики.'
            )
            return
        
        telegram_user = f"@{user.username}" if user.username else user.first_name
        telegram_id = str(user.id)  # Добавляем ID для точности
        
        # Сохраняем данные для колбэка
        user_context[user.id] = {
            "url": url,
            "telegram_user": telegram_user,
            "telegram_id": telegram_id,  # Сохраняем ID
            "username": username if platform in ["tiktok", "instagram", "facebook"] else display_name,
            "platform": platform
        }
        
        # Добавляем в локальную БД
        db.add_link(user.id, url, "profile", username=username if platform in ["tiktok", "instagram"] else display_name)
        
        # Создаём кнопки для выбора
        keyboard = [
            [
                InlineKeyboardButton("✅ Нет (новый)", callback_data=f"profile_new_{user.id}"),
                InlineKeyboardButton("⚠️ Да (старый)", callback_data=f"profile_old_{user.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Экранируем специальные символы для Markdown
        def escape_markdown(text):
            """Экранирует специальные символы Markdown"""
            special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in special_chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        escaped_username = escape_markdown(display_name)
        escaped_content = escape_markdown(content_type)
        
        await processing_msg.delete()
        await update.message.reply_text(
            f'{platform_emoji} ✅ Профиль {display_name} готов к добавлению!\n\n'
            f'❓ На этом аккаунте есть старые {content_type} '
            f'(снятые до начала работы с нами)?\n\n'
            f'• Выберите "Нет" если аккаунт новый или все {content_type} сняты для нас\n'
            f'• Выберите "Да" если есть старые {content_type} '
            f'(мы не будем их учитывать)',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error processing link: {e}")
        await processing_msg.delete()
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')

async def profile_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора статуса профиля (NEW/OLD)"""
    query = update.callback_query
    logger.info(f"📘 PROFILE CALLBACK RECEIVED: {query.data}")
    await query.answer()
    
    data_parts = query.data.split("_")
    logger.info(f"🔍 Data parts: {data_parts}")
    
    if len(data_parts) < 3:
        logger.error(f"❌ Неправильный формат данных: {data_parts}")
        await query.edit_message_text('❌ Ошибка: неправильный формат данных.')
        return
    
    status_choice = data_parts[1]  # "new" или "old"
    user_id = int(data_parts[2])
    
    logger.info(f"🔍 Status: {status_choice}, User ID: {user_id}")
    
    profile_data = user_context.get(user_id)
    logger.info(f"🔍 Profile data: {profile_data}")
    
    if not profile_data:
        await query.edit_message_text('❌ Ошибка: данные потеряны. Попробуйте добавить профиль снова.')
        return
    
    status = "NEW" if status_choice == "new" else "OLD"
    
    # Сохраняем статус в контекст
    profile_data["status"] = status
    user_context[user_id] = profile_data
    
    # Теперь спрашиваем о тематике
    keyboard = [
        [
            InlineKeyboardButton("😂 Юмор", callback_data=f"topic_юмор_{user_id}"),
            InlineKeyboardButton("⚽ Спорт", callback_data=f"topic_спорт_{user_id}")
        ],
        [
            InlineKeyboardButton("🎮 Киберспорт", callback_data=f"topic_киберспорт_{user_id}"),
            InlineKeyboardButton("🎬 Сериалы/фильмы", callback_data=f"topic_сериалы/фильмы_{user_id}")
        ],
        [
            InlineKeyboardButton("🎰 Гемблинг", callback_data=f"topic_гемблинг_{user_id}"),
            InlineKeyboardButton("📺 Телешоу", callback_data=f"topic_телешоу_{user_id}")
        ],
        [
            InlineKeyboardButton("🧠 Познавательное", callback_data=f"topic_познавательное_{user_id}"),
            InlineKeyboardButton("🤖 AI", callback_data=f"topic_ai_{user_id}")
        ],
        [
            InlineKeyboardButton("💃 Танцы", callback_data=f"topic_танцы_{user_id}"),
            InlineKeyboardButton("🎵 Клипы", callback_data=f"topic_клипы_{user_id}")
        ],
        [
            InlineKeyboardButton("✏️ Своя тематика", callback_data=f"topic_custom_{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f'✅ Статус выбран: {status}\n\n'
        f'📌 Теперь выберите тематику контента:',
        reply_markup=reply_markup
    )
    
    logger.info(f"✅ Запрос тематики для user {user_id}")

async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора тематики профиля"""
    query = update.callback_query
    logger.info(f"📘 TOPIC CALLBACK RECEIVED: {query.data}")
    await query.answer()
    
    data_parts = query.data.split("_")
    if len(data_parts) < 3:
        await query.edit_message_text('❌ Ошибка: неправильный формат данных.')
        return
    
    topic_choice = data_parts[1]
    user_id = int(data_parts[2])
    
    profile_data = user_context.get(user_id)
    if not profile_data:
        await query.edit_message_text('❌ Ошибка: данные потеряны. Попробуйте добавить профиль снова.')
        return
    
    # Если выбрана своя тематика, спрашиваем текст
    if topic_choice == "custom":
        profile_data["awaiting_topic"] = True
        user_context[user_id] = profile_data
        await query.edit_message_text(
            '✏️ Напишите свою тематику (например: "Путешествия", "Кулинария", "Бизнес"):'
        )
        return
    
    # Иначе сохраняем выбранную тематику
    topic = topic_choice.strip().capitalize()
    status = profile_data.get("status", "NEW")
    platform = profile_data.get("platform", "tiktok")
    
    # Определяем emoji
    if platform == "tiktok":
        platform_emoji = "🎵"
    elif platform == "instagram":
        platform_emoji = "📷"
    elif platform == "facebook":
        platform_emoji = "👤"
    elif platform == "youtube":
        platform_emoji = "🎬"
    else:
        platform_emoji = "📱"
    
    logger.info(f"✅ Добавляем {platform} профиль: {status}, {topic}")

    # Получаем текущий проект пользователя
    current_project_id = project_manager.get_user_current_project(str(user_id))
    project_name = ""
    if current_project_id:
        project = project_manager.get_project(current_project_id)
        if project:
            project_name = project["name"]

    if sheets_db:
        try:
            result = sheets_db.add_profile(
                telegram_user=profile_data["telegram_user"],
                url=profile_data["url"],
                status=status,
                platform=platform,
                topic=topic,
                project_name=project_name
            )
            
            logger.info(f"📊 Результат добавления: {result}")
            
            if result and not result.get("exists"):
                if status == "NEW":
                    if platform in ["tiktok", "instagram"]:
                        message = (
                            f'{platform_emoji} ✅ Профиль добавлен!\n\n'
                            f'👤 {profile_data["username"]}\n'
                            f'📌 Тематика: {topic}\n'
                            f'📊 Статус: {status}\n\n'
                            f'Статистика будет автоматически обновляться.\n'
                            f'Используйте /mystats для просмотра.'
                        )
                    else:
                        message = (
                            f'{platform_emoji} ✅ Профиль добавлен!\n\n'
                            f'👤 {profile_data["username"]}\n'
                            f'📌 Тематика: {topic}\n'
                            f'📊 Статус: {status}\n\n'
                            f'⚠️ Статистика для {platform.upper()} обновляется вручную.\n'
                            f'Данные будут видны в /mystats после внесения.'
                        )
                else:
                    message = (
                        f'{platform_emoji} ✅ Профиль добавлен!\n\n'
                        f'👤 {profile_data["username"]}\n'
                        f'📌 Тематика: {topic}\n'
                        f'📊 Статус: {status}\n\n'
                        f'⚠️ Этот профиль не будет обновляться автоматически.\n'
                        f'Статистика будет видна в /mystats после внесения данных.'
                    )
                
                await query.edit_message_text(message)
                logger.info("✅ Профиль добавлен успешно")
            else:
                await query.edit_message_text('❌ Ошибка при сохранении профиля.')
                logger.error("❌ Профиль не был добавлен")
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f'❌ Ошибка: {str(e)}')
    else:
        logger.error("❌ sheets_db не инициализирован!")
        await query.edit_message_text('❌ Google Sheets не подключен')
    
    user_context.pop(user_id, None)
    logger.info("🧹 Очищен user_context")


async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает статистику пользователя по всем платформам"""
    user = update.effective_user
    telegram_user = f"@{user.username}" if user.username else user.first_name

    if not sheets_db:
        await update.message.reply_text('❌ Google Sheets не подключен.')
        return

    # Проверяем, есть ли у пользователя текущий проект
    current_project_id = project_manager.get_user_current_project(str(user.id))

    if not current_project_id:
        # Если пользователь не в проекте - предлагаем выбрать проект
        user_projects = project_manager.get_user_projects(str(user.id))

        if not user_projects:
            await update.message.reply_text(
                '❌ У вас нет доступных проектов.\n\n'
                'Обратитесь к администратору для добавления в проект.'
            )
            return

        # Показываем список проектов для выбора
        message = '📊 *Выберите проект для просмотра статистики:*\n\n'
        keyboard = []

        for i, project in enumerate(user_projects, 1):
            message += f'*{i}. {project["name"]}*\n'
            message += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
            if project.get('geo'):
                message += f'🌍 Гео: {project["geo"]}\n'
            message += f'📅 {project["start_date"]} — {project["end_date"]}\n\n'

            keyboard.append([
                InlineKeyboardButton(
                    f"📊 {project['name']}",
                    callback_data=f"select_stats_project_{project['id']}"
                )
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        return

    # Если пользователь в проекте - получаем имя проекта и показываем статистику
    project = project_manager.get_project(current_project_id)
    project_name = project["name"] if project else ""

    profiles = sheets_db.get_user_profiles(telegram_user, project_name=project_name)
    
    if not profiles:
        await update.message.reply_text(
            '📊 У вас пока нет отслеживаемых профилей.\n\n'
            'Отправьте ссылку на профиль TikTok, Instagram, Facebook или YouTube для начала работы.'
        )
        return
    
    # Подготавливаем данные для snapshot
    current_data = {
        "tiktok": [],
        "instagram": [],
        "facebook": [],
        "youtube": []
    }
    
    # Группируем по платформам
    tiktok_profiles = [p for p in profiles if p.get("platform") == "tiktok"]
    instagram_profiles = [p for p in profiles if p.get("platform") == "instagram"]
    facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
    youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]
    
    # Заполняем current_data для расчета прироста
    for p in tiktok_profiles:
        current_data["tiktok"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
    for p in instagram_profiles:
        current_data["instagram"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
    for p in facebook_profiles:
        current_data["facebook"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
    for p in youtube_profiles:
        current_data["youtube"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
    
    # Получаем прирост на основе предыдущего snapshot
    daily_growth = db.calculate_growth_from_snapshot(user.id, current_data)
    
    # Сохраняем новый snapshot
    db.save_stats_snapshot(user.id, current_data)
    
    message = f'📊 *Ваша статистика*\n\n'
    
    total_followers = 0
    total_videos = 0
    total_views = 0
    
    # TikTok профили
    if tiktok_profiles:
        message += '🎵 *TikTok*\n'
        for i, profile in enumerate(tiktok_profiles, 1):
            try:
                followers = int(profile.get("followers", 0) or 0)
                videos = int(profile.get("videos", 0) or 0)
                views = int(profile.get("total_views", 0) or 0)
                likes = int(profile.get("likes", 0) or 0)
                comments = int(profile.get("comments", 0) or 0)
                status = profile.get("status", "NEW")
                
                total_followers += followers
                total_videos += videos
                total_views += views
                
                username = parse_tiktok_username(profile["url"])
                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                
                # Экранируем подчеркивание в никнейме
                escaped_username = username.replace('_', '\\_')
                message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                message += f'👥 Подписчиков: {format_number(followers)}\n'
                message += f'🎬 Видео: {videos}\n'
                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                message += f'❤️ Лайков: {format_number(likes)}\n'
                message += f'💬 Комментариев: {comments}\n'
                
                # ДОБАВЛЯЕМ ПРИРОСТ для конкретного профиля
                if daily_growth:
                    views_growth = daily_growth.get(profile["url"], 0)
                    if views_growth != 0:
                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                
                message += '\n'
            except:
                continue
        
        message += '\n'
    
    # Instagram профили
    if instagram_profiles:
        message += '📷 *Instagram*\n'
        for i, profile in enumerate(instagram_profiles, 1):
            try:
                followers = int(profile.get("followers", 0) or 0)
                reels = int(profile.get("videos", 0) or 0)
                views = int(profile.get("total_views", 0) or 0)
                likes = int(profile.get("likes", 0) or 0)
                comments = int(profile.get("following", 0) or 0)
                status = profile.get("status", "NEW")
                
                total_followers += followers
                total_videos += reels
                total_views += views
                
                username = parse_instagram_username(profile["url"])
                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                
                # Экранируем подчеркивание в никнейме
                escaped_username = username.replace('_', '\\_')
                message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                message += f'👥 Подписчиков: {format_number(followers)}\n'
                message += f'🎬 Reels: {reels}\n'
                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                message += f'❤️ Лайков: {format_number(likes)}\n'
                message += f'💬 Комментариев: {comments}\n'
                
                # ДОБАВЛЯЕМ ПРИРОСТ для конкретного профиля
                if daily_growth:
                    views_growth = daily_growth.get(profile["url"], 0)
                    if views_growth != 0:
                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                
                message += '\n'
            except Exception as e:
                logger.error(f"Ошибка обработки Instagram профиля: {e}")
                continue
        
        message += '\n'
    
    # Facebook профили
    if facebook_profiles:
        message += '👤 *Facebook*\n'
        for i, profile in enumerate(facebook_profiles, 1):
            try:
                followers = int(profile.get("followers", 0) or 0)
                posts = int(profile.get("videos", 0) or 0)
                views = int(profile.get("total_views", 0) or 0)
                likes = int(profile.get("likes", 0) or 0)
                status = profile.get("status", "NEW")
                
                total_followers += followers
                total_videos += posts
                total_views += views
                
                username = parse_facebook_username(profile["url"])
                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                
                escaped_username = username.replace('_', '\\_')
                message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                message += f'👥 Подписчиков: {format_number(followers)}\n'
                message += f'📝 Посты: {posts}\n'
                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                message += f'❤️ Лайков: {format_number(likes)}\n'
                
                # ДОБАВЛЯЕМ ПРИРОСТ для конкретного профиля
                if daily_growth:
                    views_growth = daily_growth.get(profile["url"], 0)
                    if views_growth != 0:
                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                
                message += '\n'
            except:
                continue
        
        message += '\n'
    
    # YouTube профили
    if youtube_profiles:
        message += '🎬 *YouTube*\n'
        for i, profile in enumerate(youtube_profiles, 1):
            try:
                followers = int(profile.get("followers", 0) or 0)
                videos = int(profile.get("videos", 0) or 0)
                views = int(profile.get("total_views", 0) or 0)
                likes = int(profile.get("likes", 0) or 0)
                status = profile.get("status", "NEW")
                
                total_followers += followers
                total_videos += videos
                total_views += views
                
                display_name = parse_youtube_username(profile["url"])
                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                
                escaped_username = display_name.replace('_', '\\_')
                message += f'{i}\\. {escaped_username} {status_emoji}\n'
                message += f'👥 Подписчиков: {format_number(followers)}\n'
                message += f'🎬 Видео: {videos}\n'
                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                message += f'❤️ Лайков: {format_number(likes)}\n'
                
                # ДОБАВЛЯЕМ ПРИРОСТ для конкретного профиля
                if daily_growth:
                    views_growth = daily_growth.get(profile["url"], 0)
                    if views_growth != 0:
                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                
                message += '\n'
            except:
                continue
        
        message += '\n'
    
    # Общая статистика
    # ОБЩИЙ ПРИРОСТ
    total_views_growth = 0
    if daily_growth:
        total_views_growth = sum(daily_growth.values())
    
    message += f'━━━━━━━━━━━━━━━\n'
    message += f'📈 *ИТОГО:*\n'
    message += f'👥 Всего подписчиков: {format_number(total_followers)}\n'
    message += f'🎬 Контента: {total_videos}\n'
    
    # Добавляем новую строку для прироста (всегда)
    growth_line = format_growth_line(total_views_growth, label="Прирост")
    message += f'{growth_line}\n'
    
    message += f'👁 Всего просмотров: {format_number(total_views, full=True)}'

    await update.message.reply_text(message, parse_mode="Markdown")

async def my_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список проектов пользователя и позволяет выбрать текущий"""
    user = update.effective_user
    user_id = str(user.id)

    # Получаем проекты пользователя
    projects = project_manager.get_user_projects(user_id)

    if not projects:
        await update.message.reply_text(
            '📂 У вас пока нет проектов.\n\n'
            'Ожидайте, когда администратор добавит вас в проект.'
        )
        return

    message = '📂 *Выберите проект:*\n\n'
    keyboard = []

    for i, project in enumerate(projects, 1):
        message += f'*{i}. {project["name"]}*\n'
        message += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'

        if project.get('geo'):
            message += f'🌍 Гео: {project["geo"]}\n'

        message += f'📅 {project["start_date"]} — {project["end_date"]}\n\n'

        # Добавляем кнопку для каждого проекта
        keyboard.append([
            InlineKeyboardButton(
                f"Выбрать: {project['name']}",
                callback_data=f"select_project_{project['id']}"
            )
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def show_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает список профилей пользователя по всем платформам"""
    user = update.effective_user
    telegram_user = f"@{user.username}" if user.username else user.first_name

    if not sheets_db:
        await update.message.reply_text('❌ Google Sheets не подключен.')
        return

    # Получаем текущий проект пользователя
    current_project_id = project_manager.get_user_current_project(str(user.id))
    project_name = ""
    if current_project_id:
        project = project_manager.get_project(current_project_id)
        if project:
            project_name = project["name"]

    # Получаем профили, отфильтрованные по проекту
    profiles = sheets_db.get_user_profiles(telegram_user, project_name=project_name if project_name else None)
    
    if not profiles:
        await update.message.reply_text('У вас пока нет добавленных профилей.')
        return
    
    message = f'📋 *Ваши профили:*\n\n'
    
    # Группируем по платформам
    tiktok_profiles = [p for p in profiles if p.get("platform") == "tiktok"]
    instagram_profiles = [p for p in profiles if p.get("platform") == "instagram"]
    facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
    youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]
    
    if tiktok_profiles:
        message += '🎵 *TikTok:*\n'
        for i, profile in enumerate(tiktok_profiles, 1):
            username = profile["url"].split("@")[-1].split("/")[0] if "@" in profile["url"] else "unknown"
            status = profile.get("status", "NEW")
            status_text = "🆕 NEW" if status == "NEW" else "📦 OLD"
            
            # Экранируем подчеркивание в никнейме
            escaped_username = username.replace('_', '\\_')
            message += f'{i}. @{escaped_username} - {status_text}\n'
            message += f'   {profile["url"]}\n\n'
    
    if instagram_profiles:
        message += '📷 *Instagram:*\n'
        for i, profile in enumerate(instagram_profiles, 1):
            username = profile["url"].split("/")[-2] if "/" in profile["url"] else "unknown"
            status = profile.get("status", "NEW")
            status_text = "🆕 NEW" if status == "NEW" else "📦 OLD"
            
            # Экранируем подчеркивание в никнейме
            escaped_username = username.replace('_', '\\_')
            message += f'{i}. @{escaped_username} - {status_text}\n'
            message += f'   {profile["url"]}\n\n'
    
    if facebook_profiles:
        message += '👤 *Facebook:*\n'
        for i, profile in enumerate(facebook_profiles, 1):
            username = profile["url"].split("/")[-2] if "/" in profile["url"] else profile["url"].split("/")[-1]
            username = username.replace("https:", "").replace("www.facebook.com", "").strip("/")
            status = profile.get("status", "NEW")
            status_text = "🆕 NEW" if status == "NEW" else "📦 OLD"
            
            message += f'{i}. {username} - {status_text}\n'
            message += f'   {profile["url"]}\n\n'
    
    if youtube_profiles:
        message += '🎬 *YouTube:*\n'
        for i, profile in enumerate(youtube_profiles, 1):
            if "@" in profile["url"]:
                channel_name = profile["url"].split("@")[-1].split("/")[0]
                display_name = f"@{channel_name}"
            else:
                display_name = profile["url"].split("/")[-1]
            status = profile.get("status", "NEW")
            status_text = "🆕 NEW" if status == "NEW" else "📦 OLD"
            
            message += f'{i}. {display_name} - {status_text}\n'
            message += f'   {profile["url"]}\n\n'
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def download_video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /download для скачивания TikTok видео"""
    user = update.effective_user
    
    # Проверяем есть ли ссылка в аргументах
    if not context.args:
        daily_count = tiktok_downloader.get_daily_downloads(user.id)
        remaining = 6 - daily_count
        
        await update.message.reply_text(
            f'📥 *Скачивание TikTok видео*\n\n'
            f'Использование: `/download <ссылка на TikTok видео>`\n\n'
            f'Пример:\n'
            f'`/download https://www.tiktok.com/@username/video/1234567890`\n\n'
            f'📊 Сегодня скачано: {daily_count}/6\n'
            f'Осталось: {remaining}',
            parse_mode="Markdown"
        )
        return
    
    video_url = context.args[0]
    
    # Проверяем что это TikTok ссылка
    if 'tiktok.com' not in video_url.lower():
        await update.message.reply_text(
            '❌ Это не ссылка на TikTok видео!\n\n'
            'Отправьте ссылку вида:\n'
            'https://www.tiktok.com/@username/video/1234567890'
        )
        return
    
    # Проверяем лимит
    if not tiktok_downloader.can_download(user.id):
        daily_count = tiktok_downloader.get_daily_downloads(user.id)
        await update.message.reply_text(
            f'⚠️ *Лимит исчерпан!*\n\n'
            f'Вы уже скачали {daily_count}/6 видео сегодня.\n'
            f'Попробуйте завтра!',
            parse_mode="Markdown"
        )
        return
    
    # Скачиваем
    msg = await update.message.reply_text('⏳ Получаю видео...')
    
    try:
        result = tiktok_downloader.download_video(video_url)
        
        if result.get("success"):
            # Записываем скачивание
            tiktok_downloader.add_download(user.id, video_url)
            
            daily_count = tiktok_downloader.get_daily_downloads(user.id)
            remaining = 6 - daily_count
            
            download_url = result.get("download_url")
            title = result.get("title", "TikTok Video")
            author = result.get("author", "Unknown")
            
            await msg.edit_text(
                f'✅ *Видео готово!*\n\n'
                f'👤 Автор: {author}\n'
                f'📝 {title[:100]}\n\n'
                f'[📥 Скачать видео]({download_url})\n\n'
                f'📊 Скачано сегодня: {daily_count}/6\n'
                f'Осталось: {remaining}',
                parse_mode="Markdown"
            )
        else:
            error = result.get("error", "Неизвестная ошибка")
            await msg.edit_text(
                f'❌ Ошибка получения видео:\n{error}\n\n'
                f'Проверьте ссылку и попробуйте снова.'
            )
    
    except Exception as e:
        logger.error(f"Ошибка скачивания видео: {e}")
        await msg.edit_text(f'❌ Ошибка: {str(e)}')

# ============ АДМИН КОМАНДЫ ============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-панель с кнопками"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return
    
    keyboard = [
        [InlineKeyboardButton("📁 Управление проектами", callback_data="admin_projects")],
        [InlineKeyboardButton("🔄 Обновить статистику", callback_data="admin_update")],
        [InlineKeyboardButton("📨 Разослать статистику", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📊 Общая статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        '👑 *Панель администратора*\n\n'
        'Выберите действие:',
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка кнопок пользовательской панели"""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user = query.from_user
    
    if action == "user_mystats":
        # Вызываем my_stats
        telegram_user = f"@{user.username}" if user.username else user.first_name

        if not sheets_db:
            await query.edit_message_text('❌ Google Sheets не подключен.')
            return

        # Получаем текущий проект пользователя
        current_project_id = project_manager.get_user_current_project(str(user.id))
        project_name = ""
        if current_project_id:
            project = project_manager.get_project(current_project_id)
            if project:
                project_name = project["name"]

        profiles = sheets_db.get_user_profiles(telegram_user, project_name=project_name if project_name else None)
        
        if not profiles:
            await query.edit_message_text(
                '📊 У вас пока нет отслеживаемых профилей.\n\n'
                'Отправьте ссылку на профиль TikTok, Instagram, Facebook или YouTube для начала работы.'
            )
            return
        
        message = f'📊 *Ваша статистика* ({len(profiles)} профилей)\n\n'
        
        tiktok_profiles = [p for p in profiles if p.get("platform") == "tiktok"]
        instagram_profiles = [p for p in profiles if p.get("platform") == "instagram"]
        facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
        youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]
        
        total_followers = 0
        total_videos = 0
        total_views = 0
        
        # Строим сообщение (сокращённая версия для callback)
        if tiktok_profiles:
            tt_followers = sum(int(p.get("followers", 0) or 0) for p in tiktok_profiles)
            tt_videos = sum(int(p.get("videos", 0) or 0) for p in tiktok_profiles)
            tt_views = sum(int(p.get("total_views", 0) or 0) for p in tiktok_profiles)
            total_followers += tt_followers
            total_videos += tt_videos
            total_views += tt_views
            message += f'🎵 *TIKTOK:* {len(tiktok_profiles)} профилей\n'
            message += f'👁 Просмотров: {format_number(tt_views, full=True)}\n\n'
        
        if instagram_profiles:
            ig_followers = sum(int(p.get("followers", 0) or 0) for p in instagram_profiles)
            ig_reels = sum(int(p.get("videos", 0) or 0) for p in instagram_profiles)
            ig_views = sum(int(p.get("total_views", 0) or 0) for p in instagram_profiles)
            total_followers += ig_followers
            total_videos += ig_reels
            total_views += ig_views
            message += f'📷 *INSTAGRAM:* {len(instagram_profiles)} профилей\n'
            message += f'👁 Просмотров: {format_number(ig_views, full=True)}\n\n'
        
        message += f'━━━━━━━━━━━━━━━\n'
        message += f'*📈 ИТОГО:*\n'
        message += f'👁 Всего просмотров: {format_number(total_views, full=True)}\n\n'
        message += f'Для подробной статистики: /mystats'
        
        await query.edit_message_text(message, parse_mode="Markdown")
    
    elif action == "user_links":
        # Показываем список профилей
        telegram_user = f"@{user.username}" if user.username else user.first_name

        if not sheets_db:
            await query.edit_message_text('❌ Google Sheets не подключен.')
            return

        # Получаем текущий проект пользователя
        current_project_id = project_manager.get_user_current_project(str(user.id))
        project_name = ""
        if current_project_id:
            project = project_manager.get_project(current_project_id)
            if project:
                project_name = project["name"]

        profiles = sheets_db.get_user_profiles(telegram_user, project_name=project_name if project_name else None)
        
        if not profiles:
            await query.edit_message_text('У вас пока нет добавленных профилей.')
            return
        
        message = f'📋 *Ваши профили* ({len(profiles)})\n\n'
        message += 'Используйте /links для полного списка'
        
        await query.edit_message_text(message, parse_mode="Markdown")
    
    elif action == "user_download":
        # Инфо о скачивании
        daily_count = tiktok_downloader.get_daily_downloads(user.id)
        remaining = 6 - daily_count
        
        await query.edit_message_text(
            f'📥 *Скачивание TikTok видео*\n\n'
            f'Использование:\n'
            f'`/download <ссылка на видео>`\n\n'
            f'Пример:\n'
            f'`/download https://www.tiktok.com/@user/video/123`\n\n'
            f'📊 Сегодня скачано: {daily_count}/6\n'
            f'Осталось: {remaining}',
            parse_mode="Markdown"
        )
    
    elif action == "user_help":
        # Справка
        help_text = (
            '📚 *Справка по командам*\n\n'
            '🔹 /start - Начать работу\n'
            '🔹 /mystats - Моя статистика\n'
            '🔹 /links - Список профилей\n'
            '🔹 /download - Скачать видео (6/день)\n\n'
            '📝 Отправьте ссылку на профиль для добавления'
        )
        await query.edit_message_text(help_text, parse_mode="Markdown")
    
    elif action == "quick_download":
        # Быстрое скачивание
        link_data = user_context.get(user.id)
        if not link_data:
            await query.edit_message_text('❌ Ссылка потеряна. Отправьте снова.')
            return
        
        video_url = link_data.get("link")
        
        # Проверяем лимит
        if not tiktok_downloader.can_download(user.id):
            daily_count = tiktok_downloader.get_daily_downloads(user.id)
            await query.edit_message_text(
                f'⚠️ *Лимит исчерпан!*\n\n'
                f'Вы уже скачали {daily_count}/6 видео сегодня.\n'
                f'Попробуйте завтра!',
                parse_mode="Markdown"
            )
            return
        
        await query.edit_message_text('⏳ Получаю видео...')
        
        try:
            result = tiktok_downloader.download_video(video_url)
            
            if result.get("success"):
                tiktok_downloader.add_download(user.id, video_url)
                
                daily_count = tiktok_downloader.get_daily_downloads(user.id)
                remaining = 6 - daily_count
                
                download_url = result.get("download_url")
                title = result.get("title", "TikTok Video")
                author = result.get("author", "Unknown")
                
                # Проверяем что ссылка не пустая
                if not download_url:
                    logger.error(f"❌ Пустая ссылка на видео! Raw data: {result.get('raw_data')}")
                    await query.edit_message_text(
                        f'❌ *Ошибка получения видео*\n\n'
                        f'API не вернул ссылку на скачивание.\n'
                        f'Попробуйте другое видео или повторите позже.\n\n'
                        f'📊 Скачано сегодня: {daily_count}/6',
                        parse_mode="Markdown"
                    )
                    return
                
                action_keyboard = get_action_menu()
                
                await query.edit_message_text('📥 Скачиваю видео...')
                
                # Скачиваем и отправляем видео файлом
                try:
                    import requests
                    import io
                    
                    video_response = requests.get(download_url, timeout=60)
                    video_response.raise_for_status()
                    
                    video_file = io.BytesIO(video_response.content)
                    video_file.name = f"{author}_{title[:30]}.mp4"
                    
                    await query.edit_message_text('📤 Отправляю видео...')
                    
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=video_file,
                        caption=(
                            f'✅ *Видео готово!*\n\n'
                            f'👤 Автор: {author}\n'
                            f'📝 {title[:100]}\n\n'
                            f'📊 Скачано сегодня: {daily_count}/6\n'
                            f'Осталось: {remaining}'
                        ),
                        parse_mode="Markdown",
                        supports_streaming=True
                    )
                    
                    await query.message.delete()
                    
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text='💡 Выберите действие:',
                        reply_markup=action_keyboard
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки видео: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
                    # Если не получилось отправить видео, даём ссылку
                    await query.edit_message_text(
                        f'✅ *Видео готово!*\n\n'
                        f'👤 Автор: {author}\n'
                        f'📝 {title[:100]}\n\n'
                        f'Видео слишком большое для отправки в Telegram.\n\n'
                        f'[📥 Скачать видео]({download_url})\n\n'
                        f'📊 Скачано сегодня: {daily_count}/6\n'
                        f'Осталось: {remaining}',
                        parse_mode="Markdown",
                        disable_web_page_preview=False
                    )
                    
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text='💡 Выберите действие:',
                        reply_markup=action_keyboard
                    )
            else:
                error = result.get("error", "Неизвестная ошибка")
                await query.edit_message_text(
                    f'❌ Ошибка получения видео:\n{error}'
                )
        except Exception as e:
            await query.edit_message_text(f'❌ Ошибка: {str(e)}')
    
    elif action == "quick_profile":
        # Добавление профиля
        link_data = user_context.get(user.id)
        if not link_data:
            await query.edit_message_text('❌ Ссылка потеряна. Отправьте снова.')
            return
        
        await query.edit_message_text('⏳ Добавляю профиль...')
        
        # Тут нужно вызвать логику добавления профиля
        # Создаём фейковое обновление для process_link
        user_mode[user.id] = "add_profile"
        await query.edit_message_text(
            '➕ Отправьте ссылку на профиль снова для добавления'
        )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопок админ-панели"""
    query = update.callback_query
    logger.info(f"📘 CALLBACK RECEIVED: {query.data}")
    
    # Пропускаем profile_ колбэки
    if query.data.startswith("profile_"):
        logger.info("⭐ Пропускаем profile_ колбэк")
        return
    
    await query.answer()

    user = query.from_user
    action = query.data
    logger.info(f"📘 ACTION: {action}")

    # Обработка кнопки "Добавить профиль" (доступна всем пользователям)
    if action == "add_profile":
        user_mode[user.id] = "add_profile"
        await query.edit_message_text(
            '➕ *Добавление профиля*\n\n'
            'Отправьте ссылку на профиль TikTok, Instagram, Facebook или YouTube',
            parse_mode="Markdown"
        )
        return

    # Обработка выбора проекта для статистики (без установки текущего проекта)
    if action.startswith("select_stats_project_"):
        project_id = action.replace("select_stats_project_", "")
        user_id = str(user.id)

        # Проверяем, что пользователь в этом проекте
        user_projects = project_manager.get_user_projects(user_id)
        if not any(p['id'] == project_id for p in user_projects):
            await query.edit_message_text('❌ У вас нет доступа к этому проекту.')
            return

        # Получаем информацию о проекте
        project = project_manager.get_project(project_id)

        # Удаляем сообщение с выбором проекта
        await query.message.delete()

        # Временно устанавливаем проект для показа статистики
        # Создаем фейковое update с message вместо callback_query
        from telegram import Message, Chat
        fake_message = Message(
            message_id=0,
            date=query.message.date,
            chat=query.message.chat,
            from_user=user
        )
        from telegram import Update as TgUpdate
        fake_update = TgUpdate(update_id=0, message=fake_message)
        fake_update._effective_user = user
        fake_update._effective_chat = query.message.chat

        # Сохраняем текущий проект пользователя
        old_project_id = project_manager.get_user_current_project(user_id)

        # Временно устанавливаем проект для статистики
        project_manager.set_user_current_project(user_id, project_id)

        # Показываем статистику
        await my_stats(fake_update, context)

        # Восстанавливаем предыдущий проект (если был)
        if old_project_id:
            project_manager.set_user_current_project(user_id, old_project_id)

        return

    # Обработка выбора проекта (доступна всем пользователям)
    if action.startswith("select_project_"):
        project_id = action.replace("select_project_", "")
        user_id = str(user.id)

        # Проверяем, что пользователь в этом проекте
        user_projects = project_manager.get_user_projects(user_id)
        if not any(p['id'] == project_id for p in user_projects):
            await query.edit_message_text('❌ У вас нет доступа к этому проекту.')
            return

        # Проверяем, не выбран ли уже этот проект
        current_project_id = project_manager.get_user_current_project(user_id)
        if current_project_id == project_id:
            # Если уже выбран этот проект - просто показываем меню проекта
            project = project_manager.get_project(project_id)

            # Получаем статистику пользователя по текущему проекту
            telegram_user = f"@{user.username}" if user.username else user.first_name
            user_total_views = 0

            if sheets_db:
                try:
                    # Фильтруем профили по имени проекта
                    profiles = sheets_db.get_user_profiles(telegram_user, project_name=project["name"])
                    for profile in profiles:
                        views = int(profile.get("total_views", 0) or 0)
                        user_total_views += views
                except:
                    pass

            # Удаляем старое сообщение
            await query.message.delete()

            # Отправляем меню проекта
            is_admin = user.id in ADMIN_IDS
            keyboard = get_project_keyboard(is_admin)

            message_text = f'📂 Проект: *{project["name"]}*\n\n'
            message_text += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
            message_text += f'🌍 Гео: {project.get("geo", "Не указано")}\n'
            message_text += f'📅 {project["start_date"]} — {project["end_date"]}\n'

            if user_total_views > 0:
                message_text += f'\n👁 Ваши просмотры: {format_number(user_total_views, full=True)}\n'

            message_text += f'\nИспользуйте кнопки ниже для работы с проектом'

            await context.bot.send_message(
                chat_id=user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return

        # Устанавливаем текущий проект
        success = project_manager.set_user_current_project(user_id, project_id)

        if success:
            project = project_manager.get_project(project_id)

            # Получаем статистику пользователя по выбранному проекту
            telegram_user = f"@{user.username}" if user.username else user.first_name
            user_total_views = 0

            if sheets_db:
                try:
                    # Фильтруем профили по имени проекта
                    profiles = sheets_db.get_user_profiles(telegram_user, project_name=project["name"])
                    for profile in profiles:
                        views = int(profile.get("total_views", 0) or 0)
                        user_total_views += views
                except:
                    pass

            # Удаляем старое сообщение
            await query.message.delete()

            # Отправляем новое сообщение с клавиатурой проекта
            is_admin = user.id in ADMIN_IDS
            keyboard = get_project_keyboard(is_admin)

            message_text = f'✅ Выбран проект: *{project["name"]}*\n\n'
            message_text += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
            message_text += f'🌍 Гео: {project.get("geo", "Не указано")}\n'
            message_text += f'📅 {project["start_date"]} — {project["end_date"]}\n'

            if user_total_views > 0:
                message_text += f'\n👁 Ваши просмотры: {format_number(user_total_views, full=True)}\n'

            message_text += f'\nИспользуйте кнопки ниже для работы с проектом'

            await context.bot.send_message(
                chat_id=user.id,
                text=message_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await query.edit_message_text('❌ Ошибка при выборе проекта.')
        return

    # Обработка меню проекта (доступна всем пользователям)
    if action.startswith("project_menu_"):
        menu_action = action.replace("project_menu_", "")
        user_id = str(user.id)
        current_project_id = project_manager.get_user_current_project(user_id)

        if not current_project_id:
            await query.edit_message_text('❌ Сначала выберите проект через /my_projects')
            return

        if menu_action == "change":
            # Показать список проектов для смены
            projects = project_manager.get_user_projects(user_id)

            if not projects:
                await query.edit_message_text('📂 У вас нет других проектов.')
                return

            message = '📂 *Выберите проект:*\n\n'
            keyboard = []

            for i, project in enumerate(projects, 1):
                message += f'*{i}. {project["name"]}*\n'
                message += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
                if project.get('geo'):
                    message += f'🌍 Гео: {project["geo"]}\n'
                message += f'📅 {project["start_date"]} — {project["end_date"]}\n\n'

                # Добавляем кнопку для каждого проекта
                keyboard.append([
                    InlineKeyboardButton(
                        f"Выбрать: {project['name']}",
                        callback_data=f"select_project_{project['id']}"
                    )
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)
            return

        elif menu_action == "main":
            # Вернуться в главное меню (команда /start)
            await query.message.delete()
            # Вызываем функцию start через создание фейкового update
            from telegram import Update as TgUpdate
            fake_update = TgUpdate(update_id=0, message=query.message)
            await start(fake_update, context)
            return

        elif menu_action == "add":
            # Добавить аккаунт
            user_mode[user.id] = "add_profile"
            await query.edit_message_text(
                '➕ *Добавление профиля в проект*\n\n'
                'Отправьте ссылку на профиль TikTok, Instagram, Facebook или YouTube',
                parse_mode="Markdown"
            )
            return

        elif menu_action == "stats":
            # Показать статистику проекта
            await query.edit_message_text('⏳ Загружаю статистику...')
            # TODO: Реализовать показ статистики по проекту
            await query.edit_message_text('📊 Статистика проекта (в разработке)')
            return

        elif menu_action == "profiles":
            # Показать профили проекта
            await query.edit_message_text('⏳ Загружаю профили...')
            # TODO: Реализовать показ профилей проекта
            await query.edit_message_text('👤 Мои профили в проекте (в разработке)')
            return

        elif menu_action == "download":
            # Скачать видео
            await query.edit_message_text(
                '📥 *Скачивание видео*\n\n'
                'Отправьте ссылку на видео из TikTok, Instagram, Facebook или YouTube',
                parse_mode="Markdown"
            )
            return

        return

    # Проверка доступа для админских функций
    if user.id not in ADMIN_IDS:
        await query.edit_message_text('❌ Нет доступа.')
        return

    if not action.startswith("admin_") and not action.startswith("project_"):
        return
    
    if action == "admin_update":
        # Показываем выбор платформы
        keyboard = [
            [InlineKeyboardButton("🎵 TikTok", callback_data="admin_update_tiktok")],
            [InlineKeyboardButton("📷 Instagram", callback_data="admin_update_instagram")],
            [InlineKeyboardButton("🔄 Обе платформы", callback_data="admin_update_both")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            '🔄 *Обновление статистики*\n\n'
            'Выберите платформу:',
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif action == "admin_update_tiktok":
        # Сохраняем выбор платформы в context.user_data
        context.user_data['update_platform'] = 'tiktok'
        await query.edit_message_text(
            '🎵 *Обновление TikTok*\n\n'
            '📊 Введите минимальное количество просмотров для учёта видео:\n'
            '(например: 30000)\n\n'
            'Видео с просмотрами меньше этого значения не будут учитываться в статистике.',
            parse_mode="Markdown"
        )
    
    elif action == "admin_update_instagram":
        # Сохраняем выбор платформы в context.user_data
        context.user_data['update_platform'] = 'instagram'
        await query.edit_message_text(
            '📷 *Обновление Instagram*\n\n'
            '📊 Введите минимальное количество просмотров для учёта reels:\n'
            '(например: 30000)\n\n'
            'Reels с просмотрами меньше этого значения не будут учитываться в статистике.',
            parse_mode="Markdown"
        )
    
    elif action == "admin_update_both":
        # Сохраняем выбор платформы в context.user_data
        context.user_data['update_platform'] = 'both'
        await query.edit_message_text(
            '🔄 *Обновление обеих платформ*\n\n'
            '📊 Введите минимальное количество просмотров для учёта видео/reels:\n'
            '(например: 30000)\n\n'
            'Видео/Reels с просмотрами меньше этого значения не будут учитываться в статистике.',
            parse_mode="Markdown"
        )
    
    elif action == "admin_broadcast":
        await query.edit_message_text('📨 Начинаю рассылку статистики...')
        try:
            if not sheets_db:
                await query.edit_message_text('❌ Google Sheets не подключен!')
                return
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT DISTINCT user_id, username, first_name FROM users WHERE is_active = 1")
            users = cursor.fetchall()
            
            sent_count = 0
            error_count = 0
            
            for user_row in users:
                try:
                    user_id = user_row[0]
                    username = user_row[1]
                    first_name = user_row[2]
                    
                    telegram_user = f"@{username}" if username else first_name
                    profiles = sheets_db.get_user_profiles(telegram_user)
                    
                    if not profiles:
                        continue
                    
                    # Подготавливаем данные для snapshot
                    current_data = {
                        "tiktok": [],
                        "instagram": [],
                        "facebook": [],
                        "youtube": []
                    }
                    
                    # Группируем по платформам
                    tiktok_profiles = [p for p in profiles if p.get("platform") == "tiktok"]
                    instagram_profiles = [p for p in profiles if p.get("platform") == "instagram"]
                    facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
                    youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]
                    
                    # Заполняем current_data для расчета прироста
                    for p in tiktok_profiles:
                        current_data["tiktok"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    for p in instagram_profiles:
                        current_data["instagram"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    for p in facebook_profiles:
                        current_data["facebook"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    for p in youtube_profiles:
                        current_data["youtube"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    
                    # Получаем прирост на основе предыдущего snapshot
                    daily_growth = db.calculate_growth_from_snapshot(user_id, current_data)
                    
                    # Сохраняем новый snapshot
                    db.save_stats_snapshot(user_id, current_data)
                    
                    # Формируем сообщение (аналогично my_stats)
                    message = f'📊 *Ваша статистика*\n\n'
                    
                    total_followers = 0
                    total_videos = 0
                    total_views = 0
                    
                    if tiktok_profiles:
                        message += '🎵 *TIKTOK:*\n\n'
                        for i, profile in enumerate(tiktok_profiles, 1):
                            try:
                                followers = int(profile.get("followers", 0) or 0)
                                videos = int(profile.get("videos", 0) or 0)
                                views = int(profile.get("total_views", 0) or 0)
                                status = profile.get("status", "NEW")
                                
                                total_followers += followers
                                total_videos += videos
                                total_views += views
                                
                                username_tiktok = parse_tiktok_username(profile["url"])
                                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                                
                                message += f'*{i}. @{username_tiktok}* {status_emoji}\n'
                                message += f'👥 Подписчиков: {format_number(followers)}\n'
                                message += f'🎬 Видео: {videos}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                                
                                # ПРИРОСТ для конкретного профиля
                                if daily_growth:
                                    views_growth = daily_growth.get(profile["url"], 0)
                                    if views_growth != 0:
                                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                                
                                message += '\n'
                            except:
                                continue
                    
                    if instagram_profiles:
                        message += '📷 *INSTAGRAM:*\n\n'
                        for i, profile in enumerate(instagram_profiles, 1):
                            try:
                                followers = int(profile.get("followers", 0) or 0)
                                reels = int(profile.get("videos", 0) or 0)
                                views = int(profile.get("total_views", 0) or 0)
                                likes = int(profile.get("likes", 0) or 0)
                                comments = int(profile.get("following", 0) or 0)
                                status = profile.get("status", "NEW")
                                
                                total_followers += followers
                                total_videos += reels
                                total_views += views
                                
                                username_ig = parse_instagram_username(profile["url"])
                                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                                
                                message += f'*{i}. @{username_ig}* {status_emoji}\n'
                                message += f'👥 Подписчиков: {format_number(followers)}\n'
                                message += f'🎬 Reels: {reels}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                                message += f'❤️ Лайков: {format_number(likes)}\n'
                                message += f'💬 Комментариев: {comments}\n'
                                
                                # ПРИРОСТ для конкретного профиля
                                if daily_growth:
                                    views_growth = daily_growth.get(profile["url"], 0)
                                    if views_growth != 0:
                                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                                
                                message += '\n'
                            except:
                                continue
                    
                    # Facebook
                    facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
                    if facebook_profiles:
                        message += '👤 *FACEBOOK:*\n\n'
                        for i, profile in enumerate(facebook_profiles, 1):
                            try:
                                followers = int(profile.get("followers", 0) or 0)
                                posts = int(profile.get("videos", 0) or 0)
                                views = int(profile.get("total_views", 0) or 0)
                                status = profile.get("status", "NEW")
                                
                                total_followers += followers
                                total_videos += posts
                                total_views += views
                                
                                username_fb = profile["url"].split("/")[-2] if "/" in profile["url"] else profile["url"].split("/")[-1]
                                username_fb = username_fb.replace("https:", "").replace("www.facebook.com", "").strip("/")
                                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                                
                                message += f'*{i}. {username_fb}* {status_emoji}\n'
                                message += f'👥 Подписчиков: {format_number(followers)}\n'
                                message += f'📝 Посты: {posts}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                                
                                # ПРИРОСТ для конкретного профиля
                                if daily_growth:
                                    views_growth = daily_growth.get(profile["url"], 0)
                                    if views_growth != 0:
                                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                                
                                message += '\n'
                            except:
                                continue
                        
                        message += '\n'
                    
                    # YouTube
                    youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]
                    if youtube_profiles:
                        message += '🎬 *YOUTUBE:*\n\n'
                        for i, profile in enumerate(youtube_profiles, 1):
                            try:
                                followers = int(profile.get("followers", 0) or 0)
                                videos = int(profile.get("videos", 0) or 0)
                                views = int(profile.get("total_views", 0) or 0)
                                status = profile.get("status", "NEW")
                                
                                total_followers += followers
                                total_videos += videos
                                total_views += views
                                
                                if "@" in profile["url"]:
                                    channel_name = profile["url"].split("@")[-1].split("/")[0]
                                    display_name = f"@{channel_name}"
                                else:
                                    channel_name = profile["url"].split("/")[-1]
                                    display_name = channel_name
                                
                                status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")
                                
                                message += f'*{i}. {display_name}* {status_emoji}\n'
                                message += f'👥 Подписчиков: {format_number(followers)}\n'
                                message += f'🎬 Видео: {videos}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                                
                                # ПРИРОСТ для конкретного профиля
                                if daily_growth:
                                    views_growth = daily_growth.get(profile["url"], 0)
                                    if views_growth != 0:
                                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'
                                
                                message += '\n'
                            except:
                                continue
                        
                        message += '\n'
                    
                    # ОБЩИЙ ПРИРОСТ
                    total_views_growth = 0
                    if daily_growth:
                        total_views_growth = sum(daily_growth.values())
                    
                    message += f'━━━━━━━━━━━━━━━\n'
                    message += f'*📈 ИТОГО:*\n'
                    message += f'👥 Всего подписчиков: {format_number(total_followers)}\n'
                    message += f'🎬 Контента: {total_videos}\n'
                    
                    # Добавляем новую строку для прироста (всегда)
                    growth_line = format_growth_line(total_views_growth, label="Прирост")
                    message += f'{growth_line}\n'
                    
                    message += f'👁 Всего просмотров: {format_number(total_views, full=True)}'
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode="Markdown"
                    )
                    
                    sent_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                    error_count += 1
            
            await query.edit_message_text(
                f'✅ *Рассылка завершена!*\n\n'
                f'📨 Отправлено: {sent_count}\n'
                f'❌ Ошибок: {error_count}',
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Ошибка рассылки: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f'❌ Ошибка: {str(e)}')
    
    elif action == "admin_stats":
        # Показываем выбор: общая статистика или по проектам
        projects = project_manager.get_all_projects(active_only=True)

        keyboard = [
            [InlineKeyboardButton("📊 Общая статистика", callback_data="stats_overall")]
        ]

        if projects:
            keyboard.append([InlineKeyboardButton("📁 Статистика по проектам", callback_data="stats_projects")])

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            '📊 *Статистика*\n\n'
            'Выберите тип статистики:',
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    elif action == "stats_overall":
        try:
            if not sheets_db:
                await query.edit_message_text('❌ Google Sheets не подключен!')
                return

            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
            users_count = cursor.fetchone()[0]

            summary = sheets_db.get_summary_stats()
            
            if summary:
                # Удаляем старое сообщение
                await query.message.delete()
                
                # Первое сообщение (TikTok + Instagram)
                message1 = f'📊 *Общая статистика системы*\n\n👥 Пользователей: {users_count}\n\n'
                message1 += (
                    f'🎵 *TikTok:*\n'
                    f'  📱 Профилей: {summary["tiktok"]["total"]}\n'
                    f'  🆕 NEW: {summary["tiktok"]["new"]}\n'
                    f'  📦 OLD: {summary["tiktok"]["old"]}\n'
                    f'  🚫 BAN: {summary["tiktok"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["tiktok"]["followers"])}\n'
                    f'  🎬 Видео: {summary["tiktok"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["tiktok"]["views"], full=True)}\n\n'
                )
                message1 += (
                    f'📷 *Instagram:*\n'
                    f'  📱 Профилей: {summary["instagram"]["total"]}\n'
                    f'  🆕 NEW: {summary["instagram"]["new"]}\n'
                    f'  📦 OLD: {summary["instagram"]["old"]}\n'
                    f'  🚫 BAN: {summary["instagram"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["instagram"]["followers"])}\n'
                    f'  🎬 Reels: {summary["instagram"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["instagram"]["views"], full=True)}'
                )
                
                # Второе сообщение (Facebook + YouTube + Итого)
                message2 = (
                    f'👤 *Facebook:*\n'
                    f'  📱 Профилей: {summary["facebook"]["total"]}\n'
                    f'  🆕 NEW: {summary["facebook"]["new"]}\n'
                    f'  📦 OLD: {summary["facebook"]["old"]}\n'
                    f'  🚫 BAN: {summary["facebook"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["facebook"]["followers"])}\n'
                    f'  📝 Посты: {summary["facebook"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["facebook"]["views"], full=True)}\n\n'
                )
                message2 += (
                    f'🎬 *YouTube:*\n'
                    f'  📱 Профилей: {summary["youtube"]["total"]}\n'
                    f'  🆕 NEW: {summary["youtube"]["new"]}\n'
                    f'  📦 OLD: {summary["youtube"]["old"]}\n'
                    f'  🚫 BAN: {summary["youtube"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["youtube"]["followers"])}\n'
                    f'  🎬 Видео: {summary["youtube"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["youtube"]["views"], full=True)}\n\n'
                )
                
                total_profiles = (summary["tiktok"]["total"] + summary["instagram"]["total"] + 
                                summary["facebook"]["total"] + summary["youtube"]["total"])
                total_followers = (summary["tiktok"]["followers"] + summary["instagram"]["followers"] + 
                                 summary["facebook"]["followers"] + summary["youtube"]["followers"])
                total_content = (summary["tiktok"]["videos"] + summary["instagram"]["videos"] + 
                               summary["facebook"]["videos"] + summary["youtube"]["videos"])
                total_views = (summary["tiktok"]["views"] + summary["instagram"]["views"] + 
                             summary["facebook"]["views"] + summary["youtube"]["views"])
                
                # Подготавливаем данные для расчета прироста
                platforms_stats = {
                    "tiktok": {"total_views": summary["tiktok"]["views"]},
                    "instagram": {"total_views": summary["instagram"]["views"]},
                    "facebook": {"total_views": summary["facebook"]["views"]},
                    "youtube": {"total_views": summary["youtube"]["views"]}
                }
                
                # Рассчитываем прирост на основе глобального snapshot
                daily_growth = db.calculate_global_growth(platforms_stats)
                
                # Сохраняем новый глобальный snapshot
                db.save_global_stats_snapshot(platforms_stats)
                
                # Общий прирост для итогового блока
                total_views_growth = 0
                if daily_growth:
                    total_views_growth = sum(daily_growth.get(p, {}).get("views", 0) for p in platforms_stats.keys())
                
                message2 += (
                    f'━━━━━━━━━━━━━━━\n'
                    f'📈 *ИТОГО:*\n'
                    f'📱 Всего профилей: {total_profiles}\n'
                    f'👥 Всего подписчиков: {format_number(total_followers)}\n'
                    f'🎬 Контента: {total_content}\n'
                )
                
                # Добавляем новую строку для общего прироста (всегда)
                growth_line = format_growth_line(total_views_growth, label="Общий прирост")
                message2 += f'{growth_line}\n'
                
                message2 += f'👁 Всего просмотров: {format_number(total_views, full=True)}'
                
                # Отправляем оба сообщения
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message1,
                    parse_mode="Markdown"
                )
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message2,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text('📊 Нет данных для статистики.')
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f'❌ Ошибка: {str(e)}')

    elif action == "stats_projects":
        # Показываем список проектов для выбора статистики
        projects = project_manager.get_all_projects(active_only=True)

        if not projects:
            await query.edit_message_text(
                '📁 Нет активных проектов.',
                parse_mode="Markdown"
            )
            return

        message = '📁 *Выберите проект для просмотра статистики:*\n\n'
        keyboard = []

        for i, project in enumerate(projects, 1):
            message += f'*{i}. {project["name"]}*\n'
            message += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
            if project.get('geo'):
                message += f'🌍 Гео: {project["geo"]}\n'
            message += f'📅 {project["start_date"]} — {project["end_date"]}\n\n'

            keyboard.append([
                InlineKeyboardButton(
                    f"📊 {project['name']}",
                    callback_data=f"stats_project_{project['id']}"
                )
            ])

        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_stats")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    elif action.startswith("stats_project_"):
        # Показываем статистику по конкретному проекту
        project_id = action.replace("stats_project_", "")
        project = project_manager.get_project(project_id)

        if not project:
            await query.edit_message_text('❌ Проект не найден')
            return

        try:
            if not sheets_db:
                await query.edit_message_text('❌ Google Sheets не подключен!')
                return

            # Получаем участников проекта
            project_users = project_manager.get_project_users(project_id)
            users_count = len(project_users)

            # Получаем статистику по проекту
            summary = sheets_db.get_summary_stats(project_name=project["name"])

            if summary:
                # Удаляем старое сообщение
                await query.message.delete()

                # Первое сообщение (заголовок + TikTok + Instagram)
                message1 = f'📊 *Статистика проекта: {project["name"]}*\n\n'
                message1 += f'👥 Участников: {users_count}\n'
                message1 += f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
                message1 += f'📅 {project["start_date"]} — {project["end_date"]}\n\n'

                message1 += (
                    f'🎵 *TikTok:*\n'
                    f'  📱 Профилей: {summary["tiktok"]["total"]}\n'
                    f'  🆕 NEW: {summary["tiktok"]["new"]}\n'
                    f'  📦 OLD: {summary["tiktok"]["old"]}\n'
                    f'  🚫 BAN: {summary["tiktok"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["tiktok"]["followers"])}\n'
                    f'  🎬 Видео: {summary["tiktok"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["tiktok"]["views"], full=True)}\n\n'
                )
                message1 += (
                    f'📷 *Instagram:*\n'
                    f'  📱 Профилей: {summary["instagram"]["total"]}\n'
                    f'  🆕 NEW: {summary["instagram"]["new"]}\n'
                    f'  📦 OLD: {summary["instagram"]["old"]}\n'
                    f'  🚫 BAN: {summary["instagram"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["instagram"]["followers"])}\n'
                    f'  🎬 Reels: {summary["instagram"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["instagram"]["views"], full=True)}'
                )

                # Второе сообщение (Facebook + YouTube + Итого)
                message2 = (
                    f'👤 *Facebook:*\n'
                    f'  📱 Профилей: {summary["facebook"]["total"]}\n'
                    f'  🆕 NEW: {summary["facebook"]["new"]}\n'
                    f'  📦 OLD: {summary["facebook"]["old"]}\n'
                    f'  🚫 BAN: {summary["facebook"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["facebook"]["followers"])}\n'
                    f'  📝 Посты: {summary["facebook"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["facebook"]["views"], full=True)}\n\n'
                )
                message2 += (
                    f'🎬 *YouTube:*\n'
                    f'  📱 Профилей: {summary["youtube"]["total"]}\n'
                    f'  🆕 NEW: {summary["youtube"]["new"]}\n'
                    f'  📦 OLD: {summary["youtube"]["old"]}\n'
                    f'  🚫 BAN: {summary["youtube"]["ban"]}\n'
                    f'  👥 Подписчиков: {format_number(summary["youtube"]["followers"])}\n'
                    f'  🎬 Видео: {summary["youtube"]["videos"]}\n'
                    f'  👁 Просмотров: {format_number(summary["youtube"]["views"], full=True)}\n\n'
                )

                total_profiles = (summary["tiktok"]["total"] + summary["instagram"]["total"] +
                                summary["facebook"]["total"] + summary["youtube"]["total"])
                total_followers = (summary["tiktok"]["followers"] + summary["instagram"]["followers"] +
                                 summary["facebook"]["followers"] + summary["youtube"]["followers"])
                total_content = (summary["tiktok"]["videos"] + summary["instagram"]["videos"] +
                               summary["facebook"]["videos"] + summary["youtube"]["videos"])
                total_views = (summary["tiktok"]["views"] + summary["instagram"]["views"] +
                             summary["facebook"]["views"] + summary["youtube"]["views"])

                message2 += (
                    f'━━━━━━━━━━━━━━━\n'
                    f'📈 *ИТОГО:*\n'
                    f'📱 Всего профилей: {total_profiles}\n'
                    f'👥 Всего подписчиков: {format_number(total_followers)}\n'
                    f'🎬 Контента: {total_content}\n'
                    f'👁 Всего просмотров: {format_number(total_views, full=True)}\n\n'
                )

                # Прогресс выполнения цели
                target = project["target_views"]
                if target > 0:
                    progress_percent = (total_views / target) * 100
                    message2 += f'🎯 *Прогресс цели:* {progress_percent:.1f}%\n'
                    message2 += f'   {format_number(total_views, full=True)} / {format_number(target, full=True)}'

                # Отправляем оба сообщения
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message1,
                    parse_mode="Markdown"
                )
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message2,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(f'📊 Нет данных для проекта *{project["name"]}*.', parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Ошибка получения статистики проекта: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f'❌ Ошибка: {str(e)}')

    elif action == "admin_users":
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT user_id, username, first_name, created_at 
                FROM users 
                WHERE is_active = 1 
                ORDER BY created_at DESC
            """)
            users = cursor.fetchall()
            
            if not users:
                await query.edit_message_text('👥 Пользователей пока нет.')
                return
            
            message = f'👥 *Список пользователей* ({len(users)})\n\n'
            
            for i, user_row in enumerate(users, 1):
                user_id = user_row[0]
                username = user_row[1]
                first_name = user_row[2]
                
                # Экранируем специальные символы Markdown для никнеймов
                if username:
                    # Заменяем _ на \_ чтобы Markdown не интерпретировал как курсив
                    escaped_username = username.replace('_', '\\_')
                    display_name = f"@{escaped_username}"
                else:
                    display_name = first_name
                
                message += f'{i}. {display_name}\n'
            
            await query.edit_message_text(message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Ошибка получения пользователей: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f'❌ Ошибка: {str(e)}')

    elif action == "admin_projects":
        # Показываем список проектов
        projects = project_manager.get_all_projects(active_only=True)

        if not projects:
            keyboard = [
                [InlineKeyboardButton("➕ Создать проект", callback_data="project_create")],
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                '📁 *Управление проектами*\n\n'
                'Проектов пока нет.\nСоздайте первый проект!',
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            message = '📁 *Список проектов:*\n\n'
            keyboard = []

            for project in projects:
                # Получаем количество пользователей
                users_count = len(project_manager.get_project_users(project['id']))
                message += f"📌 *{project['name']}*\n"
                message += f"  📅 {project['start_date']} — {project['end_date']}\n"
                message += f"  🎯 Цель: {format_number(project['target_views'])} просмотров\n"
                message += f"  👥 Участников: {users_count}\n\n"

                keyboard.append([InlineKeyboardButton(
                    f"📂 {project['name']}",
                    callback_data=f"project_view_{project['id']}"
                )])

            keyboard.append([InlineKeyboardButton("➕ Создать проект", callback_data="project_create")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_back")])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

    elif action.startswith("project_view_"):
        # Показываем детали проекта
        project_id = action.replace("project_view_", "")
        project = project_manager.get_project(project_id)

        if not project:
            await query.edit_message_text('❌ Проект не найден')
            return

        users = project_manager.get_project_users(project_id)

        message = f"📂 *{project['name']}*\n\n"
        message += f"📊 *Таблица:* {project['google_sheet_name']}\n"
        message += f"📅 *Срок:* {project['start_date']} — {project['end_date']}\n"
        message += f"🎯 *Цель:* {format_number(project['target_views'])} просмотров\n\n"
        message += f"👥 *Участники ({len(users)}):*\n"

        if users:
            for user in users:
                username = f"@{user['username']}" if user['username'] else user['first_name']
                message += f"  • {username}\n"
        else:
            message += "  _Участников нет_\n"

        keyboard = [
            [InlineKeyboardButton("➕ Добавить участника", callback_data=f"project_adduser_{project_id}")],
            [InlineKeyboardButton("➖ Удалить участника", callback_data=f"project_removeuser_{project_id}")],
            [InlineKeyboardButton("🔄 Обновить статистику", callback_data=f"project_update_{project_id}")],
            [InlineKeyboardButton("📨 Разослать статистику", callback_data=f"project_broadcast_{project_id}")],
            [InlineKeyboardButton("🗑 Деактивировать проект", callback_data=f"project_deactivate_{project_id}")],
            [InlineKeyboardButton("◀️ К списку проектов", callback_data="admin_projects")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    elif action.startswith("project_removeuser_"):
        project_id = action.replace("project_removeuser_", "")
        # Экранируем дефисы в project_id для MarkdownV2
        escaped_id = project_id.replace('-', '\\-')
        await query.edit_message_text(
            '➖ *Удаление участника*\n\n'
            f'Используйте команду /remove\\_user {escaped_id} @username для удаления пользователя из проекта\\.',
            parse_mode="MarkdownV2"
        )

    elif action.startswith("project_deactivate_"):
        project_id = action.replace("project_deactivate_", "")
        project = project_manager.get_project(project_id)

        if project_manager.deactivate_project(project_id):
            await query.edit_message_text(
                f'✅ Проект *{project["name"]}* деактивирован.',
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text('❌ Ошибка деактивации проекта')

    elif action.startswith("project_update_"):
        # Обновление статистики по проекту
        project_id = action.replace("project_update_", "")
        project = project_manager.get_project(project_id)

        if not project:
            await query.edit_message_text('❌ Проект не найден')
            return

        # Сохраняем project_id в context для обработки выбора платформы
        context.user_data['project_id_for_update'] = project_id

        # Показываем меню выбора платформы
        keyboard = [
            [InlineKeyboardButton("🎵 TikTok", callback_data=f"project_update_tiktok_{project_id}")],
            [InlineKeyboardButton("📷 Instagram", callback_data=f"project_update_instagram_{project_id}")],
            [InlineKeyboardButton("🔄 Обе платформы", callback_data=f"project_update_both_{project_id}")],
            [InlineKeyboardButton("◀️ Назад", callback_data=f"admin_project_view_{project_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f'🔄 *Обновление статистики проекта*\n\n'
            f'📂 Проект: *{project["name"]}*\n\n'
            f'Выберите платформу для обновления:',
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    elif action.startswith("project_update_tiktok_"):
        project_id = action.replace("project_update_tiktok_", "")
        context.user_data['update_platform'] = 'tiktok'
        context.user_data['project_id_for_update'] = project_id
        await query.edit_message_text(
            '🎵 *Обновление TikTok*\n\n'
            '📊 Введите минимальное количество просмотров для учёта видео:\n'
            '(например: 30000)\n\n'
            'Видео с просмотрами меньше этого значения не будут учитываться в статистике.',
            parse_mode="Markdown"
        )
        return

    elif action.startswith("project_update_instagram_"):
        project_id = action.replace("project_update_instagram_", "")
        context.user_data['update_platform'] = 'instagram'
        context.user_data['project_id_for_update'] = project_id
        await query.edit_message_text(
            '📷 *Обновление Instagram*\n\n'
            '📊 Введите минимальное количество просмотров для учёта reels:\n'
            '(например: 30000)\n\n'
            'Reels с просмотрами меньше этого значения не будут учитываться в статистике.',
            parse_mode="Markdown"
        )
        return

    elif action.startswith("project_update_both_"):
        project_id = action.replace("project_update_both_", "")
        context.user_data['update_platform'] = 'both'
        context.user_data['project_id_for_update'] = project_id
        await query.edit_message_text(
            '🔄 *Обновление обеих платформ*\n\n'
            '📊 Введите минимальное количество просмотров для учёта видео/reels:\n'
            '(например: 30000)\n\n'
            'Видео/Reels с просмотрами меньше этого значения не будут учитываться в статистике.',
            parse_mode="Markdown"
        )
        return

    elif action.startswith("project_broadcast_"):
        # Рассылка статистики по проекту
        project_id = action.replace("project_broadcast_", "")
        project = project_manager.get_project(project_id)

        if not project:
            await query.edit_message_text('❌ Проект не найден')
            return

        await query.edit_message_text(f'📨 Начинаю рассылку статистики по проекту *{project["name"]}*...', parse_mode="Markdown")

        try:
            if not sheets_db:
                await query.edit_message_text('❌ Google Sheets не подключен!')
                return

            # Получаем всех участников проекта
            project_users = project_manager.get_project_users(project_id)

            if not project_users:
                await query.edit_message_text(f'⚠️ В проекте *{project["name"]}* нет участников', parse_mode="Markdown")
                return

            sent_count = 0
            error_count = 0
            skipped_count = 0

            for project_user in project_users:
                try:
                    user_id = project_user['user_id']
                    username = project_user['username']
                    first_name = project_user['first_name']

                    telegram_user = f"@{username}" if username else first_name

                    # Получаем профили пользователя только для этого проекта
                    profiles = sheets_db.get_user_profiles(telegram_user, project_name=project["name"])

                    if not profiles:
                        skipped_count += 1
                        continue

                    # Подготавливаем данные для snapshot
                    current_data = {
                        "tiktok": [],
                        "instagram": [],
                        "facebook": [],
                        "youtube": []
                    }

                    # Группируем по платформам
                    tiktok_profiles = [p for p in profiles if p.get("platform") == "tiktok"]
                    instagram_profiles = [p for p in profiles if p.get("platform") == "instagram"]
                    facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
                    youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]

                    # Заполняем current_data для расчета прироста
                    for p in tiktok_profiles:
                        current_data["tiktok"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    for p in instagram_profiles:
                        current_data["instagram"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    for p in facebook_profiles:
                        current_data["facebook"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
                    for p in youtube_profiles:
                        current_data["youtube"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})

                    # Получаем прирост на основе предыдущего snapshot
                    daily_growth = db.calculate_growth_from_snapshot(user_id, current_data)

                    # Сохраняем новый snapshot
                    db.save_stats_snapshot(user_id, current_data)

                    message = f'📊 *Статистика по проекту: {project["name"]}*\n\n'

                    total_views = 0

                    # TikTok профили
                    if tiktok_profiles:
                        message += '🎵 *TikTok*\n'
                        for i, profile in enumerate(tiktok_profiles, 1):
                            try:
                                views = int(profile.get("total_views", 0) or 0)
                                total_views += views

                                username_str = parse_tiktok_username(profile["url"])
                                status_emoji = "🆕" if profile.get("status") == "NEW" else ("📦" if profile.get("status") == "OLD" else "🚫")

                                escaped_username = username_str.replace('_', '\\_')
                                message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n'

                                if daily_growth:
                                    views_growth = daily_growth.get(profile["url"], 0)
                                    if views_growth != 0:
                                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'

                                message += '\n'
                            except:
                                continue

                        message += '\n'

                    # Instagram профили
                    if instagram_profiles:
                        message += '📷 *Instagram*\n'
                        for i, profile in enumerate(instagram_profiles, 1):
                            try:
                                views = int(profile.get("total_views", 0) or 0)
                                total_views += views

                                username_str = parse_instagram_username(profile["url"])
                                status_emoji = "🆕" if profile.get("status") == "NEW" else ("📦" if profile.get("status") == "OLD" else "🚫")

                                escaped_username = username_str.replace('_', '\\_')
                                message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n'

                                if daily_growth:
                                    views_growth = daily_growth.get(profile["url"], 0)
                                    if views_growth != 0:
                                        message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'

                                message += '\n'
                            except:
                                continue

                        message += '\n'

                    # Facebook профили
                    if facebook_profiles:
                        message += '📘 *Facebook*\n'
                        for i, profile in enumerate(facebook_profiles, 1):
                            try:
                                views = int(profile.get("total_views", 0) or 0)
                                total_views += views

                                message += f'{i}\\. {profile["username"]}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n\n'
                            except:
                                continue

                        message += '\n'

                    # YouTube профили
                    if youtube_profiles:
                        message += '🎥 *YouTube*\n'
                        for i, profile in enumerate(youtube_profiles, 1):
                            try:
                                views = int(profile.get("total_views", 0) or 0)
                                total_views += views

                                message += f'{i}\\. {profile["username"]}\n'
                                message += f'👁 Просмотров: {format_number(views, full=True)}\n\n'
                            except:
                                continue

                        message += '\n'

                    message += f'━━━━━━━━━━━━━━━\n'
                    message += f'*📈 ИТОГО:*\n'
                    message += f'👁 Всего просмотров: {format_number(total_views, full=True)}\n'

                    # Отправляем сообщение
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode="MarkdownV2"
                    )
                    sent_count += 1

                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
                    error_count += 1

            # Отправляем результат админу
            result_message = (
                f'✅ *Рассылка по проекту {project["name"]} завершена!*\n\n'
                f'📨 Отправлено: {sent_count}\n'
                f'⏭ Пропущено (нет профилей): {skipped_count}\n'
                f'❌ Ошибок: {error_count}'
            )

            await query.edit_message_text(result_message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Ошибка рассылки по проекту: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.edit_message_text(f'❌ Ошибка рассылки: {str(e)}')

    elif action == "admin_back":
        # Возврат в главное меню админ панели
        keyboard = [
            [InlineKeyboardButton("📁 Управление проектами", callback_data="admin_projects")],
            [InlineKeyboardButton("🔄 Обновить статистику", callback_data="admin_update")],
            [InlineKeyboardButton("📨 Разослать статистику", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📊 Общая статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            '👑 *Панель администратора*\n\n'
            'Выберите действие:',
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def admin_update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /update для обновления TikTok и Instagram"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return
    
    msg = await update.message.reply_text('🔄 Начинаю обновление статистики...')

    try:
        if not sheets_db:
            await msg.edit_text('❌ Google Sheets не подключен!')
            return

        # Используем асинхронную версию обновления
        result = await sheets_db.update_all_profiles_async(tiktok_api, instagram_api)

        message = (
            f'✅ *Обновление завершено!*\n\n'
            f'🎵 TikTok:\n'
            f'  📊 Обновлено (NEW): {result["tiktok"]["updated"]}\n'
            f'  ⭐ Пропущено (OLD): {result["tiktok"]["skipped"]}\n'
            f'  ❌ Ошибок: {result["tiktok"]["errors"]}\n\n'
            f'📷 Instagram:\n'
            f'  📊 Обновлено (NEW): {result["instagram"]["updated"]}\n'
            f'  ⭐ Пропущено (OLD): {result["instagram"]["skipped"]}\n'
            f'  ❌ Ошибок: {result["instagram"]["errors"]}\n\n'
            f'💡 Используй /update_tiktok или /update_instagram для раздельного обновления'
        )

        await msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
        await msg.edit_text(f'❌ Ошибка: {str(e)}')

async def admin_update_tiktok_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /update_tiktok для обновления только TikTok"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return
    
    msg = await update.message.reply_text('🔄 Обновляю TikTok профили...')

    try:
        if not sheets_db:
            await msg.edit_text('❌ Google Sheets не подключен!')
            return

        # Используем асинхронную версию обновления
        result = await sheets_db.update_all_profiles_async(tiktok_api, None)

        message = (
            f'✅ *TikTok обновлён!*\n\n'
            f'📊 Обновлено (NEW): {result["tiktok"]["updated"]}\n'
            f'⭐ Пропущено (OLD): {result["tiktok"]["skipped"]}\n'
            f'❌ Ошибок: {result["tiktok"]["errors"]}'
        )

        await msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка обновления TikTok: {e}")
        await msg.edit_text(f'❌ Ошибка: {str(e)}')

async def admin_update_instagram_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /update_instagram для обновления только Instagram"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return
    
    msg = await update.message.reply_text('🔄 Обновляю Instagram профили...')

    try:
        if not sheets_db:
            await msg.edit_text('❌ Google Sheets не подключен!')
            return

        # Используем асинхронную версию обновления
        result = await sheets_db.update_all_profiles_async(None, instagram_api)

        message = (
            f'✅ *Instagram обновлён!*\n\n'
            f'📊 Обновлено (NEW): {result["instagram"]["updated"]}\n'
            f'⭐ Пропущено (OLD/BAN): {result["instagram"]["skipped"]}\n'
            f'❌ Ошибок: {result["instagram"]["errors"]}'
        )

        await msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка обновления Instagram: {e}")
        await msg.edit_text(f'❌ Ошибка: {str(e)}')

async def send_stats_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str,
                             first_name: str, db, sheets_db, semaphore: asyncio.Semaphore):
    """Асинхронная отправка статистики одному пользователю"""
    async with semaphore:
        try:
            telegram_user = f"@{username}" if username else first_name
            profiles = sheets_db.get_user_profiles(telegram_user)

            if not profiles:
                return False

            # Подготавливаем данные для snapshot
            current_data = {
                "tiktok": [],
                "instagram": [],
                "facebook": [],
                "youtube": []
            }

            # Группируем по платформам
            tiktok_profiles = [p for p in profiles if p.get("platform") == "tiktok"]
            instagram_profiles = [p for p in profiles if p.get("platform") == "instagram"]
            facebook_profiles = [p for p in profiles if p.get("platform") == "facebook"]
            youtube_profiles = [p for p in profiles if p.get("platform") == "youtube"]

            # Заполняем current_data для расчета прироста
            for p in tiktok_profiles:
                current_data["tiktok"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
            for p in instagram_profiles:
                current_data["instagram"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
            for p in facebook_profiles:
                current_data["facebook"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})
            for p in youtube_profiles:
                current_data["youtube"].append({"url": p["url"], "views": int(p.get("total_views", 0) or 0)})

            # Получаем прирост на основе предыдущего snapshot
            daily_growth = db.calculate_growth_from_snapshot(user_id, current_data)

            # Сохраняем новый snapshot
            db.save_stats_snapshot(user_id, current_data)

            # Формируем сообщение
            message = f'📊 *Ваша статистика*\n\n'

            total_followers = 0
            total_videos = 0
            total_views = 0

            if tiktok_profiles:
                message += '🎵 *TikTok*\n'
                for i, profile in enumerate(tiktok_profiles, 1):
                    try:
                        followers = int(profile.get("followers", 0) or 0)
                        videos = int(profile.get("videos", 0) or 0)
                        views = int(profile.get("total_views", 0) or 0)
                        likes = int(profile.get("likes", 0) or 0)
                        comments = int(profile.get("comments", 0) or 0)
                        status = profile.get("status", "NEW")

                        total_followers += followers
                        total_videos += videos
                        total_views += views

                        username_tiktok = parse_tiktok_username(profile["url"])
                        status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")

                        escaped_username = username_tiktok.replace('_', '\\_')
                        message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                        message += f'👥 Подписчиков: {format_number(followers)}\n'
                        message += f'🎬 Видео: {videos}\n'
                        message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                        message += f'❤️ Лайков: {format_number(likes)}\n'
                        message += f'💬 Комментариев: {comments}\n'

                        # ПРИРОСТ для конкретного профиля
                        if daily_growth:
                            views_growth = daily_growth.get(profile["url"], 0)
                            if views_growth != 0:
                                message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'

                        message += '\n'
                    except:
                        continue

            if instagram_profiles:
                message += '📷 *Instagram*\n'
                for i, profile in enumerate(instagram_profiles, 1):
                    try:
                        followers = int(profile.get("followers", 0) or 0)
                        reels = int(profile.get("videos", 0) or 0)
                        views = int(profile.get("total_views", 0) or 0)
                        likes = int(profile.get("likes", 0) or 0)
                        comments = int(profile.get("following", 0) or 0)
                        status = profile.get("status", "NEW")

                        total_followers += followers
                        total_videos += reels
                        total_views += views

                        username_ig = parse_instagram_username(profile["url"])
                        status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")

                        escaped_username = username_ig.replace('_', '\\_')
                        message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                        message += f'👥 Подписчиков: {format_number(followers)}\n'
                        message += f'🎬 Reels: {reels}\n'
                        message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                        message += f'❤️ Лайков: {format_number(likes)}\n'
                        message += f'💬 Комментариев: {comments}\n'

                        # ПРИРОСТ для конкретного профиля
                        if daily_growth:
                            views_growth = daily_growth.get(profile["url"], 0)
                            if views_growth != 0:
                                message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'

                        message += '\n'
                    except:
                        continue

            if facebook_profiles:
                message += '👤 *Facebook*\n'
                for i, profile in enumerate(facebook_profiles, 1):
                    try:
                        followers = int(profile.get("followers", 0) or 0)
                        posts = int(profile.get("videos", 0) or 0)
                        views = int(profile.get("total_views", 0) or 0)
                        likes = int(profile.get("likes", 0) or 0)
                        status = profile.get("status", "NEW")

                        total_followers += followers
                        total_videos += posts
                        total_views += views

                        username_fb = parse_facebook_username(profile["url"])
                        status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")

                        escaped_username = username_fb.replace('_', '\\_')
                        message += f'{i}\\. @{escaped_username} {status_emoji}\n'
                        message += f'👥 Подписчиков: {format_number(followers)}\n'
                        message += f'📝 Посты: {posts}\n'
                        message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                        message += f'❤️ Лайков: {format_number(likes)}\n'

                        # ПРИРОСТ для конкретного профиля
                        if daily_growth:
                            views_growth = daily_growth.get(profile["url"], 0)
                            if views_growth != 0:
                                message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'

                        message += '\n'
                    except:
                        continue

            if youtube_profiles:
                message += '🎬 *YouTube*\n'
                for i, profile in enumerate(youtube_profiles, 1):
                    try:
                        followers = int(profile.get("followers", 0) or 0)
                        videos = int(profile.get("videos", 0) or 0)
                        views = int(profile.get("total_views", 0) or 0)
                        likes = int(profile.get("likes", 0) or 0)
                        status = profile.get("status", "NEW")

                        total_followers += followers
                        total_videos += videos
                        total_views += views

                        display_name = parse_youtube_username(profile["url"])
                        status_emoji = "🆕" if status == "NEW" else ("📦" if status == "OLD" else "🚫")

                        escaped_username = display_name.replace('_', '\\_')
                        message += f'{i}\\. {escaped_username} {status_emoji}\n'
                        message += f'👥 Подписчиков: {format_number(followers)}\n'
                        message += f'🎬 Видео: {videos}\n'
                        message += f'👁 Просмотров: {format_number(views, full=True)}\n'
                        message += f'❤️ Лайков: {format_number(likes)}\n'

                        # ПРИРОСТ для конкретного профиля
                        if daily_growth:
                            views_growth = daily_growth.get(profile["url"], 0)
                            if views_growth != 0:
                                message += f'📈 Прирост: {format_growth_compact(views_growth)}\n'

                        message += '\n'
                    except:
                        continue

            # ОБЩИЙ ПРИРОСТ
            total_views_growth = 0
            if daily_growth:
                total_views_growth = sum(daily_growth.values())

            message += f'━━━━━━━━━━━━━━━\n'
            message += f'📈 *ИТОГО:*\n'
            message += f'👥 Всего подписчиков: {format_number(total_followers)}\n'
            message += f'🎬 Контента: {total_videos}\n'

            # Добавляем новую строку для прироста (всегда)
            growth_line = format_growth_line(total_views_growth, label="Прирост")
            message += f'{growth_line}\n'

            message += f'👁 Всего просмотров: {format_number(total_views, full=True)}'

            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown"
            )

            return True

        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            return False

async def broadcast_stats_async(context: ContextTypes.DEFAULT_TYPE, msg_id: int, chat_id: int,
                                db, sheets_db):
    """Асинхронная фоновая рассылка статистики всем пользователям"""
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT DISTINCT user_id, username, first_name FROM users WHERE is_active = 1")
        users = cursor.fetchall()

        # Ограничиваем количество одновременных задач до 10
        semaphore = asyncio.Semaphore(10)

        tasks = []
        for user_row in users:
            user_id = user_row[0]
            username = user_row[1]
            first_name = user_row[2]

            task = asyncio.create_task(
                send_stats_to_user(context, user_id, username, first_name, db, sheets_db, semaphore)
            )
            tasks.append(task)

        # Ждем завершения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Подсчитываем результаты
        sent_count = sum(1 for r in results if r is True)
        error_count = len(results) - sent_count

        # Обновляем исходное сообщение с результатами
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=(
                f'✅ *Рассылка завершена!*\n\n'
                f'📨 Отправлено: {sent_count}\n'
                f'❌ Ошибок: {error_count}'
            ),
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка фоновой рассылки: {e}")
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f'❌ Ошибка рассылки: {str(e)}'
            )
        except:
            pass

async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /broadcast для рассылки статистики С ПРИРОСТОМ"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return
    
    msg = await update.message.reply_text('📨 Начинаю рассылку статистики...')
    
    try:
        if not sheets_db:
            await msg.edit_text('❌ Google Sheets не подключен!')
            return

        # Запускаем рассылку в фоновом режиме
        asyncio.create_task(
            broadcast_stats_async(context, msg.message_id, update.effective_chat.id, db, sheets_db)
        )

        # Сразу возвращаем управление, чтобы бот мог обрабатывать другие запросы
        await msg.edit_text(
            '📨 *Рассылка запущена в фоновом режиме*\n\n'
            'Вы получите уведомление о завершении.\n'
            'Бот продолжает работать в обычном режиме.',
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка запуска рассылки: {e}")
        await msg.edit_text(f'❌ Ошибка: {str(e)}')
async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /stats для общей статистики по всем платформам с приростом"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return
    
    try:
        # Получаем количество пользователей
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        users_count = cursor.fetchone()[0]
        
        # Получаем общую статистику
        summary_data = db.get_analytics_summary()
        
        if not summary_data:
            await update.message.reply_text('📊 Нет данных для статистики.')
            return
        
        # Группируем статистику по платформам
        platforms_stats = {
            "tiktok": {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "views": 0, "videos": 0, "total_views": 0},
            "instagram": {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "views": 0, "videos": 0, "total_views": 0},
            "facebook": {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "views": 0, "videos": 0, "total_views": 0},
            "youtube": {"total": 0, "new": 0, "old": 0, "ban": 0, "followers": 0, "views": 0, "videos": 0, "total_views": 0}
        }
        
        for item in summary_data:
            platform = item.get("platform", "tiktok")
            if platform in platforms_stats:
                platforms_stats[platform]["total"] += 1
                
                stats = item["stats"]
                platforms_stats[platform]["followers"] += stats.get("followers", 0)
                views = stats.get("views", 0) + stats.get("total_views", 0)
                platforms_stats[platform]["views"] += views
                platforms_stats[platform]["total_views"] += views  # Для snapshot
                platforms_stats[platform]["videos"] += stats.get("videos", 0) + stats.get("reels", 0)
                
                # Подсчитываем статусы
                followers = stats.get("followers", 0)
                if followers < 10000:
                    platforms_stats[platform]["new"] += 1
                elif followers > 100000:
                    platforms_stats[platform]["old"] += 1
        
        # Рассчитываем прирост на основе глобального snapshot
        daily_growth = db.calculate_global_growth(platforms_stats)
        logger.info(f"DEBUG: daily_growth = {daily_growth}")
        
        # Сохраняем новый глобальный snapshot
        db.save_global_stats_snapshot(platforms_stats)
        
        # Общий прирост для итогового блока
        total_views_growth = 0
        if daily_growth:
            total_views_growth = sum(daily_growth.get(p, {}).get("views", 0) for p in platforms_stats.keys())
        logger.info(f"DEBUG: total_views_growth = {total_views_growth}")
        
        # Формируем сообщение 1 (TikTok + Instagram)
        message1 = f'📊 *Общая статистика системы*\n\n👥 Пользователей: {users_count}\n\n'
        
        # TikTok
        tiktok = platforms_stats["tiktok"]
        
        message1 += '🎵 *TikTok:*\n'
        message1 += f'  📱 Профилей: {tiktok["total"]}\n'
        message1 += f'  🆕 NEW: {tiktok["new"]}\n'
        message1 += f'  📦 OLD: {tiktok["old"]}\n'
        message1 += f'  🚫 BAN: {tiktok["ban"]}\n'
        message1 += f'  👥 Подписчиков: {format_number(tiktok["followers"])}\n'
        message1 += f'  🎬 Видео: {tiktok["videos"]}\n'
        message1 += f'  👁 Просмотров: {format_number(tiktok["views"], full=True)}\n'
        
        # Добавляем прирост ТОЛЬКО если он не равен 0
        if daily_growth:
            tiktok_growth = daily_growth.get("tiktok", {})
            views_growth = tiktok_growth.get("views", 0)
            if views_growth != 0:
                message1 += f'  📈 Прирост {format_growth_compact(views_growth)}\n'
        
        message1 += '\n'
        
        # Instagram
        instagram = platforms_stats["instagram"]
        
        message1 += '📷 *Instagram:*\n'
        message1 += f'  📱 Профилей: {instagram["total"]}\n'
        message1 += f'  🆕 NEW: {instagram["new"]}\n'
        message1 += f'  📦 OLD: {instagram["old"]}\n'
        message1 += f'  🚫 BAN: {instagram["ban"]}\n'
        message1 += f'  👥 Подписчиков: {format_number(instagram["followers"])}\n'
        message1 += f'  🎬 Reels: {instagram["videos"]}\n'
        message1 += f'  👁 Просмотров: {format_number(instagram["views"], full=True)}\n'
        
        # Добавляем прирост ТОЛЬКО если он не равен 0
        if daily_growth:
            instagram_growth = daily_growth.get("instagram", {})
            views_growth = instagram_growth.get("views", 0)
            if views_growth != 0:
                message1 += f'  📈 Прирост {format_growth_compact(views_growth)}'
        
        # Формируем сообщение 2 (Facebook + YouTube + Итого)
        message2 = ''
        
        # Facebook
        facebook = platforms_stats["facebook"]
        
        message2 += '👤 *Facebook:*\n'
        message2 += f'  📱 Профилей: {facebook["total"]}\n'
        message2 += f'  🆕 NEW: {facebook["new"]}\n'
        message2 += f'  📦 OLD: {facebook["old"]}\n'
        message2 += f'  🚫 BAN: {facebook["ban"]}\n'
        message2 += f'  👥 Подписчиков: {format_number(facebook["followers"])}\n'
        message2 += f'  📝 Посты: {facebook["videos"]}\n'
        message2 += f'  👁 Просмотров: {format_number(facebook["views"], full=True)}\n'
        
        # Добавляем прирост ТОЛЬКО если он не равен 0
        if daily_growth:
            facebook_growth = daily_growth.get("facebook", {})
            views_growth = facebook_growth.get("views", 0)
            if views_growth != 0:
                message2 += f'  📈 Прирост {format_growth_compact(views_growth)}\n'
        
        message2 += '\n'
        
        # YouTube
        youtube = platforms_stats["youtube"]
        
        message2 += '🎬 *YouTube:*\n'
        message2 += f'  📱 Профилей: {youtube["total"]}\n'
        message2 += f'  🆕 NEW: {youtube["new"]}\n'
        message2 += f'  📦 OLD: {youtube["old"]}\n'
        message2 += f'  🚫 BAN: {youtube["ban"]}\n'
        message2 += f'  👥 Подписчиков: {format_number(youtube["followers"])}\n'
        message2 += f'  🎬 Видео: {youtube["videos"]}\n'
        message2 += f'  👁 Просмотров: {format_number(youtube["views"], full=True)}\n'
        
        # Добавляем прирост ТОЛЬКО если он не равен 0
        if daily_growth:
            youtube_growth = daily_growth.get("youtube", {})
            views_growth = youtube_growth.get("views", 0)
            if views_growth != 0:
                message2 += f'  📈 Прирост {format_growth_compact(views_growth)}\n'
        
        message2 += '\n'
        
        # Итоговая статистика
        total_profiles = sum(p["total"] for p in platforms_stats.values())
        total_followers = sum(p["followers"] for p in platforms_stats.values())
        total_content = sum(p["videos"] for p in platforms_stats.values())
        total_views = sum(p["views"] for p in platforms_stats.values())
        
        message2 += (
            f'━━━━━━━━━━━━━━━\n'
            f'📈 *ИТОГО:*\n'
            f'📱 Всего профилей: {total_profiles}\n'
            f'👥 Всего подписчиков: {format_number(total_followers)}\n'
            f'🎬 Контента: {total_content}\n'
        )
        
        # Добавляем новую строку для общего прироста (всегда)
        growth_line = format_growth_line(total_views_growth, label="Общий прирост")
        logger.info(f"DEBUG: growth_line = {repr(growth_line)}")
        message2 += f'{growth_line}\n'
        
        message2 += f'👁 Всего просмотров: {format_number(total_views, full=True)}'
        
        logger.info(f"DEBUG: message2 итоговый блок:\n{message2}")
        
        # Отправляем оба сообщения
        await update.message.reply_text(message1, parse_mode="Markdown")
        await update.message.reply_text(message2, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')

# ============ CONVERSATION HANDLER ДЛЯ СОЗДАНИЯ ПРОЕКТА ============
# Состояния разговора
PROJECT_NAME, PROJECT_SHEET, PROJECT_START, PROJECT_END, PROJECT_TARGET, PROJECT_GEO = range(6)

async def create_project_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания проекта (может быть из callback или команды)"""
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        message = update.message or update.callback_query.message
        await message.reply_text('❌ У вас нет доступа к этой команде.')
        return ConversationHandler.END

    # Если это callback_query, редактируем сообщение
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            '✨ *Создание нового проекта*\n\n'
            'Шаг 1/6: Введите название проекта:',
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            '✨ *Создание нового проекта*\n\n'
            'Шаг 1/6: Введите название проекта:',
            parse_mode="Markdown"
        )

    return PROJECT_NAME

async def project_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получено название проекта"""
    context.user_data['project_name'] = update.message.text

    await update.message.reply_text(
        f'✅ Название: *{update.message.text}*\n\n'
        'Шаг 2/6: Введите точное название Google таблицы:',
        parse_mode="Markdown"
    )

    return PROJECT_SHEET

async def project_sheet_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получено название таблицы"""
    context.user_data['project_sheet'] = update.message.text

    await update.message.reply_text(
        f'✅ Таблица: *{update.message.text}*\n\n'
        'Шаг 3/6: Введите дату начала проекта (формат: YYYY-MM-DD):\n'
        'Например: 2025-01-01',
        parse_mode="Markdown"
    )

    return PROJECT_START

async def project_start_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получена дата начала"""
    start_date = update.message.text

    # Валидация формата даты
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', start_date):
        await update.message.reply_text(
            '❌ Неверный формат даты. Используйте YYYY-MM-DD\n'
            'Например: 2025-01-01'
        )
        return PROJECT_START

    context.user_data['project_start'] = start_date

    await update.message.reply_text(
        f'✅ Дата начала: *{start_date}*\n\n'
        'Шаг 4/6: Введите дату окончания проекта (формат: YYYY-MM-DD):\n'
        'Например: 2025-12-31',
        parse_mode="Markdown"
    )

    return PROJECT_END

async def project_end_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получена дата окончания"""
    end_date = update.message.text

    # Валидация формата даты
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', end_date):
        await update.message.reply_text(
            '❌ Неверный формат даты. Используйте YYYY-MM-DD\n'
            'Например: 2025-12-31'
        )
        return PROJECT_END

    context.user_data['project_end'] = end_date

    await update.message.reply_text(
        f'✅ Дата окончания: *{end_date}*\n\n'
        'Шаг 5/6: Введите целевое количество просмотров:\n'
        'Например: 1000000',
        parse_mode="Markdown"
    )

    return PROJECT_TARGET

async def project_target_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получена цель по просмотрам"""
    try:
        target_views = int(update.message.text)
    except ValueError:
        await update.message.reply_text(
            '❌ Неверный формат числа. Введите целое число:\n'
            'Например: 1000000'
        )
        return PROJECT_TARGET

    context.user_data['project_target'] = target_views

    await update.message.reply_text(
        f'✅ Цель: *{format_number(target_views)}* просмотров\n\n'
        'Шаг 6/6: Введите географию заказа:\n'
        'Например: Украина, Корея, Весь мир',
        parse_mode="Markdown"
    )

    return PROJECT_GEO

async def project_geo_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получена гео - создаем проект"""
    geo = update.message.text.strip()
    context.user_data['project_geo'] = geo

    # Создаем проект
    try:
        project = project_manager.create_project(
            name=context.user_data['project_name'],
            google_sheet_name=context.user_data['project_sheet'],
            start_date=context.user_data['project_start'],
            end_date=context.user_data['project_end'],
            target_views=context.user_data['project_target'],
            geo=geo
        )

        await update.message.reply_text(
            f'✅ *Проект создан успешно!*\n\n'
            f'📁 Название: {project["name"]}\n'
            f'📊 Таблица: {project["google_sheet_name"]}\n'
            f'📅 Период: {project["start_date"]} - {project["end_date"]}\n'
            f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
            f'🌍 Гео: {project["geo"]}\n'
            f'🔑 ID: {project["id"]}\n\n'
            f'Используйте /add\\_user {project["id"]} @username для добавления участников.',
            parse_mode="Markdown"
        )

        # Очищаем данные
        context.user_data.clear()

    except Exception as e:
        logger.error(f"Ошибка создания проекта: {e}")
        await update.message.reply_text(f'❌ Ошибка создания проекта: {str(e)}')

    return ConversationHandler.END

async def project_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена создания проекта"""
    context.user_data.clear()
    await update.message.reply_text(
        '❌ Создание проекта отменено.',
        reply_markup=None
    )
    return ConversationHandler.END

# ============ КОНЕЦ CONVERSATION HANDLER ДЛЯ СОЗДАНИЯ ПРОЕКТА ============

# ============ CONVERSATION HANDLER ДЛЯ ДОБАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯ ============
# Состояние разговора для добавления пользователя
ADD_USER_USERNAME = 0

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало добавления пользователя"""
    query = update.callback_query
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await query.answer("❌ Нет доступа")
        return ConversationHandler.END

    # Извлекаем project_id из callback_data
    project_id = query.data.replace("project_adduser_", "")
    context.user_data['add_user_project_id'] = project_id

    await query.answer()
    await query.edit_message_text(
        '➕ *Добавление участника*\n\n'
        'Введите username пользователя (с @ или без):',
        parse_mode="Markdown"
    )

    return ADD_USER_USERNAME

async def add_user_username_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получен username пользователя"""
    username = update.message.text.strip().lstrip('@')
    project_id = context.user_data.get('add_user_project_id')

    if not project_id:
        await update.message.reply_text('❌ Ошибка: проект не найден')
        return ConversationHandler.END

    # Проверяем существует ли пользователь в базе
    db.cursor.execute('SELECT user_id, first_name FROM users WHERE username = ?', (username,))
    user_row = db.cursor.fetchone()

    if not user_row:
        await update.message.reply_text(
            f'❌ Пользователь @{username} не найден в базе.\n'
            'Пользователь должен сначала запустить бота командой /start'
        )
        context.user_data.clear()
        return ConversationHandler.END

    user_id = user_row[0]
    first_name = user_row[1]

    # Добавляем пользователя в проект
    if project_manager.add_user_to_project(project_id, str(user_id)):
        # Устанавливаем этот проект как текущий для пользователя
        project_manager.set_user_current_project(str(user_id), project_id)

        project = project_manager.get_project(project_id)

        await update.message.reply_text(
            f'✅ Пользователь @{username} ({first_name}) добавлен в проект "{project["name"]}"'
        )

        # Отправляем уведомление пользователю
        try:
            keyboard = [
                [InlineKeyboardButton("➕ Добавить профиль", callback_data="add_profile")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            geo_text = f'🌍 Гео: {project["geo"]}\n' if project.get("geo") else ''

            await context.bot.send_message(
                chat_id=user_id,
                text=f'🎉 Вы добавлены в проект *{project["name"]}*\n\n'
                     f'🎯 Цель: {format_number(project["target_views"])} просмотров\n'
                     f'{geo_text}'
                     f'📅 Период: {project["start_date"]} — {project["end_date"]}',
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
    else:
        await update.message.reply_text(
            f'⚠️ Пользователь @{username} уже в проекте'
        )

    context.user_data.clear()
    return ConversationHandler.END

async def add_user_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена добавления пользователя"""
    context.user_data.clear()
    await update.message.reply_text('❌ Добавление пользователя отменено.')
    return ConversationHandler.END

# ============ КОНЕЦ CONVERSATION HANDLER ДЛЯ ДОБАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯ ============

async def create_project_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /create_project для создания нового проекта"""
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return

    # Формат: /create_project Название | Таблица | 2025-01-01 | 2025-12-31 | 1000000
    if not context.args:
        await update.message.reply_text(
            '❌ Неверный формат команды.\n\n'
            'Используйте:\n'
            '`/create_project НазваниеПроекта | ИмяТаблицы | 2025-01-01 | 2025-12-31 | 1000000`\n\n'
            'Где:\n'
            '• НазваниеПроекта — название проекта\n'
            '• ИмяТаблицы — точное название Google таблицы\n'
            '• Первая дата — дата начала (YYYY-MM-DD)\n'
            '• Вторая дата — дата окончания (YYYY-MM-DD)\n'
            '• Число — целевые просмотры',
            parse_mode="Markdown"
        )
        return

    try:
        # Объединяем все аргументы и разбиваем по разделителю
        full_text = ' '.join(context.args)
        parts = [p.strip() for p in full_text.split('|')]

        if len(parts) != 5:
            raise ValueError("Неверное количество параметров")

        name, google_sheet_name, start_date, end_date, target_views = parts
        target_views = int(target_views)

        # Создаем проект
        project = project_manager.create_project(
            name=name,
            google_sheet_name=google_sheet_name,
            start_date=start_date,
            end_date=end_date,
            target_views=target_views
        )

        await update.message.reply_text(
            f'✅ *Проект создан!*\n\n'
            f'📂 *Название:* {project["name"]}\n'
            f'📊 *Таблица:* {project["google_sheet_name"]}\n'
            f'📅 *Срок:* {project["start_date"]} — {project["end_date"]}\n'
            f'🎯 *Цель:* {format_number(project["target_views"])} просмотров\n\n'
            f'ID проекта: `{project["id"]}`\n\n'
            f'Теперь добавьте участников командой:\n'
            f'`/add_user {project["id"]} @username`',
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Ошибка создания проекта: {e}")
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')


async def add_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /add_user для добавления пользователя в проект"""
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return

    # Формат: /add_user project_id @username
    if len(context.args) < 2:
        await update.message.reply_text(
            '❌ Неверный формат команды.\n\n'
            'Используйте: `/add_user project_id @username`',
            parse_mode="Markdown"
        )
        return

    try:
        project_id = context.args[0]
        username = context.args[1].lstrip('@')

        # Проверяем существование проекта
        project = project_manager.get_project(project_id)
        if not project:
            await update.message.reply_text('❌ Проект не найден')
            return

        # Ищем пользователя в базе по username
        cursor = db.conn.cursor()
        cursor.execute("SELECT user_id, first_name FROM users WHERE username = ?", (username,))
        user_row = cursor.fetchone()

        if not user_row:
            await update.message.reply_text(
                f'❌ Пользователь @{username} не найден в базе данных.\n'
                f'Пользователь должен сначала запустить бота командой /start'
            )
            return

        target_user_id = user_row[0]
        first_name = user_row[1]

        # Добавляем пользователя в проект
        if project_manager.add_user_to_project(project_id, target_user_id):
            # Отправляем уведомление пользователю
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f'✨ *Вы добавлены в проект!*\n\n'
                        f'📂 Проект: *{project["name"]}*\n'
                        f'📅 Срок: {project["start_date"]} — {project["end_date"]}\n'
                        f'🎯 Цель: {format_number(project["target_views"])} просмотров\n\n'
                        f'Используйте /start для начала работы.'
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление пользователю: {e}")

            await update.message.reply_text(
                f'✅ Пользователь @{username} ({first_name}) добавлен в проект *{project["name"]}*',
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f'⚠️ Пользователь уже в проекте')

    except Exception as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')


async def remove_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /remove_user для удаления пользователя из проекта"""
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return

    # Формат: /remove_user project_id @username
    if len(context.args) < 2:
        await update.message.reply_text(
            '❌ Неверный формат команды.\n\n'
            'Используйте: `/remove_user project_id @username`',
            parse_mode="Markdown"
        )
        return

    try:
        project_id = context.args[0]
        username = context.args[1].lstrip('@')

        # Проверяем существование проекта
        project = project_manager.get_project(project_id)
        if not project:
            await update.message.reply_text('❌ Проект не найден')
            return

        # Ищем пользователя в базе по username
        cursor = db.conn.cursor()
        cursor.execute("SELECT user_id, first_name FROM users WHERE username = ?", (username,))
        user_row = cursor.fetchone()

        if not user_row:
            await update.message.reply_text(f'❌ Пользователь @{username} не найден')
            return

        target_user_id = user_row[0]
        first_name = user_row[1]

        # Удаляем пользователя из проекта
        if project_manager.remove_user_from_project(project_id, target_user_id):
            await update.message.reply_text(
                f'✅ Пользователь @{username} ({first_name}) удален из проекта *{project["name"]}*',
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f'⚠️ Пользователь не найден в проекте')

    except Exception as e:
        logger.error(f"Ошибка удаления пользователя: {e}")
        await update.message.reply_text(f'❌ Ошибка: {str(e)}')


async def list_projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /projects для просмотра списка проектов"""
    user = update.effective_user

    if user.id not in ADMIN_IDS:
        await update.message.reply_text('❌ У вас нет доступа к этой команде.')
        return

    projects = project_manager.get_all_projects(active_only=True)

    if not projects:
        await update.message.reply_text('📁 Проектов пока нет.')
        return

    message = '📁 *Список проектов:*\n\n'

    for project in projects:
        users_count = len(project_manager.get_project_users(project['id']))
        message += f"📌 *{project['name']}*\n"
        message += f"  📊 Таблица: {project['google_sheet_name']}\n"
        message += f"  📅 {project['start_date']} — {project['end_date']}\n"
        message += f"  🎯 Цель: {format_number(project['target_views'])} просмотров\n"
        message += f"  👥 Участников: {users_count}\n"
        message += f"  🆔 ID: `{project['id']}`\n\n"

    await update.message.reply_text(message, parse_mode="Markdown")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            '❌ Произошла ошибка при обработке запроса. Попробуйте позже.'
        )

def main() -> None:
    """Запуск бота"""
    # Создаём приложение с новым API
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("mystats", my_stats))
    application.add_handler(CommandHandler("my_projects", my_projects))
    application.add_handler(CommandHandler("links", show_links))
    application.add_handler(CommandHandler("download", download_video_command))
    
    # Админ команды
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("update", admin_update_command))
    application.add_handler(CommandHandler("update_tiktok", admin_update_tiktok_command))
    application.add_handler(CommandHandler("update_instagram", admin_update_instagram_command))
    application.add_handler(CommandHandler("broadcast", admin_broadcast_command))
    application.add_handler(CommandHandler("stats", admin_stats_command))

    # Команды управления проектами
    application.add_handler(CommandHandler("create_project", create_project_command))
    application.add_handler(CommandHandler("add_user", add_user_command))
    application.add_handler(CommandHandler("remove_user", remove_user_command))
    application.add_handler(CommandHandler("projects", list_projects_command))

    # ConversationHandler для создания проектов
    create_project_conv = ConversationHandler(
        entry_points=[
            CommandHandler("new_project", create_project_start),
            CallbackQueryHandler(create_project_start, pattern="^project_create$")
        ],
        states={
            PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_name_received)],
            PROJECT_SHEET: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_sheet_received)],
            PROJECT_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_start_received)],
            PROJECT_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_end_received)],
            PROJECT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_target_received)],
            PROJECT_GEO: [MessageHandler(filters.TEXT & ~filters.COMMAND, project_geo_received)],
        },
        fallbacks=[CommandHandler("cancel", project_cancel)],
        allow_reentry=True
    )
    application.add_handler(create_project_conv)

    # ConversationHandler для добавления пользователей
    add_user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_user_start, pattern="^project_adduser_")
        ],
        states={
            ADD_USER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_username_received)],
        },
        fallbacks=[CommandHandler("cancel", add_user_cancel)],
        allow_reentry=True
    )
    application.add_handler(add_user_conv)

    # Обработчики кнопок - ПОРЯДОК ВАЖЕН! Сначала специфичные паттерны
    application.add_handler(CallbackQueryHandler(profile_status_callback, pattern="^profile_"))
    application.add_handler(CallbackQueryHandler(topic_callback, pattern="^topic_"))
    application.add_handler(CallbackQueryHandler(user_callback, pattern="^quick_"))
    application.add_handler(CallbackQueryHandler(user_callback, pattern="^user_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^add_profile$"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^select_stats_project_"))  # Для просмотра статистики
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^select_project_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^project_menu_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^project_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # Обработчик текстовых сообщений (кнопки и ссылки) - В КОНЦЕ!
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard_buttons))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
