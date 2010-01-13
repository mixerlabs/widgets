"""The router provides a class that allows for URL routing to member
methods. The ``Routable'' sets up the basics of URL routing, while
``Widget'' in ``widget.py'' sets widgets up in a tree of Routables
that can route URLs through the widget hierarchy."""
import inspect
import cjson
import re

from djangologging             import SUPPRESS_OUTPUT_ATTR
from django.core.urlresolvers  import RegexURLResolver
from django.template.loader    import find_template_source, render_to_string
from django.conf.urls.defaults import patterns, url
from django.http               import (HttpResponse,
                                       HttpResponseNotAllowed,
                                       Http404)
from django.template           import Template, Context

from util.functional import pick, memoize_
from util.coerce     import coerce
from util.digest     import pydigest_str

# | Resolution & routing.
class Resolver(RegexURLResolver):
    """Wrapper around Django's URL resolver to make it more convenient
    to use outside of ``url.py''s"""
    def __init__(self, *pairs):
        super(Resolver, self).__init__('', None)

        # Set up the given url pairs.
        self.urlpatterns     = patterns('', *pairs)
        self._urlconf_module = self

class Routable(object):
    """The routable class provides members decorated with ``@view'' or
    ``@ajax'' with a routable URL namespace, and the means by which to
    call into the defined views (via __call__ -- ie. Routables are
    callable())"""
    def _resolver(self):
        views = inspect.getmembers(self, lambda m: hasattr(m, '_urlpattern'))
        views = pick(1, views)
        pairs = []
        for view in views:
            pairs.append(url(view._urlpattern, view, name=view._viewname))

        return Resolver(*pairs)

    @property
    def request(self):
        """The current request being processed (via our callable)."""
        return getattr(self, '_request', None)

    def __call__(self, request, path):
        """Route the given request & path, calling the view."""
        self._request = request
        try:
            view, args, kwargs = self.resolve(path)
            return view(request, *args, **kwargs)
        finally:
            del self._request

    def resolve(self, path):
        return self._resolver().resolve(path)

    def reverse(self, view, *args, **kwargs):
        """Reverse the view (or view name) with the given arguments on
        this object."""
        return self._resolver().reverse(view, *args, **kwargs)

    def reverse_ajax(self, name):
        """Reverse the given named ajax handler."""
        return self.reverse('ajax_%s' % name)

    def __getstate__(self):
        dict = self.__dict__.copy()
        # Never serialize _request, it's ephemeral.
        if '_request' in dict:
            del dict['_request']

        return dict

# | Decorators
def view(pattern, name=None):
    """The view decorator declares the member function a view, with a
    URL pattern defined as an arguent."""
    def decorate(fun):
        fun._urlpattern = pattern
        fun._viewname   = name
        return fun

    return decorate

def ajax(name, encode=True):
    """The ajax decorator declares the method an ajax handler with the
    given name."""
    def decorate(fun):
        def handler(self, request):
            if request.method != 'POST':
                return HttpResponseNotAllowed(['POST'])

            # JSON-decode kwargs and return the results JSON-encoded 
            kwargs = dict(request.POST.items())
            kwargs = coerce(kwargs, unicode, str)

            # Make the response & decorate it so that we don't get log
            # messages (from djangologging).
            response = fun(self, **kwargs)
            if encode:
                response = cjson.encode(response or '')

            response = HttpResponse(response)
            setattr(response, SUPPRESS_OUTPUT_ATTR, True)
            return response

        handler._urlpattern = r'^_ajax/%s' % name
        handler._viewname   = 'ajax_%s' % name

        return handler

    return decorate

def render_template(fun):
    """A convenience decorator for rendering views with a
    template. The decorated function returns a tuple of (template, context)"""
    def decorated(*args, **kwargs):
        template, context = fun(*args, **kwargs)
        return render_to_string(template, context)

    return decorated

def render_template_with_namespace(fun):
    """A decorator for widget renderers or ajax functions that
    substitutes protected & private names in the template. The
    protected namespace is per-widget-instance while the private
    namespace is per-widget-instance-template."""
    def decorated(self, *args, **kwargs):
        template, context = fun(self, *args, **kwargs)
        return render_to_string_with_namespace(
            self.namespace, template, context)

    return decorated

def render_to_string_with_namespace(
        protected_ns, template_name,
        dictionary=None, context_instance=None):
    source, origin = find_template_source(template_name)
    private_ns     = '_' + memoize_(pydigest_str, protected_ns + template_name)
    source         = subns(protected_ns, private_ns, source)

    template = Template(source, origin, template_name)

    if context_instance:
        context_instance.update(dictionary)
    else:
        context_instance = Context(dictionary)

    return template.render(context_instance)

def subns(protected_ns, private_ns, content):
    """Substitute private & protected namespaces in the given content
    string."""

    content = ('%s_' % private_ns).join(content.split('___'))
    content = ('%s_' % protected_ns).join(content.split('__'))

    return content
