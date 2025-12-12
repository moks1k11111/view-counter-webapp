"""
PostgreSQL Database adapter
Полностью совместим с SQLiteDatabase API
"""
import psycopg2
import psycopg2.extras
import json
from datetime import datetime, timedelta
import logging
import uuid
import os
from urllib.parse import urlparse
from db_cursor_wrapper import CursorWrapper

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


class PostgreSQLDatabase:
    """Класс для работы с PostgreSQL"""

    def __init__(self, database_url):
        """
        Инициализация подключения к PostgreSQL

        :param database_url: URL подключения к PostgreSQL
                            (postgresql://user:pass@host:port/dbname)
        """
        self.database_url = database_url
        logger.info(f"🐘 Connecting to PostgreSQL...")

        # Парсим URL для логирования (без пароля)
        parsed = urlparse(database_url)
        safe_url = f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}{parsed.path}"
        logger.info(f"📡 Connection: {safe_url}")

        # Подключаемся к PostgreSQL
        self.conn = psycopg2.connect(database_url)
        self.conn.autocommit = False

        # Используем DictCursor для совместимости с SQLite Row
        real_cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Оборачиваем курсор для автоконвертации ? в %s
        self.cursor = CursorWrapper(real_cursor, is_postgres=True)

        logger.info("✅ Connected to PostgreSQL")

        self._create_tables()
        self._migrate_database()

    def _migrate_database(self):
        """Миграция базы данных - добавление новых таблиц и полей"""
        try:
            # Проверяем наличие таблицы stats_snapshots
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'stats_snapshots'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу stats_snapshots...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS stats_snapshots (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    profile_url TEXT NOT NULL,
                    total_views INTEGER DEFAULT 0,
                    timestamp TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                ''')
                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_snapshots_user_platform ON stats_snapshots(user_id, platform)'
                )
                self.conn.commit()
                logger.info("✅ Таблица stats_snapshots создана")

            # Проверяем наличие таблицы projects
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'projects'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу projects...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    google_sheet_name TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    target_views INTEGER DEFAULT 0,
                    geo TEXT DEFAULT '',
                    kpi_views INTEGER DEFAULT 1000,
                    created_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT true,
                    is_finished BOOLEAN DEFAULT false
                )
                ''')
                self.conn.commit()
                logger.info("✅ Таблица projects создана")

            # Проверяем наличие таблицы project_users
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'project_users'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу project_users...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS project_users (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    added_at TIMESTAMP NOT NULL,
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
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'user_context'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу user_context...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_context (
                    user_id TEXT PRIMARY KEY,
                    current_project_id TEXT,
                    last_updated TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (current_project_id) REFERENCES projects(id)
                )
                ''')
                self.conn.commit()
                logger.info("✅ Таблица user_context создана")

            # Проверяем и добавляем поля в projects если их нет
            self._add_column_if_not_exists('projects', 'geo', 'TEXT DEFAULT \'\'')
            self._add_column_if_not_exists('projects', 'is_finished', 'BOOLEAN DEFAULT false')
            self._add_column_if_not_exists('projects', 'allowed_platforms',
                f"TEXT DEFAULT '{json.dumps({'tiktok': True, 'instagram': True, 'facebook': True, 'youtube': True, 'threads': True})}'")
            self._add_column_if_not_exists('projects', 'last_admin_update', 'TIMESTAMP DEFAULT NULL')

            # Проверяем наличие таблицы project_social_accounts
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'project_social_accounts'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу project_social_accounts...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS project_social_accounts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    username TEXT NOT NULL,
                    profile_link TEXT NOT NULL,
                    status TEXT DEFAULT 'NEW',
                    topic TEXT DEFAULT '',
                    telegram_user TEXT DEFAULT '',
                    added_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT true,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    UNIQUE(project_id, profile_link)
                )
                ''')
                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_social_accounts_project ON project_social_accounts(project_id)'
                )
                self.conn.commit()
                logger.info("✅ Таблица project_social_accounts создана")

            # Добавляем telegram_user если его нет
            self._add_column_if_not_exists('project_social_accounts', 'telegram_user', "TEXT DEFAULT ''")

            # Проверяем наличие таблицы account_snapshots
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'account_snapshots'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу account_snapshots...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    followers INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    videos INTEGER DEFAULT 0,
                    views INTEGER DEFAULT 0,
                    snapshot_time TIMESTAMP NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES project_social_accounts(id)
                )
                ''')
                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_snapshots_account_time ON account_snapshots(account_id, snapshot_time)'
                )
                self.conn.commit()
                logger.info("✅ Таблица account_snapshots создана")

            # Проверяем наличие таблицы account_daily_stats
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'account_daily_stats'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу account_daily_stats...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS account_daily_stats (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    followers_start INTEGER DEFAULT 0,
                    followers_end INTEGER DEFAULT 0,
                    followers_growth INTEGER DEFAULT 0,
                    likes_start INTEGER DEFAULT 0,
                    likes_end INTEGER DEFAULT 0,
                    likes_growth INTEGER DEFAULT 0,
                    comments_start INTEGER DEFAULT 0,
                    comments_end INTEGER DEFAULT 0,
                    comments_growth INTEGER DEFAULT 0,
                    videos_start INTEGER DEFAULT 0,
                    videos_end INTEGER DEFAULT 0,
                    videos_growth INTEGER DEFAULT 0,
                    views_start INTEGER DEFAULT 0,
                    views_end INTEGER DEFAULT 0,
                    views_growth INTEGER DEFAULT 0,
                    FOREIGN KEY (account_id) REFERENCES project_social_accounts(id),
                    UNIQUE(account_id, date)
                )
                ''')
                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_daily_stats_account_date ON account_daily_stats(account_id, date)'
                )
                self.conn.commit()
                logger.info("✅ Таблица account_daily_stats создана")

            # Проверяем наличие таблицы jobs (для фоновых задач)
            self.cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'jobs'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info("Создаю таблицу jobs...")
                self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    project_id TEXT,
                    status TEXT DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    processed INTEGER DEFAULT 0,
                    result TEXT,
                    error TEXT,
                    meta TEXT,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
                ''')
                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_jobs_project_status ON jobs(project_id, status)'
                )
                self.cursor.execute(
                    'CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)'
                )
                self.conn.commit()
                logger.info("✅ Таблица jobs создана")

        except Exception as e:
            logger.error(f"Ошибка при миграции базы данных: {e}")
            self.conn.rollback()
            raise

    def _add_column_if_not_exists(self, table, column, definition):
        """Добавить колонку в таблицу если её нет"""
        try:
            self.cursor.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                )
            """)
            if not self.cursor.fetchone()['exists']:
                logger.info(f"Добавляю поле {column} в таблицу {table}...")
                self.cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                self.conn.commit()
                logger.info(f"✅ Поле {column} добавлено в таблицу {table}")
        except Exception as e:
            logger.error(f"Ошибка при добавлении колонки {column}: {e}")
            self.conn.rollback()

    def _create_tables(self):
        """Создание базовых таблиц в базе данных"""
        try:
            # Таблица пользователей
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP,
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
                created_at TIMESTAMP,
                is_active BOOLEAN,
                last_checked TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            ''')

            # Таблица аналитики
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS analytics (
                id TEXT PRIMARY KEY,
                link_id TEXT NOT NULL,
                timestamp TIMESTAMP,
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
                created_at TIMESTAMP
            )
            ''')

            # Создаем индексы для оптимизации
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_user_id ON links(user_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_link_id ON analytics(link_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_analytics_timestamp ON analytics(timestamp)')

            self.conn.commit()
            logger.info("✅ Создана структура базы данных PostgreSQL")

        except Exception as e:
            logger.error(f"Ошибка при создании таблиц: {e}")
            self.conn.rollback()
            raise

    def _generate_id(self):
        """Генерирует уникальный ID"""
        return str(uuid.uuid4())

    # Все остальные методы идентичны SQLiteDatabase, только self.conn.commit() после изменений
    # Для экономии места приведу только ключевые методы для Jobs API

    def create_job(self, job_type: str, project_id: str = None, meta: dict = None) -> str:
        """Создать новую фоновую задачу"""
        try:
            job_id = str(uuid.uuid4())
            created_at = datetime.now()
            meta_json = json.dumps(meta) if meta else None

            self.cursor.execute('''
                INSERT INTO jobs (id, type, project_id, status, created_at, meta)
                VALUES (%s, %s, %s, 'pending', %s, %s)
            ''', (job_id, job_type, project_id, created_at, meta_json))

            self.conn.commit()
            logger.info(f"✅ Job created: {job_id} ({job_type})")
            return job_id

        except Exception as e:
            logger.error(f"❌ Error creating job: {e}")
            self.conn.rollback()
            raise

    def update_job(self, job_id: str, status: str = None, progress: int = None,
                   processed: int = None, total: int = None, result: dict = None,
                   error: str = None):
        """Обновить статус задачи"""
        try:
            updates = []
            params = []

            if status is not None:
                updates.append("status = %s")
                params.append(status)

                # Автоматически устанавливаем timestamps
                if status == 'running' and not self._job_has_started_at(job_id):
                    updates.append("started_at = %s")
                    params.append(datetime.now())
                elif status in ('completed', 'failed'):
                    updates.append("finished_at = %s")
                    params.append(datetime.now())

            if progress is not None:
                updates.append("progress = %s")
                params.append(progress)

            if processed is not None:
                updates.append("processed = %s")
                params.append(processed)

            if total is not None:
                updates.append("total = %s")
                params.append(total)

            if result is not None:
                updates.append("result = %s")
                params.append(json.dumps(result))

            if error is not None:
                updates.append("error = %s")
                params.append(error)

            if not updates:
                return

            params.append(job_id)
            query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = %s"

            self.cursor.execute(query, params)
            self.conn.commit()

        except Exception as e:
            logger.error(f"❌ Error updating job {job_id}: {e}")
            self.conn.rollback()
            raise

    def _job_has_started_at(self, job_id: str) -> bool:
        """Проверить, установлено ли started_at для job"""
        try:
            self.cursor.execute("SELECT started_at FROM jobs WHERE id = %s", (job_id,))
            row = self.cursor.fetchone()
            return row and row['started_at'] is not None
        except:
            return False

    def get_job(self, job_id: str) -> dict:
        """Получить информацию о задаче"""
        try:
            self.cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            row = self.cursor.fetchone()

            if not row:
                return None

            job = dict(row)

            # Парсим JSON поля
            if job.get('result'):
                try:
                    job['result'] = json.loads(job['result'])
                except:
                    pass

            if job.get('meta'):
                try:
                    job['meta'] = json.loads(job['meta'])
                except:
                    pass

            # Преобразуем datetime в ISO string для совместимости
            for key in ['created_at', 'started_at', 'finished_at']:
                if job.get(key) and isinstance(job[key], datetime):
                    job[key] = job[key].isoformat()

            return job

        except Exception as e:
            logger.error(f"❌ Error getting job {job_id}: {e}")
            raise

    def get_project_jobs(self, project_id: str, limit: int = 10) -> list:
        """Получить задачи проекта"""
        try:
            self.cursor.execute('''
                SELECT * FROM jobs
                WHERE project_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            ''', (project_id, limit))

            rows = self.cursor.fetchall()
            jobs = []

            for row in rows:
                job = dict(row)

                # Парсим JSON поля
                if job.get('result'):
                    try:
                        job['result'] = json.loads(job['result'])
                    except:
                        pass

                if job.get('meta'):
                    try:
                        job['meta'] = json.loads(job['meta'])
                    except:
                        pass

                # Преобразуем datetime в ISO string
                for key in ['created_at', 'started_at', 'finished_at']:
                    if job.get(key) and isinstance(job[key], datetime):
                        job[key] = job[key].isoformat()

                jobs.append(job)

            return jobs

        except Exception as e:
            logger.error(f"❌ Error getting jobs for project {project_id}: {e}")
            raise

    def delete_old_jobs(self, days: int = 7):
        """Удалить старые завершенные задачи"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            self.cursor.execute('''
                DELETE FROM jobs
                WHERE status IN ('completed', 'failed')
                AND finished_at < %s
            ''', (cutoff_date,))

            deleted_count = self.cursor.rowcount
            self.conn.commit()

            logger.info(f"🗑️ Deleted {deleted_count} old jobs (older than {days} days)")
            return deleted_count

        except Exception as e:
            logger.error(f"❌ Error deleting old jobs: {e}")
            self.conn.rollback()
            raise

    def add_user(self, user_id, username, first_name, last_name=None):
        """Добавление нового пользователя"""
        try:
            self.cursor.execute(
                "SELECT * FROM users WHERE user_id = %s",
                (str(user_id),)
            )
            existing_user = self.cursor.fetchone()

            if existing_user:
                return dict(existing_user)

            user = {
                "id": self._generate_id(),
                "user_id": str(user_id),
                "username": username or "",
                "first_name": first_name or "",
                "last_name": last_name or "",
                "created_at": datetime.now().isoformat(),
                "is_active": True
            }

            self.cursor.execute(
                """
                INSERT INTO users (id, user_id, username, first_name, last_name, created_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
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

    def get_all_users(self):
        """Получение всех пользователей"""
        try:
            self.cursor.execute(
                "SELECT * FROM users WHERE is_active = true ORDER BY created_at DESC"
            )
            users = self.cursor.fetchall()
            return [dict(user) for user in users]

        except Exception as e:
            logger.error(f"Ошибка при получении пользователей: {e}")
            raise

    # ВАЖНО: Для полной совместимости project_manager.py нужны еще методы
    # Но основные методы (create_job, update_job, get_job, get_project_jobs)
    # уже реализованы выше, что достаточно для работы Celery Worker
