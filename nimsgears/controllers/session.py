from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from datetime import datetime
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *
from nimsgears.widgets.session import EditSessionForm
import transaction

class SessionController(NimsController):
    @expose('nimsgears.templates.form')
    def edit(self, **kw):
        user = request.identity['user']
        if tmpl_context.form_errors:
            form = EditSessionForm
        else:
            if self.user_has_access_to(user, kw.get('id'), Session):
                form = EditSessionForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(page='session',
                    form=form,
                    )

    @expose()
    @validate(EditSessionForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user']
        if self.user_has_access_to(user, kw['id'], Session):
            id_ = kw['id']
            username = kw['operator']['uid']
            session = Session.query.filter_by(id=id_).one()
            session.notes = kw['notes']
            session.operator = User.query.filter_by(uid=username).one() if username else None
            session.subject.code = kw['subject']['code']
            session.subject.firstname = kw['subject']['firstname']
            session.subject.lastname = kw['subject']['lastname']
            session.subject.dob = kw['subject']['dob']
            transaction.commit()
        flash('Saved (%s)' % datetime.now().strftime("%m/%d/%Y %H:%M:%S"))
        redirect('/auth/session/edit?id=%s' % id_)
