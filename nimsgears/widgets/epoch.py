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
        flip_angle = twf.LabelField()
        num_timepoints = twf.LabelField()
        num_slices = twf.LabelField()
        protocol_name = twf.LabelField()
        scan_type = twf.LabelField()
        num_bands = twf.LabelField()
        prescribed_duration = twf.LabelField()
        mm_per_vox  = twf.LabelField()
        fov = twf.LabelField()
        acquisition_matrix=twf.LabelField()
        phase_encode_undersample = twf.LabelField()
        slice_encode_undersample = twf.LabelField()
