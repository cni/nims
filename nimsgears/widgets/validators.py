import tw2.core as twc
from nimsgears.model import *
from tg import request

class SubjectCodeDoesntExist(twc.Validator):
    """
    Confirm a subject code doesn't exist.

    `id`
        Name of the sibling field this must match
    """
    msgs = {
        'exists': twc._("Subject code already exists."),
        'parseerr': twc._("Error parsing session and subject code")
    }

    def validate_python(self, value, state):
        super(SubjectCodeDoesntExist, self).validate_python(value, state)
        session_id = value['id']
        subject_id = int(value['subject']['id'])
        subject_code = value['subject']['code']
        session = Session.query.filter_by(id=session_id).first()
        if not session:
            raise twc.ValidationError('parseerr', self)
        subject = Subject.query.filter_by(code=subject_code).filter_by(experiment=session.experiment).first()
        if subject and subject.id != subject_id:
            raise twc.ValidationError('exists', self)

class UserExists(twc.Validator):
    """
    Confirm a user exists.

    """
    msgs = {
        'doesntexist': twc._("User does not exist.")
    }

    def validate_python(self, value, state=None):
        super(UserExists, self).validate_python(value, state)
        matches = User.query.filter_by(uid=value).all()
        if len(matches) == 0:
            raise twc.ValidationError('doesntexist', self)

class ExperimentDoesntExist(twc.Validator):
    """
    Confirm an experiment doesn't already exist.

    `owner`
        Name of the sibling field this must match
    """
    msgs = {
        'exists': twc._("Experiment already exists")
    }

    def __init__(self, owner, **kw):
        super(ExperimentDoesntExist, self).__init__(**kw)
        self.owner = owner

    def validate_python(self, value, state):
        super(ExperimentDoesntExist, self).validate_python(value, state)
        if state[self.owner] == twc.validation.Invalid:
            state[self.owner] = None
        experiment_exists = (Experiment.query
            .join(ResearchGroup)
            .filter(Experiment.name==value)
            .filter(ResearchGroup.gid==state[self.owner])
            .first())
        if experiment_exists:
            raise twc.ValidationError('exists', self)
