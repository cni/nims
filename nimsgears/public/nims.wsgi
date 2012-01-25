import os
import sys
import site

site.addsitedir('/usr/local/pythonenv/tg2/lib/python2.7/site-packages')

sys.path.append('/usr/local/www/apache22/nims')

os.environ['PYTHON_EGG_CACHE'] = '/tmp/python_egg_cache'                # apache must have write access

#from paste.script.util.logging_config import fileConfig
#fileConfig('/usr/local/www/apache22/nims/production.ini')

from paste.deploy import loadapp
application = loadapp('config:/usr/local/www/apache22/nims/production.ini')
