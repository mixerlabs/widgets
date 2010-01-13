"""Views for widgets."""
from __future__ import absolute_import

import simplejson

from django.conf                    import settings
from django.contrib.auth.models     import User
from django.core.paginator          import Paginator, InvalidPage
import django.db.models
from django.http                    import HttpResponse, HttpResponseForbidden
from django.core.urlresolvers       import reverse
from django.shortcuts               import (render_to_response as
                                            django_render_to_response)
from django.template.defaultfilters import escapejs

from util.db  import nestable_commit_on_success
from util.dict import getvalues
from util.seq import first

from .forms       import CreatePageForm
from .models      import WikiHome, WikiPage
from .page        import OneColumnPage, NeedsAuthentication, NeedsCaptcha
from .transcoding import append_wiki_to_onecolumnpage

from www.common                  import render_to_response, context as ctx
from www.common.tabs             import PAGES
from www.registration.captcha    import is_captcha_needed
from www.registration.decorators import login_required_inside_dialog
from www.wiki.models             import Page as Wiki_Page
from www.share.views             import render_share_widgets

def wiki_page(request, wiki_slug, page_slug, rest):
    """A wrapper around the real ``wiki_page'' to catch authentication
    errors in order to return the proper HTTP 403."""
    try:
        return _wiki_page(request, wiki_slug, page_slug, rest)
    except NeedsAuthentication:
        return HttpResponseForbidden('Needs authentication')
    except NeedsCaptcha:
        return HttpResponseForbidden('Needs captcha', status=409)

@nestable_commit_on_success
def _wiki_page(request, wiki_slug, page_slug, rest):
    """Route the request through a widget tree addressed by
    `wiki_slug' and `page_slug' (whose head is kept in a ``WikiPage'')"""
    return WikiPage.objects.get_or_create_wikipage(
        wiki_slug, page_slug).page(request, rest)

def _split_best_ofs(page_set):
    try:
        lilb_id = User.objects.get(username='lilb').id
    except User.DoesNotExist:
        lilb_id = -1
    # TODO: In future, may want to promote pages with 
    # significant user contributions
    filter_args = dict(created_by__id=lilb_id, 
                       title__startswith='Best')
    return (page_set.filter(~django.db.models.Q(**filter_args)), 
            page_set.filter(**filter_args))

def directory(request, wiki_slug, category=None, best_ofs=False):
    """Directory view for widget pages. This view handles three types of 
    page views - the top level directory view, the a category view, and 
    a best-of page view. Each of these can be ordered by title or recency
    of last edit."""
    wiki, _   = WikiHome.objects.get_or_create(slug=wiki_slug)
    categories = wiki.get_categories()
    context = {
        'categories'         : categories,
        'guid_title'         : ctx.get_context().get('guid_title', ''),
        'wiki_slug'          : wiki_slug,
        'show_best_ofs'      : best_ofs,
    }

    # Top level directory page get special treatment
    if not (category or best_ofs or request.GET.get('order')):
        context['order'] = 'categories'
        pages = wiki.all_pages
        cats = filter(lambda cat: cat['count'] > 0, categories)
        context['category_paginator'] = Paginator(cats, 5)
        context['title'] = 'Pages about %s' % context['guid_title']
    else:
        context['order'] = request.GET.get('order', 'title')
        if category is None:
            pages = wiki.all_pages
        else:
            category = first(filter(lambda x: x['id']==category, categories))
            if not category:
                raise Http404
            pages = wiki.pages_of_category(category['id'])
            context['category'] = category

        if context['order'] == 'title':
            # Sort by title
            pages = pages.order_by('title')
            pages, best = _split_best_ofs(pages)
            # Annonying that can't case-insensitive sort in db, so doing
            # it only for non-best-of pages
            pages = sorted(pages.select_related(), 
                           key=lambda x: (x.title or x.slug).lower())
        elif context['order'] == 'recent':
            # Sort by modified date
            pages = pages.order_by('-modified_on')
            pages, best = _split_best_ofs(pages)

        if best_ofs:
            context['best_of_paginator'] = Paginator(best, 10)        
        else:
            context['page_paginator'] = Paginator(pages, 10)
    # Do the pagination
    for pg_type in ('page', 'best_of', 'category'):
        paginator = context.get('%s_paginator' % pg_type)
        if paginator:
            pg_num = request.GET.get(pg_type, 1)
            try:                
                context['%s_paginator_page' % pg_type] = paginator.page(pg_num)
            except InvalidPage:
                raise Http404
            context['%s_url_template' % pg_type] = '?order=%s&%s=${num}' % \
                                                    (context['order'], pg_type)

    # Pull out only pages for current category (on directory home page)
    if 'category_paginator_page' in context:
        for cat in context['category_paginator_page'].object_list:
            cat['pages'] = wiki.pages_of_category(cat['id']
                                                 ).order_by('-modified_on')[:3]


    # Titles
    if category and best_ofs:
        context['title'] = 'Best %s in %s' % (category['title'], 
                                              context['guid_title'])
    elif category:
        context['title'] = '%s in %s' % (category['title'], 
                                         context['guid_title'])
    elif best_ofs:
        context['title'] = 'Best in %s' % context['guid_title']
    else:
        context['title'] = 'Pages about %s' % context['guid_title']

    # Breadcrumbs 
    crumbs = request.ctx.setdefault('crumbs', [])
    if category or best_ofs:
        # If not home page, add crumb to home
        crumbs.append((reverse('widgets_wiki_directory', 
                       kwargs=dict(wiki_slug=wiki_slug)), 'Pages'))
    if category and best_ofs:
        # If in category, best ofs, add crumb to category
        crumbs.append((reverse('widgets_wiki_category_directory', 
                       kwargs=dict(wiki_slug=wiki_slug, 
                                   category=category['id'])), 
                      category['title']))
    return render_to_response('widgets/directory.html', context, 
                              base_opts={'tab': PAGES})


def browser_ajax(request, wiki_slug):
    """Ajax handler for mini browser"""
    try:
        cat, page_num, skip_link, forward = getvalues(request.GET,
                'cat', 'page_num', 'skip_link', 'forward')
    except KeyError:
        return HttpResponseBadRequest()    

    if cat == 'sfall':
        wiki_slug = 'san-francisco-ca'
        cat = 'all'
    wiki, _   = WikiHome.objects.get_or_create(slug=wiki_slug)
    if cat == 'all':
        pages = wiki.all_pages_but_home
    else:
        pages = wiki.pages_of_category(cat)
    max_page = pages.count() - 1
    page_num = max(min(int(page_num), max_page), 0)
    link = None
    if page_num <= max_page:
        page = pages.order_by('-modified_on')[page_num] 
        link = page.get_absolute_url()
        if link == skip_link:
            if max_page < 1:
                link = None
            else:
                forward = (page_num == 0) or (forward and page_num < max_page)
                page_num += 1 if forward else -1
                page = pages.order_by('-modified_on')[page_num] 
                link = page.get_absolute_url()
                
    return HttpResponse(simplejson.dumps(dict(
        link = link,
        type=page.get_fb_type(),
        id=page.id,
        feedback=simplejson.loads(page.get_fb_as_json()),
        share=render_share_widgets(page.title, link),
        content = page.page.render_readonly() if link else 'No pages',
        prev_page = (page_num - 1) if page_num > 0 else None,
        next_page = (page_num + 1) if page_num < max_page else None)))


def create_page_dialog(request, wiki_slug):
    """Dialog for creating a new page in a wiki"""
    cat = request.REQUEST.get('cat', '')
    
    if request.user.is_anonymous():
        next = ("javascript:$.mixerbox('" + reverse('login_dialog') +
                "', 'captcha_login', function(paa) { if (!paa) " +
                "return '" + reverse('on_login') + "?' + $.param({ " +
                "next: location.pathname, command: 'create_page', " +
                "cat: '" + (cat or "__none__") + "' }) })")
        return django_render_to_response('common/close_mixerbox.html', {
                'next': next })
    if request.method == "POST":
        form = CreatePageForm(data=request.POST)
        if form.is_valid():
            return django_render_to_response('common/close_mixerbox.html', {
                    'next': form.create_page(wiki_slug) })
    else:
        form = CreatePageForm(initial={'cat': cat or '__none__'})
    return django_render_to_response(
            'widgets/create_page_dialog.html', { 'form': form,
            'is_captcha_needed': is_captcha_needed() })
    
