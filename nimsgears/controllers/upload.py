import os
from tg import expose, redirect, request
from nimsgears.controllers.nims import NimsController
from nimsgears.model.nims import ResearchGroup

import dicom
from nimsdata.nimsdata import NIMSData
from nimsdata.nimsdata import NIMSDataError
from nimsdata.nimsdicom import NIMSDicom
import json
import unittest

class UploadController(NimsController):

    @expose('nimsgears.templates.upload')
    def index(self):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        groups = user.member_group_names
        if 'unknown' in groups: groups.remove('unknown')
        return dict(page='upload', research_groups=groups)

    @expose()
    def submit(self, **kwargs):
        result = { 'processed': False }

        if 'files[]' in kwargs and 'experiment' in kwargs and 'group_value' in kwargs:
            files = kwargs['files[]']
            result['experiment'] = kwargs['experiment']
            result['group_value'] = kwargs['group_value']
            if not type(files) is list:
                files = [files]

            result['files'] = []

            i = 0
            for file in files:
                content = file.file.read()
                name = '/tmp/test-%d.data' % i
                parse_file = '/tmp/test-%d.parse_file' % i
                out = open(name, 'w')
                out_parse_file = open(parse_file, 'a')
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

                    file_result['status'] = True
                    file_result['message'] = "OK"

                    pat_name = data._hdr.PatientName

                    out_parse_file.write(str('\nPatient Name: %s \n\n' % data._hdr.PatientName))
                    out_parse_file.write(str(data._hdr))
                    out_parse_file.close()

                except NIMSDataError:
                    fname = file.filename
                    print "Couldn't understand the file", file.filename
                    file_result['status'] = False
                    file_result['message'] = "File %s is not a Dicom" % file.filename
                    # print '++++++++++++ result_error: ', result
                except:
                    file_result['status'] = False
                    file_result['message'] = "File %s could not be parsed" % file.filename

                result['files'].append(file_result)

            #print '\nResult: ' + str(result)
            return json.dumps(result)
        else:
            result['processed'] = False
            result['message'] = 'One or more fields missing, make sure your submit is complete'
            return json.dumps(result)


