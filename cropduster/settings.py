import os.path

from django.conf import settings


CROPDUSTER_ROOT = getattr(settings, 'CROPDUSTER_ROOT', os.path.normpath(os.path.dirname(__file__)))
CROPDUSTER_MEDIA_ROOT = getattr(settings, 'CROPDUSTER_MEDIA_ROOT', os.path.join(CROPDUSTER_ROOT, 'media'))
CROPDUSTER_MEDIA_URL = getattr(settings, 'CROPDUSTER_MEDIA_URL', settings.STATIC_URL + 'cropduster/')
MAX_WIDTH = getattr(settings, 'CROPDUSTER_MAX_WIDTH', 1000)
MAX_HEIGHT = getattr(settings, 'CROPDUSTER_MAX_HEIGHT',  1000)