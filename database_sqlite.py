import sqlite3
import json
from datetime import datetime, timedelta
import logging
import uuid
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class SQLiteDatabase:
    """Класс для работы с SQLite в качестве базы данных"""
    
    def __init__(self, db_file="tiktok_analytics.db"):
        """
        Инициализация подключения к SQLite
        
        :param db_file: Путь к файлу базы данных
        """
        try:
            # Проверяем, существует ли файл базы данных
            db_exists = os.path.exists(db_file)
            
            # Создаем подключение
            self.conn = sqlite3.connect(db_file)
            self.conn.row_factory = sqlite3.Row  # Для получения результатов в виде словарей
            self.cursor = self.conn.cursor()
            
            # Если база данных новая, создаем структуру
            if not db_exists:
                self._create_tables()
            else:
                # Если база существует, проверяем и добавляем новые таблицы
                self._migrate_database()
            
            logger.info(f"Подключено к базе данных SQLite: {db_file}")
            
        except Exception as e:
            logger.error(f"Ошибка подключения к SQLite: {e}")
            raise
    
    def _migrate_database(self):
        """Миграция базы данных - добавление новых таблиц"""
        try:
            # Проверяем наличие таблицы stats_snapshots
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='stats_snapshots'"
            )

            if not self.cursor.fetchone():
                logger.info("Создаю таблицу stats_snapshots...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats_snapshots (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    profile_url TEXT NOT NULL,
                    total_views INTEGER DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                ''')

                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_snapshots_user_platform ON stats_snapshots(user_id, platform)'
                )

                self.conn.commit()
                logger.info("✅ Таблица stats_snapshots создана")

            # Проверяем наличие таблицы projects
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
            )

            if not self.cursor.fetchone():
                logger.info("Создаю таблицу projects...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    google_sheet_name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    target_views INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1
                )
                ''')

                self.conn.commit()
                logger.info("✅ Таблица projects создана")

            # Проверяем наличие таблицы project_users
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='project_users'"
            )

            if not self.cursor.fetchone():
                logger.info("Создаю таблицу project_users...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS project_users (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE(project_id, user_id)
                )
                ''')

                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_project_users ON project_users(project_id, user_id)'
                )

                self.conn.commit()
                logger.info("✅ Таблица project_users создана")

            # Проверяем наличие таблицы user_context
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_context'"
            )

            if not self.cursor.fetchone():
                logger.info("Создаю таблицу user_context...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_context (
                    user_id TEXT PRIMARY KEY,
                    current_project_id TEXT,
                    last_updated TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (current_project_id) REFERENCES projects(id)
                )
                ''')

                self.conn.commit()
                logger.info("✅ Таблица user_context создана")

            # Проверяем наличие поля geo в таблице projects
            self.cursor.execute("PRAGMA table_info(projects)")
            columns = [column[1] for column in self.cursor.fetchall()]

            if 'geo' not in columns:
                logger.info("Добавляю поле geo в таблицу projects...")
                self.cursor.execute('ALTER TABLE projects ADD COLUMN geo TEXT DEFAULT ""')
                self.conn.commit()
                logger.info("✅ Поле geo добавлено в таблицу projects")

        except Exception as e:
            logger.error(f"Ошибка при миграции базы данных: {e}")
            raise
    
    def _create_tables(self):
        """Создание таблиц в базе данных"""
        try:
            # Таблица пользователей
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT,
                is_active BOOLEAN
            )
            ''')
            
            # Таблица ссылок
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS links (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL,
                platform TEXT,
                type TEXT,
                username TEXT,
                video_id TEXT,
                sec_uid TEXT,
                created_at TEXT,
                is_active BOOLEAN,
                last_checked TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            ''')
            
            # Таблица аналитики
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS analytics (
                id TEXT PRIMARY KEY,
                link_id TEXT NOT NULL,
                timestamp TEXT,
                stats TEXT,
                FOREIGN KEY (link_id) REFERENCES links(id)
            )
            ''')
            
            # Таблица использования API
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_usage (
                id TEXT PRIMARY KEY,
                date TEXT UNIQUE,
                total INTEGER DEFAULT 0,
                profile_info INTEGER DEFAULT 0,
                video_info INTEGER DEFAULT 0,
                created_at TEXT
            )
            ''')
            
            # НОВАЯ ТАБЛИЦА: Снимки статистики для расчета прироста
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats_snapshots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                profile_url TEXT NOT NULL,
                total_views INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            ''')
            
            # Создаем индексы для оптимизации
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_user_id ON links(user_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_link_id ON analytics(link_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_timestamp ON analytics(timestamp)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_snapshots_user_platform ON stats_snapshots(user_id, platform)')
            
            self.conn.commit()
            logger.info("Создана структура базы данных SQLite")
            
        except Exception as e:
            logger.error(f"Ошибка при создании таблиц: {e}")
            raise
    
    def _generate_id(self):
        """Генерирует уникальный ID"""
        return str(uuid.uuid4())
    
    def add_user(self, user_id, username, first_name, last_name=None):
        """Добавление нового пользователя"""
        try:
            # Проверяем, существует ли пользователь
            self.cursor.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (str(user_id),)
            )
            existing_user = self.cursor.fetchone()
            
            if existing_user:
                # Преобразуем Row в dict
                return dict(existing_user)
            
            # Создаем нового пользователя
            user = {
                "id": self._generate_id(),
                "user_id": str(user_id),
                "username": username or "",
                "first_name": first_name or "",
                "last_name": last_name or "",
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True
            }
            
            # Добавляем в базу
            self.cursor.execute(
                """
                INSERT INTO users (id, user_id, username, first_name, last_name, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"], 
                    user["user_id"], 
                    user["username"], 
                    user["first_name"], 
                    user["last_name"], 
                    user["created_at"], 
                    user["is_active"]
                )
            )
            self.conn.commit()
            
            return user
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при добавлении пользователя: {e}")
            raise
    
    def add_link(self, user_id, url, link_type, username=None, video_id=None, sec_uid=None):
        """Добавление новой ссылки для отслеживания"""
        try:
            # Проверяем наличие дубликатов
            self.cursor.execute(
                """
                SELECT * FROM links 
                WHERE user_id = ? AND url = ? AND is_active = 1
                """,
                (str(user_id), url)
            )
            existing_link = self.cursor.fetchone()
            
            if existing_link:
                return dict(existing_link)
            
            # Создаем новую запись
            link = {
                "id": self._generate_id(),
                "user_id": str(user_id),
                "url": url,
                "platform": "tiktok",
                "type": link_type,
                "username": username or "",
                "video_id": video_id or "",
                "sec_uid": sec_uid or "",
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True,
                "last_checked": None
            }
            
            # Добавляем в базу
            self.cursor.execute(
                """
                INSERT INTO links (
                    id, user_id, url, platform, type, username, 
                    video_id, sec_uid, created_at, is_active, last_checked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    link["id"],
                    link["user_id"],
                    link["url"],
                    link["platform"],
                    link["type"],
                    link["username"],
                    link["video_id"],
                    link["sec_uid"],
                    link["created_at"],
                    link["is_active"],
                    link["last_checked"]
                )
            )
            self.conn.commit()
            
            return link
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при добавлении ссылки: {e}")
            raise
    
    def get_user_links(self, user_id):
        """Получение всех ссылок пользователя"""
        try:
            self.cursor.execute(
                """
                SELECT * FROM links
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
                """,
                (str(user_id),)
            )
            links = self.cursor.fetchall()
            
            return [dict(link) for link in links]
            
        except Exception as e:
            logger.error(f"Ошибка при получении ссылок: {e}")
            raise
    
    def get_all_active_links(self):
        """Получение всех активных ссылок"""
        try:
            self.cursor.execute(
                """
                SELECT * FROM links
                WHERE is_active = 1
                ORDER BY created_at DESC
                """
            )
            links = self.cursor.fetchall()
            
            return [dict(link) for link in links]
            
        except Exception as e:
            logger.error(f"Ошибка при получении активных ссылок: {e}")
            raise
    
    def delete_link(self, link_id):
        """Удаление (деактивация) ссылки"""
        try:
            self.cursor.execute(
                """
                UPDATE links
                SET is_active = 0
                WHERE id = ?
                """,
                (link_id,)
            )
            self.conn.commit()
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при удалении ссылки: {e}")
            raise
    
    def save_analytics(self, link_id, stats):
        """Сохранение аналитических данных"""
        try:
            analytics_id = self._generate_id()
            timestamp = datetime.utcnow().isoformat()
            stats_json = json.dumps(stats)
            
            # Сохраняем запись аналитики
            self.cursor.execute(
                """
                INSERT INTO analytics (id, link_id, timestamp, stats)
                VALUES (?, ?, ?, ?)
                """,
                (analytics_id, link_id, timestamp, stats_json)
            )
            
            # Обновляем время последней проверки для ссылки
            self.cursor.execute(
                """
                UPDATE links
                SET last_checked = ?
                WHERE id = ?
                """,
                (timestamp, link_id)
            )
            
            self.conn.commit()
            
            return {
                "id": analytics_id,
                "link_id": link_id,
                "timestamp": timestamp,
                "stats": stats
            }
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при сохранении аналитики: {e}")
            raise
    
    def get_analytics_for_link(self, link_id, limit=10):
        """Получение последних аналитических данных для ссылки"""
        try:
            self.cursor.execute(
                """
                SELECT id, link_id, timestamp, stats FROM analytics
                WHERE link_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (link_id, limit)
            )
            analytics = self.cursor.fetchall()
            
            result = []
            for entry in analytics:
                entry_dict = dict(entry)
                # Преобразуем JSON строку обратно в словарь
                entry_dict["stats"] = json.loads(entry_dict["stats"])
                # Преобразуем timestamp в объект datetime
                entry_dict["timestamp"] = datetime.fromisoformat(entry_dict["timestamp"])
                result.append(entry_dict)
                
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении аналитики: {e}")
            raise
    
    def get_analytics_summary(self, user_id=None):
        """Получение сводной аналитики"""
        try:
            if user_id:
                # Получаем все ссылки пользователя
                self.cursor.execute(
                    """
                    SELECT id FROM links
                    WHERE user_id = ? AND is_active = 1
                    """,
                    (str(user_id),)
                )
                links = self.cursor.fetchall()
                link_ids = [link["id"] for link in links]
                
                if not link_ids:
                    return []
                
                # Строим запрос с использованием link_ids
                placeholders = ', '.join(['?' for _ in link_ids])
                query = f"""
                WITH latest_analytics AS (
                    SELECT a.*, 
                           ROW_NUMBER() OVER(PARTITION BY a.link_id ORDER BY a.timestamp DESC) as rn
                    FROM analytics a
                    WHERE a.link_id IN ({placeholders})
                )
                SELECT la.id, la.link_id, la.timestamp, la.stats,
                       l.url, l.type, l.username, l.platform
                FROM latest_analytics la
                JOIN links l ON la.link_id = l.id
                WHERE rn = 1
                """
                self.cursor.execute(query, link_ids)
            else:
                # Получаем последние записи для всех ссылок
                query = """
                WITH latest_analytics AS (
                    SELECT a.*, 
                           ROW_NUMBER() OVER(PARTITION BY a.link_id ORDER BY a.timestamp DESC) as rn
                    FROM analytics a
                )
                SELECT la.id, la.link_id, la.timestamp, la.stats,
                       l.url, l.type, l.username, l.platform
                FROM latest_analytics la
                JOIN links l ON la.link_id = l.id
                WHERE rn = 1 AND l.is_active = 1
                """
                self.cursor.execute(query)
            
            results = self.cursor.fetchall()
            
            summary = []
            for result in results:
                result_dict = dict(result)
                # Преобразуем JSON строку обратно в словарь
                result_dict["stats"] = json.loads(result_dict["stats"])
                summary.append(result_dict)
                
            return summary
            
        except Exception as e:
            logger.error(f"Ошибка при получении сводной аналитики: {e}")
            raise
    
    def get_daily_growth(self, user_id=None):
        """
        Получение ежедневного прироста статистики
        
        Сравнивает последние данные с данными за вчера
        """
        try:
            # Получаем текущее время
            now = datetime.utcnow()
            yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            
            # Формируем запрос для получения текущих и вчерашних данных
            if user_id:
                # Получаем ссылки пользователя
                self.cursor.execute(
                    """
                    SELECT id FROM links
                    WHERE user_id = ? AND is_active = 1
                    """,
                    (str(user_id),)
                )
                links = self.cursor.fetchall()
                link_ids = [link["id"] for link in links]
                
                if not link_ids:
                    return {}
                
                placeholders = ', '.join(['?' for _ in link_ids])
                
                # Запрос для получения последних данных
                current_query = f"""
                WITH latest_analytics AS (
                    SELECT a.*, 
                           ROW_NUMBER() OVER(PARTITION BY a.link_id ORDER BY a.timestamp DESC) as rn
                    FROM analytics a
                    WHERE a.link_id IN ({placeholders})
                )
                SELECT la.link_id, la.stats, l.platform, l.type
                FROM latest_analytics la
                JOIN links l ON la.link_id = l.id
                WHERE rn = 1
                """
                
                # Запрос для получения вчерашних данных
                yesterday_query = f"""
                WITH yesterday_analytics AS (
                    SELECT a.*, 
                           ROW_NUMBER() OVER(PARTITION BY a.link_id ORDER BY a.timestamp DESC) as rn
                    FROM analytics a
                    WHERE a.link_id IN ({placeholders})
                    AND a.timestamp >= ? AND a.timestamp < ?
                )
                SELECT ya.link_id, ya.stats, l.platform, l.type
                FROM yesterday_analytics ya
                JOIN links l ON ya.link_id = l.id
                WHERE rn = 1
                """
                
                self.cursor.execute(current_query, link_ids)
                current_data = self.cursor.fetchall()
                
                self.cursor.execute(yesterday_query, link_ids + [yesterday_start.isoformat(), yesterday_end.isoformat()])
                yesterday_data = self.cursor.fetchall()
            else:
                # Для всех ссылок
                current_query = """
                WITH latest_analytics AS (
                    SELECT a.*, 
                           ROW_NUMBER() OVER(PARTITION BY a.link_id ORDER BY a.timestamp DESC) as rn
                    FROM analytics a
                )
                SELECT la.link_id, la.stats, l.platform, l.type
                FROM latest_analytics la
                JOIN links l ON la.link_id = l.id
                WHERE rn = 1 AND l.is_active = 1
                """
                
                yesterday_query = """
                WITH yesterday_analytics AS (
                    SELECT a.*, 
                           ROW_NUMBER() OVER(PARTITION BY a.link_id ORDER BY a.timestamp DESC) as rn
                    FROM analytics a
                    WHERE a.timestamp >= ? AND a.timestamp < ?
                )
                SELECT ya.link_id, ya.stats, l.platform, l.type
                FROM yesterday_analytics ya
                JOIN links l ON ya.link_id = l.id
                WHERE rn = 1 AND l.is_active = 1
                """
                
                self.cursor.execute(current_query)
                current_data = self.cursor.fetchall()
                
                self.cursor.execute(yesterday_query, (yesterday_start.isoformat(), yesterday_end.isoformat()))
                yesterday_data = self.cursor.fetchall()
            
            # Преобразуем в словари для удобной работы
            current_dict = {}
            for row in current_data:
                row_dict = dict(row)
                row_dict["stats"] = json.loads(row_dict["stats"])
                current_dict[row_dict["link_id"]] = row_dict
            
            yesterday_dict = {}
            for row in yesterday_data:
                row_dict = dict(row)
                row_dict["stats"] = json.loads(row_dict["stats"])
                yesterday_dict[row_dict["link_id"]] = row_dict
            
            # Подсчитываем прирост по платформам
            growth = {
                "tiktok": {"followers": 0, "likes": 0, "views": 0, "videos": 0},
                "instagram": {"followers": 0, "likes": 0, "views": 0, "videos": 0},
                "facebook": {"followers": 0, "likes": 0, "views": 0, "videos": 0},
                "youtube": {"followers": 0, "likes": 0, "views": 0, "videos": 0}
            }
            
            # Сравниваем текущие данные с вчерашними
            for link_id, current in current_dict.items():
                if link_id in yesterday_dict:
                    yesterday = yesterday_dict[link_id]
                    platform = current.get("platform", "tiktok")
                    
                    # Подсчитываем разницу
                    current_stats = current["stats"]
                    yesterday_stats = yesterday["stats"]
                    
                    if platform in growth:
                        growth[platform]["followers"] += (current_stats.get("followers", 0) - yesterday_stats.get("followers", 0))
                        growth[platform]["likes"] += (current_stats.get("likes", 0) - yesterday_stats.get("likes", 0))
                        growth[platform]["views"] += (current_stats.get("views", 0) + current_stats.get("total_views", 0) - 
                                                      yesterday_stats.get("views", 0) - yesterday_stats.get("total_views", 0))
                        growth[platform]["videos"] += (current_stats.get("videos", 0) + current_stats.get("reels", 0) - 
                                                       yesterday_stats.get("videos", 0) - yesterday_stats.get("reels", 0))
            
            return growth
            
        except Exception as e:
            logger.error(f"Ошибка при получении ежедневного прироста: {e}")
            logger.error(f"Traceback: {e}", exc_info=True)
            return {}
    
    def get_growth_stats(self, link_id, days=7):
        """Получение статистики роста за указанный период"""
        analytics = self.get_analytics_for_link(link_id)
        
        if len(analytics) < 2:
            return {
                "not_enough_data": True,
                "message": f"Недостаточно данных для расчета роста за {days} дней"
            }
        
        # Берем первую и последнюю записи для сравнения
        first = analytics[-1]  # Самая старая запись
        last = analytics[0]    # Самая новая запись
        
        # Рассчитываем разницу в зависимости от типа данных
        stats_type = first["stats"].get("type")
        
        if stats_type == "video":
            growth = {
                "views": last["stats"].get("views", 0) - first["stats"].get("views", 0),
                "likes": last["stats"].get("likes", 0) - first["stats"].get("likes", 0),
                "comments": last["stats"].get("comments", 0) - first["stats"].get("comments", 0),
                "shares": last["stats"].get("shares", 0) - first["stats"].get("shares", 0)
            }
        elif stats_type == "profile":
            growth = {
                "followers": last["stats"].get("followers", 0) - first["stats"].get("followers", 0),
                "videos": last["stats"].get("videos", 0) - first["stats"].get("videos", 0),
                "likes": last["stats"].get("likes", 0) - first["stats"].get("likes", 0)
            }
        else:
            growth = {}
        
        return {
            "period_days": days,
            "start_date": first["timestamp"],
            "end_date": last["timestamp"],
            "growth": growth,
            "type": stats_type
        }
    
    def track_api_usage(self, endpoint):
        """Отслеживание использования API"""
        try:
            today = datetime.utcnow().date().isoformat()
            
            # Проверяем, есть ли запись для сегодня
            self.cursor.execute(
                "SELECT * FROM api_usage WHERE date = ?",
                (today,)
            )
            today_record = self.cursor.fetchone()
            
            if today_record:
                # Обновляем существующую запись
                total = today_record["total"] + 1
                endpoint_count = today_record[endpoint] + 1 if endpoint in today_record.keys() else 1
                
                update_query = f"""
                UPDATE api_usage
                SET total = ?, {endpoint} = ?
                WHERE date = ?
                """
                self.cursor.execute(update_query, (total, endpoint_count, today))
            else:
                # Создаем новую запись
                record_id = self._generate_id()
                profile_info = 1 if endpoint == "profile_info" else 0
                video_info = 1 if endpoint == "video_info" else 0
                
                self.cursor.execute(
                    """
                    INSERT INTO api_usage (id, date, total, profile_info, video_info, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id, today, 1, profile_info, video_info, 
                        datetime.utcnow().isoformat()
                    )
                )
            
            self.conn.commit()
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при отслеживании использования API: {e}")
            raise
    
    def get_api_usage_today(self):
        """Получение статистики использования API за сегодня"""
        try:
            today = datetime.utcnow().date().isoformat()
            
            self.cursor.execute(
                "SELECT * FROM api_usage WHERE date = ?",
                (today,)
            )
            record = self.cursor.fetchone()
            
            return dict(record) if record else None
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики API: {e}")
            raise
    
    def save_stats_snapshot(self, user_id, profiles_data):
        """
        Сохраняет снимок текущей статистики пользователя
        
        :param user_id: ID пользователя
        :param profiles_data: Словарь с данными профилей по платформам
                             {"platform": [{"url": ..., "views": ...}, ...]}
        """
        try:
            now = datetime.utcnow().isoformat()
            
            # Удаляем старые снимки пользователя
            self.cursor.execute(
                "DELETE FROM stats_snapshots WHERE user_id = ?",
                (str(user_id),)
            )
            
            # Сохраняем новые снимки
            for platform, profiles in profiles_data.items():
                for profile in profiles:
                    snapshot_id = self._generate_id()
                    self.cursor.execute(
                        """
                        INSERT INTO stats_snapshots (id, user_id, platform, profile_url, total_views, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (snapshot_id, str(user_id), platform, profile["url"], profile["views"], now)
                    )
            
            self.conn.commit()
            logger.info(f"Снимок статистики сохранен для пользователя {user_id}")
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при сохранении снимка статистики: {e}")
            raise
    
    def get_stats_snapshot(self, user_id):
        """
        Получает последний снимок статистики пользователя
        
        :param user_id: ID пользователя
        :return: Словарь с данными предыдущего снимка
        """
        try:
            self.cursor.execute(
                """
                SELECT platform, profile_url, total_views, timestamp
                FROM stats_snapshots
                WHERE user_id = ?
                """,
                (str(user_id),)
            )
            
            results = self.cursor.fetchall()
            
            if not results:
                return None
            
            # Группируем по платформам
            snapshot = {}
            for row in results:
                row_dict = dict(row)
                platform = row_dict["platform"]
                
                if platform not in snapshot:
                    snapshot[platform] = []
                
                snapshot[platform].append({
                    "url": row_dict["profile_url"],
                    "views": row_dict["total_views"],
                    "timestamp": row_dict["timestamp"]
                })
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Ошибка при получении снимка статистики: {e}")
            raise
    
    def calculate_growth_from_snapshot(self, user_id, current_profiles):
        """
        Рассчитывает прирост на основе сравнения текущих данных с последним снимком
        
        :param user_id: ID пользователя
        :param current_profiles: Текущие данные профилей
        :return: Словарь с приростом по URL профилей {url: views_diff}
        """
        try:
            # Получаем предыдущий снимок
            previous_snapshot = self.get_stats_snapshot(user_id)
            
            if not previous_snapshot:
                # Если снимка нет, возвращаем пустой словарь
                return {}
            
            # Рассчитываем прирост по каждому URL
            growth_by_url = {}
            
            for platform, current_profiles_list in current_profiles.items():
                if platform not in previous_snapshot:
                    continue
                
                # Создаем словарь предыдущих данных по URL
                previous_by_url = {p["url"]: p["views"] for p in previous_snapshot[platform]}
                
                # Считаем прирост для каждого профиля
                for profile in current_profiles_list:
                    url = profile["url"]
                    current_views = profile.get("views", 0)
                    previous_views = previous_by_url.get(url, 0)
                    views_diff = current_views - previous_views
                    growth_by_url[url] = views_diff
            
            return growth_by_url
            
        except Exception as e:
            logger.error(f"Ошибка при расчете прироста: {e}")
            return {}
    
    def save_global_stats_snapshot(self, stats_data):
        """
        Сохраняет снимок общей статистики всей системы
        
        :param stats_data: Словарь с данными по платформам
                          {"platform": {"total_views": ...}, ...}
        """
        try:
            now = datetime.utcnow().isoformat()
            
            # Удаляем старые снимки (user_id = "global")
            self.cursor.execute(
                "DELETE FROM stats_snapshots WHERE user_id = ?",
                ("global",)
            )
            
            # Сохраняем новые снимки
            for platform, data in stats_data.items():
                snapshot_id = self._generate_id()
                self.cursor.execute(
                    """
                    INSERT INTO stats_snapshots (id, user_id, platform, profile_url, total_views, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, "global", platform, "system", data.get("total_views", 0), now)
                )
            
            self.conn.commit()
            logger.info(f"Снимок глобальной статистики сохранен")
            
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Ошибка при сохранении глобального снимка: {e}")
            raise
    
    def calculate_global_growth(self, current_stats):
        """
        Рассчитывает прирост общей статистики системы
        
        :param current_stats: Текущие данные по платформам
        :return: Словарь с приростом по платформам
        """
        try:
            # Получаем предыдущий глобальный снимок
            self.cursor.execute(
                """
                SELECT platform, total_views
                FROM stats_snapshots
                WHERE user_id = ?
                """,
                ("global",)
            )
            
            results = self.cursor.fetchall()
            
            if not results:
                # Если снимка нет, возвращаем нулевой прирост
                return {
                    "tiktok": {"views": 0},
                    "instagram": {"views": 0},
                    "facebook": {"views": 0},
                    "youtube": {"views": 0}
                }
            
            # Создаем словарь предыдущих данных
            previous_stats = {}
            for row in results:
                row_dict = dict(row)
                previous_stats[row_dict["platform"]] = row_dict["total_views"]
            
            # Рассчитываем прирост
            growth = {
                "tiktok": {"views": 0},
                "instagram": {"views": 0},
                "facebook": {"views": 0},
                "youtube": {"views": 0}
            }
            
            for platform in ["tiktok", "instagram", "facebook", "youtube"]:
                current_views = current_stats.get(platform, {}).get("total_views", 0)
                previous_views = previous_stats.get(platform, 0)
                growth[platform]["views"] = current_views - previous_views
            
            return growth
            
        except Exception as e:
            logger.error(f"Ошибка при расчете глобального прироста: {e}")
            return {
                "tiktok": {"views": 0},
                "instagram": {"views": 0},
                "facebook": {"views": 0},
                "youtube": {"views": 0}
            }
    
    def get_all_users(self):
        """Получение всех пользователей"""
        try:
            self.cursor.execute(
                "SELECT * FROM users WHERE is_active = 1 ORDER BY created_at DESC"
            )
            users = self.cursor.fetchall()
            
            return [dict(user) for user in users]
            
        except Exception as e:
            logger.error(f"Ошибка при получении пользователей: {e}")
            raise
