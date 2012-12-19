import tw2.core as twc
import tw2.forms as twf
import tw2.sqla as tws
from tg import request
from nimsgears.widgets.validators import UserExists, SubjectCodeDoesntExist
from formencode.compound import All
from nimsgears.model import ResearchGroup, Session, Subject, User

user_list = lambda: [u.uid for u in User.query.all()]
class EditSessionForm(tws.DbFormPage):
    entity = Session
    title = None
    class child(twf.TableForm):
        action = 'post_edit'
        id = twf.HiddenField()
        subject = twf.LabelField()
        exam = twf.LabelField()
        timestamp = twf.LabelField()
        notes = twf.TextArea(validator=twc.StringLengthValidator(max=1024))
        class operator(twf.TableLayout):
            uid = twf.SingleSelectField(label="SUNetID", options=twc.Deferred(user_list), validator=twc.Any(twc.StringLengthValidator(min=0,max=0), UserExists()))
        class subject(twf.TableLayout):
            id = twf.HiddenField()
            code = twf.TextField(validator=twc.StringLengthValidator(max=31))
            firstname = twf.TextField(label="First Name", validator=twc.StringLengthValidator(max=63))
            lastname = twf.TextField(label="Last Name", validator=twc.StringLengthValidator(max=63))
            dob = twf.TextField(label="Date of Birth", validator=twc.DateTimeValidator(format="%m/%d/%Y"))
    validator = SubjectCodeDoesntExist()
