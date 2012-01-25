# @author:  Reno Bowen
#           Gunnar Schaefer

"""
This is a set of NIMS-related utility functions used in the nims and reaper packages.
"""

import os
import re
import shutil
import difflib
import datetime
import tempfile
import logging, logging.handlers

TAG_PSD_NAME =          (0x0019, 0x109c)
TAG_PHYSIO_FLAG =       (0x0019, 0x10ac)


class TempDirectory:

    """
    Class constructed for context managed temporary directory creation and
    destruction.

    Usage:
        with TempDirectory() as temp_dir:
            ...
    """

    def __enter__(self):
        """Create temporary directory on context entry, returning the path."""
        self.temp_dir = tempfile.mkdtemp()
        return self.temp_dir

    def __exit__(self, type, value, traceback):
        """Remove temporary directory tree."""
        shutil.rmtree(self.temp_dir)


def psd_name(header):
    return unicode(os.path.basename(header[TAG_PSD_NAME].value)) if TAG_PSD_NAME in header else u'unknown'


def physio_flag(header):
    return (header[TAG_PHYSIO_FLAG].value)


def acq_date(header):
    if 'AcquisitionDate' in header: return header.AcquisitionDate
    elif 'StudyDate' in header:     return header.StudyDate
    else:                           return '19000101'


def acq_time(header):
    if 'AcquisitionTime' in header: return header.AcquisitionTime
    elif 'StudyTime' in header:     return header.StudyTime
    else:                           return '000000'


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

    formatter = logging.Formatter('%(asctime)s [%(name)12.12s:%(levelname)s] %(message)s')

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.warning('********** Logging initialized **********')

    return logger


def parse_subject(name, dob, known_subjects):
    """
    """
    #lab_info = patient_id.lower().split('/', 1)
    #lab_id = clean_string(lab_info[0])
    #exp_id = clean_string(lab_info[1]) if len(lab_info) > 1 else ''

    #lab_id_matches = difflib.get_close_matches(lab_id, known_ids, cutoff=0.8)
    #if len(lab_id_matches) == 1:
    #    lab_id = lab_id_matches[0]
    #else:
    #    exp_id = lab_id + '/' + exp_id
    #    lab_id = 'unknown'
    #return (unicode(lab_id), unicode(exp_id))


    lastname, firstname = name.split('^') if '^' in name else ('', '')
    dob = datetime.datetime.strptime(dob, '%Y%m%d') if dob else None

    return (unicode(lastname.capitalize()), unicode(firstname.capitalize()), dob)


def parse_patient_id(patient_id, known_ids):
    """
    Accept a nims formatted patient id and return lab id and experiment id.

    For example:
        wandell/multiclass returns ('wandell', 'multiclass')
        wandell returns ('wandell', '')

    We use fuzzy matching to find the best matching known lab id. If we can't
    do so with high confidence, the lab id is set to 'unknown'.

    For example:
        foobar/multiclass returns ('unknown', 'foobar/multiclass')
    """
    lab_info = patient_id.lower().split('/', 1)
    lab_id = clean_string(lab_info[0])
    exp_id = clean_string(lab_info[1]) if len(lab_info) > 1 else ''

    lab_id_matches = difflib.get_close_matches(lab_id, known_ids, cutoff=0.8)
    if len(lab_id_matches) == 1:
        lab_id = lab_id_matches[0]
    else:
        exp_id = lab_id + '/' + exp_id
        lab_id = 'unknown'
    return (unicode(lab_id), unicode(exp_id))


def clean_string(string):
    """
    Nims standard string cleaning utility function.  Keeps numbers and letters,
    strips excess characters, replaces consecutive spaces, dashes, and
    underscores with single underscores.

    For example:
        '-__-&&&HELLO GOOD    SIR   (()))___----' returns 'HELLO_GOOD_SIR'
    """
    string = re.sub('[^A-Za-z0-9 _\-]', '', string)
    string = re.sub('[ _\-]+', '_', string.strip(' _-'))
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


def pid_is_active(pid):
    """ Determine if given pid is alive (Unix only)."""
    return os.path.exists("/proc/%s" % pid)


def get_port(port_filename):
    port = None
    with open(port_filename, 'r') as port_file:
        port = int(port_file.read())
    return port


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
    ldap_base = 'dc=stanford,dc=edu'
    ldap_attrs = ['displayName', 'mail']
    try:
        import ldap
        srv = ldap.initialize(ldap_uri)
        res = srv.search_s(ldap_base, ldap.SCOPE_SUBTREE, '(uid=%s)' % uid, ldap_attrs)
    except:
        pass
    try:
        name = res[0][1]['displayName'][0]
    except:
        name = ''
    try:
        email = res[0][1]['mail'][0]
    except:
        email = '%s@stanford.edu' % uid if name else ''
    return unicode(name), unicode(email)
