# @author:  Gunnar Schaefer

from tg import config, expose, flash, redirect, request, response
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates
import webob.exc

import os
import shlex
import datetime
import subprocess
from collections import OrderedDict

import nimsutil
from nimsgears import model
from nimsgears.model import *

from nimsgears.lib.base import BaseController
from nimsgears.controllers.experiments import ExperimentsController
from nimsgears.controllers.browse import BrowseController
from nimsgears.controllers.search import SearchController
from nimsgears.controllers.groups import GroupsController
from nimsgears.controllers.experiment import ExperimentController
from nimsgears.controllers.session import SessionController
from nimsgears.controllers.epoch import EpochController
from nimsgears.controllers.dataset import DatasetController

import json

__all__ = ['AuthController']


class AuthController(BaseController):

    experiments = ExperimentsController()
    browse = BrowseController()
    search = SearchController()
    groups = GroupsController()
    experiment = ExperimentController()
    session = SessionController()
    epoch = EpochController()
    dataset = DatasetController()

    allow_only = predicates.not_anonymous(msg=l_('You must be logged in to view this page.'))

    # FIXME: handle deactivated users
    #active_user = predicates.in_group('users', msg=l_('Your account is inactive. You can request activation below.'))

    def _not_active_user(msg):
        flash(msg)
        redirect('/auth/activate')

    @expose()
    def index(self):
        redirect('/auth/browse')

    @expose('nimsgears.templates.activate')
    def activate(self, **kwargs):
        return self.prefs()

    @expose('nimsgears.templates.toggle_admin')
    def toggle_admin(self, came_from):
        user = request.identity['user']
        DBSession.add(user)
        user.admin_mode = not user.admin_mode
        redirect(came_from)

    @expose('nimsgears.templates.prefs')
    def prefs(self, **kwargs):
        user = request.identity['user']

        if kwargs:
            DBSession.add(user)
            for key, value in kwargs.iteritems():
                setattr(user, key, value)
            flash(l_('Your settings have been updated.'))

        if not user.firstname or not user.lastname or not user.email:
            ldap_firstname, ldap_lastname, ldap_email = nimsutil.ldap_query(user.uid)
        firstname = user.firstname or ldap_firstname
        lastname = user.lastname or ldap_lastname
        email = user.email or ldap_email

        prefs = OrderedDict()
        prefs['firstname'] = ('First Name', firstname)
        prefs['lastname'] = ('Last Name', lastname)
        prefs['email'] = ('Email Address', email)

        return dict(page='prefs', prefs=prefs)

    @expose('nimsgears.templates.status')
    def status(self):
        #if not predicates.in_group('active_users').is_met(request.environ):
        #    flash(l_('Your account is not yet active.'))
        #    redirect('/auth/prefs')

        failed_jobs = Job.query.filter(Job.status == u'failed').order_by(Job.id).all()
        active_jobs = Job.query.filter(Job.status == u'running').order_by(Job.id).all()
        queued_jobs = Job.query.filter(Job.status == u'pending').order_by(Job.id).limit(200).all()
        return dict(
                page='status',
                failed_jobs=failed_jobs,
                active_jobs=active_jobs,
                queued_jobs=queued_jobs,
                )

    @expose('nimsgears.templates.admin')
    def admin(self):
        return dict(page='admin', params={})

    @expose(content_type='application/octet-stream')
    def getfile(self, **kwargs):
        user = request.identity['user']
        if 'id' in kwargs and 'filename' in kwargs:
            ds = Dataset.get(int(kwargs['id']))
            filepath = os.path.join(config.get('store_path'), ds.relpath, kwargs['filename'])
            privilege = u'Read-Only' if (ds.kind == u'primary' or ds.kind == u'secondary') else u'Anon-Read'
            if user.is_superuser or user.has_access_to(ds, privilege):
                if os.path.exists(filepath):
                    response.content_disposition = 'attachment; filename=%s' % kwargs['filename'].encode('utf-8')
                    response.content_length = os.path.getsize(filepath) # not actually working
                    return open(filepath, 'r')
                else:
                    raise webob.exc.HTTPNotFound()
            else:
                raise webob.exc.HTTPForbidden()

    @expose()
    def image_viewer(self, **kwargs):
        panojs_url = 'https://cni.stanford.edu/js/panojs/'
        ds = Dataset.get(int(kwargs['dataset_id']))
        pyramid_db_file = os.path.join(config.get('store_path'), ds.relpath, ds.filenames[0])
        tile_size, x_size, y_size = nimsutil.pyramid.get_info_from_db(pyramid_db_file)
        html = ('<head>\n<meta http-equiv="imagetoolbar" content="no"/>\n'
                '<style type="text/css">@import url(' + panojs_url + 'styles/panojs.css);</style>\n'
                '<script type="text/javascript" src="' + panojs_url + 'extjs/ext-core.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/utils.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/PanoJS.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/controls.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/pyramid_imgcnv.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/control_thumbnail.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/control_info.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'panojs/control_svg.js"></script>\n'
                '<script type="text/javascript" src="' + panojs_url + 'viewer.js"></script>\n'
                '<style type="text/css">body { font-family: sans-serif; margin: 0; padding: 10px; color: #000000; background-color: #FFFFFF; font-size: 0.7em; } </style>\n'
                '<script type="text/javascript">\nvar viewer = null;Ext.onReady('
                'function () { createViewer( viewer, "viewer", "./images", "'+str(ds.id)+'_","'+str(tile_size)+'","'+str(x_size)+'","'+str(y_size)+'") } );</script>\n'
                '</head>\n<body>\n'
                '<div style="width: 100%; height: 100%;"><div id="viewer" class="viewer" style="width: 100%; height: 100%;" ></div></div>\n'
                '</body>\n</html>\n')
        return html

    @expose(content_type='image/jpeg')
    def images(self, *args):
        user = request.identity['user']
        dataset_id,z,x,y = args[0].split('_')
        ds = Dataset.get(dataset_id)
        pyramid_db_file = os.path.join(config.get('store_path'), ds.relpath, ds.filenames[0])
        image = nimsutil.pyramid.get_tile_from_db(pyramid_db_file, z, y, x)
        return image

    @expose(content_type='image/png')
    def pngimage(self, *args):
        return open('/tmp/image.png', 'r')

    @expose(content_type='application/x-tar')
    def download(self, **kwargs):
        user = request.identity['user']
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
