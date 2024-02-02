from datetime import datetime
from datetime import timezone
from typing import Any, Dict
from sqlalchemy.types import DateTime, TypeDecorator
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


class APIModel(Base):
    """
    Extension of db.Model that provides dictionary converters.
    """

    __abstract__ = True

    def as_dict(self) -> Dict[str, Any]:
        """Returns the following instance as a dictionary of key-value pairs.

        :return: dictionary of (column name, columns value)
        :rtype: Dict[str, Any]
        """
        return dict((column.name, getattr(self, column.name)) for column in self.__table__.columns)

    def props_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        """Returns a dictionary of key-value pairs, excluding primary keys, useful for update queries.

        :param exclude_none: whether to keep missing values or not, defaults to False
        :type exclude_none: bool, optional
        :return: dictionary with the entity attributes, without primary key.
        :rtype: Dict[str, Any]
        """
        items = self.as_dict()
        items.pop(list(self.__table__.primary_key)[0].name)
        if exclude_none:
            items = {k: v for k, v in items.items() if v is not None}
        return items


class TimezoneDateTime(TypeDecorator):
    """
    Extension of the basic DateTime class, returning non-naive UTC timestamps,
    while still using non-timezone timestamps in the DB.
    """

    impl = DateTime
    cache_ok = False

    def process_result_value(self, value: datetime, dialect: Any) -> datetime:
        """Returns a non-naive datetime, by extending the naive result and adding the UTC timezone

        :param value: datetime as returned by the SQLAlchemy conversion
        :type value: datetime
        :param dialect: database dialect, Postgresql in this case
        :type dialect: Any
        :return: datetime containing the correct timezone information
        :rtype: datetime
        """
        if value is not None:
            return value.replace(tzinfo=timezone.utc)
