"""
Celery Tasks for View Counter WebApp

Background tasks for heavy operations:
- Google Sheets synchronization
- Periodic data sync
- Stats update notifications
"""

import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import Celery, graceful fallback if not available
try:
    from celery import Celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Celery = None
    logger.warning("⚠️ Celery not installed, background tasks disabled")

# Initialize Celery (only if available)
if CELERY_AVAILABLE:
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', '6379')
    redis_password = os.getenv('REDIS_PASSWORD', '')

    # Broker URL
    if redis_password:
        broker_url = f'redis://:{redis_password}@{redis_host}:{redis_port}/1'
    else:
        broker_url = f'redis://{redis_host}:{redis_port}/1'

    # Result backend URL
    result_backend = broker_url.replace('/1', '/2')  # Use different DB for results

    celery_app = Celery(
        'view_counter_tasks',
        broker=broker_url,
        backend=result_backend
    )

    # Celery Configuration
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=600,  # 10 minutes max per task
        worker_prefetch_multiplier=1,  # Take one task at a time
        worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (prevent memory leaks)
    )
else:
    # Dummy celery_app for imports
    celery_app = None
    logger.warning("⚠️ Celery app not initialized (module not available)")


def _create_task_decorator():
    """Create task decorator or no-op if Celery unavailable"""
    if CELERY_AVAILABLE and celery_app:
        return celery_app.task
    else:
        # No-op decorator
        def dummy_decorator(*args, **kwargs):
            def wrapper(func):
                return func
            return wrapper
        return dummy_decorator

task = _create_task_decorator()

@task(name='sync_project_to_sheets')
def sync_project_to_sheets(project_id: str, project_name: str, accounts_data: list):
    """
    Синхронизация проекта с Google Sheets (фоновая задача)

    Args:
        project_id: ID проекта
        project_name: Название проекта
        accounts_data: Список аккаунтов для синхронизации

    Returns:
        dict: {"success": bool, "message": str, "synced_count": int}
    """
    logger.info(f"📤 [Celery] Starting sync to Google Sheets for project {project_id}")

    try:
        # Import здесь чтобы избежать circular imports
        from project_sheets_manager import ProjectSheetsManager
        from config import DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS_JSON

        # Создаём менеджер Google Sheets
        sheets_manager = ProjectSheetsManager(
            DEFAULT_GOOGLE_SHEETS_NAME,
            GOOGLE_SHEETS_CREDENTIALS_JSON
        )

        # Синхронизируем каждый аккаунт
        synced_count = 0
        for account in accounts_data:
            try:
                # Обновляем данные в таблице
                sheets_manager.update_account_in_project(
                    project_name=project_name,
                    account_url=account['profile_link'],
                    updates={
                        'Views': account.get('views', 0),
                        'Videos': account.get('videos', 0),
                        'Followers': account.get('followers', 0),
                        'Likes': account.get('likes', 0),
                        'Comments': account.get('comments', 0),
                    }
                )
                synced_count += 1
                logger.info(f"✅ [Celery] Synced account {account.get('username', 'unknown')}")
            except Exception as e:
                logger.error(f"❌ [Celery] Failed to sync account {account.get('username')}: {e}")

        logger.info(f"✅ [Celery] Sync completed: {synced_count}/{len(accounts_data)} accounts")

        return {
            "success": True,
            "message": f"Synced {synced_count} accounts to Google Sheets",
            "synced_count": synced_count
        }

    except Exception as e:
        logger.error(f"❌ [Celery] Sync to sheets failed: {e}")
        return {
            "success": False,
            "message": str(e),
            "synced_count": 0
        }


@task(name='sync_account_to_sheets')
def sync_account_to_sheets(project_name: str, account_data: dict):
    """
    Синхронизация одного аккаунта с Google Sheets

    Args:
        project_name: Название проекта
        account_data: Данные аккаунта

    Returns:
        dict: {"success": bool, "message": str}
    """
    logger.info(f"📤 [Celery] Syncing single account to Sheets: {account_data.get('username')}")

    try:
        from project_sheets_manager import ProjectSheetsManager
        from config import DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS_JSON

        sheets_manager = ProjectSheetsManager(
            DEFAULT_GOOGLE_SHEETS_NAME,
            GOOGLE_SHEETS_CREDENTIALS_JSON
        )

        # Обновляем аккаунт в таблице
        sheets_manager.update_account_in_project(
            project_name=project_name,
            account_url=account_data['profile_link'],
            updates={
                'Views': account_data.get('views', 0),
                'Videos': account_data.get('videos', 0),
                'Followers': account_data.get('followers', 0),
                'Likes': account_data.get('likes', 0),
                'Comments': account_data.get('comments', 0),
            }
        )

        logger.info(f"✅ [Celery] Account synced: {account_data.get('username')}")

        return {
            "success": True,
            "message": f"Account {account_data.get('username')} synced"
        }

    except Exception as e:
        logger.error(f"❌ [Celery] Account sync failed: {e}")
        return {
            "success": False,
            "message": str(e)
        }


@task(name='periodic_sync_all_projects')
def periodic_sync_all_projects():
    """
    Периодическая синхронизация всех активных проектов (запускается по расписанию)

    Returns:
        dict: {"synced_projects": int, "failed_projects": int}
    """
    logger.info("🔄 [Celery] Starting periodic sync for all active projects")

    try:
        from project_manager import ProjectManager
        from database_sqlite import SQLiteDatabase

        # Инициализируем менеджер проектов
        db = SQLiteDatabase()
        project_manager = ProjectManager(db)

        # Получаем все активные проекты
        all_projects = project_manager.get_all_projects()
        active_projects = [p for p in all_projects if p.get('is_active', 1) == 1]

        logger.info(f"📊 [Celery] Found {len(active_projects)} active projects")

        synced_count = 0
        failed_count = 0

        for project in active_projects:
            try:
                project_id = project['id']
                project_name = project['name']

                # Получаем аккаунты проекта
                accounts = project_manager.get_project_social_accounts(project_id)

                if accounts:
                    # Запускаем синхронизацию в фоне
                    sync_project_to_sheets.delay(project_id, project_name, accounts)
                    synced_count += 1
                    logger.info(f"✅ [Celery] Queued sync for project {project_name}")

            except Exception as e:
                logger.error(f"❌ [Celery] Failed to queue project {project.get('name')}: {e}")
                failed_count += 1

        logger.info(f"✅ [Celery] Periodic sync completed: {synced_count} queued, {failed_count} failed")

        return {
            "synced_projects": synced_count,
            "failed_projects": failed_count
        }

    except Exception as e:
        logger.error(f"❌ [Celery] Periodic sync failed: {e}")
        return {
            "synced_projects": 0,
            "failed_projects": 0
        }


@task(name='smart_sync_all_projects')
def smart_sync_all_projects():
    """
    Smart sync for all active projects using MAX() merge strategy

    This is a Celery task wrapper around the standalone smart_sync function.
    It implements CQRS-lite architecture:
    1. Read from Google Sheets (manual edits)
    2. Parse fresh data (from parsers/SQLite)
    3. Merge using MAX() strategy
    4. Update SQLite
    5. Create daily snapshots

    Returns:
        dict: Sync results
    """
    logger.info("🔄 [Celery] Starting smart sync for all projects")

    try:
        from database_sqlite import SQLiteDatabase
        from config import DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS_JSON
        from smart_sync import sync_all_projects_standalone

        # Initialize database
        db = SQLiteDatabase()

        # Run smart sync
        result = sync_all_projects_standalone(
            db=db,
            sheets_credentials=GOOGLE_SHEETS_CREDENTIALS_JSON,
            sheets_name=DEFAULT_GOOGLE_SHEETS_NAME
        )

        logger.info(f"✅ [Celery] Smart sync completed: {result.get('success_count', 0)} projects")

        return result

    except Exception as e:
        logger.error(f"❌ [Celery] Smart sync failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@task(name='smart_sync_single_project')
def smart_sync_single_project(project_id: str):
    """
    Smart sync for a single project

    Args:
        project_id: Project ID to sync

    Returns:
        dict: Sync results
    """
    logger.info(f"🔄 [Celery] Starting smart sync for project {project_id}")

    try:
        from database_sqlite import SQLiteDatabase
        from config import DEFAULT_GOOGLE_SHEETS_NAME, GOOGLE_SHEETS_CREDENTIALS_JSON
        from smart_sync import sync_single_project_standalone

        # Initialize database
        db = SQLiteDatabase()

        # Run smart sync
        result = sync_single_project_standalone(
            db=db,
            sheets_credentials=GOOGLE_SHEETS_CREDENTIALS_JSON,
            sheets_name=DEFAULT_GOOGLE_SHEETS_NAME,
            project_id=project_id
        )

        logger.info(f"✅ [Celery] Smart sync completed for project {project_id}")

        return result

    except Exception as e:
        logger.error(f"❌ [Celery] Smart sync failed for project {project_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id
        }


# Periodic Tasks Schedule (Celery Beat)
if CELERY_AVAILABLE and celery_app:
    celery_app.conf.beat_schedule = {
        'smart-sync-all-projects-every-5-minutes': {
            'task': 'smart_sync_all_projects',
            'schedule': 300.0,  # 5 minutes - быстрые обновления для актуальных данных
        },
    }

if __name__ == '__main__':
    logger.info("🚀 Celery worker started")
    logger.info(f"📡 Broker: {broker_url}")
    logger.info(f"💾 Backend: {result_backend}")
