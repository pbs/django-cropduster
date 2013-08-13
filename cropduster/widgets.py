import re

try:
    from collections import OrderedDict
except ImportError:
    from django.utils.datastructures import SortedDict as OrderedDict

from django import forms
from django.forms.widgets import Input
from django.forms.util import flatatt
from django.utils.html import escape, conditional_escape
from django.conf import settings
from django.contrib.admin import helpers
from django.contrib.admin.sites import site
from django.db.models.fields.files import ImageFieldFile
from django.template.loader import render_to_string
from django.utils.encoding import force_unicode

from .admin import cropduster_inline_factory
from .models import Image, Thumb
from .utils import json


class CropDusterThumbWidget(forms.SelectMultiple):

    def render_option(self, selected_choices, option_value, option_label):
        attrs = {}
        try:
            value = Thumb.objects.get(pk=option_value)
        except (TypeError, Thumb.DoesNotExist):
            pass
        else:
            attrs = {
                'data-width': value.width,
                'data-height': value.height,
            }
        option_value = force_unicode(option_value)
        if option_value in selected_choices:
            selected_html = u' selected="selected"'
            if not self.allow_multiple_selected:
                # Only allow for a single selection.
                selected_choices.remove(option_value)
        else:
            selected_html = ''
        return (
            u'<option value="%(value)s"%(selected)s%(attrs)s>%(label)s</option>') % {
                'value': escape(option_value),
                'selected': selected_html,
                'attrs': flatatt(attrs),
                'label': conditional_escape(force_unicode(option_label)),
        }


class CropDusterWidget(Input):

    sizes = None
    field = None

    class Media:
        css = {'all': (u'%scropduster/css/CropDuster.css' % settings.STATIC_URL,),}
        js = (
            u'%scropduster/js/jsrender.js' % settings.STATIC_URL,
            u'%scropduster/js/CropDuster.js' % settings.STATIC_URL,
        )

    def __init__(self, field=None, sizes=None, attrs=None):
        self.field = field
        self.sizes = sizes or self.sizes

        if attrs is not None:
            self.attrs = attrs.copy()
        else:
            self.attrs = {}
    
    def render(self, name, value, attrs=None, bound_field=None):
        final_attrs = self.build_attrs(attrs, type=self.input_type, name=name)
        # Whether we are rendering from the generated inline formset
        # or rendering on the actual form.
        if name.endswith('-id'):
            return u""

        obj = None
        image_value = ''

        if isinstance(value, ImageFieldFile):
            obj = value.cropduster_image
            image_value = value.name
            if image_value.startswith('/') and obj.image:
                image_value = obj.image.name
            value = getattr(obj, 'pk', None)
        elif isinstance(value, basestring) and not value.isdigit():
            try:
                obj = Image.objects.get(image=value)
            except Image.DoesNotExist:
                obj = None
                image_value = value
                value = None
            else:
                image_value = value
                value = obj.pk
        elif isinstance(value, (long, int)) or (isinstance(value, basestring) and value.isdigit()):
            try:
                obj = Image.objects.get(pk=value)
            except Image.DoesNotExist:
                pass
            else:
                if obj.image:
                    image_value = obj.image.name
        else:
            obj = value
            try:
                value = obj.pk
            except AttributeError:
                obj = None
        if image_value and image_value.startswith(settings.MEDIA_ROOT):
            image_value = re.sub(r'^%s/?' % re.compile(settings.MEDIA_ROOT), '', image_value)

        if isinstance(obj, Image) and not obj.image and image_value:
            obj.image = image_value

        thumbs = OrderedDict({})

        if value:
            if obj is None:
                obj = Image.objects.get(pk=value)
            if obj is not None:
                for thumb in obj.thumbs.all().order_by('-width'):
                    size_name = thumb.name
                    thumbs[size_name] = obj.get_image_url(size_name)

        final_attrs.update({
            'value': value or u"",
            'sizes': json.dumps(self.sizes),
        })

        formfield = getattr(bound_field, 'field', None)
        related = getattr(formfield, 'related', None)
        dbfield = getattr(related, 'field', None)
        image_field = getattr(dbfield, 'image_field', None)

        formset = self.get_inline_admin_formset(name, value, instance=obj, bound_field=bound_field)
        return render_to_string("cropduster/custom_field.html", {
            'upload_to': getattr(image_field, 'upload_to', ''),
            'image_value': image_value,
            'inline_admin_formset': formset,
            'prefix': name,
            'media_url': settings.MEDIA_URL,
            'final_attrs': final_attrs,
            'thumbs': thumbs,
        })

    def get_inline_admin_formset(self, name, value, instance=None, bound_field=None):
        formfield = getattr(bound_field, 'field', None)
        related = getattr(formfield, 'related', None)
        dbfield = getattr(related, 'field', None)

        if dbfield is None:
            return None
        request = getattr(formfield, 'request', None)
        inline_cls = cropduster_inline_factory(field=dbfield)
        inline = inline_cls(dbfield.model, site)

        FormSet = inline.get_formset(request, obj=instance)
        
        formset_kwargs = {
            'data': getattr(request, 'POST', None) or bound_field.form.data or None,
            'prefix': name,
        }
        if instance:
            formset_kwargs['instance'] = instance.content_object
            formset_kwargs['queryset'] = instance.__class__._default_manager

        formset = FormSet(**formset_kwargs)
        parent_admin = getattr(self, 'parent_admin', None)
        root_admin = getattr(parent_admin, 'root_admin', parent_admin)
        fieldsets = list(inline.get_fieldsets(request, instance))
        readonly = list(inline.get_readonly_fields(request, instance))
        return helpers.InlineAdminFormSet(inline, formset,
            fieldsets, readonly_fields=readonly, model_admin=root_admin)


def cropduster_widget_factory(sizes, related=None):
    return type('CropDusterWidget', (CropDusterWidget,), {
        'sizes': sizes,
        '__module__': CropDusterWidget.__module__,
        'related': related,
        'parent_model': getattr(related, 'model', None),
        'rel_field': getattr(related, 'field', None),
    })
