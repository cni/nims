
class Metadata(object):

    def get_metadata(self):
        md.exam_uid = nimsutil.pack_dicom_uid(md.exam_uid)
        md.series_uid = nimsutil.pack_dicom_uid(md.series_uid)
        md.psd_name = unicode(md.psd_name)
        md.series_desc = nimsutil.clean_string(md.series_desc)
        all_groups = [rg.id for rg in ResearchGroup.query.all()]
        md.subj_code, md.subj_fn, md.subj_ln, md.subj_dob = nimsutil.parse_subject(md.patient_name, md.patient_dob)
        md.group_name, md.exp_name = nimsutil.parse_patient_id(md.patient_id, ResearchGroup.get_all_ids())

        md.acq_no = dcm.acq_no
        md.exam_uid = nimsutil.pack_dicom_uid(dcm.exam_uid)
        md.series_uid = nimsutil.pack_dicom_uid(dcm.series_uid)
        md.psd_name = unicode(dcm.psd_name)
        md.physio_flag = dcm.physio_flag
        md.series_desc = nimsutil.clean_string(dcm.series_desc)
        md.timestamp = dcm.timestamp
        md.duration = dcm.duration
        md.subj_code, md.subj_fn, md.subj_ln, md.subj_dob = nimsutil.parse_subject(dcm.patient_name, dcm.patient_dob)
        md.group_name, md.exp_name = nimsutil.parse_patient_id(dcm.patient_id, ResearchGroup.get_all_ids())

    def read(self, filename):
        pass

    def write(self, filename):
        pass


