import os
import json
import uuid
import dicom
from datetime import date
from tg import expose, redirect, request

from nimsdata.nimsdata import NIMSData
from nimsdata.nimsdicom import NIMSDicom
from nimsdata.nimsdata import NIMSDataError
from nimsgears.model.nims import ResearchGroup, User
from nimsgears.controllers.nims import NimsController



class UploadController(NimsController):

    @expose('nimsgears.templates.upload')
    def index(self):
        user = self.get_user()
        groups = sorted( '%s - %s' % (exp.owner.gid, exp.name)
                    for exp, priv in user.experiments_with_access_privilege(u'Read-Only', ignore_superuser=True) )
        if 'unknown' in groups: groups.remove('unknown')
        return dict(page='upload', research_groups=groups)

    @expose()
    def start_upload(self):
        result = {}
        user = self.get_user()
        todays_date = str(date.today())

        try:
            # Generating new upload id
            upload_id = "%s-%s-%s" % (user.uid, todays_date, uuid.uuid1())
            upload_directory = 'uploads/.%s.tmp' % (upload_id)
            os.mkdir(upload_directory, 0755)
            result['upload_id'] = upload_id
            result['status'] = True
        except Exception as e:
            result['status'] = False
            result['message'] = str(e)

        return json.dumps(result)

    @expose()
    def end_upload(self, upload_id,
                    SeriesInstanceUID, GroupValue, Notes):

        self.verify_user(upload_id)

        tmp_upload_directory = 'uploads/.%s.tmp' % (upload_id)

        # Create JSON file with data summary
        summary = {}
        summary['SeriesInstanceUID'] = SeriesInstanceUID
        summary['Group'], summary['Experiment'] = GroupValue.split(' - ', 1)
        summary['Date'] = str(date.today())
        summary['User'] = self.get_user().uid
        summary['Notes'] = Notes
        json_path = os.path.join( tmp_upload_directory, 'summary.json')
        out = open(json_path, 'w')
        json.dump(summary, out, indent=True)
        out.close()

        # Finalize the upload by moving the directory in its final destination
        final_upload_path =  'uploads/%s' % (upload_id)
        os.rename(tmp_upload_directory, final_upload_path)

        result = {'status' : True, 'message' : 'Upload complete'}
        return json.dumps(result)

    @expose()
    def upload_file(self, upload_id, file):
        self.verify_user(upload_id)

        tmp_upload_directory = 'uploads/.%s.tmp' % (upload_id)

        file_result = {}
        file_result['filename'] = file.filename

        file_path = os.path.join(tmp_upload_directory, file.filename)
        content = file.file.read()
        out = open(file_path, 'w')
        out.write(content)
        out.close()

        try:
            data = NIMSDicom(file_path)
            # print 'Patient name:', data.subj_firstname, data.subj_lastname
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

        return json.dumps(file_result)


    def get_user(self):
        return request.identity['user'] if request.identity else User.get_by(uid=u'@public')

    def verify_user(self, upload_id):
        # Verify the user is the same
        if (self.get_user().uid != upload_id.split('-')[0]):
            raise Exception('Invalid user id')
