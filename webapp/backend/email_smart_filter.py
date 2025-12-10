"""
Smart Email Filter
Умный фильтр для защиты от кражи аккаунтов и извлечения кодов
"""

import re
import logging
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)


class EmailSmartFilter:
    """Smart filter for email security and code extraction"""

    # Blacklist: стоп-слова для обнаружения попыток смены данных
    BLACKLIST_EN = [
        'change email', 'change e-mail', 'change your email',
        'update email', 'update your email',
        'reset password', 'change password',
        'change phone', 'update phone',
        'unlink', 'unlink account', 'remove account',
        'deactivate', 'delete account',
        'verify new email', 'confirm new email',
        'recovery email', 'alternate email',
        'primary email changed', 'email address changed'
    ]

    BLACKLIST_RU = [
        'смена почты', 'изменить почту', 'изменение почты',
        'сменить email', 'изменить email',
        'сброс пароля', 'смена пароля', 'изменить пароль',
        'изменить телефон', 'смена телефона',
        'отвязать', 'удалить аккаунт', 'деактивировать',
        'новая почта', 'резервная почта',
        'почта изменена', 'адрес изменен'
    ]

    BLACKLIST_UA = [
        'зміна пошти', 'змінити пошту',
        'скидання паролю', 'зміна паролю',
        'змінити телефон',
        "відв'язати", 'видалити акаунт'
    ]

    # Code trigger words (где обычно находятся коды)
    CODE_TRIGGER_WORDS = [
        'code', 'verification code', 'confirmation code', 'security code',
        'код', 'код подтверждения', 'код верификации', 'код безопасности',
        'ваш код', 'your code', 'one-time code', 'otp',
        'verification', 'authenticate', 'verify'
    ]

    def __init__(self):
        """Initialize filter"""
        # Объединяем все blacklist в один
        self.blacklist = (
            self.BLACKLIST_EN +
            self.BLACKLIST_RU +
            self.BLACKLIST_UA
        )

        # Compile regex для поиска кодов
        # Ищем от 4 до 8 цифр подряд
        self.code_pattern = re.compile(r'\b\d{4,8}\b')

        logger.info(f"✅ Smart filter initialized with {len(self.blacklist)} blacklist rules")

    def check_email_safety(self, subject: str, body: str) -> Tuple[bool, Optional[str]]:
        """
        Проверить письмо на безопасность (нет попыток смены данных)

        Args:
            subject: Тема письма
            body: Тело письма

        Returns:
            (is_safe, reason) - True если безопасно, False если найдены стоп-слова
        """
        # Объединяем subject и body для проверки
        full_text = f"{subject} {body}".lower()

        # Проверяем каждое стоп-слово
        for blacklisted_word in self.blacklist:
            if blacklisted_word.lower() in full_text:
                reason = f"Detected suspicious phrase: '{blacklisted_word}'"
                logger.warning(f"⚠️ {reason}")
                return False, reason

        return True, None

    def extract_codes(self, subject: str, body: str) -> List[str]:
        """
        Извлечь коды подтверждения из письма

        Args:
            subject: Тема письма
            body: Тело письма

        Returns:
            List of found codes (typically 4-8 digit numbers)
        """
        # Ищем коды в теме и теле
        full_text = f"{subject}\n{body}"

        # Находим все совпадения
        matches = self.code_pattern.findall(full_text)

        if not matches:
            return []

        # Фильтруем очевидно неподходящие (например, годы)
        filtered_codes = []
        for match in matches:
            # Исключаем годы (1900-2099)
            if match.startswith('19') or match.startswith('20'):
                if len(match) == 4:
                    continue

            filtered_codes.append(match)

        logger.info(f"📋 Found {len(filtered_codes)} potential codes")
        return filtered_codes

    def extract_verification_code(self, subject: str, body: str) -> Optional[str]:
        """
        Извлечь наиболее вероятный код верификации

        Args:
            subject: Тема письма
            body: Тело письма

        Returns:
            Most likely verification code or None
        """
        # Ищем триггерные слова в теме/теле
        full_text_lower = f"{subject} {body}".lower()

        has_trigger = any(
            trigger.lower() in full_text_lower
            for trigger in self.CODE_TRIGGER_WORDS
        )

        if not has_trigger:
            logger.info("ℹ️ No verification trigger words found")
            return None

        # Извлекаем все коды
        codes = self.extract_codes(subject, body)

        if not codes:
            return None

        # Выбираем наиболее вероятный код
        # Приоритет: 6 цифр > 5 цифр > 4 цифры > 7-8 цифр
        code_priorities = {
            6: 1,  # Самый частый формат
            5: 2,
            4: 3,
            7: 4,
            8: 5
        }

        best_code = min(codes, key=lambda c: code_priorities.get(len(c), 99))
        logger.info(f"✅ Selected best code: {best_code} (length: {len(best_code)})")

        return best_code

    def analyze_email(self, subject: str, body: str) -> Dict:
        """
        Полный анализ письма

        Args:
            subject: Тема письма
            body: Тело письма

        Returns:
            Dict with analysis results
        """
        # Проверка безопасности
        is_safe, unsafe_reason = self.check_email_safety(subject, body)

        # Извлечение кодов
        all_codes = self.extract_codes(subject, body)
        verification_code = self.extract_verification_code(subject, body) if is_safe else None

        return {
            'is_safe': is_safe,
            'unsafe_reason': unsafe_reason,
            'all_codes': all_codes,
            'verification_code': verification_code,
            'has_codes': len(all_codes) > 0
        }


if __name__ == "__main__":
    # Test smart filter
    logging.basicConfig(level=logging.INFO)

    filter = EmailSmartFilter()

    # Test 1: Безопасное письмо с кодом
    print("\n--- Test 1: Safe Email ---")
    subject1 = "Your verification code"
    body1 = "Your TikTok verification code is: 123456. This code will expire in 10 minutes."

    result1 = filter.analyze_email(subject1, body1)
    print(f"Is Safe: {result1['is_safe']}")
    print(f"Verification Code: {result1['verification_code']}")

    # Test 2: Опасное письмо (попытка смены)
    print("\n--- Test 2: Unsafe Email ---")
    subject2 = "Email change requested"
    body2 = "We received a request to change your email address. Click here to confirm."

    result2 = filter.analyze_email(subject2, body2)
    print(f"Is Safe: {result2['is_safe']}")
    print(f"Reason: {result2['unsafe_reason']}")

    # Test 3: Русское письмо с кодом
    print("\n--- Test 3: Russian Email ---")
    subject3 = "Код подтверждения"
    body3 = "Ваш код: 789012. Никому не сообщайте этот код."

    result3 = filter.analyze_email(subject3, body3)
    print(f"Is Safe: {result3['is_safe']}")
    print(f"Verification Code: {result3['verification_code']}")

    # Test 4: Опасное на русском
    print("\n--- Test 4: Russian Unsafe ---")
    subject4 = "Смена почты"
    body4 = "Вы запросили смену почты на вашем аккаунте"

    result4 = filter.analyze_email(subject4, body4)
    print(f"Is Safe: {result4['is_safe']}")
    print(f"Reason: {result4['unsafe_reason']}")
