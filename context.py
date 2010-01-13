"""Add widgets onto URI contexts."""
from django.conf import settings

import www.common.context

from .models import WikiPage, WikiHome
from .page   import OneColumnPage

def home_widget_context(context):
    """If it exists, add the home wiki to the context, otherwise set
    it to None."""
    if 'id' not in context:
        return

    ctx  = context.setdefault('widgets', {})
    guid = context['id']

    if settings.WIDGETS_ENABLE_HOME_PAGE:
        wiki_page = WikiPage.objects.get_or_create_wikipage(guid, 'Home')
        ctx['wiki'] = wiki_page.wiki
        ctx['home'] = wiki_page.page
    else:
        ctx['wiki'], _ = WikiHome.objects.get_or_create(slug=guid)

if settings.WIDGETS_ENABLED:
    www.common.context.pre_processors.add(home_widget_context)
