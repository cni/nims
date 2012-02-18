# @author:  Gunnar Schaefer

import transaction
from paste.request import get_cookies


class RemoteUserIdentifier(object):

    def __init__(self, user_class, dbsession, cookie_name='tg.remote_user'):
        self.user_class = user_class
        self.dbsession = dbsession
        self.cookie_name = cookie_name

    def identify(self, environ):
        if 'REMOTE_USER' in environ:
            remote_user = unicode(environ['REMOTE_USER'])
            # FIXME: use repoze translations for user_name
            #        also in tg.config['sa_auth']['translations']['user_name']
            if not self.dbsession.query(self.user_class).filter_by(uid=remote_user).first():
                print 'adding identity for new user "%s"' % remote_user
                self.user_class(uid=remote_user, password=remote_user)
                transaction.commit()
            return {'repoze.who.userid': remote_user}
        else:
            cookie = get_cookies(environ).get(self.cookie_name)
            if cookie:
                return {'repoze.who.userid': unicode(cookie.value.decode('base64'))}
        return None

    def remember(self, environ, identity):
        cookie_value = '%s' % identity['repoze.who.userid']
        cookie_value = cookie_value.encode('base64').rstrip()
        cookie = get_cookies(environ).get(self.cookie_name)
        value = getattr(cookie, 'value', None)
        if value != cookie_value:
            # return a Set-Cookie header
            cookie = '%s=%s; Path=/;' % (self.cookie_name, cookie_value)
            return [('Set-Cookie', cookie)]

    def forget(self, environ, identity):
        # clear and expire the cookie
        cookie = ('%s=""; Path=/; Expires=Fri, 22-Jun-1979 22:05:00 CET' % self.cookie_name)
        return [('Set-Cookie', cookie)]
