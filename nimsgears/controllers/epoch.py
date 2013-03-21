from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from datetime import datetime
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *
from nimsgears.widgets.epoch import EditEpochForm
import transaction

class EpochController(NimsController):
    @expose('nimsgears.templates.form')
    def edit(self, **kw):
        user = request.identity['user']
        if tmpl_context.form_errors:
            form = EditEpochForm
        else:
            if user.has_access_to(Epoch.get(kw.get('id')), u'Read-Only'):
                form = EditEpochForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(page='epoch',
                    form=form,
                    )

    @expose()
    @validate(EditEpochForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user']
        if user.has_access_to(Epoch.get(kw.get('id')), u'Read-Write'):
            id_ = kw['id']
            epoch = Epoch.query.filter_by(id=kw['id']).one()
            epoch.description = kw['description']
            transaction.commit()
        flash('Saved (%s)' % datetime.now().strftime("%m/%d/%Y %H:%M:%S"))
        redirect('/auth/epoch/edit?id=%s' % id_)
