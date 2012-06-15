# @author:  Gunnar Schaefer
#           Reno Bowen

from tg import expose, flash, lurl, request, redirect
from tg.i18n import ugettext as _, lazy_ugettext as l_

from nimsgears.lib.base import BaseController
from nimsgears.controllers.auth import AuthController
from nimsgears.controllers.error import ErrorController

__all__ = ['RootController']


class RootController(BaseController):

    """Root controller for the nimsgears application."""

    auth = AuthController()
    error = ErrorController()

    @expose('nimsgears.templates.index')
    def index(self):
        """Handle the front-page."""
        return dict(page='index')

    @expose('nimsgears.templates.about')
    def about(self):
        """Handle the 'about' page."""
        return dict(page='about')

    @expose('nimsgears.templates.environ')
    def environ(self):
        """This method showcases TG's access to the wsgi environment."""
        return dict(environment=request.environ)

    @expose('nimsgears.templates.login')
    def login(self, came_from=lurl('/')):
        """Start the user login."""
        login_counter = request.environ['repoze.who.logins']
        if login_counter > 0:
            flash(_('Wrong credentials.'), 'warning')
        return dict(page='login', login_counter=str(login_counter), came_from=came_from)

    @expose()
    def post_login(self, came_from=lurl('/')):
        """
        Redirect the user to the initially requested page on successful
        authentication or redirect her back to the login page if login failed.
        """
        if not request.identity:
            login_counter = request.environ['repoze.who.logins'] + 1
            redirect('/login', params=dict(came_from=came_from, __logins=login_counter))
        redirect(came_from)

    @expose()
    def post_logout(self, came_from=lurl('/')):
        """Redirect the user to the home page on logout."""
        redirect('/')
