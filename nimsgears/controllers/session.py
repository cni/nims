from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from datetime import datetime
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *
from nimsgears.widgets.session import EditSessionForm
import transaction

class SessionController(NimsController):
    @expose('nimsgears.templates.form')
    def edit(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        if tmpl_context.form_errors:
            form = EditSessionForm
        else:
            if user.has_access_to(Session.get(kw.get('id')), u'Read-Only'):
                form = EditSessionForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(page='session', form=form)

    @expose()
    @validate(EditSessionForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        session = Session.get(kw['id'])
        if user.has_access_to(session, u'Read-Write'):
            session.notes = kw['notes']
            session.operator = User.get_by(uid=kw['operator']['uid'])
            session.subject.code = kw['subject']['code']
            session.subject.firstname = kw['subject']['firstname']
            session.subject.lastname = kw['subject']['lastname']
            session.subject.dob = kw['subject']['dob']
            transaction.commit()
            flash('Saved (%s)' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        else:
            flash('permission denied')
        redirect('../session/edit?id=%s' % kw['id'])
