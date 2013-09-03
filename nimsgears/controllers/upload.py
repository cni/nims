
from tg import expose
from nimsgears.controllers.nims import NimsController

class UploadController(NimsController):

    @expose('nimsgears.templates.upload')
    def index(self):
        return dict(page='upload')

    @expose()
    def submit(self):
        # This method will be called when a file is being uploaded
        return dict()
        

               

