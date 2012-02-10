from django.template import Library
from django.utils.encoding import iri_to_uri
from cropduster.settings import CROPDUSTER_MEDIA_URL

register = Library()

def cropduster_media_prefix():
	"""
	Returns the string contained in the setting ADMIN_MEDIA_PREFIX.
	"""
	return iri_to_uri(CROPDUSTER_MEDIA_URL)

cropduster_media_prefix = register.simple_tag(cropduster_media_prefix)
