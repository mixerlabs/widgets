"""Provide transcoding from wikis to (OneColumnPage) widgets using the
wiki HTML as an intermediate format."""

# CAUTION: this transcoder breaks many abstractions. We read directly
# from the generated HTML of the wiki page, and also manipulate
# widgets directly via their instance variables.

# todo:
#  - HTML
#  - header + 1 section == section header. [2 pass]
#  - strip all-whitespace HTML sections. (ie no element has any text_content)

# XXX - really should do proper recursive-descent parsing, but given
# that widgets are inherently flat anyway, this flat-parsing works
# well.

from __future__ import absolute_import
from __future__ import with_statement

import re
import lxml.html
from itertools               import groupby, islice
from copy                    import deepcopy
from django.utils.safestring import mark_safe

from util                     import storage
from util.dynvar              import binding
from util.functional          import concat
from www.common.media_storage import media_file_storage
from www.common.models        import Thumb, Photo
from www.feedback.models      import Feedback
import www.wiki.render

from .              import html
from .page          import OneColumnPage
from .models        import WikiPage
from .headingwidget import Heading
from .listwidget    import List
from .dividerwidget import Divider
from .sectionwidget import Section
from .picturewidget import Picture

# | Fillers
#
# These take a collection of elements & fills out a preinstantiated
# widget out of them.

def html_of_elems(elems, wrap_in_div=False):
    """Create HTML from a list of elements, cleaning the HTML and
    stripping whitespace, optionally wrapping them in a div (when
    needed)."""
    elems = map(deepcopy, elems)
    if wrap_in_div and (len(elems) != 1 or elems[0].tag != 'div'):
        div = lxml.html.Element('div')
        div.extend(elems)
        elems = [div]

    def clean_elem(elem):
        html.CLEANER(elem)
        if html.strip_whitespace(elem):
            return lxml.html.tostring(elem)
        else:
            return ''

    return mark_safe(''.join(map(clean_elem, elems)))

def fill_heading(widget, elems):
    [elem] = elems
    assert elem.tag in ('h1', 'h2', 'h3')
    widget.contents = elem.text_content().strip()
    return widget.contents

def fill_list(widget, elems):
    [elem] = elems
    assert elem.tag in ['ol', 'ul']
    # TODO: Support nested lists instead of flattening them
    items = elem.iterchildren(tag='li')
    # TODO: don't strip out HTML when we have support for it.
    widget.items = [item.text_content().strip() for item in items]
    return True

def fill_section(widget, elems):
    widget.contents = html_of_elems(elems, wrap_in_div=True)
    return html.has_text(elems)

# For dissecting img src=..
IMAGE_RE = re.compile(r'''
^
.*                                       # path prefix
/image_(?P<media_hash>[^/]+)             # the media hash
/(?P<photo_slug>[^./]+)(?P<ext>\.[^.]+)  # slug + ext
$''', re.VERBOSE)

def fill_picture(widget, elems):
    [elem] = elems
    [img]  = elem.cssselect('img')
    m      = IMAGE_RE.match(img.attrib['src'])
    assert m
    try:
        [caption] = elem.cssselect('div.wiki_img_caption')
        caption = caption.text_content().strip()
    except ValueError:
        caption = ''

    d = m.groupdict()
    # Copy the original high-resolution photo to our picture widget &
    # set the size appropriately.
    basename = d['media_hash'] + d['ext']
    try:
        wiki_photo = Thumb.objects.filter(image=basename)[0].photo
    except IndexError:
        try:
            wiki_photo = Photo.objects.filter(image=basename)[0]
        except IndexError:
            print 'Failed to locate thumb or photo for %s, skipping' % basename
            return False

    try:
        file = media_file_storage.open(wiki_photo.image.name)
    except IOError:
        print 'Failed to locate media file %s, skipping' % wiki_photo.image.name
        return False
    file.content_type = 'application/octet-stream'

    widget.set_picture(
        image=file, caption=img.attrib.get('alt', ''), freeze=False,
        attributes=wiki_photo.attributes, uploaded_at=wiki_photo.uploaded_at,
        user=wiki_photo.user, ip_address=wiki_photo.ip_address,
        caption=caption, width=wiki_photo.width, height=wiki_photo.height)
    widget.size = {150: 'small',
                   300: 'medium',
                   600: 'small'}.get(int(img.attrib['width']), 'small')
    widget.picture.image.file.open()
    return True

def move_images_top_top_level(html):
    """ Move images to the top level (right after the top-level ancestor)
    Example: <div><h2>Hi<img></h2></div> becomes <div><h2>Hi</h2><img></div>    
    """
    branch_index = len(html) - 1
    # Walk in reversed order so adding elements doesn't upset the indexing
    while branch_index >= 0:
        branch = html[branch_index]
        # look for 3 kinds of image containers - by moving  one at a
        # time with precendence, nested matches don't pose a problem
        images = (concat(branch.cssselect('div.wiki_img_%s' % which)
                for which in ['left', 'center', 'right', 'none']) +
                branch.cssselect('div.wiki_img_frame') +
                branch.cssselect('a.wiki_img_link'))
        if images and branch != images[0]:
            # Only do the highest precendence match
            image = images[0]
            # Remove this element tree
            image.getparent().remove(image)
            # And re-add to the top level following the current branch
            html.insert(branch_index + 1, image)
        else:
            branch_index -= 1
            
def append_wiki_to_onecolumnpage(wiki_page_version, page):
    """Parse the title & body in `wiki_page_version' and append it to
    the OneColumnPage `page'."""
    
    html_snippet = www.wiki.render.render_page(wiki_page_version)
    # Put the snippet inside a div so lxml has an unambiguous root element
    html = lxml.html.fromstring('<div>%s</div>' % html_snippet)

    move_images_top_top_level(html)
    
    # Our strategy is as follows: find elements that define chunks
    # (ie. widgets), and partition them accordingly. Everything that
    # doesn't fit is a "section" widget.

    # Define partitioning elements for each type of widget.
    elems_of_type = {
        'heading' : html.cssselect('h1') +
                    html.cssselect('h2') +
                    html.cssselect('h3'),
        'list'    : html.cssselect('ol') +
                    html.cssselect('ul'),
        'divider' : html.cssselect('hr'),
        # We need to describe any potential root element of a image,
        # so that the remainder doesn't end up in a section widget.
        'picture' : concat(html.cssselect('div.wiki_img_%s' % which)
                           for which in ['left', 'center', 'right', 'none']) +
                    html.cssselect('div.wiki_img_frame'),
    }

    # Define how to make a widget from a set of elements as
    # partitioned by the above elements.
    widget_of_type = {
        'heading' : (Heading , fill_heading       ),
        'list'    : (List    , fill_list          ),
        'divider' : (Divider , lambda *args: True ),
        'section' : (Section , fill_section       ),
        'picture' : (Picture , fill_picture       ),
    }

    # Reverse it, concatenating out individual elements so that we are
    # mapping each element with a type to its type.
    cutoffs = dict((elem, elemtype)
                   for elemtype, elems in elems_of_type.items()
                   for elem in elems)

    def parent_cutoff_elem_of_elem(elem):
        if elem is None:
            return None

        parent = parent_cutoff_elem_of_elem(elem.getparent())
        if parent is not None:
            return parent
        elif elem in cutoffs:
            return elem
        else:
            return None

    def all_parents_of_elem(elem):
        parent = elem.getparent()
        if parent is None:
            return []
        else:
            return [parent] + all_parents_of_elem(parent)

    def collect_roots(elems):
        """Filter the set of elements down to the set of common roots."""
        elemset = set(elems)
        for elem in elemset.copy():
            if set(all_parents_of_elem(elem)) & elemset:
                elemset.remove(elem)

        return sorted(elemset, key=elems.index)

    # Set the title.
    page.title = wiki_page_version.title
    if wiki_page_version.category:
        page.category = wiki_page_version.category

    # Set the created_by
    page.edit_user = wiki_page_version.edit_user
    page.edit_ip_address = wiki_page_version.edit_ip_address
    page.edit_time = wiki_page_version.created_at
    
    for elem, elems in groupby(html.iterdescendants(),
                               parent_cutoff_elem_of_elem):
        elems = list(elems)

        if elem is None:
            elemtype = 'section'
        else:
            elemtype = cutoffs[elem]

        if elemtype in widget_of_type:
            klass, fill = widget_of_type[elemtype]
            widget      = klass()
            page.order.append(page.append(widget))

            elems  = collect_roots(elems)
            if not fill(widget, elems):
                del page.order[-1]

    # | Postprocessing
    # 
    # Collapse adjacent header & section widgets, integrating the
    # former into the latter.
    collect = []
    for i0, i1 in zip(range(len(page.order)), range(1, len(page.order))):
        w0 = page[page.order[i0]]
        w1 = page[page.order[i1]]
        
        if isinstance(w0, Heading) and (isinstance(w1, Section) or
                                        isinstance(w1, List)):
            collect.append(i0)
            w1.title = w0.contents

    for i in sorted(collect, reverse=True):
        del page[page.order[i]]
        del page.order[i]


def transcode_wiki_to_onecolumnpage(wiki_page, page, later_than=None):
    """ Transcode each version of 'wiki_page' on top of 'page' widget such
    that page gets completely erased and rewritten each time, and there will
    only be one WidgetState object created for the page root and 1 change
    object for each successive page version.
    
    Also, migrate any feedback points from the wiki to the widget. """
    first = later_than is None
    versions = wiki_page.pageversion_set.order_by('version')
    if later_than:
        versions = versions.filter(created_at__gt=later_than)
    #print '%d versions' % versions.count()
    #ddd = 0
    for version in versions:
        #print 'version %d' % ddd
        #print 'children %d' % len(page.children)
        #ddd += 1        
        page.clear()
        transcoding = storage(version=version)
        with binding(transcoding=transcoding,
                     is_hidden_change=version.is_hidden_change):
            if first:
                # Extra freeze first time so page starts from an empty state
                first = False
                page.freeze()
            page.freeze()
            # Re-use the same state_id for additonal freezes on this object
            # this wiki version transcode
            transcoding.state_id = page.get_state_id()
            append_wiki_to_onecolumnpage(version, page)
            transcoding.create_change = True
            page.freeze()
            
    # Migrate any feedback from wiki page to widget page delegate
    Feedback.objects.migrate_feedback_to_new_object(wiki_page, page.delegate)

