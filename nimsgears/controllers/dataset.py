from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *
from nimsgears.widgets.dataset import EditDatasetForm

class DatasetController(NimsController):
    @expose()
    def index(self, **kw):
        user = request.identity['user']
        dataset = Dataset.query.filter_by(id=kw.get('id')).first()
        if dataset:
            redirect(dataset.shadowpath(user))
        else:
            return "No such dataset."
