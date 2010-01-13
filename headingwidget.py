from django.utils.html       import conditional_escape
from django.utils.safestring import mark_safe

from .       import html
from .widget import Widget
from .router import view, ajax, render_template_with_namespace

class Heading(Widget):
    """The heading widget providers headers"""
    css_container = 'header'
    css_hover     = 'header-over'

    def __init__(self):
        super(Heading, self).__init__()
        self.contents = 'Untitled'

    @property
    def html_blob(self):
        return self.contents

    def render(self):
        return mark_safe('<h2>%s</h2>' % conditional_escape(self.contents))

    @render_template_with_namespace
    def render_edit(self):
        return 'widgets/_edit_heading.html', {'widget': self}

    @ajax('edit')
    def edit(self):
        return self.render_edit()

    @ajax('save')
    def save(self, contents):
        self.contents = mark_safe(html.clean(contents))
        self.freeze()
        return self.render()
