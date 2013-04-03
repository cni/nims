# @author:  Gunnar Schaefer
#           Reno Bowen

import os
import json
import shlex
import datetime
import subprocess

from tg import config, expose, flash, lurl, request, redirect, response
from tg.i18n import ugettext as _, lazy_ugettext as l_
import webob.exc

import nimsutil
from nimsgears.model import *

from nimsgears.lib.base import BaseController
from nimsgears.controllers.auth import AuthController
from nimsgears.controllers.pub import PubController
from nimsgears.controllers.error import ErrorController
from nimsgears.controllers.experiment import ExperimentController
from nimsgears.controllers.session import SessionController
from nimsgears.controllers.epoch import EpochController
from nimsgears.controllers.dataset import DatasetController
from nimsgears.controllers.user import UserController

__all__ = ['RootController']

store_path = config.get('store_path')


class RootController(BaseController):

    """Root controller for the nimsgears application."""

    auth = AuthController()
    pub = PubController()
    error = ErrorController()
    experiment = ExperimentController()
    session = SessionController()
    epoch = EpochController()
    dataset = DatasetController()
    user = UserController()

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

    @expose('nimsgears.templates.pyramid', render_params={'doctype': None})
    def pyramid(self, **kwargs):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        ds = Dataset.get(kwargs['dataset_id'])
        if user.has_access_to(ds):
            db_file = os.path.join(store_path, ds.relpath, ds.filenames[0])
            return dict(zip(['dataset_id', 'tile_size', 'x_size', 'y_size'], (ds.id,) + nimsutil.pyramid.info_from_db(db_file)))

    @expose(content_type='image/jpeg')
    def pyramid_tile(self, *args):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        dataset_id, z, x, y = map(int, args[0].rsplit('.', 1)[0].split('_'))
        ds = Dataset.get(dataset_id)
        if user.has_access_to(ds):
            del response.pragma
            response.etag = args[0]
            response.cache_control = 'max-age = 86400'
            response.last_modified = ds.updatetime
            return nimsutil.pyramid.tile_from_db(os.path.join(store_path, ds.relpath, ds.filenames[0]), z, x, y)

    @expose(content_type='application/octet-stream')
    def file(self, **kwargs):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        if 'id' in kwargs and 'filename' in kwargs:
            ds = Dataset.get(kwargs['id'])
            filepath = os.path.join(store_path, ds.relpath, kwargs['filename'])
            if user.has_access_to(ds, u'Read-Only' if (ds.kind == u'primary' or ds.kind == u'secondary') else u'Anon-Read'):
                if os.path.exists(filepath):
                    response.content_disposition = 'attachment; filename=%s' % kwargs['filename'].encode('utf-8')
                    response.content_length = os.path.getsize(filepath) # not actually working
                    return open(filepath, 'r')
                else:
                    raise webob.exc.HTTPNotFound()
            else:
                raise webob.exc.HTTPForbidden()

    @expose(content_type='application/x-tar')
    def download(self, **kwargs):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        user_path = '%s/%s' % (config.get('links_path'), 'superuser' if user.is_superuser else user.uid)
        files = None
        if 'id_dict' in kwargs and 'sess' in kwargs['id_dict']:
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['sess']]
            res = (DBSession.query(Session, Experiment, ResearchGroup, Dataset, Epoch)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(ResearchGroup, Experiment.owner)
                    .join(Epoch, Session.epochs)
                    .join(Dataset, Epoch.datasets)
                    .filter((Dataset.kind == u'peripheral') | (Dataset.kind == u'derived'))
                    .filter(Session.id.in_(id_list))
                    .all())
            files = ['nims/%s/%s/%s/%s/%s' % (r.ResearchGroup.gid, r.Experiment.name, r.Session.dirname, r.Epoch.dirname, f) for r in res for f in r.Dataset.filenames]
        elif 'id_dict' in kwargs and 'dataset' in kwargs['id_dict']:
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['dataset']]
            res = (DBSession.query(Dataset, Epoch, Session, Experiment, ResearchGroup)
                    .join(Epoch, Dataset.container)
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(ResearchGroup, Experiment.owner)
                    .filter(Dataset.id.in_(id_list))
                    .all())
            files = ['nims/%s/%s/%s/%s/%s' % (r.ResearchGroup.gid, r.Experiment.name, r.Session.dirname, r.Epoch.dirname, f) for r in res for f in r.Dataset.filenames]
        if files:
            tar_proc = subprocess.Popen(shlex.split('tar -chf - -C %s %s' % (user_path, ' '.join(files))), stdout=subprocess.PIPE)
            response.content_disposition = 'attachment; filename=%s_%s' % ('nims', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
            return tar_proc.stdout

    @expose(content_type='application/x-tar')
    def tarball(self, **kwargs):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        tar_proc = subprocess.Popen(shlex.split('nims_tar.sh tmp_dir'), stdout=subprocess.PIPE)
        response.content_disposition = 'attachment; filename=%s_%s' % ('nims', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
