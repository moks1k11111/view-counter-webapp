import asyncio
import imaplib
import email
from email.header import decode_header
import logging
import re
import base64
import requests
import ssl
from typing import Optional, List, Dict
from python_socks.sync import Proxy

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class OutlookOAuth2IMAPClient:
    """
    Outlook IMAP клиент с поддержкой OAuth2 аутентификации

    Использует refresh_token для получения access_token
    Поддерживает SOCKS5 прокси
    """

    def __init__(
        self,
        email: str,
        refresh_token: str,
        client_id: str,
        proxy_string: Optional[str] = None
    ):
        """
        Инициализация OAuth2 IMAP клиента

        :param email: Email адрес Outlook
        :param refresh_token: OAuth2 refresh token
        :param client_id: OAuth2 client ID
        :param proxy_string: SOCKS5 прокси в формате socks5://user:pass@host:port
        """
        self.email = email
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.proxy_string = proxy_string
        self.access_token = None
        self.imap = None

        # Outlook OAuth2 endpoints
        self.token_url = "https://login.live.com/oauth20_token.srf"
        self.imap_server = "outlook.office365.com"
        self.imap_port = 993

    def get_access_token(self) -> Optional[str]:
        """
        Получить access_token используя refresh_token

        :return: Access token или None при ошибке
        """
        try:
            data = {
                'client_id': self.client_id,
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token
            }

            # Если есть прокси - используем его для запроса
            proxies = None
            if self.proxy_string:
                proxies = {
                    'http': self.proxy_string,
                    'https': self.proxy_string
                }

            response = requests.post(
                self.token_url,
                data=data,
                proxies=proxies,
                timeout=30
            )

            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data.get('access_token')
                logger.info(f"✅ OAuth2: Access token получен для {self.email}")
                return self.access_token
            else:
                logger.error(f"❌ OAuth2: Ошибка получения токена: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"❌ OAuth2: Ошибка при запросе токена: {e}")
            return None

    def generate_auth_string(self) -> str:
        """
        Генерация строки аутентификации для IMAP XOAUTH2

        :return: Base64 encoded auth string
        """
        auth_string = f"user={self.email}\1auth=Bearer {self.access_token}\1\1"
        return base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

    async def connect(self) -> bool:
        """
        Подключение к Outlook IMAP с OAuth2

        :return: True если успешно, False при ошибке
        """
        try:
            # Получаем access token
            if not self.get_access_token():
                logger.error(f"❌ Не удалось получить access token для {self.email}")
                return False

            # Подключаемся к IMAP
            loop = asyncio.get_event_loop()

            def _connect():
                # IMAP4_SSL не поддерживает прокси напрямую
                # Для прокси нужно использовать python-socks
                if self.proxy_string:
                    logger.info(f"🔌 Подключение к IMAP через прокси: {self.proxy_string}")

                    # Парсим прокси строку
                    # Формат: socks5://user:pass@host:port или socks5h://user:pass@host:port
                    proxy_match = re.match(r'socks5h?://([^:]+):([^@]+)@([^:]+):(\d+)', self.proxy_string)
                    if not proxy_match:
                        raise ValueError(f"Неверный формат прокси: {self.proxy_string}")

                    proxy_user, proxy_pass, proxy_host, proxy_port = proxy_match.groups()

                    # Конвертируем socks5h:// в socks5:// (python-socks не поддерживает socks5h)
                    # socks5h означает что DNS резолвится через прокси, но для python-socks это не важно
                    proxy_url_normalized = self.proxy_string.replace('socks5h://', 'socks5://')

                    # Создаем SOCKS5 прокси
                    proxy = Proxy.from_url(proxy_url_normalized)
                    sock = proxy.connect(dest_host=self.imap_server, dest_port=self.imap_port)
                    logger.info(f"✅ SOCKS5 соединение установлено: {self.imap_server}:{self.imap_port}")

                    # Оборачиваем сокет в SSL
                    context = ssl.create_default_context()
                    ssl_sock = context.wrap_socket(sock, server_hostname=self.imap_server)
                    logger.info(f"✅ SSL handshake завершен")

                    # Создаем IMAP соединение через SSL-сокет
                    # Используем IMAP4 (не IMAP4_SSL!) и передаем готовый SSL-сокет
                    self.imap = imaplib.IMAP4(self.imap_server)
                    self.imap.sock = ssl_sock
                    # Читаем приветствие сервера
                    self.imap.welcome = self.imap._get_response()
                    logger.info(f"✅ IMAP приветствие получено: {self.imap.welcome}")
                else:
                    # Прямое подключение без прокси
                    self.imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)

                # Аутентификация через OAuth2
                auth_string = self.generate_auth_string()
                self.imap.authenticate('XOAUTH2', lambda x: auth_string.encode())

                logger.info(f"✅ Подключено к IMAP: {self.email}")
                return True

            result = await loop.run_in_executor(None, _connect)
            return result

        except imaplib.IMAP4.error as e:
            logger.error(f"❌ IMAP ошибка аутентификации для {self.email}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к IMAP для {self.email}: {e}")
            return False

    async def get_latest_emails(self, limit: int = 5) -> List[Dict]:
        """
        Получить последние N писем из inbox

        :param limit: Количество писем
        :return: Список словарей с информацией о письмах
        """
        if not self.imap:
            logger.error("❌ IMAP не подключен")
            return []

        try:
            loop = asyncio.get_event_loop()

            def _fetch():
                # Выбираем inbox
                self.imap.select("INBOX")

                # Ищем все письма
                status, messages = self.imap.search(None, 'ALL')
                if status != 'OK':
                    return []

                email_ids = messages[0].split()

                # Берем последние N
                latest_ids = email_ids[-limit:] if len(email_ids) > limit else email_ids

                emails = []

                for email_id in reversed(latest_ids):  # Новые сначала
                    status, msg_data = self.imap.fetch(email_id, '(RFC822)')

                    if status != 'OK':
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])

                            # Декодируем subject
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding or "utf-8", errors='ignore')

                            # Декодируем from
                            from_header, encoding = decode_header(msg.get("From"))[0]
                            if isinstance(from_header, bytes):
                                from_header = from_header.decode(encoding or "utf-8", errors='ignore')

                            # Получаем body
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    content_type = part.get_content_type()
                                    if content_type == "text/plain":
                                        try:
                                            body = part.get_payload(decode=True).decode(errors='ignore')
                                            break
                                        except:
                                            pass
                            else:
                                try:
                                    body = msg.get_payload(decode=True).decode(errors='ignore')
                                except:
                                    body = ""

                            emails.append({
                                "subject": subject,
                                "from": from_header,
                                "date": msg.get("Date"),
                                "body": body
                            })

                return emails

            emails = await loop.run_in_executor(None, _fetch)
            logger.info(f"✅ Получено {len(emails)} писем для {self.email}")
            return emails

        except Exception as e:
            logger.error(f"❌ Ошибка получения писем для {self.email}: {e}")
            return []

    async def disconnect(self):
        """Закрыть IMAP соединение"""
        if self.imap:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.imap.logout)
                logger.info(f"✅ IMAP отключен: {self.email}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при отключении IMAP: {e}")
