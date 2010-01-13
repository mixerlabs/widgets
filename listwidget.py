from django.utils.safestring import mark_safe

from util.str import peel

from .       import html
from .widget import Widget
from .router import view, ajax, render_template_with_namespace

class List(Widget):
    """Lists are ordered items."""
    css_container = 'list'
    css_hover     = 'list-over'

    def __init__(self):
        super(List, self).__init__()
        self.items       = []
        self.title       = None
        self.description = None

    @property
    def html_blob(self):
        return (self.title or '')       + \
               (self.description or '') + \
               ' '.join(self.items)

    @render_template_with_namespace
    def render(self):
        return 'widgets/_view_list.html', {'widget': self}

    @render_template_with_namespace
    def render_edit(self):
        return 'widgets/_edit_list.html', {'widget': self}

    @ajax('edit')
    def edit(self):
        return self.render_edit()

    @ajax('save')
    def save(self, **kwargs):
        """Save a new version of the list.

        kwargs:
          title: List title
          description: List description
          item_0, item_1, ...: The items in the list (strings).
        """
        self.title       = mark_safe(html.clean(kwargs.pop('title')))
        self.description = kwargs.pop('description')

        self.items = ['']*len(kwargs)

        for k, v in kwargs.items():
            _, num = peel(k, '_')
            self.items[int(num)] = v

        # Kill empty items.
        self.items = filter(None, self.items)

        self.freeze()
        return self.render()

    def __setstate__(self, dict):
        super(List, self).__setstate__(dict)

        # "Migrations"
        self.__dict__.setdefault('title'       , None)
        self.__dict__.setdefault('description' , None)
