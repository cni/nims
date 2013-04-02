from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from datetime import datetime
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *
from nimsgears.widgets.experiment import NewExperimentForm, EditExperimentForm
import transaction

class ExperimentController(NimsController):
    @expose('nimsgears.templates.form')
    def edit(self, **kw):
        user = request.identity['user']
        if tmpl_context.form_errors:
            form = EditExperimentForm
        else:
            if user.has_access_to(Experiment.get(kw.get('id')), u'Read-Only'):
                form = EditExperimentForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(page='experiment', form=form)

    @expose()
    @validate(EditExperimentForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user']
        exp = Experiment.get(kw['id'])
        if user.has_access_to(exp, u'Read-Write'):
            exp.name = kw['name'].lower()
            exp.owner = ResearchGroup.get_by(gid=kw['owner'])
            transaction.commit()
            flash('Saved (%s)' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        else:
            flash('permission denied')
        redirect('/auth/experiment/edit?id=%s' % kw['id'])

    @expose('nimsgears.templates.experiments.add')
    def create(self, **kw):
        return dict(page='experiments', form=NewExperimentForm)

    @expose()
    @validate(NewExperimentForm, error_handler=create)
    def post_create(self, **kw):
        user = request.identity['user']
        if kw['owner'] in user.admin_group_names:
            experiment = Experiment.from_owner_name(owner=ResearchGroup.query.filter_by(gid=kw['owner']).one(), name=kw['name'])
            DBSession.add(experiment)
        redirect('/auth/experiment/create')
