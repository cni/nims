# @author:  Reno Bowen
#           Gunnar Schaefer

"""A set of NIMS-related utility functions."""

import os
import re
import gzip
import shutil
import string
import tarfile
import difflib
import hashlib
import datetime
import tempfile
import logging, logging.handlers


class TempDir(object):

    """Context managed temporary directory creation and automatic removal."""
    def __init__(self, dir=None):
        self.dir = dir
        super(TempDir, self).__init__()

    def __enter__(self):
        """Create temporary directory on context entry, returning the path."""
        self.temp_dir = tempfile.mkdtemp(dir=self.dir)
        return self.temp_dir

    def __exit__(self, exc_type, exc_value, traceback):
        """Remove temporary directory tree."""
        shutil.rmtree(self.temp_dir)


def configure_log(filepath=None, console=True, level='debug'):
    """Return a nims-configured logger."""
    logging._levelNames[10] = 'DBUG'
    logging._levelNames[20] = 'INFO'
    logging._levelNames[30] = 'WARN'
    logging._levelNames[40] = 'ERR '
    logging._levelNames[50] = 'CRIT'

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    formatter = logging.Formatter('%(asctime)s %(name)12.12s:%(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    if filepath:
        handler = logging.handlers.TimedRotatingFileHandler(filepath, when='W6')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.warning('********** Logging initialized **********')
    if console:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def parse_subject(name, dob):
    lastname, firstname = name.split('^') if '^' in name else ('', '')
    try:
        dob = datetime.datetime.strptime(dob, '%Y%m%d').date()
        if dob < datetime.date(1900, 1, 1):
            raise ValueError
    except ValueError:
        dob = None
    return (unicode(firstname.capitalize()), unicode(lastname.capitalize()), dob)


def parse_patient_id(patient_id, known_ids):
    """
    Accept a NIMS-formatted patient id and return lab id and experiment id.

    We use fuzzy matching to find the best matching known lab id. If we can't
    do so with high confidence, the lab id is set to 'unknown'.
    """
    subj_code, dummy, lab_info = patient_id.strip(string.punctuation + string.whitespace).lower().rpartition('@')
    lab_id, dummy, exp_id = (clean_string(z[0]) or z[1] for z in zip(lab_info.partition('/'), ('unknown', '', 'untitled')))
    lab_id_matches = difflib.get_close_matches(lab_id, known_ids, cutoff=0.8)
    if len(lab_id_matches) == 1:
        lab_id = lab_id_matches[0]
    else:
        lab_id = 'unknown'
        exp_id = patient_id
    return (unicode(subj_code), unicode(lab_id), unicode(exp_id))


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
    ldap_base = 'dc=stanford,dc=edu'        # subtrees 'cn=people' and 'cn=accounts' exist
    ldap_attrs = ['suDisplayNameFirst', 'suDisplayNameLast', 'mail', 'cn']
    firstname = ''
    lastname = ''
    email = ''
    try:
        import ldap, ldap.sasl
        srv = ldap.initialize(ldap_uri)
        srv.sasl_interactive_bind_s('', ldap.sasl.gssapi(''))
        results = srv.search_s(ldap_base, ldap.SCOPE_SUBTREE, '(uid=%s)' % uid, ldap_attrs)
    except:
        pass
    else:
        for subtree, res_dict in results:
            if 'people' in subtree:
                firstname = res_dict.get('suDisplayNameFirst', [''])[0]
                lastname = res_dict.get('suDisplayNameLast', [''])[0]
                email = res_dict.get('mail', [''])[0] or ('%s@stanford.edu' % uid if lastname else '')
                break
            if 'accounts' in subtree:
                name_list = (res_dict.get('cn', [''])[0]).split(' ')
                firstname = name_list[0]
                lastname = name_list[-1]
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


def hrsize(size):
    if size < 1000:
        return '%3d%s' % (size, 'B')
    for suffix in 'KMGTPEZY':
        size /= 1024.
        if size < 10.:
            return '%3.1f%s' % (size, suffix)
        if size < 1000.:
            return '%3.0f%s' % (size, suffix)
    return '%.0f%s' % (size, 'Y')


def gzip_inplace(path, mode=None):
    gzpath = path + '.gz'
    with gzip.open(gzpath, 'wb', compresslevel=4) as gzfile:
        with open(path) as pathfile:
            gzfile.writelines(pathfile)
    shutil.copystat(path, gzpath)
    if mode: os.chmod(gzpath, mode)
    os.remove(path)


def redigest(path):

    def hash_file(fd):
        for chunk in iter(lambda: fd.read(1048576 * hash_.block_size), ''):
            hash_.update(chunk)

    hash_ = hashlib.sha1()
    filepaths = [os.path.join(path, f) for f in os.listdir(path)]
    for filepath in sorted(filepaths):
        if tarfile.is_tarfile(filepath):
            archive = tarfile.open(filepath, 'r:*')
            for member in archive:
                if not member.isfile(): continue
                fd = archive.extractfile(member)
                hash_file(fd)
        else:
            with open(filepath, 'rb') as fd:
                hash_file(fd)
    return hash_.digest()
