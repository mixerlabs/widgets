from __future__ import absolute_import

from django import forms

from www.registration.fields import CaptchaField, CaptchaWidget
from www.widgets.models import WikiPage
from www.wiki.common import (settings as wiki_settings,
                             title_to_wikiword)

from util import sym

CATEGORIES_FOR_CHOICE = [(k, v['title'])
      for k, v in wiki_settings.CATEGORIES.iteritems()]

class CreatePageForm(forms.Form):
    title = forms.CharField(required=True, max_length=120,
            widget=forms.TextInput(attrs={
            'class': 'formwidth mixertwiddle_select',
            'title': 'e.g., San Francisco Hipsters'}))
    cat = forms.ChoiceField(choices=CATEGORIES_FOR_CHOICE,
            widget=forms.Select(attrs={ 'style': 'padding:2px' }))
    captcha = CaptchaField(widget=CaptchaWidget(attrs={'class':'formwidth'}))

    def clean_title(self):
        title = self.cleaned_data['title']
        try:
            # Just to make sure that we can get a valid wiki word out
            self.slug = title_to_wikiword(self.cleaned_data['title'])
        except sym.invalid_title.exc:
            raise forms.ValidationError('Cannot convert %s to a page url. '
                    'Try adding a word or two using English letters.' % title)
        return title
    
    def create_page(self, wiki_slug):
        wiki_page = WikiPage.objects.get_or_create_wikipage(wiki_slug,
                self.slug, self.cleaned_data['title'], self.cleaned_data['cat'])
        return wiki_page.get_absolute_url()
