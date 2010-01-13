import sys

from django.utils.safestring import mark_safe
from django.core.paginator   import Paginator, InvalidPage

from .       import html
from .widget import Widget
from .router import (view, ajax, render_template_with_namespace,
                     render_to_string_with_namespace)

class Section(Widget):
    """Sections provide markdown-rendered paragraphs of text."""
    css_container = 'text'
    css_hover     = 'text-over'
    css_contents  = 'paragraphs'

    def __init__(self):
        super(Section, self).__init__()
        self.contents = ''
        self.title    = None

    @render_template_with_namespace
    def render(self):
        return 'widgets/_view_section.html', {'widget': self}

    @render_template_with_namespace
    def render_edit(self):
        return 'widgets/_edit_section.html', {'widget': self}

    @property
    def html_blob(self):
        return (self.title or '') + self.contents

    @ajax('edit')
    def edit(self):
        return self.render_edit()

    @ajax('save')
    def save(self, contents, title):
        if not contents:
            # This confuses the editor & its utilities less.
            contents = '<p></p>'

        try:
            self.contents = mark_safe(html.clean(contents))
        except Exception, e:
            print >>sys.stderr, \
                'exception (%r) while cleaning %s' % (e, contents)

        self.title = mark_safe(html.clean(title))

        self.freeze()
        return self.render()

    @view('^add-link-inline$', 'add-link-inline')
    def add_link_inline(self, request):
        from django.http import HttpResponse

        # This won't scale for very large wikis, but the fix is pretty
        # easy.
        recent = list(self.delegate.recent_wikipages())

        try:
            paginator = Paginator(recent, 5).page(request.GET.get('page', 1))
        except InvalidPage:
            raise Http404

        return HttpResponse(
            render_to_string_with_namespace(
                self.namespace, 'widgets/_edit_section_add_link_inline.html',
                {'paginator': paginator})
        )
