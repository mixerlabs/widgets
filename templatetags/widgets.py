from __future__ import absolute_import

from django.core.urlresolvers       import reverse
from django.template.loader         import render_to_string
from django.template.defaultfilters import stringfilter
from django                         import template

from util.str import random_key
from util.url import merge_cgi_params

from www.profiles.utils import screen_name_from_user
from www.widgets.router import subns
from www.widgets.models import WikiPage
from www.wiki.common    import settings

register = template.Library()

@register.tag
def widget_callback(parser, token):
    try:
        _, variable = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, (
            '%r tag requires exactly one argument' % (token.contents.split()[0]))

    return Callback(variable)

class Callback(template.Node):
    def __init__(self, variable):
        self.variable = variable

    def render(self, context):
        raise ValueError

@register.tag
def widget_call(parser, token):
    try:
        _, widget, name = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, (
            '%r tag requires exactly two arguments' % (
                token.contents.split()[0]))

    nodes = parser.parse(('endwidget_call',))
    parser.delete_first_token()
    for i, node in enumerate(nodes):
        if isinstance(node, Callback):
            # We found a callback node, separate out args & callback,
            # parsing also the variable argument.
            args     = template.NodeList(nodes[:i])
            callback = template.NodeList(nodes[i + 1:])
            variable = node.variable
            break
    else:
        # Nothing found, we don't have a callback.
        args     = nodes
        callback = template.NodeList()
        variable = 'data'

    return Call(widget, name, variable, args, callback)

class Call(template.Node):
    def __init__(self, widget, name, variable, args, callback):
        self.widget   = template.Variable(widget)
        self.name     = template.Variable(name)
        self.args     = args
        self.callback = callback
        self.variable = variable

    def render(self, context):
        widget = self.widget.resolve(context)
        name   = self.name.resolve(context)

        return render_to_string(
            'widgets/_call.js', {
                'ajaxurl'  : widget.reverse_ajax(name),
                'args'     : self.args.render(context),
                'variable' : self.variable,
                'callback' : self.callback.render(context),
                'name'     : '_' + random_key(10),
            })

@register.simple_tag
def widget_ajaxurl(widget, name):
    return widget.reverse_ajax(name)

@register.simple_tag
def widget_url(widget, name):
    return widget.reverse(name)
    
@register.simple_tag
def widget_page_snippet(widget_page, max_length=80):
    """Text snippet for a page."""
    text = widget_page.tokens
    if len(text) <= max_length:
        return text
    snippet = text[:max_length-3]
    index = snippet.rfind(' ')
    if index >= 0:
        snippet = snippet[:index].rstrip(' .')
    snippet = snippet + '...'
    return snippet

@register.simple_tag
def widget_page_linked_user(widget_page, utype):
    if utype == 'creator':
        user, ip = widget_page.created_by, widget_page.created_from_ip
    else:
        user, ip = widget_page.page.edit_user_and_ip

    if user:
        return '<a href="%s">%s</a>' % (
            reverse('view_profile', args=[user.username]), 
                    screen_name_from_user(user))
    elif ip:
        return ip     
    return ''   

@register.inclusion_tag('widgets/_page_group.html')
def widget_page_group(page_set, order):
    """Group of page results. `page_set' is the list of pages to display.
    `order' determines whether edit time and edit user are shown. Values
    for `order' can be:
        - recent: display edit time
        - title: display edit time and user
        - .*: no edit time or user"""
    show_last_edit_time = order=='recent'
    show_last_edit_user = order in ('title', 'recent')

    return {'page_set': page_set,
            'show_last_edit_time': show_last_edit_time,
            'show_last_edit_user': show_last_edit_user,
           }

@register.simple_tag
def widget_directory_url(wiki_slug):
    return reverse('widgets_wiki_directory',
                  kwargs={'wiki_slug': wiki_slug})

@register.simple_tag
def widget_changes_url(wiki_slug):
    return reverse('changes',
                  kwargs={'town': wiki_slug})

@register.simple_tag
def widget_create_page_url(wiki_slug, cat_id=None):
    url = reverse('widgets_create_page_dialog', kwargs={'wiki_slug': wiki_slug})
    if cat_id:
        url = merge_cgi_params(url, dict(cat=cat_id))
    return "javascript:$.mixerbox('%s', 'captcha_login')" % url

@register.simple_tag
def widget_category_url(wiki_slug, category):
    assert category in settings.CATEGORIES
    return reverse('widgets_wiki_category_directory',
                   kwargs={'wiki_slug': wiki_slug,
                           'category': category})

@register.simple_tag
def widget_linked_category(wiki_slug, category, extra=''):
    assert category in settings.CATEGORIES
    name = settings.CATEGORIES[category]['title']
    url = widget_category_url(wiki_slug, category)
    return '<a href="%s" category_id="%s">%s</a>' % (url, category, name)

@register.inclusion_tag('widgets/_recent.html')
def widget_recent_pages(wiki_slug, title, city_layout):
    return dict(title=title, city_layout=city_layout,
        recent=WikiPage.objects.recent_pages(wiki_slug),
        wiki_slug=wiki_slug)


# Unused, but probably handy soon:
## @register.filter
## @stringfilter
## def namespace(name, widget):
##     return subns(widget.template, name)
## namespace.is_safe = True
