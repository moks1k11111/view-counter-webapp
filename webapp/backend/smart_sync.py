"""
Smart Sync Service for View Counter WebApp

Implements CQRS-lite architecture with intelligent synchronization:
1. Read from Google Sheets (source of truth for manual edits)
2. Parse fresh data from social media platforms
3. Merge using MAX() strategy to preserve manual edits while updating with fresh data
4. Store metrics in account_snapshots (one snapshot per day per account)

Data Architecture:
- Metrics (views, likes, followers, etc.) are stored ONLY in account_snapshots table
- project_social_accounts table contains only metadata (username, profile_link, status, topic)
- Frontend should read metrics from snapshots or cache, not from project_social_accounts

This service can be run:
- As a Celery Beat scheduled task (when Redis available)
- Via HTTP endpoint (for Render Cron Jobs on free tier)
- Manually for testing
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import traceback

logger = logging.getLogger(__name__)


class SmartSyncService:
    """
    Intelligent synchronization service with MAX() merge strategy

    Algorithm:
    1. Read current data from Google Sheets (includes manual edits)
    2. Parse fresh data from social media platforms
    3. Merge: Take MAX(sheets_value, parsed_value) for each metric
    4. Create daily snapshots (primary storage for metrics and historical tracking)

    Note: Metrics are stored only in account_snapshots table.
    The project_social_accounts table contains only metadata (username, profile_link, status, topic).
    """

    def __init__(self, project_manager, sheets_manager):
        """
        Initialize sync service

        Args:
            project_manager: ProjectManager instance
            sheets_manager: ProjectSheetsManager instance
        """
        self.project_manager = project_manager
        self.sheets_manager = sheets_manager

    def sync_project(self, project_id: str) -> Dict:
        """
        Synchronize a single project using smart MAX() merge strategy

        Args:
            project_id: Project ID to synchronize

        Returns:
            dict: Sync results with statistics
        """
        logger.info(f"🔄 [SmartSync] Starting sync for project {project_id}")

        try:
            # Get project info
            project = self.project_manager.get_project(project_id)
            if not project:
                return {
                    "success": False,
                    "error": "Project not found",
                    "project_id": project_id
                }

            project_name = project['name']
            logger.info(f"📊 [SmartSync] Project: {project_name}")

            # Get all accounts for this project
            accounts = self.project_manager.get_project_social_accounts(project_id)
            if not accounts:
                logger.info(f"⚠️ [SmartSync] No accounts found for project {project_id}")
                return {
                    "success": True,
                    "message": "No accounts to sync",
                    "project_id": project_id,
                    "synced_count": 0
                }

            logger.info(f"👥 [SmartSync] Found {len(accounts)} accounts to sync")

            # Step 1: Read current data from Google Sheets
            sheets_data = self._read_from_sheets(project_name, accounts)

            # Step 2: Parse fresh data from platforms (using existing snapshots as fresh data)
            # In the future, this could call actual parsers
            parsed_data = self._get_parsed_data(accounts)

            # Step 3: Merge using MAX() strategy
            merged_data = self._merge_max_strategy(sheets_data, parsed_data)

            # Step 4: Create daily snapshots (primary storage for metrics)
            snapshot_count = self._create_daily_snapshots(project_id, merged_data)

            logger.info(f"✅ [SmartSync] Completed for {project_name}: {snapshot_count} snapshots created")

            return {
                "success": True,
                "project_id": project_id,
                "project_name": project_name,
                "total_accounts": len(accounts),
                "snapshot_count": snapshot_count,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ [SmartSync] Error syncing project {project_id}: {e}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "project_id": project_id
            }

    def sync_all_active_projects(self) -> Dict:
        """
        Synchronize all active projects

        Returns:
            dict: Overall sync results
        """
        logger.info("🔄 [SmartSync] Starting sync for ALL active projects")

        try:
            # Get all active projects
            all_projects = self.project_manager.get_all_projects()
            active_projects = [p for p in all_projects if p.get('is_active', 1) == 1]

            logger.info(f"📊 [SmartSync] Found {len(active_projects)} active projects")

            results = []
            success_count = 0
            error_count = 0

            for project in active_projects:
                project_id = project['id']
                result = self.sync_project(project_id)
                results.append(result)

                if result.get('success'):
                    success_count += 1
                else:
                    error_count += 1

            logger.info(f"✅ [SmartSync] Batch sync completed: {success_count} succeeded, {error_count} failed")

            return {
                "success": True,
                "total_projects": len(active_projects),
                "success_count": success_count,
                "error_count": error_count,
                "results": results,
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ [SmartSync] Batch sync failed: {e}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

    def _read_from_sheets(self, project_name: str, accounts: List[Dict]) -> Dict[str, Dict]:
        """
        Read current data from Google Sheets

        Args:
            project_name: Project name in Sheets
            accounts: List of account dictionaries

        Returns:
            dict: Mapping of account_id to sheets data
        """
        sheets_data = {}

        try:
            # Get all rows from the project worksheet
            rows = self.sheets_manager.get_project_accounts(project_name)

            # Map by profile URL for easier lookup
            for row in rows:
                profile_url = row.get('Account URL', '') or row.get('Link', '')
                if profile_url:
                    # Determine platform from URL
                    url_lower = profile_url.lower()
                    platform = ''
                    if 'tiktok.com' in url_lower:
                        platform = 'tiktok'
                    elif 'instagram.com' in url_lower:
                        platform = 'instagram'
                    elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
                        platform = 'facebook'
                    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
                        platform = 'youtube'

                    sheets_data[profile_url] = {
                        'followers': self._safe_int(row.get('Followers', 0)),
                        'likes': self._safe_int(row.get('Likes', 0)),
                        'comments': self._safe_int(row.get('Comments', 0)),
                        'videos': self._safe_int(row.get('Videos', 0)),
                        'views': self._safe_int(row.get('Views', 0)),
                        'platform': platform,  # Include platform for merge strategy
                    }

            logger.info(f"📥 [SmartSync] Read {len(sheets_data)} accounts from Sheets")

        except Exception as e:
            logger.warning(f"⚠️ [SmartSync] Could not read from Sheets: {e}")
            # Continue with empty sheets_data (will use parsed data only)

        return sheets_data

    def _get_parsed_data(self, accounts: List[Dict]) -> Dict[str, Dict]:
        """
        Get fresh parsed data (currently uses existing SQLite data)

        In the future, this would call actual parsers for each platform.
        For now, we use the current SQLite data as "parsed" data.

        Args:
            accounts: List of account dictionaries from SQLite

        Returns:
            dict: Mapping of profile_link to parsed data
        """
        parsed_data = {}

        for account in accounts:
            profile_link = account.get('profile_link', '')
            if profile_link:
                parsed_data[profile_link] = {
                    'followers': account.get('followers', 0),
                    'likes': account.get('likes', 0),
                    'comments': account.get('comments', 0),
                    'videos': account.get('videos', 0),
                    'views': account.get('views', 0),
                    'platform': account.get('platform', '').lower(),  # Include platform for merge strategy
                }

        logger.info(f"🔍 [SmartSync] Loaded {len(parsed_data)} accounts from SQLite (parsed data)")

        return parsed_data

    def _merge_max_strategy(
        self,
        sheets_data: Dict[str, Dict],
        parsed_data: Dict[str, Dict]
    ) -> Dict[str, Dict]:
        """
        Merge sheets and parsed data using SHEETS PRIORITY strategy for ALL platforms

        ALL platforms: Sheets priority - use Sheets if > 0, otherwise fallback to parsed

        This ensures Google Sheets is the SOURCE OF TRUTH for all manual edits,
        while still allowing fallback to parsed data if Sheets is empty.

        Args:
            sheets_data: Data from Google Sheets (includes manual edits) - SOURCE OF TRUTH
            parsed_data: Fresh parsed data (fallback only)

        Returns:
            dict: Merged data with Sheets priority for all platforms
        """
        merged = {}

        # Get all unique profile URLs
        all_urls = set(sheets_data.keys()) | set(parsed_data.keys())

        for url in all_urls:
            sheets = sheets_data.get(url, {})
            parsed = parsed_data.get(url, {})

            # Determine platform (prefer sheets platform, fallback to parsed)
            platform = sheets.get('platform', '') or parsed.get('platform', '')

            # SHEETS PRIORITY for ALL platforms - Google Sheets is the SOURCE OF TRUTH
            # If Sheets has value > 0, use it. Otherwise fallback to parsed data.
            merged[url] = {
                'followers': sheets.get('followers', 0) if sheets.get('followers', 0) > 0 else parsed.get('followers', 0),
                'likes': sheets.get('likes', 0) if sheets.get('likes', 0) > 0 else parsed.get('likes', 0),
                'comments': sheets.get('comments', 0) if sheets.get('comments', 0) > 0 else parsed.get('comments', 0),
                'videos': sheets.get('videos', 0) if sheets.get('videos', 0) > 0 else parsed.get('videos', 0),
                'views': sheets.get('views', 0) if sheets.get('views', 0) > 0 else parsed.get('views', 0),
            }
            logger.info(f"📊 [SmartSync] {platform.upper() or 'UNKNOWN'} Sheets priority (source of truth) for {url}")

        logger.info(f"🔀 [SmartSync] Merged {len(merged)} accounts using SHEETS PRIORITY strategy")

        return merged

    def _create_daily_snapshots(self, project_id: str, merged_data: Dict[str, Dict]) -> int:
        """
        Create daily snapshots for historical tracking

        Only creates one snapshot per account per day.

        Args:
            project_id: Project ID
            merged_data: Merged data to snapshot

        Returns:
            int: Number of snapshots created
        """
        snapshot_count = 0
        today = datetime.utcnow().date()

        # Get all accounts for this project
        accounts = self.project_manager.get_project_social_accounts(project_id)

        for account in accounts:
            profile_link = account.get('profile_link', '')
            account_id = account.get('id')

            if not account_id or profile_link not in merged_data:
                continue

            try:
                # Check if snapshot already exists for today
                # get_account_snapshots signature: (account_id, start_date, end_date, limit)
                today_str = today.isoformat()
                existing_snapshots = self.project_manager.get_account_snapshots(
                    account_id=account_id,
                    start_date=today_str,
                    end_date=today_str,
                    limit=1
                )

                metrics = merged_data[profile_link]

                # UPDATE existing snapshot if it exists, otherwise CREATE new one
                if existing_snapshots and len(existing_snapshots) > 0:
                    # Update existing snapshot with new data AND new timestamp
                    existing_snapshot_id = existing_snapshots[0].get('id')
                    logger.info(f"📝 [SmartSync] Updating existing snapshot {existing_snapshot_id} for account {account_id}")

                    # Update snapshot in database with current UTC time
                    self.project_manager.db.cursor.execute('''
                        UPDATE account_snapshots
                        SET followers = ?, likes = ?, comments = ?, videos = ?, views = ?,
                            total_videos_fetched = ?, snapshot_time = ?
                        WHERE id = ?
                    ''', (
                        metrics.get('followers', 0),
                        metrics.get('likes', 0),
                        metrics.get('comments', 0),
                        metrics.get('videos', 0),
                        metrics.get('views', 0),
                        metrics.get('videos', 0),
                        datetime.utcnow().isoformat(),  # NEW timestamp!
                        existing_snapshot_id
                    ))
                    self.project_manager.db.commit()
                    snapshot_count += 1
                else:
                    # Create new snapshot with merged data
                    self.project_manager.add_account_snapshot(
                        account_id=account_id,
                        followers=metrics.get('followers', 0),
                        likes=metrics.get('likes', 0),
                        comments=metrics.get('comments', 0),
                        videos=metrics.get('videos', 0),
                        views=metrics.get('views', 0),
                        total_videos_fetched=metrics.get('videos', 0)
                    )
                    snapshot_count += 1

            except Exception as e:
                logger.error(f"❌ [SmartSync] Failed to create snapshot for account {account_id}: {e}")

        logger.info(f"📸 [SmartSync] Created {snapshot_count} snapshots")

        return snapshot_count

    @staticmethod
    def _safe_int(value) -> int:
        """Safely convert value to int, returning 0 for invalid values"""
        try:
            # Remove commas and spaces from numbers
            if isinstance(value, str):
                value = value.replace(',', '').replace(' ', '').strip()
            return int(float(value))
        except (ValueError, TypeError):
            return 0


# Standalone function for easy calling
def sync_all_projects_standalone(db, sheets_credentials: str, sheets_name: str) -> Dict:
    """
    Standalone function to sync all projects (no Celery required)

    This can be called directly from:
    - HTTP endpoint
    - Cron job script
    - Manual testing

    Args:
        db: Database instance
        sheets_credentials: JSON string or path to Google Sheets credentials
        sheets_name: Name of the Google Sheets document

    Returns:
        dict: Sync results
    """
    try:
        from project_manager import ProjectManager
        from project_sheets_manager import ProjectSheetsManager

        # Initialize managers
        project_manager = ProjectManager(db)

        # ProjectSheetsManager expects: (credentials_file, spreadsheet_name, credentials_json)
        sheets_manager = ProjectSheetsManager(
            credentials_file="",  # Empty since we use credentials_json
            spreadsheet_name=sheets_name,
            credentials_json=sheets_credentials
        )

        # Create sync service and run
        sync_service = SmartSyncService(project_manager, sheets_manager)
        result = sync_service.sync_all_active_projects()

        return result

    except Exception as e:
        logger.error(f"❌ [SmartSync] Standalone sync failed: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


def sync_single_project_standalone(
    db,
    sheets_credentials: str,
    sheets_name: str,
    project_id: str
) -> Dict:
    """
    Standalone function to sync a single project

    Args:
        db: Database instance
        sheets_credentials: JSON string or path to Google Sheets credentials
        sheets_name: Name of the Google Sheets document
        project_id: Project ID to sync

    Returns:
        dict: Sync results
    """
    try:
        from project_manager import ProjectManager
        from project_sheets_manager import ProjectSheetsManager

        # Initialize managers
        project_manager = ProjectManager(db)

        # ProjectSheetsManager expects: (credentials_file, spreadsheet_name, credentials_json)
        sheets_manager = ProjectSheetsManager(
            credentials_file="",  # Empty since we use credentials_json
            spreadsheet_name=sheets_name,
            credentials_json=sheets_credentials
        )

        # Create sync service and run
        sync_service = SmartSyncService(project_manager, sheets_manager)
        result = sync_service.sync_project(project_id)

        return result

    except Exception as e:
        logger.error(f"❌ [SmartSync] Standalone sync failed for project {project_id}: {e}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "timestamp": datetime.utcnow().isoformat()
        }
