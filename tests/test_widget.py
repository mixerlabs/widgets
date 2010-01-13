from __future__ import absolute_import

if __name__ == '__main__':
    import conf
    conf.configure_django('www.settings')

import unittest

from django.http import Http404

from www.widgets.widget import Widget
from www.widgets.models import WidgetState
from www.widgets.router import view

# Has to be toplevel so it can be pickled.
class MyWidget(Widget):
    @view('^test-(\d+)$', 'view_name')
    def test_view(self, request, an_int):
        return self.parent_key, an_int

class TestWidget(unittest.TestCase):
    def test_basic(self):
        w = Widget()
        w.foo = 'bar'
        w.freeze()
        w.foo = 'baz'
        w.freeze()

        state = WidgetState.objects.get(pk=w.get_state_id())
        self.assertEquals('baz', state.widget.foo)
        self.assertEquals('bar', state.previous.widget.foo)
        self.assertEquals(None, state.previous.previous)

    def test_children(self):
        # Make sure we can create & retrieve a small widget tree.
        w0 = Widget()
        w0.which = 'parent'
        w1 = Widget()
        w1.which = 'child'
        w0.append(w1)
        w1a = Widget()
        w1a.which = '1-a'
        w1b = Widget()
        w1b.which = '1-b'
        self.assertEquals(0, w1.append(w1a))
        self.assertEquals(1, w1.append(w1b))

        # Freezing the parent should freeze all children transitively,
        # because we need their refs.
        w0.freeze()

        self.assert_(w0._state_id is not None)
        self.assert_(w1._state_id is not None)
        self.assert_(w1a._state_id is not None)
        self.assert_(w1b._state_id is not None)

        # Restore the tree from looking up the root.
        state = WidgetState.objects.get(pk=w0._state_id)
        self.assertEquals('parent', state.widget.which)
        self.assertEquals(1, len(state.widget))
        self.assertEquals('child', state.widget[0].which)
        self.assertEquals('1-a', state.widget[0][0].which)
        self.assertEquals('1-b', state.widget[0][1].which)

        # Make sure parent references are restored properly.
        self.assertEquals(state.widget, state.widget[0].parent)
        self.assertEquals(state.widget[0], state.widget[0][0].parent)

        # Now make sure updates work up the tree.
        state_ids = w0.map(lambda w: w._state_id)
        w1b.freeze()
        new_state_ids = w0.map(lambda w: w._state_id)

        # Only [0][0] is untouched since it's a peer to [0][1],
        # all other nodes are parents.
        self.assertEquals(set([state.widget[0][0]._state_id]),
                          set(new_state_ids) & set(state_ids))

    def test_routing(self):
        root = Widget()
        root.append(MyWidget())
        root.append(MyWidget())
        root.append(Widget())
        root[2].append(MyWidget())

        # Now route some requests.
        self.assertEquals((0, '123'), root({}, '_0/test-123'))
        self.assertEquals((1, '333'), root({}, '_1/test-333'))

        # Bad index.
        self.assertRaises(Http404, root.__call__, {}, '_3/test-333')
        # Bad argument.
        self.assertRaises(Http404, root.__call__, {}, '_1/test-abc')
        # No view.
        self.assertRaises(Http404, root.__call__, {}, '_2/test-123')

        # Nested.
        self.assertEquals((0, '999'), root({}, '_2/_0/test-999'))

        # Reverse.
        self.assertEquals('_2/_0/test-876', root[2][0].reverse('view_name', 876))

def test_suite():
    from util.django_layer import make_django_suite
    return make_django_suite(__name__)

if __name__ == '__main__':
    unittest.main()
