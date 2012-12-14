import tw2.core as twc
import tw2.forms as twf
import tw2.sqla as tws
from tg import request
from nimsgears.widgets.validators import ExperimentDoesntExist
from formencode.compound import All
from nimsgears.model import ResearchGroup, Session, Subject, User, Dataset

class EditDatasetForm(tws.DbFormPage):
    entity = Dataset
    class child(twf.TableForm):
        action = '/auth/dataset/post_edit'
        id = twf.HiddenField()
