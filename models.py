"""Models for widgets. These deal with storing widget state & routing
wiki widgets."""

from __future__ import absolute_import
from __future__ import with_statement

import os.path

from datetime   import datetime, timedelta

from django.db                  import models
from django.conf                import settings
from django.core.urlresolvers   import reverse
from django.contrib.auth.models import User
from tagging.models             import Tag, TaggedItem

from util.cache         import cache_key_, invalidate_cache_key
from util.django_models import get_or_none
from util.dynvar        import binding, bindings
from util.functional    import pick

from www.wiki.common import settings as wiki_settings

from util                           import cache
from util.db                        import nestable_commit_on_success
from util.functional                import pick
from www.common.context             import get_ip
from www.common.templatetags.static import reverse_static_url
from www.feedback.models            import Feedback
from www.guid.resolver              import resolve_url_to_ctx
from www.linkgraph.models           import Edge

from util.django_fields import PickleField

# | CATEGORIES
#
#   The following deal with converting categories to tags and vice
#   versa. We create a separate tag namespace for categories for
#   future flexibility.
def category_of_tag(tag):
    """Return the category (a string) from a tag (also a string)."""
    label, category = tag.split(':', 1)
    assert label == 'category'
    return category

def tag_of_category(category):
    """Return the tag of the given category -- inverse of
    ``category_of_tag()''"""
    return 'category:%s' % category

def title_of_category(category):
    return wiki_settings.CATEGORIES[category]['title']

def category_of_object(obj):
    """Return the category of the given object according to
    django-tagging. If it does not have one, return the default as
    defined in wiki_settings."""
    tags = Tag.objects.get_for_object(obj)
    return category_of_tag(tags[0].name) if len(tags) > 0 else None

# | Widget state management.
class WidgetState(models.Model):
    """The WidgetState is a linked list of pickled widget class
    instances."""
    widget   = PickleField()
    previous = models.ForeignKey('self', null=True, blank=True)

# | Wiki router.
#
# Any router maps a prefix to a page. The page itself is responsible
# for routing the rest of the path.
class WikiHome(models.Model):
    slug = models.SlugField(max_length=400, unique=True)
    
    @property
    def all_pages(self):
        #TODO: Filter out empty and deleted pages
        return self.wikipage_set

    @property
    def all_pages_but_home(self):
        return self.all_pages.exclude(slug='Home')
    
    def pages_of_category(self, category):
        """Return query set for Pages in category (string)"""
        if category is None:
            category = '__none__'
        
        if category not in wiki_settings.CATEGORIES:
            raise ValueError, 'Invalid category %s' % category

        if category == '__none__':
            cats = map(tag_of_category, wiki_settings.CATEGORIES.keys())
            qs = TaggedItem.objects.get_by_model(WikiPage, cats)
            qs = self.all_pages_but_home.exclude(id__in=pick('id',
                                                             qs.values('id')))
        else:
            qs = TaggedItem.objects.get_by_model(WikiPage, 
                                                 [tag_of_category(category)])
            qs = qs.filter(wiki=self).exclude(slug='Home')
        return qs
        
    def get_categories(self):
        """Return categories for a wiki. Results are cached for an hour.
        When changing categories of pages, on should call 
        'refresh_categories' to invalidate the cache."""
        return cache_key_('widget_page_categories', 60*60, lambda: self.slug,
                          self._get_categories)

    def get_pb_categories(self):
        """Return customized categories for the page browser. """
        # Get at most 8 categories with a non-zero count sorted by -count, title
        categories = sorted(filter(lambda x: x['count'], self.get_categories()),
                            key=lambda x: (-x['count'], x['title']))[:8]
        
        if categories:
            # Add link to category entries
            for category in categories:
                category['link'] = reverse('widgets_wiki_category_directory',
                                           kwargs=dict(wiki_slug=self.slug,
                                                       category=category['id']))
            # pseudo category for all pages
            categories.insert(0, dict(title='All pages',
                                      id='all',
                                      count=self.all_pages_but_home.count(),
                                      link=reverse('widgets_wiki_directory',
                                          kwargs=dict(wiki_slug=self.slug))))
        else:
            sfwiki, _ = WikiHome.objects.get_or_create(slug='san-francisco-ca')            
            # pseudo category for 'all san francisco' pages
            categories = [dict(title='San Francisco Pages',
                               id='sfall',
                               count=sfwiki.all_pages_but_home.count(),
                               link=reverse('widgets_wiki_directory',
                                   kwargs=dict(wiki_slug=sfwiki.slug)))]
        return categories

    def refresh_categories(self):
        invalidate_cache_key('widget_page_categories', self.slug)

    def _get_categories(self):        
        def cat_cmp(x, y):
            score = lambda c: c['id'] == '__none__' and -1 or c['count']
            return cmp(score(x), score(y))
        categories = wiki_settings.CATEGORIES.copy()
        for category in categories.values():
            category['count'] = self.pages_of_category(category['id']).count()
        categories = sorted(categories.values(), cmp=cat_cmp, reverse=True)
        return categories

    

class WikiPageManager(models.Manager):
    @nestable_commit_on_success
    def get_or_create_wikipage(self, wiki_slug, page_slug, title=None,
                               category=None):
        """like .get_or_create, except a WikiHome is created when
        needed & transcoding may be performed from a corresponding
        wiki (as in www.wiki) page.

        Args:
          wiki_slug: e.g. 'san-francisco-ca'
          page_slug: e.g. 'Page1'. User created pages must be capitalized.
          title:     title to use if creating a apge, or None for no title
          category:  category id to use if creating a page or None
        """
        from www.wiki.models import Wiki, WikiHost, Page as Wiki_Page
        from .page           import OneColumnPage
        from .transcoding    import transcode_wiki_to_onecolumnpage

        try:
            wiki_page = self.get(slug=page_slug, wiki__slug=wiki_slug)

            if settings.WIDGETS_TRANSCODE_WIKI_PAGES:
                # See if any new versions of the wiki have been made since the
                # first transcode
                try:
                    host, _ = WikiHost.objects.get_or_create(name='guid')
                    wiki, _ = Wiki.objects.get_or_create(host=host, 
                                                         slug=wiki_slug)
                    wiki_p = wiki.all_pages.get(slug=page_slug,
                                                wiki__slug=wiki_slug)
                    transcode_wiki_to_onecolumnpage(wiki_p, wiki_page.page,
                                                    wiki_page.modified_on)
                except Wiki_Page.DoesNotExist:
                    pass
        except WikiPage.DoesNotExist:
            # Create a new one!
            wiki, _       = WikiHome.objects.get_or_create(slug=wiki_slug)
            wiki_page     = WikiPage(slug=page_slug, wiki=wiki)
            page          = OneColumnPage(wiki_page)
            if title is not None:
                page.title = title
            if category is not None:
                page.category = category

            if settings.WIDGETS_TRANSCODE_WIKI_PAGES:
                # If a wiki page already exists, transcode its
                # contents to our newly created page.
                try:
                    host, _ = WikiHost.objects.get_or_create(name='guid')
                    wiki, _ = Wiki.objects.get_or_create(host=host, 
                                                         slug=wiki_slug)
                    wiki_p = wiki.all_pages.get(slug=page_slug,
                                                wiki__slug=wiki_slug)
                    transcode_wiki_to_onecolumnpage(wiki_p, page)
                except Wiki_Page.DoesNotExist:
                    page.freeze()
            else:
                page.freeze()

        return wiki_page
    
    def recent_pages(self, wiki_slug):
        """ Similar to WikiPage.recent_pages, except takes a wiki_slug and
        doesn't match on Home or anything before wiki_birthday, and returns at
        most 5 items.  """
        return self.filter(wiki__slug=wiki_slug)\
            .filter(modified_on__gte=wiki_settings.WIKI_BIRTHDAY)\
            .exclude(slug=wiki_settings.GUID_HOME_PAGE_NAME)\
            .order_by('-modified_on')[:wiki_settings.GUID_NUM_RECENT_WIKIS]
    

class WikiPage(models.Model):
    """Store a reference to the *head* WidgetState for a page."""
    DEFAULT_THUMB = lambda: reverse_static_url('img/placeholder35x.png')

    wiki = models.ForeignKey(WikiHome)
    slug = models.SlugField(max_length=400)

    # This stores the head state
    head = models.ForeignKey(WidgetState)

    # | Denormalized fields
    created_by      = models.ForeignKey(User, null=True)
    created_from_ip = models.IPAddressField(default='0.0.0.0')
    created_at      = models.DateTimeField(default=datetime.now)
    modified_on     = models.DateTimeField(default=datetime.now)
    title           = models.CharField(max_length=500)
    tokens          = models.TextField()

    objects = WikiPageManager()

    class Meta:
        unique_together = (('wiki', 'slug'),)

    def __init__(self, *args, **kwargs):
        super(WikiPage, self).__init__(*args, **kwargs)
        self._new_category = None

    @property
    def page(self):
        """The current page."""
        # This coordination of setting the delegate object is a bit
        # delicate, but it simplifies other aspects of operation, and
        # decouples the widget from the actual route & head state
        # management.
        w = self.head.widget
        w.delegate = self
        return w

    @property
    def category_title(self):
        return title_of_category(self.category)

    def category_fget(self):
        """The *category* of the wiki, is one of the strings in the
        CATEGORIES setting."""
        if self._new_category is not None:
            cat = self._new_category
        else:
            cat = category_of_object(self)
        return cat or '__none__'

    def category_fset(self, value):
        """Set the category for this page, we check that the string is
        a member of the CATEGORIES setting."""
        if value not in wiki_settings.CATEGORIES:
            raise ValueError, \
                'Category must be one of %r' % wiki_settings.CATEGORIES.keys()
        self._new_category = value

    category = property(category_fget, category_fset)

    def get_absolute_photo_or_thumb_url(self, photo_or_thumb):
        """Make photo URLs that are nice & SEOable."""
        base, ext = os.path.splitext(photo_or_thumb.get_file_name())
        return self.page.reverse(
            'image', media_hash=base,
            photo_slug=photo_or_thumb.get_slug(), ext=ext)

    def get_absolute_url(self):
        return reverse('widgets_wiki_page_root', kwargs={
            'wiki_slug' : self.wiki.slug,
            'page_slug' : self.slug,
        })

    # | TownMe site support
    def get_fb_type(self):
        return 'widget'

    def get_fb_as_json(self):
        return Feedback.objects.get_traits_for_current_user_as_json(self)

    def get_title_for_follower(self, follower=None):
        try:
            _, ctx = resolve_url_to_ctx(self.wiki.slug)
            guid_title = ctx.get('guid_title', self.wiki.slug)
        except:
            # Don't kill the thread because we can't get the fancy title
            guid_title = self.wiki.slug            
        if self.wiki.slug == 'home':
            return guid_title
        else:
            return '%s (%s)' % (self.title, guid_title)    
    
    @cache.cache_key('widgets_page_cached_35px_thumb',
                     60*60*24*7,  # good for a week
                     lambda self: '%d' % self.id)
    def get_cached_35px_thumb_url(self):
        photo = self.page.get_representative_photo()
        if photo is None:
            return self.DEFAULT_THUMB()

        try:
            return photo.get_thumb(width=35, height=35, aspect='crop')\
                                  .get_absolute_url()
        except IOError:
            return self.DEFAULT_THUMB()
            
    def invalidate_cached_35px_thumb(self):
        cache.invalidate_cache_key(\
                'widgets_page_cached_35px_thumb', '%d' % self.id)

    # | Delegate for pages.
    @property
    def content_object(self):
        return self

    def user_can_edit(self, user):
        return user and user.is_authenticated()

    def reverse(self, rest):
        return reverse(
            'widgets_wiki_page',
            kwargs={
                'wiki_slug' : self.wiki.slug,
                'page_slug' : self.slug,
                'rest'      : rest
            }
        )

    def freeze(self, widget):
        if self.wiki.pk is None:
            self.wiki.save()

        # Set the current state to our wiki.
        self.head = WidgetState.objects.get(pk=widget.get_state_id())

        # Denormalize needed fields:
        self.modified_on  = widget.edit_time
        self.title        = widget.title
        self.tokens       = ' '.join(widget.tokens())
        
        if not self.created_at:
            self.created_at = widget.edit_time

        # The first authenticated freeze gets create cred.
        if not self.created_by:
            self.created_by = widget.edit_user
            if widget.edit_ip_address:
                self.created_from_ip = widget.edit_ip_address

        self.save()

        # After save, we update the category, since it needs a saved
        # object (pk) and invalidate the category cache for the wiki.
        if self._new_category is not None:
            tag = tag_of_category(self._new_category)
            Tag.objects.update_tags(self, tag)
            self.wiki.refresh_categories()
        # Update the linkgraph.
        src    = self.get_absolute_url()
        dsts   = set(pick(1, widget.links()))

        # Now update the link graph so that the current set of
        # destination reflects `dsts'

        # Delete old objects, then find only new links, and insert
        # them.
        Edge.objects.filter(src=src).exclude(dst__in=dsts).delete()

        self.invalidate_cached_35px_thumb()

        old = set(e.dst for e in Edge.objects.filter(src=src))
        new = dsts - old
        for dst in new:
            Edge.objects.create_safe(src=src, dst=dst)

        first_freeze = self.head.previous is None
        is_hidden_change = getattr(bindings, 'is_hidden_change', False)
        transcoding = getattr(bindings, 'transcoding', None)
        if transcoding is None and not is_hidden_change and not first_freeze:
            self.notify_followers_post_save(widget)
    
        # Finally, create a change entry for the changes app.
        if ((transcoding is None) or (transcoding.pop('create_change', False))
                and not first_freeze):
            WikiPageChange.objects.create(
                page             = self,
                changed_by       = widget.edit_user,
                title            = widget.title,
                changed_on       = widget.edit_time,
                changed_from_ip  = widget.edit_ip_address or '0.0.0.0',
                is_hidden_change = is_hidden_change,
                state            = self.head)
        

    def notify_followers_post_save(self, widget):
        prev = self.head.previous.widget if self.head.previous else None
        if (prev and widget.edit_user and prev.edit_user == widget.edit_user
              and widget.edit_time - prev.edit_time < timedelta(minutes=30)):
            # Don't notify adjacent edits within 30 minutes from the same user
            return        
        from www.notify.actions import (follow_url_on_first_user_action,
                email_edit_to_other_followers)
        follow_url_on_first_user_action(self.get_absolute_url(),
                widget.edit_user, 'E' if prev else 'C')        
        user_and_ip = (widget.edit_user, widget.edit_ip_address or '0.0.0.0')
        email_edit_to_other_followers(self, user_and_ip)


    # Define "keywords" for a page. These are based on the title or the slug.
    def get_keywords(self):
        words = self.title.strip().split()
        if words:
            return words
        words = self.wiki.slug.split('-')
        # TODO: Make this smarter?
        if len(words) < 2:
            # Only 1 word or less, wiki is probably a profile
            return []
        if len(words[-1]) == 2:
            # Ends in a 2 letter word, wiki is a city, strip off state abbrev.
            return words [:-1]
        if len(words[-1]) == 5:
            # Ends in a 5 character word (zip code), strip last two
            # words (state and zip code).
            return words [:-2]

    def recent_wikipages(self):
        return self.__class__.objects    \
                 .filter(wiki=self.wiki) \
                 .exclude(pk=self.pk)    \
                 .order_by('-modified_on')

class WikiPageChange(models.Model):
    """This stores *changes* to wiki pages. It is used by the changes
    application."""
    page = models.ForeignKey(WikiPage)

    # | Denormalized fields for quick changes access.
    changed_by       = models.ForeignKey(User, null=True)
    changed_from_ip  = models.IPAddressField(default='0.0.0.0')
    changed_on       = models.DateTimeField(default=datetime.now)
    title            = models.CharField(max_length=500)

    # True for changes marked as bad, and Lil'b's revert
    is_hidden_change = models.BooleanField(default=False)
    # The page widget's state at the time of the change
    state            = models.ForeignKey(WidgetState, null=True)

    # | Changes support.
    if settings.WIDGETS_DEFAULT:
        class ChangesMeta:
            change_type   = 'page'
            time_field    = 'changed_on'
            timeval_field = time_field
            user_field    = 'changed_by'
            user_ip_field = 'changed_from_ip'
            verb          = 'edited'
    
            # NOTE: Not stricly accurate since this only gets pages that
            # are rooted under the town, but not pages that are rooted
            # under entities that are contained in that town. But there
            # are extremely few such pages anyway, and we might even phase
            # those out, so for an emergency fix this works OK.
            town_guid_field = 'page__wiki__slug'
    
            @staticmethod
            def title(change):
                return change.page.get_title_for_follower()
    
            @staticmethod
            def get_url(change):
                """Return the URL of the parent page."""
                return change.page.get_absolute_url()
    
            @staticmethod
            def get_no_follow(vsn):
                """Return whether the links to the change should be
                no-follow."""
                return False
    
            @staticmethod
            def get_is_hidden(vsn):
                return vsn.is_hidden_change

    def get_cached_35px_thumb_url(self):
        return self.page.get_cached_35px_thumb_url()

    def possum_eat(self):
        """ Rather than deleting the version, mark it as hidden.  If it's
        the latest non-hidden version, create a version that reverts it. """
        if self.is_hidden_change:
            return
        self.is_hidden_change = True
        self.save()
        # If missing state foreign key, stop now.
        if not self.state:
            return
        
        # Walk the linked list of versions from the head (latest) earlier.
        state = self.page.head
        found_self = False
        while state:
            change = get_or_none(WikiPageChange.objects, state=state)
            visible = (not change.is_hidden_change) if change else True
            found_self = found_self or state == self.state
            if visible:
                if not found_self:
                    # A later version is visible, don't make a revert version.
                    return
                if found_self and state != self.state:
                    # An earlier visible version exists, use it for the revert.
                    break
            state = state.previous

        if state:
            old_page = state.widget
        else:
            from .page import OneColumnPage
            old_page = OneColumnPage(self.page)

        # Create a duplicate page widget with the current state_id
        page = old_page.make_duplicate(self.page.head_id)
        page.delegate = self.page

        with binding(is_hidden_change=True):
            page.freeze()
