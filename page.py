"""Page widgets are usually at the root of the widget hierarchy, and
is composed of other widgets."""
from __future__ import absolute_import

from datetime import datetime
from itertools import ifilter
import re

from django.contrib.auth.models import User
from django.core.urlresolvers   import resolve
from django.http                import HttpResponse, Http404
from django.template.loader     import render_to_string as django_render_to_string
from django.utils.html          import conditional_escape

from listings.listing.table   import ListingTable
from www.common.media_storage import media_file_storage
from www.common               import render_to_string
from www.common.context       import get_ip
from www.registration.captcha import is_captcha_needed
from www.reviews.views        import process_reviews_django
from www.widgets.templatetags.widgets import widget_linked_category
from www.wiki                 import settings
from util                     import mixlog
from util.django_models       import get_or_none
from util.dynvar              import bindings
from util.seq                 import nonrepeated
from util.functional          import pick, assoc, rassoc

from .widget import Widget
from .router import view, ajax, render_to_string_with_namespace
from .models import WikiPage

class NeedsAuthentication(Exception): pass

class NeedsCaptcha(Exception): pass

# used to replace urls like '/../place.html' with '/place.html' 
SLASH_DOTS_RE = re.compile(r'^/\.\.(?=/)')

class Page(Widget):
    def __init__(self, delegate):
        super(Page, self).__init__()

        self._delegate = delegate
        self.title = ''
        
        # This describes the last edit, and is populated for each
        # freeze().
        self.edit_user       = None
        self.edit_ip_address = None
        self.edit_time       = None
        self.latitude        = None
        self.longitude       = None
    
    def category_fget(self):
        return self._delegate.category

    def category_fset(self, value):
        self.delegate.category = value

    category = property(category_fget, category_fset)

    @property
    def category_title(self):
        return self._delegate.category_title

    @property
    def wiki(self):
        return self._delegate.wiki

    def freeze(self):
        transcoding = getattr(bindings, 'transcoding', None)
        if transcoding:
            self.edit_time = transcoding.version.created_at
            self.edit_user = transcoding.version.edit_user
            self.edit_ip_address = transcoding.version.edit_ip_address
        else:
            self.edit_time = datetime.now()
            if self.request:
                # `is_widget_authenticated_by' can be set by a widget to
                # override request authentication. For example, the photo
                # uploader widget uses this to let swfupload authenticate.
                is_widget_authenticated_by = \
                    getattr(self.request, 'is_widget_authenticated_by', False)
    
                if not (is_widget_authenticated_by
                        or self.delegate.user_can_edit(self.request.user)):
                    raise NeedsAuthentication
    
                if is_captcha_needed(self.request, consume=True):
                    raise NeedsCaptcha
    
                self.edit_user = is_widget_authenticated_by or self.request.user
                self.edit_ip_address = get_ip(self.request)
            
        super(Page, self).freeze()
        self.delegate.freeze(self)

    # Getters & setters
    def _get_delegate(self):
        return self._delegate

    def _set_delegate(self, delegate):
        self._delegate = delegate

    # We have to redefine the property, too, because class bindings
    # are lexical.
    delegate = property(_get_delegate, _set_delegate)

    # | Reversing is special for root widgets.
    #
    # `Page' is routed by a WikiPage, so we reverse it to a view that
    # knows how to route those, and thaw the page object.
    def reverse(self, view, *args, **kwargs):
        return self.delegate.reverse(
            super(Page, self).reverse(view, *args, **kwargs))

    def __getstate__(self):
        # Never store the delegate reference. This is always restored
        # for us when we're unfrozen.
        dict = super(Page, self).__getstate__()
    
        # _delegate may be missing if page was unpickled from memcached
        dict.pop('_delegate', None)

        # When freezing, don't store the user model, just store the id
        if dict['edit_user']:
            dict['edit_user'] = dict['edit_user'].id

        return dict

    def __setstate__(self, dict):
        super(Page, self).__setstate__(dict)

        # "Migrations":
        self.__dict__.setdefault('edit_user'       , None)
        self.__dict__.setdefault('edit_ip_address' , None)
        self.__dict__.setdefault('edit_time'       , None)
        self.__dict__.setdefault('latitude'        , None)
        self.__dict__.setdefault('longitude'       , None)
        
        if self.edit_user:
            # Explode the user id back into a django user model
            self.edit_user = get_or_none(User.objects, id=self.edit_user)
                

    # This is to support image serving on a per-page basis. We don't
    # technically need it, but it'll fail more gracefully if apache is
    # misconfigured. This also supports the use of reverse() for
    # images.
    @view(r'^image_(?P<media_hash>[^/]+)/(?P<photo_slug>[^./]+)(?P<ext>\.[^.]+)',
          'image')
    def image(self, request, media_hash, photo_slug, ext):
        # Apache should intercept urls of this form:
        # image_hhhhh/my-dog-spot.jpg and locally serve as if the url
        # was /media/hhhhh.jpg Warn if this function does not get
        # bypassed!
        mixlog().warning(
            'www.wiki.views.image called. Apache failed to intercept %s' %
            request.path)
        file_name = media_hash + ext
        mimetype = mimetypes.guess_type(file_name)[0]
        if not mimetype:
            raise Exception, "Image mime type undetermined"
        file = media_file_storage.open(file_name)    
        return HttpResponse(file.read(), mimetype=mimetype)

    @view(r'^-(?P<prev_num>\d+)', 'prev')
    def prev(self, request, prev_num):
        prev_num = int(prev_num)
        count = 0
        widget_state = self.get_state_object()
        old_widget = None
        while widget_state:
            if count == prev_num:
                old_widget = widget_state.widget
                old_widget.delegate = self.delegate
            count += 1
            widget_state = widget_state.previous            
        if not old_widget:
            raise Http404
        return HttpResponse(old_widget.render_previous_as_readonly(
                            prev_num, count - 1))

    # | Helpers for rendering templates.
    @property
    def edit_user_and_ip(self):
        return self.edit_user, self.edit_ip_address

    @property
    def creator_user_and_ip(self):
        return self.delegate.created_by, self.delegate.created_from_ip
                    

class OneColumnPage(Page):
    """The one-column page has one column of content, the order of
    which can be rearranged dynamically."""
    # | Valid widgets

    from .picturewidget import Picture
    from .headingwidget import Heading
    from .sectionwidget import Section
    from .listwidget    import List
    from .dividerwidget import Divider

    # These are specified in the order they appear in the toolbar for
    # adding widgets.
    WIDGETS = [
        ('heading' , Heading ),
        ('section' , Section ),
        ('list'    , List    ),
        ('image'   , Picture ),
        ('divider' , Divider ),
    ]

    # | Page control & rendering.

    def __init__(self, delegate):
        super(OneColumnPage, self).__init__(delegate)
        # `order' stores references to widgets in the order they
        # appear on the page.
        self.order = []

    def clear(self):
        del self.order[:]
        super(OneColumnPage, self).clear()

    @property
    def ordered(self):
        return [self[i] for i in self.order]

    def render_widget(self, widget, **kwargs):
        which = kwargs.pop('which', 'render')
        contents = getattr(widget, which)()
        template = kwargs.pop('template', 'widgets/_widget.html')

        context = kwargs.copy()
        context['widget']   = widget
        context['contents'] = contents
        context['page']     = self
        context['typename'] = rassoc(self.WIDGETS, widget.__class__)

        return render_to_string_with_namespace(
            widget.namespace, template, context)

    def render_widget_readonly(self, widget, **kwargs):
        return self.render_widget(widget,
                                  template='widgets/_widget_readonly.html',
                                  **kwargs)

    def base_template_and_context(self, base_template):
        """Defines the base template w/ its appropriate context."""
        title   = 'Untitled' if not self.title else self.title
        widgets = zip(self.ordered, map(self.render_widget, self.ordered))
        return 'widgets/onecolumn.html', {
            'addables'           : pick(0, self.WIDGETS),
            'widgets'            : widgets,
            'page'               : self,
            'title'              : title,
            'head_title'         : self.delegate.get_title_for_follower(),
            'base_template'      : base_template,
            'categories'         : settings.CATEGORIES,
        }

    @property
    def html_blob(self):
        """Concatenates all the html_blobs of widgets contained in this page."""
        return ''.join(child.html_blob for _, child in self.items())

    def render_embed(self, about, city_layout=False):
        """Render a version of onecolumn embeddable by city, business
        pages, etc.  If city_layout is True, use an alternate layout that
        doesn't use a header bar for the embed. """
        template, context = \
            self.base_template_and_context('widgets/onecolumn_embed.html')
        context['about'] = about
        context['city_layout'] = city_layout

        return django_render_to_string(template, context)


    def render_readonly(self):
        """Render a version of onecolumn as a snippet of formatted html."""
        title   = 'Untitled' if not self.title else self.title
        contents = ''.join(map(self.render_widget_readonly, self.ordered))

        return django_render_to_string('widgets/onecolumn_readonly.html',
                                       dict(title=title, contents=contents))


    def render_previous_as_readonly(self, prev_num, prev_count):
        """Render a non-editable previous version of onecolumn. """
        context = dict(contents=self.render_readonly(),
                       prev_num=prev_num,
                       prev_count=prev_count,
                       prev_link=None if prev_num >= prev_count else
                           self.reverse('prev', prev_num=str(prev_num + 1)),
                       next_link=None if prev_num <= 0 else
                           self.reverse('prev', prev_num=str(prev_num - 1)),
                       title='Untitled' if not self.title else self.title,
                       link=self.reverse('root'),
                       edit_time=self.edit_time,
                       user_and_ip=self.edit_user_and_ip)
        return render_to_string('widgets/onecolumn_previous.html', context,
                                base_opts = { 'page_actions_bar': False })


    def render(self, request):
        # Add map points
        map_points = request.ctx.get('map_points')
        request.ctx['map_points'] = self.render_map_points(map_points)

        # Mako map.html will call this Javascript function when the
        # user drags a marker.
        uri_ctx_override = {
            'gmap_drag_callback' : 'onecolumn_gmap_marker_dragend'}

        template, context = self.base_template_and_context('base.html')
        
        process_reviews_django(request,
                               context,
                               # get_full_path() also works, but I wanted to 
                               # keep this independant of the url resovler for
                               # now so widgets and wikis share reviews
                               '/%s/%s' % (self.delegate.wiki.slug,
                                          self.delegate.slug),
                               comments_only=True)

        # Use our djangomako renderer.
        return render_to_string(
            template, context, uri_ctx_override=uri_ctx_override)

    def render_map_points(self, map_points):
        if map_points is None:
            map_points = []

        # Add point for this page
        if self.latitude and self.longitude:
            name = conditional_escape(self.title)
            if map_points:
                # Override latitude/longitude of first map_point
                map_points[0]['name'] = name
                map_points[0]['url']  = ''
                map_points[0]['lat']  = self.latitude
                map_points[0]['lon']  = self.longitude
            else:
                # Add map_point with latitude/longitude
                point = {'type' : 'wiki',
                         'name' : name,
                         'lat'  : self.latitude,
                         'lon'  : self.longitude}
                map_points = [point]

        uris = set(pick(1, self.links()))
        # Skip urls that don't start with /, and replace leading /../ with /
        uris = [SLASH_DOTS_RE.sub('', u) for u in uris if u.startswith('/')]

        # Add business listings
        for uri in uris:
            guid = uri[1:]
            if '/' in guid:
                # Non-listing link
                continue
            listing = ListingTable.get_by_guid(guid)
            if not listing:
                # Not a GUID
                continue
            if not listing.latitude or not listing.longitude:
                # No latitude/longitude
                continue
            point = {'type'    : '',
                     'name'    : conditional_escape(listing.name),
                     'url'     : uri,
                     'address' : listing.address_line,
                     'lat'     : listing.latitude,
                     'lon'     : listing.longitude}
            map_points.append(point)

        # Add wiki pages
        from .views import wiki_page as wiki_page_view # cyclic dependency
        self_wiki_slug = self.delegate.wiki.slug
        for uri in uris:
            try:
                view, _, kwargs = resolve(uri)
            except Http404:
                # If link didn't resolve, don't 404 the whole page.
                continue                
            if view != wiki_page_view:
                # Not a wiki page
                continue
            page_slug = kwargs['page_slug']
            wiki_slug = kwargs['wiki_slug']
            if wiki_slug != self_wiki_slug:
                # Skip if in different wiki home
                continue
            try:
                wiki_page = WikiPage.objects.get(slug=page_slug,
                                                 wiki__slug=wiki_slug)
            except WikiPage.DoesNotExist:
                # Non-existant WikiPage
                continue
            if wiki_page == self.delegate:
                # Ignore self
                continue
            if not wiki_page.page.latitude or not wiki_page.page.longitude:
                # No latitude/longitude
                continue
            point = {'type' : '',
                     'name' : conditional_escape(wiki_page.page.title),
                     'url'  : uri,
                     'lat'  : wiki_page.page.latitude,
                     'lon'  : wiki_page.page.longitude}
            map_points.append(point)

        return map_points

    # | AJAX callbacks.

    @ajax('add-widget')
    def add_widget(self, addable):
        widget = assoc(self.WIDGETS, addable)()
        self.order.insert(0, self.append(widget))
        self.freeze()
        return self.render_widget(widget, which='render_edit', adding=True)

    @ajax('delete-widget')
    def delete_widget(self, which):
        for oi, o in enumerate(self.ordered):
            if which.startswith(o.namespace):
                break
        else:
            raise ValueError, 'Invalid widget'
        
        del self[self.order[oi]]
        del self.order[oi]
        self.freeze()

    @ajax('save-order')
    def save_order(self, order):
        order = order.split(',')
        for key, widget in self.items():
            for oi, o in enumerate(order):
                if o.startswith(widget.namespace):
                    self.order[oi] = key

        if nonrepeated(self.order) != self.order:
            raise ValueError, 'Order cannot have repeats.'

        self.freeze()

    @ajax('save-title-category')
    def save_title_category(self, title, category):
        if title:
            self.title = title
        if category:
            self.category = category
        if title or category:
            self.freeze()
        return {}

    @ajax('get-edit-info')
    def get_edit_info(self):
        return django_render_to_string(
            'widgets/_onecolumn_edit_info.html', {'page': self})

    # | Application support
    def get_representative_photo(self):
        # We just pick the first one that is active.
        try:
            return ifilter(
                lambda w: isinstance(w, assoc(self.WIDGETS, 'image')),
                self.ordered).next().picture
        except StopIteration:
            return None

    @ajax('set-lat-lng')
    def set_lat_lng(self, lat, lng):
        try:
            # Must be floats, but store as strings
            float(lat)
            float(lng)
        except ValueError:
            return
        self.latitude, self.longitude = lat, lng
        self.freeze()
