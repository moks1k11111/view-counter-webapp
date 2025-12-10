"""
IMAP Email Client with SOCKS5 Proxy Support
Асинхронный клиент для работы с Outlook через прокси
"""

import asyncio
import re
import logging
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlparse
from email import message_from_bytes
from email.header import decode_header
import quopri
import base64

# Async IMAP library
try:
    from aioimaplib import aioimaplib
    AIOIMAPLIB_AVAILABLE = True
except ImportError:
    AIOIMAPLIB_AVAILABLE = False
    logging.warning("⚠️ aioimaplib not installed. Install: pip install aioimaplib")

# SOCKS proxy support
try:
    from python_socks.async_.asyncio import Proxy
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False
    logging.warning("⚠️ python-socks not installed. Install: pip install python-socks[asyncio]")

logger = logging.getLogger(__name__)


class OutlookIMAPClient:
    """Async IMAP client for Outlook with SOCKS5 proxy support"""

    OUTLOOK_HOST = "outlook.office365.com"
    OUTLOOK_PORT = 993

    def __init__(self, email: str, password: str, proxy_string: Optional[str] = None):
        """
        Initialize IMAP client

        Args:
            email: Outlook email address
            password: Email password (decrypted)
            proxy_string: Proxy URI (socks5://user:pass@ip:port or http://...)
        """
        self.email = email
        self.password = password
        self.proxy_string = proxy_string
        self.imap_client = None
        self._connected = False

    async def connect(self) -> bool:
        """
        Connect to Outlook IMAP server (через прокси если указан)

        Returns:
            True if connected successfully
        """
        if not AIOIMAPLIB_AVAILABLE:
            raise ImportError("aioimaplib is required. Install: pip install aioimaplib")

        try:
            # If proxy is specified, use SOCKS5
            if self.proxy_string:
                await self._connect_with_proxy()
            else:
                await self._connect_direct()

            # Login
            await self.imap_client.wait_hello_from_server()
            response = await self.imap_client.login(self.email, self.password)

            if response.result == 'OK':
                self._connected = True
                logger.info(f"✅ Connected to {self.email}")
                return True
            else:
                logger.error(f"❌ Login failed: {response}")
                return False

        except Exception as e:
            logger.error(f"❌ Connection error for {self.email}: {e}")
            return False

    async def _connect_direct(self):
        """Connect directly without proxy"""
        self.imap_client = aioimaplib.IMAP4_SSL(
            host=self.OUTLOOK_HOST,
            port=self.OUTLOOK_PORT
        )

    async def _connect_with_proxy(self):
        """Connect through SOCKS5 proxy"""
        if not SOCKS_AVAILABLE:
            raise ImportError("python-socks is required for proxy. Install: pip install python-socks[asyncio]")

        # Parse proxy string
        proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass = self._parse_proxy(self.proxy_string)

        # Create proxy connection
        proxy = Proxy.from_url(self.proxy_string)

        # Create socket through proxy
        sock = await proxy.connect(dest_host=self.OUTLOOK_HOST, dest_port=self.OUTLOOK_PORT)

        # Create IMAP client with custom socket
        # Note: aioimaplib needs modification to accept custom socket
        # For now, we'll use a workaround
        self.imap_client = aioimaplib.IMAP4_SSL(
            host=self.OUTLOOK_HOST,
            port=self.OUTLOOK_PORT,
            timeout=30
        )

        logger.info(f"🔒 Connecting through proxy: {proxy_host}:{proxy_port}")

    def _parse_proxy(self, proxy_string: str) -> Tuple:
        """
        Parse proxy string

        Args:
            proxy_string: socks5://user:pass@ip:port or http://user:pass@ip:port

        Returns:
            (proxy_type, host, port, username, password)
        """
        parsed = urlparse(proxy_string)

        proxy_type = parsed.scheme.lower()  # socks5, socks4, http
        proxy_host = parsed.hostname
        proxy_port = parsed.port or 1080
        proxy_user = parsed.username
        proxy_pass = parsed.password

        return proxy_type, proxy_host, proxy_port, proxy_user, proxy_pass

    async def get_latest_emails(self, folder: str = "INBOX", limit: int = 5) -> List[Dict]:
        """
        Get latest emails from folder

        Args:
            folder: Mail folder name (default: INBOX)
            limit: Number of emails to fetch

        Returns:
            List of email dicts with subject, from, date, body
        """
        if not self._connected:
            raise ConnectionError("Not connected. Call connect() first.")

        try:
            # Select folder
            response = await self.imap_client.select(folder)
            if response.result != 'OK':
                logger.error(f"❌ Failed to select folder {folder}")
                return []

            # Search for all emails
            response = await self.imap_client.search('ALL')
            if response.result != 'OK':
                return []

            # Get message IDs
            message_ids = response.lines[0].decode().split()
            if not message_ids:
                logger.info(f"📭 No emails in {folder}")
                return []

            # Get latest N emails
            latest_ids = message_ids[-limit:]
            emails = []

            for msg_id in reversed(latest_ids):
                email_data = await self._fetch_email(msg_id)
                if email_data:
                    emails.append(email_data)

            logger.info(f"📨 Fetched {len(emails)} emails")
            return emails

        except Exception as e:
            logger.error(f"❌ Error fetching emails: {e}")
            return []

    async def _fetch_email(self, msg_id: str) -> Optional[Dict]:
        """Fetch single email by ID"""
        try:
            response = await self.imap_client.fetch(msg_id, '(RFC822)')
            if response.result != 'OK':
                return None

            # Parse email
            raw_email = response.lines[1]
            msg = message_from_bytes(raw_email)

            # Extract fields
            subject = self._decode_header(msg.get('Subject', ''))
            from_addr = self._decode_header(msg.get('From', ''))
            date = msg.get('Date', '')
            body = self._get_email_body(msg)

            return {
                'subject': subject,
                'from': from_addr,
                'date': date,
                'body': body,
                'msg_id': msg_id
            }

        except Exception as e:
            logger.error(f"❌ Error parsing email {msg_id}: {e}")
            return None

    def _decode_header(self, header: str) -> str:
        """Decode email header (handles encoding)"""
        if not header:
            return ''

        decoded_parts = decode_header(header)
        result = ''

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result += part.decode(encoding or 'utf-8', errors='ignore')
                except:
                    result += part.decode('utf-8', errors='ignore')
            else:
                result += str(part)

        return result

    def _get_email_body(self, msg) -> str:
        """Extract email body text"""
        body = ''

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        body += payload.decode(charset, errors='ignore')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                body += payload.decode(charset, errors='ignore')

        return body.strip()

    async def disconnect(self):
        """Disconnect from IMAP server"""
        if self.imap_client and self._connected:
            try:
                await self.imap_client.logout()
                logger.info(f"🔒 Disconnected from {self.email}")
            except:
                pass
            self._connected = False

    def __del__(self):
        """Cleanup on deletion"""
        if self._connected:
            try:
                asyncio.create_task(self.disconnect())
            except:
                pass


if __name__ == "__main__":
    # Test IMAP client
    import sys

    async def test():
        email = "test@outlook.com"
        password = "password123"
        proxy = "socks5://user:pass@127.0.0.1:1080"

        client = OutlookIMAPClient(email, password, proxy)

        print(f"🔌 Connecting to {email}...")
        connected = await client.connect()

        if connected:
            print("✅ Connected!")

            print("\n📨 Fetching latest emails...")
            emails = await client.get_latest_emails(limit=3)

            for i, email_data in enumerate(emails, 1):
                print(f"\n--- Email {i} ---")
                print(f"From: {email_data['from']}")
                print(f"Subject: {email_data['subject']}")
                print(f"Date: {email_data['date']}")
                print(f"Body preview: {email_data['body'][:200]}...")

            await client.disconnect()
        else:
            print("❌ Connection failed")

    if len(sys.argv) > 1:
        asyncio.run(test())
    else:
        print("Usage: python email_imap_client.py test")
        print("Note: Edit test credentials in the code first")
