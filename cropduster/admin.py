from django.contrib import admin
from cropduster.models import Size, SizeSet


class SizeInline(admin.TabularInline):
    model = Size
#    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {
            'fields': (
#                'name',
#                'slug',
                'width',
                'height',
#                'auto_crop',
                'size_set',
#               'aspect_ratio',
#                'retina',
            ),
        }),
    )
    max_num = 1
    min_num = 1

    def __init__(self, *args, **kwargs):
        super(SizeInline, self).__init__(*args, **kwargs)
        self.can_delete = False

class SizeSetAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    inlines = [SizeInline]

admin.site.register(SizeSet, SizeSetAdmin)

