from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from importer.settings.instance import settings

engine = create_engine(settings.database_url())
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal = scoped_session(session_factory)
SessionLocal = scoped_session(session_factory)
