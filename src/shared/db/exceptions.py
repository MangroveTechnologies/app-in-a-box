"""Database exception hierarchy."""
import psycopg2


class DatabaseError(Exception):
    def __init__(self, message, original_error=None):
        self.original_error = original_error
        super().__init__(message)


class ConnectionError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class QueryError(DatabaseError):
    pass


class TransactionError(DatabaseError):
    pass


class NotFoundError(DatabaseError):
    pass


class DuplicateError(DatabaseError):
    pass


def map_psycopg2_exception(exc, context=""):
    prefix = f"[{context}] " if context else ""
    msg = f"{prefix}{type(exc).__name__}: {exc}"

    if isinstance(exc, psycopg2.OperationalError):
        return ConnectionError(msg, exc)
    elif isinstance(exc, psycopg2.IntegrityError):
        error_msg = str(exc).lower()
        if "duplicate" in error_msg or "unique" in error_msg:
            return DuplicateError(msg, exc)
        return IntegrityError(msg, exc)
    elif isinstance(exc, psycopg2.ProgrammingError):
        return QueryError(msg, exc)
    elif isinstance(exc, psycopg2.InternalError):
        return TransactionError(msg, exc)
    else:
        return DatabaseError(msg, exc)
