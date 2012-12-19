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
            if self.user_has_access_to(user, kw.get('id'), Experiment):
                form = EditExperimentForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(page='experiment',
                    form=form,
                    )

    @expose()
    @validate(EditExperimentForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user']
        if self.user_has_access_to(user, kw['id'], Experiment):
            id_ = kw['id']
            name = kw['name']
            owner = ResearchGroup.query.filter_by(gid=kw['owner']).one()
            exp = Experiment.query.filter_by(id=id_).one()
            exp.name = name
            exp.owner = owner
            transaction.commit()
        flash('Saved (%s)' % datetime.now().strftime("%m/%d/%Y %H:%M:%S"))
        redirect('/auth/experiment/edit?id=%s' % id_)

    @expose('nimsgears.templates.experiments.add')
    def create(self, **kw):
        form = NewExperimentForm
        return dict(page='experiments',
                    form=form,
                    )

    @expose()
    @validate(NewExperimentForm, error_handler=create)
    def post_create(self, **kw):
        name = kw['name']
        owner = kw['owner']
        if owner in get_owners():
            experiment = Experiment.from_owner_name(
                owner=ResearchGroup.query.filter_by(gid=owner).one(),
                name=name)
            DBSession.add(experiment)
        redirect('/auth/experiment/create')

def get_owners():
    user = request.identity['user']
    if user.is_superuser:
        research_groups = ResearchGroup.query.all()
    else:
        research_groups = user.pi_groups + user.manager_groups
    return [group.gid for group in research_groups]
