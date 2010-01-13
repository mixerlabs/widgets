#!/usr/bin/env python

import conf
conf.configure_django('www.settings')

from townzer.utilities.simple_progress import SimpleProgress
from util.db import nestable_commit_on_success
from www.changes import invalidate_changes_cache
from www.wiki.models import Page
from www.widgets.models import WikiPage

@nestable_commit_on_success
def transcode(page):
    WikiPage.objects.get_or_create_wikipage(page.wiki.slug, page.slug)

def main():
    all = Page.objects.all()

    # Comment this out to do it for all pages
    all = all.filter(wiki__slug='san-francisco-ca')
    # use this to force a single page
    # all = all.filter(slug='Home')

    count = all.count()   
    sp = SimpleProgress(count, quiet=True)
    for i, page in enumerate(all):
        print "%s %s/%s" % (sp.format_progress(), page.wiki.slug, page.slug)
        transcode(page)
        sp.item_completed()
    print sp.format_progress()
    invalidate_changes_cache()
    print 'Flushed changes cache'
    

if __name__ == '__main__':
    main()    
    print "done\n(if this seg faults after this point, don't worry)"
