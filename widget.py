"""Provide the basis of the stateful widget hierarchy & request
routing."""
from __future__ import absolute_import

from copy import copy

from lxml.html import fromstring

from django.http               import HttpResponse, Http404
from django.db                 import transaction
from django.conf.urls.defaults import url

from util.dynvar     import bindings
from util.functional import concat, dictmap

from .       import html
from .models import WidgetState
from .router import Routable, view

class Widget(Routable):
    """The ``Widget'' is a routable object that exists in a tree with
    other instances of ``Widget''. It can route requests up and down
    the hierarchy (with a reserved namespace starting with an
    underscore)."""
    class ImmutabilityError(Exception): pass

    def __init__(self):
        self._state_id  = None
        self.parent     = None
        self.children   = {}
        self.parent_key = None

    # | Child widget management.
    def append(self, widget):
        """Append `widget' to the dict of child widgets, returning its key
        for the parent's children dict. """
        widget.parent = self
        self._last_key = getattr(self, '_last_key', -1) + 1
        widget.parent_key = self._last_key
        self.children[widget.parent_key] = widget        
        return widget.parent_key

    @property
    def root(self):
        """Access the root of the tree."""
        if self.parent:
            return self.parent.root
        else:
            return self

    @property
    def request(self):
        if self.parent:
            return self.parent.request
        else:
            return super(Widget, self).request

    # Widgets look like dicts of other widgets:
    def __getitem__(self, index):
        return self.children[index]

    def __delitem__(self, index):
        del self.children[index]
        
    def clear(self):
        self.children.clear()

    def __setitem__(self, key, value):
        raise self.ImmutabilityError

    def __len__(self):
        return len(self.children)

    def __iter__(self):
        return self.children.iterkeys()
    
    def items(self):
        return self.children.items()

    def __nonzero__(self):              # bool(widget) == True always
        return True

    def map(self, fun):
        """Map over self & all children recursively."""
        return [fun(self)] + \
               [v for child in self.children.itervalues()
                  for v in child.map(fun)]

    # | State management.
    def get_state_id(self):
        """Get the state id. If we don't have one yet, we produce one."""
        if not self._state_id:
            self.freeze()
        return self._state_id

    def get_state_object(self):
        """ Get the state object using get_state_id. """
        return WidgetState.objects.get(pk=self.get_state_id())

    def freeze(self):
        """Freezes the state of the widget onto a WidgetState instance as-is.

        Note that the children of a widget must be frozen before calling
        freeze().  Otherwise the parent widget will not have the correct state
        of its children and properties such as html_blob will not reflect the
        most recent state of the widget's children.

        TODO: Fix this so that parents freeze their children when necessary.
        """
        # TODO: use nested transactions here?
        #
        self.freezing = True
        try:
            if self._state_id and self._state_id == getattr(
                    bindings, 'transcoding', {}).get('state_id'):
                # During transcoding, overwrite page state instead of linking
                # to a newly created state.  A page root should only have 1
                # version per wiki version no matter how many freezes occurred
                # in transcoding.
                old = WidgetState.objects.get(pk=self._state_id)
                old.widget = self
                old.save()
            else:
                # This is a bit ugly. We could get around it by having the
                # PickleField inform the instance after unpickling of its
                # state ID. For now, this will do.
                new = WidgetState(widget=self, previous_id=self._state_id)
                new.save()
                self._state_id = new.widget._state_id = new.pk
                new.save()
    
            if self.parent:
                self.parent.update(self)
        finally:
            del self.freezing

    def update(self, child):
        # Called from a child: they are notifying us of an update.
        # Ignore this if we are in the process of freezing already
        if not getattr(self, 'freezing', False):
            assert child.parent == self
            self.children[child.parent_key] = child
            self.freeze()

    # | Forward & reverse URL routing
    #
    # This is nice & simple since we already have a tree.
    @view('^_(?P<child_key>\d+)/(?P<rest>.*)')
    def handle_child(self, request, child_key, rest):
        # If we have a valid child, simply route down the tree.
        child_key = int(child_key)
        try:
            return self.children[child_key](request, rest)
        except KeyError:
            raise Http404

    def reverse_child(self, child, rest):
        return self.reverse(self.handle_child, child.parent_key, rest)

    def reverse(self, view, *args, **kwargs):
        fragment = super(Widget, self).reverse(view, *args, **kwargs)
        if self.parent:
            return self.parent.reverse_child(self, fragment)
        else:
            return fragment

    # | Views.
    @view('^$', 'root')
    def _handle_root_view(self, request):
        return self.handle_root(request)

    # This version for subclassing:
    def handle_root(self, request):
        return HttpResponse(self.render(request))

    def render(self, request):
        """Renders the widget -- this should return a string, but can
        also raise an exception."""
        raise NotImplementedError
        
    # | Application support.
    def links(self):
        """Return a list of anchors (href, anchortext) that this
        widget links to."""
        if self.html_blob.strip():
            links = html.links_of_html(self.html_blob)
        else:
            links = []

        return links + concat(child.links()
                              for child in self.children.itervalues())

    def tokens(self):
        """Return a list of string tokens from the plain text representation 
        of this widget."""
        if self.html_blob.strip():
            tokens = fromstring(self.html_blob).text_content().strip().split()
        else:
            tokens = []

        return tokens + concat(child.tokens()
                               for child in self.children.itervalues())

    def make_duplicate(self, new_state_id):
        """ Returns a copy of this widget with _state_id changed to
        new_state_id. Used in conjunction with freeze for reverting. """
        dup = copy(self)
        dup._state_id = new_state_id
        return dup
        
    @property
    def html_blob(self):
        """A blob of HTML representing the contents of the widget, so
        that we can do generic analysis."""
        return ''

    # | Namespace.
    @property
    def namespace(self):
        if self.parent:
            return '%s_%s' % (self.parent.namespace, self.parent_key)
        else:
            return '_root'

    # | CSS/styling
    css_container = None
    css_contents  = None
    css_hover     = None

    # Editability determines whether we provide an editing UI for the
    # widget.
    editable      = True

    # | Delegate management.
    #
    # We simply take the delegate from our parent. Any root widgets
    # need to be aware of this.
    def _get_delegate(self):
        return self.parent.delegate if self.parent else None

    def _set_delegate(self, delegate):
        if self.parent:
            self.parent.delegate = delegate

    delegate = property(_get_delegate, _set_delegate)


    # | Pickling support.
    #
    # We map child states onto their state IDs (also making sure they
    # are frozen in the process) in order to save space.
    def __getstate__(self):
        dict = super(Widget, self).__getstate__()
        dict['children'] = dictmap(
            lambda k,v: (k, v.get_state_id()),
            dict['children'])
        for k in ('parent', 'parent_key', 'freezing'):
            dict.pop(k, None)

        return dict

    def __setstate__(self, dict):
        # Convert widget state ids back into happy child objects when restoring
        # from a frozen state.
        dict['children'] = dictmap(
            lambda k,v: (k, WidgetState.objects.get(pk=v).widget),
            dict['children'])

        self.parent     = None
        self.parent_key = None
        self.__dict__.update(dict)

        # Restore the parent reference.
        for key, child in self.children.iteritems():
            child.parent     = self
            child.parent_key = key
