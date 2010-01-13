import mimetypes

from django.conf            import settings
from django.http            import HttpResponse, HttpResponseNotAllowed
from django.utils.importlib import import_module
from django.contrib.auth    import SESSION_KEY, BACKEND_SESSION_KEY, load_backend

from atlas3.geo        import Point
from util.files        import normalize_extension_from_mime_type
from www.common.models import Photo

from .widget import Widget
from .router import view, ajax, render_template_with_namespace
from .flickr import FlickrImage

class Picture(Widget):
    """Upload, configure and display images."""
    BROKEN_SRC = ''
    WIDTH_OF_SIZE = {
        'large'  : 600,
        'medium' : 300,
        'small'  : 150,
    }

    css_container = 'picture'
    css_hover     = 'picture-over'

    def __init__(self):
        super(Picture, self).__init__()
        self.picture = None
        self.size    = 'small'
        self.title   = None

    @property
    def html_blob(self):
        return (self.title or '') + \
               (self.picture.caption if self.picture else '')

    def set_picture(self, **kwargs):
        image = kwargs['image']
        freeze = kwargs.pop('freeze', True)
        kwargs.setdefault('size', image.size)
        kwargs.setdefault('content_object', self.delegate.content_object)

        self.picture = Photo(**kwargs)
        self.picture.base_slug_on_file_name(image.name)

        mime_type = None
        if image.content_type == 'application/octet-stream':
            mime_type, encoding = mimetypes.guess_type(image.name)
            if not mime_type or encoding:
                mime_type = None

        if not mime_type:
            mime_type = image.content_type

        # Give the image an arbitrary name with the correct extension.
        ext = normalize_extension_from_mime_type(mime_type)
        if ext not in ('.jpg', '.gif', '.png', '.bmp'):
            raise ValueError, 'Please upload a gif, jpg, png, or bmp type image'

        self.picture.image.name = 'img' + ext
        self.picture.save()
        if freeze:
            self.freeze()

    @property
    def sizes(self):
        return sorted(self.WIDTH_OF_SIZE.keys(), key=self.WIDTH_OF_SIZE.get)

    @property
    def img_src(self):
        if not self.picture:
            return self.BROKEN_SRC

        try:
            h, w = self.picture.get_scaled_dimensions(
                self.WIDTH_OF_SIZE[self.size])
            thumb = self.picture.get_thumb(h, w, 'Stretch')
            return thumb.get_absolute_url()
        except IOError:
            return self.BROKEN_SRC

    @property
    def img_link(self):
        if not self.picture:
            return ''
        return self.picture.get_attribution_url()        

    @render_template_with_namespace
    def render(self):
        if not self.picture:
            return 'widgets/_no_picture.html', {}
        else:
            return 'widgets/_view_picture.html', {
                'widget': self,
            }

    @render_template_with_namespace
    def render_edit(self):
        if not self.picture:
            context = {
                'widget'               : self,
                'default_search_terms' : ' '.join(self.delegate.get_keywords()),
                'flickr_api_key'       : settings.FLICKR_API_KEY,
                'upload_url'           : self.reverse(self.upload),
                # The upload template needs to know if the user is
                # authenticated because we don't want to start
                # uploading without authentication.
                'is_authenticated'     : self.delegate.user_can_edit(
                                             self.request.user)
            }
            if 'current_town' in self.request.ctx:
                town = self.request.ctx['current_town'].census_sf1_city
                context['geo_pt'] = Point(x=float(town['INTPTLON']),
                                          y=float(town['INTPTLAT']))

            return 'widgets/_upload_picture.html', context
        else:
            return 'widgets/_configure_picture.html', {'widget': self}

    @view('^upload$')
    def upload(self, request):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        if 'picture' not in request.FILES:
            raise ValueError

        # Get the session. Wow. swfupload collects cookie values &
        # sticks them in the POST variables. We extract them &
        # authenticate the session manually.
        engine       = import_module(settings.SESSION_ENGINE)
        session_key  = request.POST.get(settings.SESSION_COOKIE_NAME)
        session      = engine.SessionStore(session_key)
        if session:
            try:
                user_id      = session[SESSION_KEY]
                backend_path = session[BACKEND_SESSION_KEY]
                backend      = load_backend(backend_path)
                user         = backend.get_user(user_id)
            except KeyError:
                user         = None

            self.request.is_widget_authenticated_by = user

        self.set_picture(image=request.FILES['picture'])

        return HttpResponse('ok')

    @ajax('edit')
    def edit(self):
        return self.render_edit()

    @ajax('save')
    def save(self, contents):
        self.freeze()
        return self.render()

    @ajax('configure-picture')
    @render_template_with_namespace
    def configure_picture(self):
        return 'widgets/_configure_picture.html', {
            'widget': self
        }

    @ajax('change-meta')
    def change_meta(self, size, caption, title):
        if size not in self.WIDTH_OF_SIZE:
            raise ValueError
        self.size            = size
        self.picture.caption = caption
        self.title           = title
        self.picture.save()
        self.freeze()

        return self.render()

    @ajax('upload-flickr-image')
    @render_template_with_namespace
    def upload_flickr_image(self, image_id):
        flickr = FlickrImage(image_id)
        self.set_picture(
            image      = flickr.temporary_file,
            attributes = flickr.attrs)

        # When we save the picture, something down the stack closes
        # the underlying file object, and the subsequent template
        # expects to be able to read the image (it will generate a
        # thumb most likely), so we reopen it ourselves. This isn't an
        # issue elsewhere because newly revived objects come with open
        # file handles.
        self.picture.image.file.open()

        return 'widgets/_configure_picture.html', {
            'widget': self
        }

    def __setstate__(self, dict):
        super(Picture, self).__setstate__(dict)

        # "Migrations":
        self.__dict__.setdefault('title', None)
