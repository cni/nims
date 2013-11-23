# @author:  Gunnar Schaefer
#           Reno Bowen

import os
import json
import datetime
import tempfile
import subprocess

from tg import config, expose, flash, lurl, request, redirect, response
from tg.i18n import ugettext as _, lazy_ugettext as l_
import webob.exc

import nimsdata
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
temp_path = config.get('temp_path')


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
            return dict(zip(['dataset_id', 'tile_size', 'x_size', 'y_size'], (ds.id,) + nimsdata.nimsmontage.get_info(db_file)))

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
            return nimsdata.nimsmontage.get_tile(os.path.join(store_path, ds.relpath, ds.filenames[0]), z, x, y)

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
        db_results = []
        epoch_paths = []
        symlinks = []
        temp_dir = tempfile.mkdtemp(dir=temp_path)
        if 'id_dict' in kwargs and 'sess' in kwargs['id_dict']:
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['sess']]
            db_query = (DBSession.query(Session, Experiment, ResearchGroup, Dataset, Epoch)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .join(Epoch, Session.epochs)
                .join(Dataset, Epoch.datasets)
                .filter(Session.id.in_(id_list)))
            if kwargs.get('raw'):
                db_results = db_query.filter(Dataset.kind != u'web').all()
            else:
                db_results = db_query.filter((Dataset.kind == u'peripheral') | (Dataset.kind == u'derived')).all()
        elif 'id_dict' in kwargs and 'epoch' in kwargs['id_dict']:
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['epoch']]
            db_query = (DBSession.query(Session, Experiment, ResearchGroup, Dataset, Epoch)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .join(Epoch, Session.epochs)
                .join(Dataset, Epoch.datasets)
                .filter(Epoch.id.in_(id_list)))
            if kwargs.get('raw'):
                db_results = db_query.filter(Dataset.kind != u'web').all()
            else:
                db_results = db_query.filter((Dataset.kind == u'peripheral') | (Dataset.kind == u'derived')).all()
        elif 'id_dict' in kwargs and 'dataset' in kwargs['id_dict']:
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['dataset']]
            db_results = (DBSession.query(Dataset, Epoch, Session, Experiment, ResearchGroup)
                    .join(Epoch, Dataset.container)
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(ResearchGroup, Experiment.owner)
                    .filter(Dataset.id.in_(id_list))
                    .all())
        for r in db_results:
            if user.has_access_to(r.Dataset, u'Read-Only' if (r.Dataset.kind == u'primary' or r.Dataset.kind == u'secondary') else u'Anon-Read'):
                if kwargs.get('legacy'):
                    ep = '%s/nims/%s/%s/%s' % (temp_dir, r.ResearchGroup.gid, r.Experiment.name, r.Session.legacy_dirname)
                else:
                    ep = '%s/nims/%s/%s/%s/%s' % (temp_dir, r.ResearchGroup.gid, r.Experiment.name, r.Session.dirname, r.Epoch.dirname)
                epoch_paths.append(ep)
                for filename in r.Dataset.filenames:
                    if kwargs.get('legacy'):
                        name, sep, ext = filename.partition('.')
                        if name.endswith('_B0'):        ext = '_B0.%s' % ext
                        elif name.endswith('_physio'):  ext = '_physio.%s' % ext
                        elif name.endswith('_dicoms'):  ext = '_dicoms.%s' % ext
                        else:                           ext = '.%s' % ext
                        sl_name = '%04d_%02d_%s%s' % (r.Epoch.series, r.Epoch.acq, r.Epoch.description, ext)
                    else:
                        sl_name = filename
                    symlinks += [(os.path.join(store_path, r.Dataset.relpath, filename), os.path.join(ep, sl_name))]
        for ep in set(epoch_paths):
            os.makedirs(ep)
        for sl in symlinks:
            os.symlink(*sl)
        tar_proc = subprocess.Popen('tar -chf - -C %s nims; rm -r %s' % (temp_dir, temp_dir), shell=True, stdout=subprocess.PIPE)
        response.content_disposition = 'attachment; filename=%s_%s' % ('nims', datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        return tar_proc.stdout
