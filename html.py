import lxml.html
import lxml.html.clean

# From http://feedparser.org/docs/html-sanitization.html, but removed
# form-related tags.

ALLOWED_TAGS = """a abbr acronym address area b big blockquote br button
caption center cite code col colgroup dd del dfn dir div dl dt em 
font h1 h2 h3 h4 h5 h6 hr i input ins kbd label legend li map 
ol optgroup option p pre q s samp small span strike strong sub sup
table tbody td tfoot th thead tr tt u ul var""".split()


CLEANER = lxml.html.clean.Cleaner(style=True,
                                  remove_unknown_tags=False,
                                  allow_tags=ALLOWED_TAGS)

# TODO: nofollow?

def clean(html):
    """Clean a *string* of HTML. If you have a ElementTree, use
    CLEANER directly."""
    if len(html) == 0:
        return ''

    doc = lxml.html.fromstring(html)
    CLEANER(doc)
    if len(doc) == 0 and doc.tag == 'p':
        # Special case: we're just simple <p>text</p> -- strip HTML
        # out.
        return doc.text
    else:
        return lxml.html.tostring(doc)

def strip_whitespace(elem):
    """Modify the element *in place*, killing all pure whitespace tags
    (as defined by having no text content). We return a boolean
    indicating whether the root level element has any textual content
    at all."""
    strip = []
    for child in elem.iter():
        if not has_text([child]):
            strip.append(child)

    if elem in strip:
        elem.clear()
        return False
    else:
        for child in strip:
            child.drop_tree()
        return True

def has_text(elems):
    """True if elems (a list of ElementTree elems) has any textual
    content."""
    return bool(
        ''.join(subelem.text_content()
                for elem in elems
                for subelem in elem.iter())
          .strip()
    )

def links_of_html(html):
    return [(elem.text_content(), link)
            for elem, _, link, _ in lxml.html.fromstring(html).iterlinks()]
