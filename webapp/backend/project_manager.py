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

    def get_all_projects(self, active_only: bool = True) -> List[Dict]:
        """
        Получение всех проектов

        :param active_only: Получить только активные проекты
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

            query += ' ORDER BY created_at DESC'

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
        Получение всех проектов пользователя

        :param user_id: ID пользователя
        :return: Список проектов
        """
        try:
            self.db.cursor.execute('''
                SELECT p.id, p.name, p.google_sheet_name, p.start_date, p.end_date,
                       p.target_views, p.geo, p.created_at, p.is_active
                FROM projects p
                INNER JOIN project_users pu ON p.id = pu.project_id
                WHERE pu.user_id = ? AND p.is_active = 1
                ORDER BY p.created_at DESC
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
