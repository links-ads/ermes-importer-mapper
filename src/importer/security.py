from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from importer.settings.constants import APP_APIKEY_HEADER
from importer.settings.instance import settings

api_key_header = APIKeyHeader(name=APP_APIKEY_HEADER, auto_error=True)


async def api_key_auth(api_key: str = Security(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
