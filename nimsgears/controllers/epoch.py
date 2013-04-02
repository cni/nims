from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from datetime import datetime
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *
from nimsgears.widgets.epoch import EditEpochForm
import transaction

class EpochController(NimsController):
    @expose('nimsgears.templates.form')
    def edit(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        if tmpl_context.form_errors:
            form = EditEpochForm
        else:
            if user.has_access_to(Epoch.get(kw.get('id')), u'Read-Only'):
                form = EditEpochForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(page='epoch', form=form)

    @expose()
    @validate(EditEpochForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        epoch = Epoch.get(kw.get('id'))
        if user.has_access_to(epoch, u'Read-Write'):
            epoch.description = kw['description']
            transaction.commit()
            flash('Saved (%s)' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        else:
            flash('permission denied')
        redirect('../epoch/edit?id=%s' % kw['id'])
