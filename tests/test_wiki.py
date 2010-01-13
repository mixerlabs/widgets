from __future__ import absolute_import

if __name__ == '__main__':
    import conf
    conf.configure_django('www.settings')

import unittest
import django.test

from www.widgets.models import WikiPage
from django.conf import settings

class TestWiki(django.test.TestCase):
    """Tests for the Wiki router."""
    def test_basic(self):
        # We test concrete URLs to ensure that the integration with
        # the rest of the site's URL routing works.

        slug  = 'Foo-bar'
        wslug = 'san-francisco-ca'
        # Ensure `slug' in san-francisco-ca doesn't exist.
        WikiPage.objects.filter(slug=slug, wiki__slug=wslug).delete()

        # This also creates the given entry.
        if settings.WIDGETS_DEFAULT:
            uri = '/%s/%s' % (wslug, slug)
        else:
            uri = '/%s/-%s' % (wslug, slug)        
        response = self.client.get(uri)
        self.assertEquals(200, response.status_code)

        self.assertEquals(
            1,
            len(WikiPage.objects.filter(slug=slug, wiki__slug=wslug))
        )

def test_suite():
    from util.django_layer import make_django_suite
    return make_django_suite(__name__)

if __name__ == '__main__':
    unittest.main()
