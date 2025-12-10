"""
Email Farm Database Models
Модели для корпоративной почтовой фермы
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class EmailFarmDatabase:
    """Database manager for Email Farm module"""

    def __init__(self, db_path: str = "tiktok_analytics.db"):
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """Initialize database connection and create tables"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        """Create all Email Farm tables"""
        cursor = self.conn.cursor()

        # Таблица email_accounts (Почтовые аккаунты)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_encrypted TEXT NOT NULL,
                proxy_string TEXT,
                status TEXT DEFAULT 'free',
                assigned_user_id INTEGER,
                assigned_at DATETIME,
                project_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (assigned_user_id) REFERENCES users(id),
                CHECK (status IN ('free', 'active', 'banned', 'archived'))
            )
        """)

        # Индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_email_status
            ON email_accounts(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_email_assigned_user
            ON email_accounts(assigned_user_id)
        """)

        # Таблица user_limits (Лимиты пользователей)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_limits (
                user_id INTEGER PRIMARY KEY,
                max_active_emails INTEGER DEFAULT 5,
                can_access_emails BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Таблица email_history (История действий с почтами)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (email_id) REFERENCES email_accounts(id),
                CHECK (action IN ('took', 'banned', 'checked_code', 'security_alert'))
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_user
            ON email_history(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_timestamp
            ON email_history(timestamp DESC)
        """)

        self.conn.commit()
        logger.info("✅ Email Farm tables initialized")

    # ============ Email Accounts CRUD ============

    def add_email_account(self, email: str, password_encrypted: str,
                         proxy_string: Optional[str] = None,
                         project_id: Optional[int] = None) -> Optional[int]:
        """Add new email account to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO email_accounts
                (email, password_encrypted, proxy_string, project_id, status)
                VALUES (?, ?, ?, ?, 'free')
            """, (email, password_encrypted, proxy_string, project_id))

            self.conn.commit()
            email_id = cursor.lastrowid
            logger.info(f"✅ Added email account: {email} (ID: {email_id})")
            return email_id

        except sqlite3.IntegrityError:
            logger.warning(f"⚠️ Email already exists: {email}")
            return None
        except Exception as e:
            logger.error(f"❌ Error adding email account: {e}")
            self.conn.rollback()
            return None

    def get_free_email(self) -> Optional[Dict]:
        """Get one free email account"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, email, password_encrypted, proxy_string, project_id
            FROM email_accounts
            WHERE status = 'free'
            LIMIT 1
        """)

        row = cursor.fetchone()
        return dict(row) if row else None

    def allocate_email_to_user(self, email_id: int, user_id: int) -> bool:
        """Allocate email to user"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE email_accounts
                SET status = 'active',
                    assigned_user_id = ?,
                    assigned_at = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'free'
            """, (user_id, datetime.now(), datetime.now(), email_id))

            if cursor.rowcount == 0:
                logger.warning(f"⚠️ Email {email_id} is not available")
                return False

            # Log history
            cursor.execute("""
                INSERT INTO email_history (user_id, email_id, action, details)
                VALUES (?, ?, 'took', 'Email allocated to user')
            """, (user_id, email_id))

            self.conn.commit()
            logger.info(f"✅ Email {email_id} allocated to user {user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error allocating email: {e}")
            self.conn.rollback()
            return False

    def get_user_emails(self, user_id: int) -> List[Dict]:
        """Get all emails assigned to user"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, email, status, assigned_at, proxy_string
            FROM email_accounts
            WHERE assigned_user_id = ?
            ORDER BY assigned_at DESC
        """, (user_id,))

        return [dict(row) for row in cursor.fetchall()]

    def mark_email_banned(self, email_id: int, user_id: int, reason: str = "User marked as invalid") -> bool:
        """Mark email as banned"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE email_accounts
                SET status = 'banned',
                    updated_at = ?
                WHERE id = ?
            """, (datetime.now(), email_id))

            # Log history
            cursor.execute("""
                INSERT INTO email_history (user_id, email_id, action, details)
                VALUES (?, ?, 'banned', ?)
            """, (user_id, email_id, reason))

            self.conn.commit()
            logger.info(f"✅ Email {email_id} marked as banned")
            return True

        except Exception as e:
            logger.error(f"❌ Error marking email as banned: {e}")
            self.conn.rollback()
            return False

    def get_email_by_id(self, email_id: int) -> Optional[Dict]:
        """Get email account by ID"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, email, password_encrypted, proxy_string,
                   status, assigned_user_id, assigned_at
            FROM email_accounts
            WHERE id = ?
        """, (email_id,))

        row = cursor.fetchone()
        return dict(row) if row else None

    # ============ User Limits ============

    def get_user_limit(self, user_id: int) -> Dict:
        """Get user email limit"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT max_active_emails, can_access_emails
            FROM user_limits
            WHERE user_id = ?
        """, (user_id,))

        row = cursor.fetchone()
        if row:
            return dict(row)

        # Return default if not found
        return {
            'max_active_emails': 5,
            'can_access_emails': True
        }

    def set_user_limit(self, user_id: int, max_emails: int, can_access: bool = True) -> bool:
        """Set user email limit"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO user_limits (user_id, max_active_emails, can_access_emails)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    max_active_emails = excluded.max_active_emails,
                    can_access_emails = excluded.can_access_emails,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, max_emails, can_access))

            self.conn.commit()
            logger.info(f"✅ Set limit for user {user_id}: {max_emails} emails")
            return True

        except Exception as e:
            logger.error(f"❌ Error setting user limit: {e}")
            self.conn.rollback()
            return False

    def get_user_active_count(self, user_id: int) -> int:
        """Count active emails for user"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM email_accounts
            WHERE assigned_user_id = ? AND status = 'active'
        """, (user_id,))

        row = cursor.fetchone()
        return row['count'] if row else 0

    # ============ History ============

    def log_action(self, user_id: int, email_id: int, action: str, details: str = None):
        """Log email action to history"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO email_history (user_id, email_id, action, details)
                VALUES (?, ?, ?, ?)
            """, (user_id, email_id, action, details))

            self.conn.commit()
        except Exception as e:
            logger.error(f"❌ Error logging action: {e}")

    def get_user_history(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get user action history"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT h.*, e.email
            FROM email_history h
            JOIN email_accounts e ON h.email_id = e.id
            WHERE h.user_id = ?
            ORDER BY h.timestamp DESC
            LIMIT ?
        """, (user_id, limit))

        return [dict(row) for row in cursor.fetchall()]

    # ============ Admin Statistics ============

    def get_stats(self) -> Dict:
        """Get overall email farm statistics"""
        cursor = self.conn.cursor()

        # Count by status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM email_accounts
            GROUP BY status
        """)
        status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

        # Count users with access
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM user_limits
            WHERE can_access_emails = 1
        """)
        users_with_access = cursor.fetchone()['count']

        return {
            'total_emails': sum(status_counts.values()),
            'free': status_counts.get('free', 0),
            'active': status_counts.get('active', 0),
            'banned': status_counts.get('banned', 0),
            'archived': status_counts.get('archived', 0),
            'users_with_access': users_with_access
        }

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("🔒 Email Farm database closed")


if __name__ == "__main__":
    # Test database creation
    logging.basicConfig(level=logging.INFO)
    db = EmailFarmDatabase()
    stats = db.get_stats()
    print(f"📊 Email Farm Stats: {stats}")
    db.close()
