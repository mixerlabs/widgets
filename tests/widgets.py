"""Define some widgets for testing. We do it here so it's always its
own module (not running as __main__) & remains picklable."""

from www.widgets.widget import Widget
from www.widgets.router import ajax, view

class TestWidget(Widget):
    @ajax('concatupper')
    def concatupper(self, arg0, arg1):
        return arg0.upper() + arg1.upper()

    @view('^$')
    def testview(self, request):
        pass
