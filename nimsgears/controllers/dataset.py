from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *

class DatasetController(NimsController):
    @expose()
    def index(self, **kw):
        user = request.identity['user']
        dataset = Dataset.get(kw.get('id'))
        if dataset:
            if dataset.filetype == u'img_pyr':
                if dataset.filenames[0].endswith('.pyrdb') or dataset.filenames[0].endswith('.hdf5'):
                    redirect('pyramid?dataset_id=%d' % dataset.id)
                else:
                    redirect(dataset.shadowpath(user) + '/pyramid.html')
            else:
                html_str = '<html><body><ul>'
                for filename in dataset.filenames:
                    html_str += '<li><a href="file?id=%d&filename=%s">%s</a></li>\n' % (dataset.id, filename, filename)
                html_str += '</ul></body></html>\n'
                return html_str
        else:
            return "No such dataset."
