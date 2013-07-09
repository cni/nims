# @author:  Reno Bowen
#           Gunnar Schaefer

"""A set of NIMS-related utility functions."""

import os
import shutil
import tarfile
import difflib
import hashlib
import tempfile
import logging, logging.handlers


class TempDir(object):

    """Context managed temporary directory creation and automatic removal."""

    def __init__(self, suffix='', prefix='tmp', dir=None):
        self.suffix = suffix
        self.prefix = prefix
        self.dir = dir

    def __enter__(self):
        """Create temporary directory on context entry, returning the path."""
        self.tempdir = tempfile.mkdtemp(suffix=self.suffix, prefix=self.prefix, dir=self.dir)
        return self.tempdir

    def __exit__(self, exc_type, exc_value, traceback):
        """Remove temporary directory tree."""
        shutil.rmtree(self.tempdir)


def get_logger(name, filepath=None, console=True, level='debug'):
    """Return a nims-configured logger."""
    logging._levelNames[10] = 'DBUG'
    logging._levelNames[20] = 'INFO'
    logging._levelNames[30] = 'WARN'
    logging._levelNames[40] = 'ERR '
    logging._levelNames[50] = 'CRIT'

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    formatter = logging.Formatter('%(asctime)s %(name)12.12s:%(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    if filepath:
        handler = logging.handlers.TimedRotatingFileHandler(filepath, when='W6')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    if console:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.warning('********** Logging initialized **********')
    return logger


def parse_patient_id(patient_id, known_groups=[]):
    """
    Accept a NIMS-formatted patient id and return a subject code, group name, and experiment name.

    Find the best fuzzy-matching group name. If this can't be done with high confidence, the group name is set to 'unknown'.
    """
    subj_code, dummy, lab_info = patient_id.lower().rpartition('@')
    group_name, dummy, exp_name = (z[0] or z[1] for z in zip(lab_info.partition('/'), ('unknown', '', 'untitled')))
    group_name_matches = difflib.get_close_matches(group_name, known_groups, cutoff=0.8)
    if len(group_name_matches) == 1:
        group_name = group_name_matches[0]
    else:
        group_name = 'unknown'
        exp_name = patient_id
    return subj_code, group_name, exp_name


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
    return firstname, lastname, email


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
