import datetime
import re


def set_utc_default_tz(timestamp: datetime.datetime) -> datetime.datetime:
    """If the input timestamp has no timezone, set utc timezone"""
    if timestamp and timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=datetime.timezone.utc)
    else:
        return timestamp


def isoformat_Z(
    timestamp: datetime.datetime, timespec="milliseconds", zpattern=re.compile(r"(\+00?(:00?)?$)|Z$")
) -> str:
    """Return the timestamp in isoformat, with UTC timezone expressed as Z"""
    return re.sub(zpattern, "", timestamp.isoformat(timespec=timespec)) + "Z" if timestamp else timestamp
