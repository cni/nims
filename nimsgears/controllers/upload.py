import os
import json
import dicom
from tg import expose, redirect, request
import uuid

from nimsdata.nimsdata import NIMSData
from nimsdata.nimsdicom import NIMSDicom
from nimsdata.nimsdata import NIMSDataError
from nimsgears.model.nims import ResearchGroup
from nimsgears.controllers.nims import NimsController



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

        if not (
                'files[]' in kwargs and
                'experiment' in kwargs and
                'group_value' in kwargs
                ):
            result['processed'] = False
            result['message'] = 'One or more fields missing, make sure your submit is complete'
            return json.dumps(result)

        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        upload_directory = 'uploads/%s-%s' % (user.uid, uuid.uuid1())
        os.mkdir(upload_directory, 0777)
        print 'Created upload directory:', upload_directory

        upload_notes = [ (k[6:],v) for (k,v) in kwargs.items() if k.startswith('notes_') ]
        for key, notes in upload_notes:
            print key, ':', notes
            path = os.path.join(upload_directory, key)
            os.mkdir( path, 0777 )
            print 'Created group directory:', os.path.join(upload_directory, key)

            # Create JSON file with data summary
            summary = {}
            summary['Notes'] = notes
            summary['StudyID'] = kwargs['StudyID_' + key]
            summary['SeriesNumber'] = kwargs['SeriesNumber_' + key]
            summary['AcquisitionNumber'] = kwargs['AcquisitionNumber_' + key]
            summary['SeriesInstanceUID'] = kwargs['SeriesInstanceUID_' + key]
            json_path = os.path.join(path, 'summary.json')
            out = open(json_path, 'w')
            json.dump(summary, out, indent=True)
            out.close()

        files = kwargs['files[]']
        result['experiment'] = kwargs['experiment']
        result['group_value'] = kwargs['group_value']
        if not type(files) is list: files = [files]
        result['files'] = []

        for file in files:
            file_result = {}

            # Extract the request id associated with this file
            file_result['id'] = kwargs.get('filename_' + file.filename, '')
            file_result['key'] = kwargs.get('file_key_' + file.filename, '')
            file_result['filename'] = file.filename

            file_path = os.path.join(upload_directory, file_result['key'], file.filename)
            content = file.file.read()
            out = open(file_path, 'w')
            out.write(content)
            out.close()

            try:
                data = NIMSDicom(file_path)
                file_result['exam_uid'] = data.exam_uid
                file_result['status'] = True
                file_result['message'] = "Uploaded"
                # pat_name = data._hdr.PatientName

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



