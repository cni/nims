import tw2.core as twc
import tw2.forms as twf
import tw2.sqla as tws
from tg import request
from nimsgears.widgets.validators import ExperimentDoesntExist
from formencode.compound import All
from nimsgears.model import Epoch

class EditEpochForm(tws.DbFormPage):
    entity = Epoch
    title = None
    class child(twf.TableForm):
        action = 'post_edit'
        id = twf.HiddenField()
        series = twf.LabelField()
        acq = twf.LabelField()
        description = twf.TextArea(validator=twc.StringLengthValidator(max=255))
        psd = twf.LabelField()
        physio_flag = twf.LabelField()
        tr = twf.LabelField()
        te = twf.LabelField()
