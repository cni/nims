import os
import sys
import site

site.addsitedir('/usr/local/www/tg2env/lib/python2.7/site-packages')

sys.path.append('/usr/local/www/nims')

os.environ['PYTHON_EGG_CACHE'] = '/tmp/python_egg_cache'                # apache must have write access

from paste.deploy import loadapp
application = loadapp('config:/usr/local/www/nims/production.ini')
