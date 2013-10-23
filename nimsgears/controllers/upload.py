import os
import json
import uuid
import dicom
from datetime import date
from tg import expose, redirect, request


from nimsdata.nimsdata import NIMSData
from nimsdata.nimsdicom import NIMSDicom
from nimsdata.nimsdata import NIMSDataError
from nimsgears.model.nims import ResearchGroup
from nimsgears.controllers.nims import NimsController



class UploadController(NimsController):

    @expose('nimsgears.templates.upload')
    def index(self):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        groups = sorted( '%s - %s' % (exp.owner.gid, exp.name)
                    for exp, priv in user.experiments_with_access_privilege(u'Read-Only', ignore_superuser=True) )
        if 'unknown' in groups: groups.remove('unknown')
        return dict(page='upload', research_groups=groups)

    @expose()
    def submit(self, **kwargs):
        result = { 'processed': False }

        if not (
                'files[]' in kwargs and
                'group_value' in kwargs
                ):
            result['processed'] = False
            result['message'] = 'One or more fields missing, make sure your submit is complete'
            return json.dumps(result)

        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        todays_date = str(date.today())
        upload_directory = 'uploads/%s-%s-%s' % (user.uid, todays_date, uuid.uuid1())
        os.mkdir(upload_directory, 0777)

        upload_notes = [ (k[6:],v) for (k,v) in kwargs.items() if k.startswith('notes_') ]
        for key, notes in upload_notes:
            #path = os.path.join(upload_directory, key)
            #os.mkdir( path, 0777 )
            #print 'Created group directory:', os.path.join(upload_directory, key)

            # Create JSON file with data summary
            summary = {}
            summary['SeriesInstanceUID'] = kwargs['SeriesInstanceUID_' + key]
            summary['Group'] = kwargs['group_value'].split(' - ', 1)[0]
            summary['Experiment'] = kwargs['group_value'].split(' - ', 1)[1]
            summary['Date'] = todays_date
            summary['User'] = user.uid
            summary['Notes'] = notes
            #json_path = os.path.join( path, 'summary.json')
            json_path = os.path.join( upload_directory, 'summary.json')
            out = open(json_path, 'w')
            json.dump(summary, out, indent=True)
            out.close()

        files = kwargs['files[]']
        result['group_value'] = kwargs['group_value']
        if not type(files) is list: files = [files]
        result['files'] = []

        for file in files:
            file_result = {}

            # Extract the request id associated with this file
            file_result['id'] = kwargs.get('filename_' + file.filename, '')
            file_result['key'] = kwargs.get('file_key_' + file.filename, '')
            file_result['filename'] = file.filename

            #file_path = os.path.join(upload_directory, file_result['key'], file.filename)
            file_path = os.path.join(upload_directory, file.filename)
            content = file.file.read()
            out = open(file_path, 'w')
            out.write(content)
            out.close()

            try:
                print 'try to open file_path: ', file_path
                data = NIMSDicom(file_path)
                file_result['exam_uid'] = data.exam_uid
                file_result['status'] = True
                file_result['message'] = "Uploaded"
                # pat_name = data._hdr.PatientName

            except NIMSDataError:
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



