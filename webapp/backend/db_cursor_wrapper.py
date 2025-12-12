"""
Database cursor wrapper для совместимости SQLite и PostgreSQL
Автоматически конвертирует ? в %s для PostgreSQL
"""


class CursorWrapper:
    """Обертка для курсора, конвертирующая ? в %s для PostgreSQL"""

    def __init__(self, cursor, is_postgres=False):
        self._cursor = cursor
        self._is_postgres = is_postgres

    def execute(self, query, params=None):
        """Выполнить SQL запрос, конвертируя ? в %s для PostgreSQL"""
        if self._is_postgres and '?' in query:
            # Конвертируем ? в %s для PostgreSQL
            query = query.replace('?', '%s')

        if params:
            return self._cursor.execute(query, params)
        else:
            return self._cursor.execute(query)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def __getattr__(self, name):
        """Проксируем все остальные атрибуты к оригинальному курсору"""
        return getattr(self._cursor, name)
