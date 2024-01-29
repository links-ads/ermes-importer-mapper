from contextlib import contextmanager
from sqlalchemy.orm.session import Session
from importer.database.session import SessionLocal


def db_webserver() -> Session:
    """Generator function that yields a DB session instance with a safe try-catch wrapper.

    :return: SessionLocal instance
    :rtype: Session
    :yield: session instance to be closed
    :rtype: Iterator[Session]
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def db_session() -> Session:
    """Generator function that yields a DB session instance with a safe try-catch wrapper.

    :return: SessionLocal instance
    :rtype: Session
    :yield: session instance to be closed
    :rtype: Iterator[Session]
    """
    return db_webserver()
