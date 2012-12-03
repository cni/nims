import os
import sys
import site

site.addsitedir('/var/local/tg2env/lib/python2.7/site-packages')

sys.path.append('/var/local/nims')

os.environ['PYTHON_EGG_CACHE'] = '/tmp/python_egg_cache'                # apache must have write access

from paste.deploy import loadapp
application = loadapp('config:/var/local/nims/production.ini')
