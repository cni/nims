import os
from tg import expose, redirect
from nimsgears.controllers.nims import NimsController
from nimsgears.model.nims import ResearchGroup

from nimsdata.nimsdata import NIMSData
from nimsdata.nimsdata import NIMSDataError
from nimsdata.nimsdicom import NIMSDicom
import json

class UploadController(NimsController):

    @expose('nimsgears.templates.upload')
    def index(self):
        groups = sorted( x.gid for x in ResearchGroup.query.all() )
        groups.remove('unknown')
        return dict(page='upload', research_groups=groups)

    @expose()
    def submit(self, **kwargs):
        result = { 'processed': False }
        print '+++++++++++++++++++++++++++++++ args: ', kwargs

        if 'files[]' in kwargs and 'experiment' in kwargs and 'group_value' in kwargs:
            files = kwargs['files[]']
            print '++++++++++++++++++++++++++', files
            result['experiment'] = kwargs['experiment']
            result['group_value'] = kwargs['group_value']
            if not type(files) is list:
                files = [files]

            result['files'] = []

            i = 0
            for file in files:
                content = file.file.read()
                name = '/tmp/test-%d.data' % i
                out = open(name, 'w')
                i += 1
                out.write(content)
                out.close()

                file_result = {}

                # Extract the request id associated with this file
                file_result['id'] = kwargs.get('filename_' + file.filename, '')
                file_result['filename'] = file.filename

                try:
                    data = NIMSDicom(name)
                    file_result['exam_uid'] = data.exam_uid
                    print data.get_metadata()

                    file_result['status'] = True
                    file_result['message'] = "OK"
                    # print '+++++++++++ result_ok: ', file_result

                except NIMSDataError:
                    print "Couldn't understand the file", file.filename
                    file_result['status'] = False
                    file_result['message'] = "File %s could not be parsed" % file.filename
                    # print '++++++++++++ result_error: ', result
                except:
                    file_result['status'] = False
                    file_result['message'] = "File %s could not be parsed" % file.filename

                result['files'].append(file_result)

            print '\nResult: ' + str(result)
            return json.dumps(result)
        else:
            result['processed'] = False
            result['message'] = 'One or more fields missing, make sure your submit is complete'
            return json.dumps(result)



