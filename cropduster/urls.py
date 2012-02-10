from django.conf.urls.defaults import patterns, url
import os

urlpatterns = patterns('',
	url(r'^upload/', "cropduster.views.upload", name='cropduster-upload'),
)
