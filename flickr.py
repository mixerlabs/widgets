"""Simple flickr encapsulation."""

import simplejson
import urllib

from django.conf import settings
from subprocess  import Popen
from shutil      import copyfileobj

from util            import mixlog
from util.functional import pick_n, memoizei

from www.common.temporary_file import TemporaryUploadedFileWithChunks

class OpenAsIe(urllib.FancyURLopener):
    version = 'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)'

class FlickrException(Exception):
    pass

class FlickrImage(object):
    """An object to represent & manipulate a flickr image. This is a
    refactoring/combination of what's in:
    bin/one_off/city-images/city-images.py and www/common/forms.py.

    TODO: We should refactor UploadedPhotoForm to use this the next
    time any code changes.."""

    def __init__(self, id):
        self.id = id

    def call(self, method, **kwargs):
        url = ('http://api.flickr.com/services/rest/?method=%s'
               '&api_key=%s&format=json&nojsoncallback=1&%s' % (
                   method, settings.FLICKR_API_KEY, urllib.urlencode(kwargs)))
        result = simplejson.load(OpenAsIe().open(url))
        if result.get('stat', 'fail') == 'fail':
            raise FlickrException(result.get('message', 'Flickr error'))
        return result

    @property
    def photo(self):
        return self.info['photo']

    @property
    @memoizei
    def info(self):
        return self.call('flickr.photos.getInfo', photo_id=self.id)

    @property
    @memoizei
    def attrs(self):
        attrs = {
            'provider' : 'flickr',
            'url'      : self.photo['urls']['url'][0]['_content']
        }

        def set_attr_if_present(tag, value, path):
            try:
                for part in path.split('/'):
                    value = value[part]
                attrs[tag] = value
            except KeyError:
                pass

        # These are optional
        for tag in ['id', 'secret', 'server', 'farm', 'license', 'rotation',
                    'originalsecret', 'originalformat', 'dateuploaded']:
            set_attr_if_present(tag, self.photo, tag)

        set_attr_if_present('username'    , self.photo , 'owner/username')
        set_attr_if_present('realname'    , self.photo , 'owner/realname')
        set_attr_if_present('location'    , self.photo , 'owner/location')
        set_attr_if_present('description' , self.photo , 'description/_content')
        set_attr_if_present('datetaken'   , self.photo , 'dates/taken')

        # If there are tags, join them as one string of keywords
        attrs['tags'] = \
            ' '.join([t['_content'] for t in self.photo['tags']['tag']])

        # Pull in geo attributes if there are any
        try:
            geo = self.call('flickr.photos.geo.getLocation', photo_id=id)
            for tag in ['longitude', 'latitude', 'accuracy']:
                set_attr_if_present(tag, geo, 'photo/location/%s' % tag)
        except FlickrException:
            pass

        # Filter off default attribute values
        for attr in attrs.keys():
            if attr in ['rotation', 'latitude', 'longitude', 'accuracy']:
                default = 0
            else:
                default = ''

            if attrs[attr] == default:
                del attrs[attr]

        return attrs

    @property
    def temporary_file(self):
        attrs = self.attrs
        rotation = int(attrs.get('rotation', 0))
        # First try to get the original high-res source image from flickr.  If
        # that doesn't work, fall back to getting the medium size one.
        try:
            if rotation and attrs['originalformat'] != 'jpg':
                # Don't fetch the orginal image if it was rotated in a format
                # other than jpg, because only jpg supports lossless rotate.
                # TODO: If this ever actually happens, consider using PIL to
                # rotate the image and save back in the proper format.
                mixlog().warning(
                    'flickr - a non-jpg rotated image:%s' % attrs['url'])
                raise KeyError

            args = tuple(urllib.quote(str(attrs[a])) for a in
                         ['farm', 'server', 'id',
                          'originalsecret', 'originalformat'])
            url = 'http://farm%s.static.flickr.com/%s/%s_%s_o.%s' % args
        except KeyError:
            try:
                args = tuple(urllib.quote(str(attrs[a])) for a in
                             ['farm', 'server', 'id', 'secret'])
                url = 'http://farm%s.static.flickr.com/%s/%s_%s.jpg' % args
            except KeyError:
                raise forms.ValidationError('Invalid flickr parameters')

        # Choose a reasonable default filename based on flickr attributes
        file_name = attrs.get('title', attrs['id'])

        # Start the fetch from flickr
        url_file = urllib.urlopen(url)
        mime_type = url_file.info().gettype()

        # TODO: make sure when flickr fails or takes too long, appropriate
        # forms.ValidationError messages go out

        # The image in a form is actually just a TemporaryUploadedFile 
        file = TemporaryUploadedFileWithChunks(file_name, mime_type, 0, None)

        # Download the url into the temporary fle.         
        if rotation in (90, 180, 270) and mime_type == 'image/jpeg':
            # Do a lossless jpeg rotate
            process = Popen(('jpegtran', '-rotate', str(rotation)),
                            stdin=PIPE, stdout=PIPE)
            file.write(process.communicate(url_file.read())[0])
            if process.returncode:
                mixlog.warn('jpegtran error %d:%s' % process.returncode, url)
                raise ValueError, 'Unable to rotate image'
        else:
            # Stream in chunks (default is 16k)
            copyfileobj(url_file, file)

        # Note the actual size and rewind the file
        file.size = file.tell()
        file.seek(0)

        return file

