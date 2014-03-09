from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
from nimsgears.controllers.nims import NimsController
from nimsgears.model import *

class DatasetController(NimsController):

    @expose()
    def index(self, **kw):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        dataset = Dataset.get(kw.get('id'))
        if dataset:
            if dataset.filetype == u'img_pyr':
                redirect('pyramid?dataset_id=%d' % dataset.id)
            elif dataset.filetype == u'json':
                redirect('qa_report?dataset_id=%d' % dataset.id)
            else:
                html_str = '<html><body>'
                if dataset.filetype == u'bitmap':
                    for filename in dataset.filenames:
                        html_str += '<a href="file?id=%d&filename=%s"><img src="file?id=%d&filename=%s"></a><br>\n' % ((dataset.id, filename) * 2)
                else:
                    html_str += '<ul>'
                    for filename in dataset.filenames:
                        html_str += '<li><a href="file?id=%d&filename=%s">%s</a></li>\n' % (dataset.id, filename, filename)
                    html_str += '</ul>'
                html_str += '</body></html>\n'
                return html_str
        else:
            return "No such dataset."
