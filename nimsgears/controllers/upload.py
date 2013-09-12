import os
from tg import expose, redirect
from nimsgears.controllers.nims import NimsController
from nimsdata.nimsdata import NIMSData
from nimsdata.nimsdicom import NIMSDicom
import json

class UploadController(NimsController):

    @expose('nimsgears.templates.upload')
    def index(self):
        return dict(page='upload')

    @expose()
    def submit(self, **kwargs):
        print '+++++++++++++++++++++++++++++++ args: ', kwargs

#        for i in dir(request):
#            print i, ' : ', request.__getattr__(i)
        if 'files[]' in kwargs:
            files = kwargs['files[]']
            if not type(files) is list:
                files = [files]

            i = 0
            for file in files:
                print dir(file)
                content = file.file.read()
                name = '/tmp/test-%d.data' % i
                out = open(name, 'w')
                out.write(content)
                out.close()

                try:
                    data = NIMSDicom(name)
                    print file.filename, ': ', len(content)
                    print '++++++++++++++ exam_uid: ', data.exam_uid
                    print data.get_metadata()
                except:
                    print "Couldn't understand the file"
                    return json.dumps({'processed' : False, 'message' : "File %s could not be parsed" % file.filename})

                # This method will be called when a file is being uploaded
                return json.dumps({'processed' : True, 'message' : "file processed ok"})
        else:
            return json.dumps({'processed': False, 'message': 'No file was selected'})



