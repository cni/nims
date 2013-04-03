import tw2.core as twc
import tw2.forms as twf
import tw2.sqla as tws
from tg import request
from nimsgears.model import User

def get_owners():
    user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
    return user.admin_group_names

class NewUserForm(twf.Form):
    submit = twf.SubmitButton(value="Create")
    action = 'post_create'
    class child(twf.TableLayout):
        uid = twf.TextField(label='SUNet ID', validator=twc.StringLengthValidator(min=1))

class EditUserForm(tws.DbFormPage):
    entity = User
    title = None
    class child(twf.TableForm):
        action = 'post_edit'
        uid = twf.LabelField(label='SUNet ID', validator=None)
        firstname = twf.TextField(label='First Name', validator=twc.StringLengthValidator(min=1))
        lastname = twf.TextField(label='Last Name', validator=twc.StringLengthValidator(min=1))
