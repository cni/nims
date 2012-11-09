import tw2.core as twc
import tw2.forms as twf
from tg import request
from nimsgears.widgets.validators import ExperimentDoesntExist
from formencode.compound import All
from nimsgears.model import ResearchGroup


def get_owners():
    user = request.identity['user']
    if user.is_superuser:
        research_groups = ResearchGroup.query.all()
    else:
        research_groups = user.pi_groups + user.manager_groups
    return [group.gid for group in research_groups]

class NewExperimentForm(twf.Form):
    submit = twf.SubmitButton(value="Create")
    class child(twf.TableLayout):
        owner = twf.SingleSelectField(options=twc.Deferred(get_owners), validator=twc.Required)
        name = twf.TextField(validator=twc.All(twc.StringLengthValidator(min=1), ExperimentDoesntExist('owner')))
