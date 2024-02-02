from importer.factory import create_app
from importer.settings.instance import settings

app = create_app(settings=settings)
