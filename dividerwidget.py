from django.utils.safestring import mark_safe

from .widget import Widget
from .router import view, ajax, render_template_with_namespace

class Divider(Widget):
    """The divider displays a simple horizontal rule."""
    css_container = 'divider'
    css_hover     = 'divider-over'

    def render(self):
        return mark_safe('<hr />')

    @render_template_with_namespace
    def render_edit(self):
        return 'widgets/_edit_divider.html', {}

    @ajax('edit')
    def edit(self):
        return self.render_edit()

    @ajax('save')
    def save(self, contents):
        self.freeze()
        return self.render()
