# -*- coding: utf-8 -*-
"""
Global configuration file for TG2-specific settings in nimsgears.

This file complements development/deployment.ini.

Please note that **all the argument values are strings**. If you want to
convert them into boolean, for example, you should use the
:func:`paste.deploy.converters.asbool` function, as in::

    from paste.deploy.converters import asbool
    setting = asbool(global_conf.get('the_setting'))
"""

from tg.configuration import AppConfig

import nimsgears
from nimsgears import model
from nimsgears.lib import app_globals, helpers

from remote_user import RemoteUserIdentifier

base_config = AppConfig()
base_config.renderers = []

base_config.package = nimsgears

# Enable json in expose
base_config.renderers.append('json')

# Set the default renderer
base_config.default_renderer = 'genshi'
base_config.renderers.append('genshi')

# Configure the base SQLALchemy Setup
base_config.use_sqlalchemy = True
base_config.model = model
base_config.DBSession = model.DBSession

# Configure the authentication backend
base_config.auth_backend = 'sqlalchemy'
base_config.sa_auth.dbsession = model.DBSession
base_config.sa_auth.user_class = model.User
base_config.sa_auth.group_class = model.Group
base_config.sa_auth.permission_class = model.Permission
base_config.sa_auth.translations.user_name = 'uid'
base_config.sa_auth.translations.group_name = 'gid'
base_config.sa_auth.translations.permission_name = 'pid'

# override this if you would like to provide a different who plugin for
# managing login and logout of your application
base_config.sa_auth.identifiers = [('remote_user_identifier', RemoteUserIdentifier(model.User, model.DBSession))]
base_config.sa_auth.remote_user_key = 'repoze.who.remote_user'

# override this if you are using a different charset for the login form
base_config.sa_auth.charset = 'utf-8'

# You may optionally define a page where you want users to be redirected to on login:
base_config.sa_auth.post_login_url = '/post_login'

# You may optionally define a page where you want users to be redirected to on logout:
base_config.sa_auth.post_logout_url = '/post_logout'
