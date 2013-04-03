from tg import expose, request, validate, flash, redirect, tmpl_context
from nimsgears.controllers.nims import NimsController
from nimsgears.model import User
from nimsgears.widgets.user import NewUserForm, EditUserForm
import json
import datetime
import transaction


class UserController(NimsController):

    @expose('nimsgears.templates.form')
    def edit(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        if tmpl_context.form_errors:
            form = EditUserForm
        else:
            if user.is_superuser:
                form = EditUserForm().req()
                form.fetch_data(request)
            else:
                form = None
        return dict(form=form)

    @expose()
    @validate(EditUserForm, error_handler=edit)
    def post_edit(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        edited_user = User.get_by(uid=kw['uid'])
        if user.is_superuser:
            edited_user.firstname = kw['firstname']
            edited_user.lastname = kw['lastname']
            transaction.commit()
            flash('Saved (%s)' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        else:
            flash('permission denied')
        redirect('../user/edit?uid=%s' % kw['uid'])

    @expose('nimsgears.templates.user.add')
    def create(self, **kw):
        return dict(form=NewUserForm)

    @expose()
    @validate(NewUserForm, error_handler=create)
    def post_create(self, **kw):
        user = request.identity['user']
        if user.admin_groups:
            user = User.by_uid(uid=kw['uid'], create=True)
        redirect('../user/create')

    @expose()
    def all(self):
        if request.identity:
            users = User.query.all()
            return json.dumps(dict(success=True, data=[(u.uid, u.name) for u in users], attrs=[{'id': 'uid=%s' % u.uid} for u in users]))
