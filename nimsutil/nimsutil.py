# @author:  Reno Bowen
#           Gunnar Schaefer

"""A set of NIMS-related utility functions."""

import os
import re
import glob
import shutil
import difflib
import datetime
import tempfile
import logging, logging.handlers
import numpy

class TempDirectory:

    """Context managed temporary directory creation and automatic removal."""

    def __enter__(self):
        """Create temporary directory on context entry, returning the path."""
        self.temp_dir = tempfile.mkdtemp()
        return self.temp_dir

    def __exit__(self, exc_type, exc_value, traceback):
        """Remove temporary directory tree."""
        shutil.rmtree(self.temp_dir)


def get_logger(name, filename=None, level='debug'):
    """Return a nims-configured logger."""
    logging._levelNames[10] = 'DBUG'
    logging._levelNames[20] = 'INFO'
    logging._levelNames[30] = 'WARN'
    logging._levelNames[40] = 'ERR '
    logging._levelNames[50] = 'CRIT'

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    if filename:
        if os.path.dirname(filename): make_joined_path(os.path.dirname(filename))
        handler = logging.handlers.TimedRotatingFileHandler(filename, when='W6')
    else:
        handler = logging.StreamHandler()

    formatter = logging.Formatter('%(asctime)s %(name)12.12s:%(levelname)s %(message)s')

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if filename:
        logger.warning('********** Logging initialized **********')

    return logger


def parse_subject(name, dob):
    if '@' in name:
        code = re.sub(r'^[^@]*@([^\^]*).*', ur'\1', name)
        lastname, firstname = ('', '')
    else:
        code = ''
        lastname, firstname = name.split('^') if '^' in name else ('', '')
    try:
        dob = datetime.datetime.strptime(dob, '%Y%m%d')
        if dob < datetime.datetime(1900, 1, 1):
            raise ValueError
    except ValueError:
        dob = None
    return (unicode(code), unicode(firstname.capitalize()), unicode(lastname.capitalize()), dob)


def parse_patient_id(patient_id, known_ids):
    """
    Accept a NIMS-formatted patient id and return lab id and experiment id.

    We use fuzzy matching to find the best matching known lab id. If we can't
    do so with high confidence, the lab id is set to 'unknown'.
    """
    lab_info = patient_id.lower().split('/', 1)
    lab_id = clean_string(lab_info[0])
    exp_id = clean_string(lab_info[1]) if len(lab_info) > 1 else 'untitled'

    lab_id_matches = difflib.get_close_matches(lab_id, known_ids, cutoff=0.8)
    if len(lab_id_matches) == 1:
        lab_id = lab_id_matches[0]
    else:
        exp_id = lab_id + '/' + exp_id
        lab_id = 'unknown'
    return (unicode(lab_id), unicode(exp_id))


def clean_string(string):
    """
    Nims standard string cleaning utility function.

    Strip unwanted characters, and replace consecutive spaces, dashes, and
    underscores with a single underscore.

    For example:
        '-__-&&&HELLO GOOD ((    SIR  )))___----   ' returns 'HELLO_GOOD_SIR'
    """
    string = re.sub(r'[^A-Za-z0-9 _-]', '', string)
    string = re.sub(r'[ _-]+', '_', string).strip('_')
    return unicode(string)


def make_joined_path(a, *p):
    """ Return joined path, creating necessary directories if they do not exist."""
    path = os.path.join(a, *p)
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise
    return path


def get_program_home(filename):
    """
    Given a filename, returns the original home of the file (i.e. after
    following links).

    For example:
        ln -s /my/fav/program/source /some/new/place/a_link
        get_program_home('/some/new/place/a_link') returns '/my/fav/program'
    """
    while os.path.islink(filename):
        filename = os.path.join(os.path.dirname(filename), os.readlink(filename))
    return os.path.abspath(os.path.dirname(filename))


def get_reference_datetime(datetime_file):
    if os.access(datetime_file, os.R_OK):
        with open(datetime_file, 'r') as f:
            this_datetime = datetime.datetime.strptime(f.readline(), '%c\n')
    else:
        this_datetime = datetime.datetime.now()
        update_reference_datetime(datetime_file, this_datetime)
    return this_datetime


def update_reference_datetime(datetime_file, new_datetime):
    with open(datetime_file, 'w') as f:
        f.write(new_datetime.strftime('%c\n'))


def ldap_query(uid):
    ldap_uri = 'ldap://ldap.stanford.edu'
    ldap_base = 'cn=people,dc=stanford,dc=edu'        # subtrees 'cn=people' and 'cn=accounts' exist (remove for searching all subtrees)
    ldap_attrs = ['suDisplayNameFirst', 'suDisplayNameLast', 'mail']
    try:
        import ldap
        srv = ldap.initialize(ldap_uri)
        res = srv.search_s(ldap_base, ldap.SCOPE_SUBTREE, '(uid=%s)' % uid, ldap_attrs)
    except:
        pass
    try:
        firstname = res[0][1]['suDisplayNameFirst'][0]
        lastname = res[0][1]['suDisplayNameLast'][0]
    except:
        firstname = ''
        lastname = ''
    try:
        email = res[0][1]['mail'][0]
    except:
        email = '%s@stanford.edu' % uid if lastname else ''
    return unicode(firstname), unicode(lastname), unicode(email)


def find_ge_physio(data_path, timestamp, psd_name):
    physio_files = os.listdir(data_path)
    if not physio_files:
        raise Exception(msg='physio files unavailable')

    physio_dict = {}
    leadtime = datetime.timedelta(days=1)
    regexp = '.+%s_((%s.+)|(%s.+))' % (psd_name, timestamp.strftime('%m%d%Y'), (timestamp+leadtime).strftime('%m%d%Y'))

    physio_files = filter(lambda pf: re.match(regexp, pf), physio_files)
    for pdt, pfn in [re.match(regexp, pf).group(1,0) for pf in physio_files]:
        physio_dict.setdefault(datetime.datetime.strptime(pdt, '%m%d%Y%H_%M_%S_%f'), []).append(pfn)
    valid_keys = filter(lambda pdt: pdt >= timestamp, physio_dict)
    return [os.path.join(data_path, pf) for pf in physio_dict[min(valid_keys)]] if valid_keys else []


def pack_dicom_uid(uid):
    """Convert standard DICOM UID to packed DICOM UID."""
    return bytearray(map(lambda i,j: (int(i)+1 if i != '.' else 11) << 4 | ((int(j)+1 if j != '.' else 11) if j else 0), uid[0::2], uid[1::2]))


def unpack_dicom_uid(uid):
    """Convert packed DICOM UID to standard DICOM UID."""
    return ''.join([str(i-1) if i < 11 else '.' for pair in [(c >> 4, c & 15) for c in bytearray(uid)] for i in pair if i > 0])


def montage(x):
    """
    Convenience function for looking at image arrays.

    For example:
        pylab.imshow(np.flipud(np.rot90(montage(im))))
        pylab.axis('off')
        pylab.show()
    """
    m, n, count = numpy.shape(x)
    mm = int(numpy.ceil(numpy.sqrt(count)))
    nn = mm
    montage = numpy.zeros((mm * m, nn * n))
    image_id = 0
    for j in range(mm):
        for k in range(nn):
            if image_id >= count:
                break
            slice_m, slice_n = j * m, k * n
            montage[slice_n:slice_n + n, slice_m:slice_m + m] = x[:, :, image_id]
            image_id += 1
    return montage
