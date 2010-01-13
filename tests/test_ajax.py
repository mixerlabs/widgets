from __future__ import absolute_import

if __name__ == '__main__':
    import conf
    conf.configure_django('www.settings')

import unittest
import django.test
from django.conf import settings

from www.widgets.models import WikiPage
from www.widgets.tests.widgets import TestWidget


class TestAjax(django.test.TestCase):
    """Tests for the Wiki router."""
    def test_basic(self):
        # We use the wiki router for our tests. The proper thing to do
        # would be to create a test router that statically routes
        # things to some root test widget, but this is convenient.
        slug  = 'Foo-bar'
        wslug = 'san-francisco-ca'
        WikiPage.objects.filter(slug=slug, wiki__slug=wslug).delete()
        if settings.WIDGETS_DEFAULT:
            uri = '/%s/%s' % (wslug, slug)
        else:
            uri = '/%s/-%s' % (wslug, slug)

        self.client.get(uri)            # ensures it exists.

        # Stick our test widet onto it, as the first widget.
        page = WikiPage.objects.get(slug=slug, wiki__slug=wslug).page
        w = TestWidget()
        self.assertEquals(0, page.append(w))
        w.freeze()

        # This also creates the given entry.
        response = self.client.post(
            '%s/_0/_ajax/concatupper' % uri, 
            {'arg0': 'hello', 'arg1': 'there'}
        )
        self.assertEquals(200, response.status_code)
        self.assertEquals('"HELLOTHERE"', response.content)

def test_suite():
    from util.django_layer import make_django_suite
    return make_django_suite(__name__)

if __name__ == '__main__':
    unittest.main()
