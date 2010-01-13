class Commands(object):
    descr = 'Widgets'

    def cmd_unpack_transcode(self, path, force=False,
                             wiki_slug=None, page_slug=None):
        """Transcode the packed wiki page in `path' onto the widget
        with the same slugs (unless overidden). Specifying `force'
        will delete the page if it already exists."""
        import conf; conf.configure_django('www.settings')
        from www.wiki.common         import random_wikiword
        from www.wiki.pack           import unpack
        from www.wiki.models         import Page
        from www.widgets.transcoding import transcode_wiki_to_onecolumnpage
        from www.widgets.models      import WikiPage, WikiHome
        from www.widgets.page        import OneColumnPage

        tmp_wiki_slug = 'ephemeral-town-usa'
        tmp_page_slug = random_wikiword()

        meta = unpack(path, wiki_slug=tmp_wiki_slug, page_slug=tmp_page_slug)

        wiki_slug = wiki_slug or meta['wiki_slug']
        page_slug = page_slug or meta['page']['slug']

        wiki_page = \
            Page.objects.get(wiki__slug=tmp_wiki_slug, slug=tmp_page_slug)

        if force:
            WikiPage.objects.filter(wiki__slug=wiki_slug, slug=page_slug)\
                            .delete()

        wiki, _      = WikiHome.objects.get_or_create(slug=wiki_slug)
        widgets_page = OneColumnPage(WikiPage(slug=page_slug, wiki=wiki))
        transcode_wiki_to_onecolumnpage(wiki_page, widgets_page)

        # Clean up the temporary wiki page.
        wiki_page.photos.all().delete()
        wiki_page.delete()

COMMANDS = Commands()
