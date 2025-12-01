import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


class ProjectManager:
    """Класс для управления проектами"""

    def __init__(self, db):
        """
        Инициализация менеджера проектов

        :param db: Экземпляр SQLiteDatabase
        """
        self.db = db

    def create_project(self, name: str, google_sheet_name: str, start_date: str,
                      end_date: str, target_views: int, geo: str = "", kpi_views: int = 1000) -> Dict:
        """
        Создание нового проекта

        :param name: Название проекта
        :param google_sheet_name: Название Google таблицы
        :param start_date: Дата начала (YYYY-MM-DD)
        :param end_date: Дата окончания (YYYY-MM-DD)
        :param target_views: Целевое количество просмотров
        :param geo: География заказа
        :param kpi_views: Минимум просмотров для учета видео
        :return: Данные созданного проекта
        """
        try:
            project_id = str(uuid.uuid4())
            created_at = datetime.now().isoformat()

            self.db.cursor.execute('''
                INSERT INTO projects (id, name, google_sheet_name, start_date, end_date,
                                     target_views, geo, kpi_views, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ''', (project_id, name, google_sheet_name, start_date, end_date, target_views, geo, kpi_views, created_at))

            self.db.conn.commit()

            logger.info(f"✅ Проект создан: {name} (ID: {project_id})")

            return {
                "id": project_id,
                "name": name,
                "google_sheet_name": google_sheet_name,
                "start_date": start_date,
                "end_date": end_date,
                "target_views": target_views,
                "geo": geo,
                "kpi_views": kpi_views,
                "created_at": created_at
            }

        except Exception as e:
            logger.error(f"Ошибка создания проекта: {e}")
            raise

    def get_project(self, project_id: str) -> Optional[Dict]:
        """
        Получение проекта по ID

        :param project_id: ID проекта
        :return: Данные проекта или None
        """
        try:
            self.db.cursor.execute('''
                SELECT id, name, google_sheet_name, start_date, end_date,
                       target_views, geo, kpi_views, created_at, is_active
                FROM projects
                WHERE id = ?
            ''', (project_id,))

            row = self.db.cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "google_sheet_name": row[2],
                    "start_date": row[3],
                    "end_date": row[4],
                    "target_views": row[5],
                    "geo": row[6],
                    "kpi_views": row[7] if row[7] is not None else 1000,
                    "created_at": row[8],
                    "is_active": row[9]
                }

            return None

        except Exception as e:
            logger.error(f"Ошибка получения проекта: {e}")
            return None

    def get_all_projects(self, active_only: bool = False) -> List[Dict]:
        """
        Получение всех проектов (включая завершенные по умолчанию)

        :param active_only: Получить только активные проекты (False = все проекты)
        :return: Список проектов
        """
        try:
            query = '''
                SELECT id, name, google_sheet_name, start_date, end_date,
                       target_views, geo, created_at, is_active
                FROM projects
            '''

            if active_only:
                query += ' WHERE is_active = 1'

            query += ' ORDER BY is_active DESC, created_at DESC'

            self.db.cursor.execute(query)
            rows = self.db.cursor.fetchall()

            projects = []
            for row in rows:
                projects.append({
                    "id": row[0],
                    "name": row[1],
                    "google_sheet_name": row[2],
                    "start_date": row[3],
                    "end_date": row[4],
                    "target_views": row[5],
                    "geo": row[6],
                    "created_at": row[7],
                    "is_active": row[8]
                })

            return projects

        except Exception as e:
            logger.error(f"Ошибка получения списка проектов: {e}")
            return []

    def add_user_to_project(self, project_id: str, user_id: str) -> bool:
        """
        Добавление пользователя в проект

        :param project_id: ID проекта
        :param user_id: ID пользователя
        :return: True если успешно
        """
        try:
            id = str(uuid.uuid4())
            added_at = datetime.now().isoformat()

            self.db.cursor.execute('''
                INSERT OR IGNORE INTO project_users (id, project_id, user_id, added_at)
                VALUES (?, ?, ?, ?)
            ''', (id, project_id, user_id, added_at))

            self.db.conn.commit()

            if self.db.cursor.rowcount > 0:
                logger.info(f"✅ Пользователь {user_id} добавлен в проект {project_id}")
                return True
            else:
                logger.info(f"⚠️ Пользователь {user_id} уже в проекте {project_id}")
                return False

        except Exception as e:
            logger.error(f"Ошибка добавления пользователя в проект: {e}")
            return False

    def remove_user_from_project(self, project_id: str, user_id: str) -> bool:
        """
        Удаление пользователя из проекта

        :param project_id: ID проекта
        :param user_id: ID пользователя
        :return: True если успешно
        """
        try:
            self.db.cursor.execute('''
                DELETE FROM project_users
                WHERE project_id = ? AND user_id = ?
            ''', (project_id, user_id))

            self.db.conn.commit()

            if self.db.cursor.rowcount > 0:
                logger.info(f"✅ Пользователь {user_id} удален из проекта {project_id}")
                return True
            else:
                logger.info(f"⚠️ Пользователь {user_id} не найден в проекте {project_id}")
                return False

        except Exception as e:
            logger.error(f"Ошибка удаления пользователя из проекта: {e}")
            return False

    def get_user_projects(self, user_id: str) -> List[Dict]:
        """
        Получение всех проектов пользователя (включая завершенные)

        :param user_id: ID пользователя
        :return: Список проектов (активные и неактивные)
        """
        try:
            self.db.cursor.execute('''
                SELECT p.id, p.name, p.google_sheet_name, p.start_date, p.end_date,
                       p.target_views, p.geo, p.created_at, p.is_active
                FROM projects p
                INNER JOIN project_users pu ON p.id = pu.project_id
                WHERE pu.user_id = ?
                ORDER BY p.is_active DESC, p.created_at DESC
            ''', (user_id,))

            rows = self.db.cursor.fetchall()

            projects = []
            for row in rows:
                projects.append({
                    "id": row[0],
                    "name": row[1],
                    "google_sheet_name": row[2],
                    "start_date": row[3],
                    "end_date": row[4],
                    "target_views": row[5],
                    "geo": row[6],
                    "created_at": row[7],
                    "is_active": row[8]
                })

            return projects

        except Exception as e:
            logger.error(f"Ошибка получения проектов пользователя: {e}")
            return []

    def get_all_projects_with_access(self, user_id: str) -> List[Dict]:
        """
        Получение всех проектов с проверкой доступа для пользователя (включая завершенные)

        Для проектов, где пользователь НЕ является участником:
        - name заменяется на "***"
        - geo заменяется на "***"
        - target_views устанавливается в 0
        - has_access = False

        :param user_id: ID пользователя
        :return: Список всех проектов с информацией о доступе
        """
        try:
            # Получаем все проекты (активные и неактивные)
            self.db.cursor.execute('''
                SELECT p.id, p.name, p.google_sheet_name, p.start_date, p.end_date,
                       p.target_views, p.geo, p.created_at, p.is_active
                FROM projects p
                ORDER BY p.is_active DESC, p.created_at DESC
            ''')

            rows = self.db.cursor.fetchall()

            projects = []
            for row in rows:
                project_id = row[0]

                # Проверяем, является ли пользователь участником проекта
                # Convert both to strings to avoid type mismatch
                self.db.cursor.execute('''
                    SELECT COUNT(*) FROM project_users
                    WHERE project_id = ? AND user_id = ?
                ''', (str(project_id), str(user_id)))

                has_access = self.db.cursor.fetchone()[0] > 0

                if has_access:
                    # Пользователь имеет доступ - показываем реальные данные
                    projects.append({
                        "id": row[0],
                        "name": row[1],
                        "google_sheet_name": row[2],
                        "start_date": row[3],
                        "end_date": row[4],
                        "target_views": row[5],
                        "geo": row[6],
                        "created_at": row[7],
                        "is_active": row[8],
                        "has_access": True
                    })
                else:
                    # Пользователь НЕ имеет доступа - маскируем данные
                    projects.append({
                        "id": row[0],
                        "name": "***",
                        "google_sheet_name": row[2],
                        "start_date": row[3],
                        "end_date": row[4],
                        "target_views": 0,
                        "geo": "***",
                        "created_at": row[7],
                        "is_active": row[8],
                        "has_access": False
                    })

            return projects

        except Exception as e:
            logger.error(f"Ошибка получения всех проектов с проверкой доступа: {e}")
            return []

    def get_project_users(self, project_id: str) -> List[Dict]:
        """
        Получение всех пользователей проекта

        :param project_id: ID проекта
        :return: Список пользователей
        """
        try:
            self.db.cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, u.last_name, pu.added_at
                FROM users u
                INNER JOIN project_users pu ON u.user_id = pu.user_id
                WHERE pu.project_id = ?
                ORDER BY pu.added_at DESC
            ''', (project_id,))

            rows = self.db.cursor.fetchall()

            users = []
            for row in rows:
                users.append({
                    "user_id": row[0],
                    "username": row[1],
                    "first_name": row[2],
                    "last_name": row[3],
                    "added_at": row[4]
                })

            return users

        except Exception as e:
            logger.error(f"Ошибка получения пользователей проекта: {e}")
            return []

    def set_user_current_project(self, user_id: str, project_id: str) -> bool:
        """
        Установка текущего проекта для пользователя

        :param user_id: ID пользователя
        :param project_id: ID проекта
        :return: True если успешно
        """
        try:
            last_updated = datetime.now().isoformat()

            # Проверяем, есть ли уже запись
            self.db.cursor.execute('''
                SELECT user_id FROM user_context WHERE user_id = ?
            ''', (user_id,))

            if self.db.cursor.fetchone():
                # Обновляем существующую запись
                self.db.cursor.execute('''
                    UPDATE user_context
                    SET current_project_id = ?, last_updated = ?
                    WHERE user_id = ?
                ''', (project_id, last_updated, user_id))
            else:
                # Создаем новую запись
                self.db.cursor.execute('''
                    INSERT INTO user_context (user_id, current_project_id, last_updated)
                    VALUES (?, ?, ?)
                ''', (user_id, project_id, last_updated))

            self.db.conn.commit()
            logger.info(f"✅ Текущий проект {project_id} установлен для пользователя {user_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка установки текущего проекта: {e}")
            return False

    def get_user_current_project(self, user_id: str) -> Optional[str]:
        """
        Получение ID текущего проекта пользователя

        :param user_id: ID пользователя
        :return: ID проекта или None
        """
        try:
            self.db.cursor.execute('''
                SELECT current_project_id FROM user_context WHERE user_id = ?
            ''', (user_id,))

            row = self.db.cursor.fetchone()
            return row[0] if row else None

        except Exception as e:
            logger.error(f"Ошибка получения текущего проекта: {e}")
            return None

    def deactivate_project(self, project_id: str) -> bool:
        """
        Деактивация проекта

        :param project_id: ID проекта
        :return: True если успешно
        """
        try:
            self.db.cursor.execute('''
                UPDATE projects SET is_active = 0 WHERE id = ?
            ''', (project_id,))

            self.db.conn.commit()

            if self.db.cursor.rowcount > 0:
                logger.info(f"✅ Проект {project_id} деактивирован")
                return True
            else:
                logger.info(f"⚠️ Проект {project_id} не найден")
                return False

        except Exception as e:
            logger.error(f"Ошибка деактивации проекта: {e}")
            return False

    # ==================== УПРАВЛЕНИЕ СОЦИАЛЬНЫМИ АККАУНТАМИ ====================

    def add_social_account_to_project(self, project_id: str, platform: str, username: str,
                                      profile_link: str, status: str = "NEW", topic: str = "") -> Optional[Dict]:
        """
        Добавление социального аккаунта в проект (с поддержкой реактивации)

        :param project_id: ID проекта
        :param platform: Платформа (tiktok/instagram/youtube/facebook)
        :param username: Username аккаунта
        :param profile_link: Ссылка на профиль
        :param status: Статус (NEW/OLD/Ban)
        :param topic: Тематика контента
        :return: Данные добавленного аккаунта
        """
        try:
            # Check if account exists (regardless of is_active status)
            self.db.cursor.execute('''
                SELECT id, is_active, added_at FROM project_social_accounts
                WHERE project_id = ? AND platform = ? AND username = ?
            ''', (project_id, platform, username))

            existing = self.db.cursor.fetchone()

            if existing:
                # Account exists - reactivate it
                account_id = existing[0]
                original_added_at = existing[2]

                self.db.cursor.execute('''
                    UPDATE project_social_accounts
                    SET is_active = 1,
                        profile_link = ?,
                        status = ?,
                        topic = ?
                    WHERE id = ?
                ''', (profile_link, status, topic, account_id))

                self.db.conn.commit()

                logger.info(f"♻️ Reactivated existing account: {username} ({platform}) in project {project_id}")

                return {
                    "id": account_id,
                    "project_id": project_id,
                    "platform": platform,
                    "username": username,
                    "profile_link": profile_link,
                    "status": status,
                    "topic": topic,
                    "added_at": original_added_at
                }
            else:
                # Account doesn't exist - create new
                account_id = str(uuid.uuid4())
                added_at = datetime.now().isoformat()

                self.db.cursor.execute('''
                    INSERT INTO project_social_accounts
                    (id, project_id, platform, username, profile_link, status, topic, added_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                ''', (account_id, project_id, platform, username, profile_link, status, topic, added_at))

                self.db.conn.commit()

                logger.info(f"✅ Created new account: {username} ({platform}) in project {project_id}")

                return {
                    "id": account_id,
                    "project_id": project_id,
                    "platform": platform,
                    "username": username,
                    "profile_link": profile_link,
                    "status": status,
                    "topic": topic,
                    "added_at": added_at
                }

        except Exception as e:
            logger.error(f"Ошибка добавления/реактивации аккаунта в проект: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_project_social_accounts(self, project_id: str, platform: Optional[str] = None) -> List[Dict]:
        """
        Получение всех социальных аккаунтов проекта

        :param project_id: ID проекта
        :param platform: Фильтр по платформе (опционально)
        :return: Список аккаунтов
        """
        try:
            query = '''
                SELECT id, project_id, platform, username, profile_link, status, topic, added_at, is_active
                FROM project_social_accounts
                WHERE project_id = ? AND is_active = 1
            '''
            params = [project_id]

            if platform:
                query += ' AND platform = ?'
                params.append(platform)

            query += ' ORDER BY added_at DESC'

            self.db.cursor.execute(query, params)
            rows = self.db.cursor.fetchall()

            accounts = []
            for row in rows:
                accounts.append({
                    "id": row[0],
                    "project_id": row[1],
                    "platform": row[2],
                    "username": row[3],
                    "profile_link": row[4],
                    "status": row[5],
                    "topic": row[6],
                    "added_at": row[7],
                    "is_active": row[8]
                })

            return accounts

        except Exception as e:
            logger.error(f"Ошибка получения аккаунтов проекта: {e}")
            return []

    def get_social_account(self, account_id: str) -> Optional[Dict]:
        """
        Получение данных социального аккаунта

        :param account_id: ID аккаунта
        :return: Данные аккаунта или None
        """
        try:
            self.db.cursor.execute('''
                SELECT id, project_id, platform, username, profile_link, status, topic, added_at, is_active
                FROM project_social_accounts
                WHERE id = ?
            ''', (account_id,))

            row = self.db.cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "project_id": row[1],
                    "platform": row[2],
                    "username": row[3],
                    "profile_link": row[4],
                    "status": row[5],
                    "topic": row[6],
                    "added_at": row[7],
                    "is_active": row[8]
                }

            return None

        except Exception as e:
            logger.error(f"Ошибка получения аккаунта: {e}")
            return None

    def update_social_account(self, account_id: str, **kwargs) -> bool:
        """
        Обновление данных социального аккаунта

        :param account_id: ID аккаунта
        :param kwargs: Поля для обновления (status, topic, etc.)
        :return: True если успешно
        """
        try:
            allowed_fields = ['status', 'topic', 'profile_link', 'username']
            updates = []
            values = []

            for field, value in kwargs.items():
                if field in allowed_fields:
                    updates.append(f"{field} = ?")
                    values.append(value)

            if not updates:
                return False

            values.append(account_id)
            query = f"UPDATE project_social_accounts SET {', '.join(updates)} WHERE id = ?"

            self.db.cursor.execute(query, values)
            self.db.conn.commit()

            if self.db.cursor.rowcount > 0:
                logger.info(f"✅ Аккаунт {account_id} обновлен")
                return True

            return False

        except Exception as e:
            logger.error(f"Ошибка обновления аккаунта: {e}")
            return False

    def remove_social_account_from_project(self, account_id: str) -> bool:
        """
        Удаление социального аккаунта из проекта

        :param account_id: ID аккаунта
        :return: True если успешно
        """
        try:
            self.db.cursor.execute('''
                UPDATE project_social_accounts SET is_active = 0 WHERE id = ?
            ''', (account_id,))

            self.db.conn.commit()

            if self.db.cursor.rowcount > 0:
                logger.info(f"✅ Аккаунт {account_id} удален из проекта")
                return True
            else:
                logger.info(f"⚠️ Аккаунт {account_id} не найден")
                return False

        except Exception as e:
            logger.error(f"Ошибка удаления аккаунта: {e}")
            return False

    # ==================== СНИМКИ СТАТИСТИКИ ====================

    def add_account_snapshot(self, account_id: str, followers: int, likes: int,
                            comments: int, videos: int, views: int) -> bool:
        """
        Добавление снимка статистики аккаунта

        :param account_id: ID аккаунта
        :param followers: Количество подписчиков
        :param likes: Количество лайков
        :param comments: Количество комментариев
        :param videos: Количество видео
        :param views: Количество просмотров
        :return: True если успешно
        """
        try:
            snapshot_id = str(uuid.uuid4())
            snapshot_time = datetime.now().isoformat()

            self.db.cursor.execute('''
                INSERT INTO account_snapshots
                (id, account_id, followers, likes, comments, videos, views, snapshot_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (snapshot_id, account_id, followers, likes, comments, videos, views, snapshot_time))

            self.db.conn.commit()

            logger.info(f"✅ Снимок статистики добавлен для аккаунта {account_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка добавления снимка: {e}")
            return False

    def get_account_snapshots(self, account_id: str, start_date: Optional[str] = None,
                             end_date: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        Получение снимков статистики аккаунта

        :param account_id: ID аккаунта
        :param start_date: Начальная дата (опционально)
        :param end_date: Конечная дата (опционально)
        :param limit: Максимальное количество снимков
        :return: Список снимков
        """
        try:
            query = '''
                SELECT id, account_id, followers, likes, comments, videos, views, snapshot_time
                FROM account_snapshots
                WHERE account_id = ?
            '''
            params = [account_id]

            if start_date:
                query += ' AND snapshot_time >= ?'
                params.append(start_date)

            if end_date:
                query += ' AND snapshot_time <= ?'
                params.append(end_date)

            query += ' ORDER BY snapshot_time DESC LIMIT ?'
            params.append(limit)

            self.db.cursor.execute(query, params)
            rows = self.db.cursor.fetchall()

            snapshots = []
            for row in rows:
                snapshots.append({
                    "id": row[0],
                    "account_id": row[1],
                    "followers": row[2],
                    "likes": row[3],
                    "comments": row[4],
                    "videos": row[5],
                    "views": row[6],
                    "snapshot_time": row[7]
                })

            return snapshots

        except Exception as e:
            logger.error(f"Ошибка получения снимков: {e}")
            return []

    def calculate_daily_stats(self, account_id: str, date: str) -> bool:
        """
        Расчет статистики за день на основе снимков

        :param account_id: ID аккаунта
        :param date: Дата в формате YYYY-MM-DD
        :return: True если успешно
        """
        try:
            # Получаем первый и последний снимок за день
            start_time = f"{date} 00:00:00"
            end_time = f"{date} 23:59:59"

            self.db.cursor.execute('''
                SELECT followers, likes, comments, videos, views
                FROM account_snapshots
                WHERE account_id = ? AND snapshot_time >= ? AND snapshot_time <= ?
                ORDER BY snapshot_time ASC
                LIMIT 1
            ''', (account_id, start_time, end_time))

            start_row = self.db.cursor.fetchone()

            if not start_row:
                logger.warning(f"Нет данных за {date} для аккаунта {account_id}")
                return False

            self.db.cursor.execute('''
                SELECT followers, likes, comments, videos, views
                FROM account_snapshots
                WHERE account_id = ? AND snapshot_time >= ? AND snapshot_time <= ?
                ORDER BY snapshot_time DESC
                LIMIT 1
            ''', (account_id, start_time, end_time))

            end_row = self.db.cursor.fetchone()

            if not end_row:
                end_row = start_row

            # Расчет прироста
            followers_start, likes_start, comments_start, videos_start, views_start = start_row
            followers_end, likes_end, comments_end, videos_end, views_end = end_row

            stats_id = str(uuid.uuid4())

            # Проверяем, есть ли уже запись за этот день
            self.db.cursor.execute('''
                SELECT id FROM account_daily_stats WHERE account_id = ? AND date = ?
            ''', (account_id, date))

            existing = self.db.cursor.fetchone()

            if existing:
                # Обновляем существующую запись
                self.db.cursor.execute('''
                    UPDATE account_daily_stats SET
                        followers_start = ?, followers_end = ?, followers_growth = ?,
                        likes_start = ?, likes_end = ?, likes_growth = ?,
                        comments_start = ?, comments_end = ?, comments_growth = ?,
                        videos_start = ?, videos_end = ?, videos_growth = ?,
                        views_start = ?, views_end = ?, views_growth = ?
                    WHERE account_id = ? AND date = ?
                ''', (
                    followers_start, followers_end, followers_end - followers_start,
                    likes_start, likes_end, likes_end - likes_start,
                    comments_start, comments_end, comments_end - comments_start,
                    videos_start, videos_end, videos_end - videos_start,
                    views_start, views_end, views_end - views_start,
                    account_id, date
                ))
            else:
                # Создаем новую запись
                self.db.cursor.execute('''
                    INSERT INTO account_daily_stats (
                        id, account_id, date,
                        followers_start, followers_end, followers_growth,
                        likes_start, likes_end, likes_growth,
                        comments_start, comments_end, comments_growth,
                        videos_start, videos_end, videos_growth,
                        views_start, views_end, views_growth
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stats_id, account_id, date,
                    followers_start, followers_end, followers_end - followers_start,
                    likes_start, likes_end, likes_end - likes_start,
                    comments_start, comments_end, comments_end - comments_start,
                    videos_start, videos_end, videos_end - videos_start,
                    views_start, views_end, views_end - views_start
                ))

            self.db.conn.commit()

            logger.info(f"✅ Статистика за {date} рассчитана для аккаунта {account_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка расчета статистики: {e}")
            return False

    def get_account_daily_stats(self, account_id: str, start_date: Optional[str] = None,
                               end_date: Optional[str] = None) -> List[Dict]:
        """
        Получение ежедневной статистики аккаунта

        :param account_id: ID аккаунта
        :param start_date: Начальная дата (опционально)
        :param end_date: Конечная дата (опционально)
        :return: Список статистики по дням
        """
        try:
            query = '''
                SELECT * FROM account_daily_stats
                WHERE account_id = ?
            '''
            params = [account_id]

            if start_date:
                query += ' AND date >= ?'
                params.append(start_date)

            if end_date:
                query += ' AND date <= ?'
                params.append(end_date)

            query += ' ORDER BY date DESC'

            self.db.cursor.execute(query, params)
            rows = self.db.cursor.fetchall()

            stats = []
            for row in rows:
                stats.append({
                    "id": row[0],
                    "account_id": row[1],
                    "date": row[2],
                    "followers_start": row[3],
                    "followers_end": row[4],
                    "followers_growth": row[5],
                    "likes_start": row[6],
                    "likes_end": row[7],
                    "likes_growth": row[8],
                    "comments_start": row[9],
                    "comments_end": row[10],
                    "comments_growth": row[11],
                    "videos_start": row[12],
                    "videos_end": row[13],
                    "videos_growth": row[14],
                    "views_start": row[15],
                    "views_end": row[16],
                    "views_growth": row[17]
                })

            return stats

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return []

    def finish_project(self, project_id: str) -> bool:
        """
        Завершение проекта (установка is_active = 0)

        :param project_id: ID проекта
        :return: True если успешно
        """
        try:
            self.db.cursor.execute('''
                UPDATE projects SET is_active = 0 WHERE id = ?
            ''', (project_id,))

            self.db.conn.commit()

            if self.db.cursor.rowcount > 0:
                logger.info(f"✅ Проект {project_id} завершен (is_active=0)")
                return True
            else:
                logger.info(f"⚠️ Проект {project_id} не найден")
                return False

        except Exception as e:
            logger.error(f"Ошибка завершения проекта: {e}")
            return False

    def delete_project_fully(self, project_id: str) -> bool:
        """
        Полное удаление проекта из базы данных

        Удаляет:
        - Записи из account_daily_stats
        - Записи из account_snapshots
        - Записи из project_social_accounts
        - Записи из project_users
        - Запись из projects

        :param project_id: ID проекта
        :return: True если успешно
        """
        try:
            # 1. Получаем все аккаунты проекта для удаления их снимков и статистики
            self.db.cursor.execute('''
                SELECT id FROM project_social_accounts WHERE project_id = ?
            ''', (project_id,))

            account_ids = [row[0] for row in self.db.cursor.fetchall()]

            # 2. Удаляем ежедневную статистику всех аккаунтов проекта
            for account_id in account_ids:
                self.db.cursor.execute('''
                    DELETE FROM account_daily_stats WHERE account_id = ?
                ''', (account_id,))

            # 3. Удаляем снимки всех аккаунтов проекта
            for account_id in account_ids:
                self.db.cursor.execute('''
                    DELETE FROM account_snapshots WHERE account_id = ?
                ''', (account_id,))

            # 4. Удаляем социальные аккаунты проекта
            self.db.cursor.execute('''
                DELETE FROM project_social_accounts WHERE project_id = ?
            ''', (project_id,))

            # 5. Удаляем пользователей проекта
            self.db.cursor.execute('''
                DELETE FROM project_users WHERE project_id = ?
            ''', (project_id,))

            # 6. Удаляем сам проект
            self.db.cursor.execute('''
                DELETE FROM projects WHERE id = ?
            ''', (project_id,))

            self.db.conn.commit()

            logger.info(f"✅ Проект {project_id} полностью удален из БД")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления проекта: {e}")
            self.db.conn.rollback()
            return False
