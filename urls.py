"""Views for widgets."""

from __future__ import absolute_import

from django.conf.urls.defaults import url, patterns

from . import views

# Our definition of a slug, appropriate for wikis, etc.:
SLUG_RE = r'[A-Z0-9][a-zA-Z0-9-]+'

urlpatterns = patterns('',
    # Handle the root case explicitly, so we don't require a trailing
    # slash.
    url(r'^(?P<page_slug>' + SLUG_RE + r')$',
        views.wiki_page, name='widgets_wiki_page_root', kwargs={'rest': ''}),

    # This is the general case, where we have a remainder URL to pass
    # on to the widget hierarchy.
    url(r'^(?P<page_slug>' + SLUG_RE + r')/(?P<rest>.*)$',
        views.wiki_page, name='widgets_wiki_page'),

    # | Other toplevels.
    url(r'^directory$', views.directory, name='widgets_wiki_directory'),
    url(r'^directory/best_ofs$', views.directory, 
        name='widgets_wiki_directory_best_of', kwargs={'best_ofs': True}),
    url(r'^directory/(?P<category>[\w-]+)$',
        views.directory,
        name='widgets_wiki_category_directory'),
    url(r'^directory/(?P<category>[\w-]+)/best_ofs$',
        views.directory,
        name='widgets_wiki_category_directory_best_of', 
        kwargs={'best_ofs': True}),
    url(r'^browser_ajax$', views.browser_ajax,
        name='widgets_browser_ajax'),
    url(r'^create_page_dialog$', views.create_page_dialog,
        name='widgets_create_page_dialog'),
    
)
