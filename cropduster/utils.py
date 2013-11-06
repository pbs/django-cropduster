# coding=utf-8
import os
from StringIO import StringIO
import datetime

from PIL import Image, ImageFile
from django.conf import settings
from django.forms.models import modelform_factory
from django.core.files.base import ContentFile

from filer.utils.files import (
    matching_file_subtypes
    )
from filer.models import Clipboard, ClipboardItem
from filer import settings as filer_settings
from filer.models import tools


# We have to up the max block size for an image when using optimize, or it
# will blow up
ImageFile.MAXBLOCK = 10000000 # ~10mb


def rescale(img, w=0, h=0, crop=True, **kwargs):
    """
    Rescale the given image, optionally cropping it to make sure the result
    image has the specified width and height.
    """
    dst_width, dst_height, dst_ratio = normalize_dimensions(img, (w, h), return_ratio=True)

    src_width, src_height = img.size
    src_ratio = float(src_width) / float(src_height)

    img_format = img.format
    if crop:
        if dst_ratio < src_ratio:
            crop_height = src_height
            crop_width = crop_height * dst_ratio
            x_offset = float(src_width - crop_width) / 2
            y_offset = 0
        else:
            crop_width = src_width
            crop_height = crop_width / dst_ratio
            x_offset = 0
            y_offset = float(src_height - crop_height) / 2

        img = img.crop((
            int(x_offset),
            int(y_offset),
            int(x_offset + crop_width),
            int(y_offset + crop_height),
        ))
    new_img = img.resize((int(dst_width), int(dst_height)), Image.ANTIALIAS)
    new_img.format = img_format

    return new_img


def normalize_dimensions(img, dimensions, return_ratio=False):
    """
    Given a PIL image and a tuple of (width, height), where `width` OR `height`
    are either numeric or NoneType, returns (dst_width, dst_height) where both
    dst_width and dst_height are integers, the None values having been scaled
    based on the image's aspect ratio.
    """
    max_width, max_height = dimensions
    dst_width, dst_height = max_width, max_height
    src_width, src_height = img.size

    if dst_width > 0 and dst_height > 0:
        pass
    elif dst_width <= 0:
        dst_width = float(src_width * max_height) / float(src_height)
    elif dst_height <= 0:
        dst_height = float(src_height * max_width) / float(src_width)
    else:
        raise ValueError("Width and height must be greater than zero")

    if return_ratio:
        dst_ratio = float(dst_width) / float(dst_height)
        return int(dst_width), int(dst_height), dst_ratio
    else:
        return int(dst_width), int(dst_height)


def create_cropped_image(image=None, x=0, y=0, w=0, h=0):
    if image is None:
        raise ValueError("A path must be specified")
    if w <= 0 or h <= 0:
        raise ValueError("Width and height must be greater than zero")

    img = Image.open(image.file.file)
    img.load()
    img_format = img.format
    new_img = img.crop((x, y, x + w, y + h))
    new_img.load()
    new_img.format = img_format
    return new_img


def rescale_signal(sender, instance, created, max_height=None, max_width=None, **kwargs):
    """
    Simplified image resize meant to work with post-save/pre-save tasks
    """

    max_width = max_width
    max_height = max_height

    if not max_width and not max_height:
        raise ValueError("Either max width or max height must be defined")

    if max_width and max_height:
        raise ValueError("To avoid improper scaling, only define a width or "
                         "a height, not both")

    if instance.image:
        im = Image.open(instance.image.path)

        if max_width:
            height = instance.image.height * max_width / instance.image.width
            size = max_width, height
        else:
            width = instance.image.width * max_height / instance.image.height
            size = width, max_height

        im.thumbnail(size, Image.ANTIALIAS)
        im.save(instance.image.path)


IMAGE_SAVE_PARAMS = {"quality": 85, "optimize": 1}


def save_image(image, path):
    """
    Attempts to save an image to the provided path.  If the
    extension provided is incorrect according to pil, it will
    try to give the correct extension.

    @param image: PIL image to save
    @type  image: PIL image

    @param path: Absolute path to the save location.
    @type  path: /path/to/image

    @returns path to image
    @rtype /path/to/image
    """
    assert os.path.isabs(path)
    dir_path, name = os.path.split(path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    tmp_path = os.path.join(dir_path, 'tmp.' + name)

    # Since people upload images with garbage extensions,
    # preserve the decoder format.  You will note that we pass
    # the format along anytime we transform an image in 'utils'
    if hasattr(settings, 'CROPDUSTER_TRANSCODE'):
        new_format = settings.CROPDUSTER_TRANSCODE.get(image.format, image.format)
    else:
        new_format = image.format
    image.save(tmp_path, new_format, **IMAGE_SAVE_PARAMS)
    os.rename(tmp_path, path)

    return path, new_format


def copy_image(image):
    """
    Copies an image, preserving format.

    @param image: PIL Image
    @type  image: PIL Image

    @return: Copy of PIL Image
    @rtype: PIL Image
    """
    img_format = image.format
    image = image.copy()
    image.format = img_format
    return image

#Inspired (or adapted, but not copy-pasted) from
# filer.admin.cliboardadmin.ClipboardAdmin.ajaxUpload.


UNKNOWN_EXTENSION = "##invalid##"


def try_to_guess_extension(img_file):
    try:
        return str(img_file.format).lower()
    except AttributeError:
        return UNKNOWN_EXTENSION


def replace_file_extension(img_file, filename):
    """
    Replace (junk or invalid extension) OR append the correct extension to an image file,
    based on the file's format metadata
    """
    file_ext = try_to_guess_extension(img_file)
    if file_ext != UNKNOWN_EXTENSION:
        idx = filename.rfind('.')
        # assume an extension length of maximum 4 chars
        # in case the file has a junk extension, that junk will be replaced: 'name.blah' -> 'name.jpeg'
        if idx != -1 and len(filename) - idx <= 5:
            filename = filename[0:idx] + '.' + file_ext
        else:
            # ...but 'something.blablabla' will be replaced with 'something.blablabla.jpeg'
            filename += '.' + file_ext
    return filename


SEP = '__'
CROP = SEP + 'crop' + SEP


def compose_filename(filer_img):
    """
    Mark the filer images that were cropped with a naming convention
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
    crt_file_name = os.path.basename(filer_img.image.file.name)
    already_cropped = os.path.basename(filer_img.image.file.name).startswith(CROP)

    if not already_cropped:
        # __crop__$timestamp__$original_filename
        filename = CROP + '{0}{1}{2}'.format(timestamp, SEP, crt_file_name)
    else:
        # replace old $timestamp with new $timestamp => __crop__$new_timestamp__$original_filename
        start = len(CROP)
        end = crt_file_name.find(SEP, start)
        if (start, end) != (-1, -1):
            filename = crt_file_name[:start] + timestamp + crt_file_name[end:]
        else:
            # maybe it was renamed from the interface and does not follow the (exact) naming convention
            filename = '{0}{1}{2}'.format(timestamp, SEP, crt_file_name)
    return filename


def save_cropped_img_to_filer(request, filer_img, cropped_pil_img):
    """
    Try to save the cropped image as a new filer image instance
    """
    filename = compose_filename(filer_img)
    # the extension we get from the filer cannot be trusted (since when renaming a file, the extension can be
    # either eliminated, either given an arbitrary value) => guess it and replace it
    filename = replace_file_extension(cropped_pil_img, filename)

    # Get clipboard
    clipboard = Clipboard.objects.get_or_create(user=request.user)[0]
    if any(f for f in clipboard.files.all() if f.actual_name == filename):
        return None

    matched_file_types = matching_file_subtypes(filename, cropped_pil_img, request)
    file_form = modelform_factory(model=matched_file_types[0], fields=('original_filename', 'owner', 'file'))

    data = StringIO()
    cropped_pil_img.save(data, cropped_pil_img.format)
    data.seek(0)
    _file = ContentFile(data.read(), filename)
    upload_form = file_form({'original_filename': filename,
                             'owner': request.user.pk},
                            {'file': _file})
    if upload_form.is_valid():
        file_obj = upload_form.save(commit=False)
        # Enforce the FILER_IS_PUBLIC_DEFAULT
        file_obj.is_public = filer_settings.FILER_IS_PUBLIC_DEFAULT
        file_obj.save()
        clipboard_item = ClipboardItem(clipboard=clipboard, file=file_obj)
        clipboard_item.save()

        tools.move_files_from_clipboard_to_folder(request, clipboard,
                                                  filer_img.image.folder)
        clipboard_item.delete()
        clipboard.files.clear()
        return file_obj.id
    return None
