#!/usr/bin/env python
#
# @author:  Bob Dougherty

"""
Nimsfs uses FUSE to expose the NIMS database to users as a browseable filesystem.
Access control is implemented assuming that the operating system uid of the process
accessing nimsfs is correct, and that this uid maps to the correct NIMS username.
If all users are assigned their Stanford-assigned uids and only kerberos authentication
is permitted on the system, then these requirements should be met.

"""

import os, sys
import errno  # for error number codes (ENOENT, etc) - note: these must be returned as negatives
import stat   # for file properties
import fcntl
import time
import pwd    # to translate uid to username
import grp    # to translate gid to groupname
import fuse
from fuse import Fuse

DATAPATH = '/nimsfs/nims'

#from paste.deploy import appconfig
#from pylons import config
#
#from nimsgears.config.environment import load_environment
#
## Adjust the following as necessary so the ini file can be found
#conf = appconfig('config:production.ini', relative_to='.')
#load_environment(conf.global_conf, conf.local_conf)
import sqlalchemy
from nimsgears.model import *
db_uri = 'postgresql://nims:nims@nimsfs.stanford.edu:5432/nims'
init_model(sqlalchemy.create_engine(db_uri))

fuse.fuse_python_api = (0, 2)

def flag2mode(flags):
    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]
    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)
    return m

def get_groups(user):
    experiments = (Experiment.query.join(Access)
                   .filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
    return sorted(set([e.owner.gid.encode() for e in experiments]))

def get_experiments(user, group_name):
    experiments = (Experiment.query.join(Access)
                   .join(ResearchGroup, Experiment.owner)
                   .filter(ResearchGroup.gid==unicode(group_name))
                   .filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
    return sorted([e.name.encode() for e in experiments])

def get_sessions(user, group_name, exp_name):
    sessions = (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .filter(ResearchGroup.gid==unicode(group_name))
                .filter(Experiment.name==unicode(exp_name))
                .filter(Access.user==user)
                .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                .all())
    return sorted([s.name.encode() for s in sessions])

def get_epochs(user, group_name, exp_name, session_name):
    # FIXME: we should explicitly set the session name so that we can be sure the exam is there.
    sp = session_name.split('_')
    if len(sp)>2:
        exam = int(sp[2])
        epochs = (Epoch.query
                  .join(Session, Epoch.session)
                  .join(Subject, Session.subject)
                  .join(Experiment, Subject.experiment)
                  .join(ResearchGroup, Experiment.owner)
                  .filter(ResearchGroup.gid==unicode(group_name))
                  .filter(Experiment.name==unicode(exp_name))
                  .filter(Session.exam==exam)
                  .filter(Access.user==user)
                  .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                  .all())
        epoch_names = sorted([(e.name + '_' + e.description).encode() for e in epochs])
    else:
        epoch_names = []
    return epoch_names

def get_datasets(user, group_name, exp_name, session_name, epoch_name):
    # FIXME: we should explicitly set the epoch name.
    sp = epoch_name.split('_')
    if len(sp)>2:
        exam,series,acq = [int(n) for n in sp[:3]]
        datasets = (Dataset.query
                   .join(Epoch, Dataset.container)
                   .join(Session, Epoch.session)
                   .join(Subject, Session.subject)
                   .join(Experiment, Subject.experiment)
                   .join(ResearchGroup, Experiment.owner)
                   .join(Access)
                   .join(User, Access.user)
                   .filter(ResearchGroup.gid==unicode(group_name))
                   .filter(Experiment.name==unicode(exp_name))
                   .filter(Session.exam==exam)
                   .filter(Epoch.series==series)
                   .filter(Epoch.acq==acq)
                   .filter(Access.user==user)
                   .filter((Access.privilege >= AccessPrivilege.value(u'Read-Only')) | ((Dataset.kind != u'primary') & (Dataset.kind != u'secondary')))
                   .all())
        datafiles = [os.path.join(DATAPATH,d.relpath,f).encode() for d in datasets for f in d.filenames]
    else:
        datafiles = []
    return datafiles

def flag2mode(flags):
    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]
    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)
    return m

class NimsfsStat(fuse.Stat):
    """
    Convenient class for Stat objects.
    Set up the stat object with appropriate
    values depending on constructor args.
    """
    def __init__(self, is_dir, size, uid, gid, timestamp=None):
        fuse.Stat.__init__(self)
        if not timestamp:
            timestamp = int(time.time())
        if is_dir:
            self.st_mode = stat.S_IFDIR | 0555
            self.st_nlink = 2
        else:
            self.st_mode = stat.S_IFREG | 0444
            self.st_nlink = 1
            self.st_size = size
        self.st_atime = timestamp
        self.st_mtime = timestamp
        self.st_ctime = timestamp
        self.st_uid = uid
        self.st_gid = gid

class Nimsfs(Fuse):

    def __init__(self, *args, **kw):
        Fuse.__init__(self, *args, **kw)
        self.root = '/'
        self.fp = None
        self.file_size = 0

    def getattr(self, path):
        is_dir = not bool(os.path.splitext(path)[1])
        size = 0
        if not is_dir:
            context = self.GetContext()
            username = pwd.getpwuid(context['uid']).pw_name
            groupname = grp.getgrgid(context['gid']).gr_name
            user = User.get_by(uid=unicode(username))
            cur_path = path.split('/')
            if len(cur_path) == 6:
                files = get_datasets(user, cur_path[1], cur_path[2], cur_path[3], cur_path[4])
                fname = next((f for f in files if f.endswith(cur_path[5])), None)
                if fname:
                    size = os.path.getsize(fname)
        return NimsfsStat(is_dir, size, 0, 0)

    def readdir(self, path, offset):
        context = self.GetContext()
        username = pwd.getpwuid(context['uid']).pw_name
        groupname = grp.getgrgid(context['gid']).gr_name
        user = User.get_by(uid=unicode(username))
        cur_path = path.split('/')
        if len(cur_path) < 2 or not cur_path[1]:
            dirs = get_groups(user)
        elif len(cur_path) < 3:
            dirs = get_experiments(user, cur_path[1])
        elif len(cur_path) < 4:
            dirs = get_sessions(user, cur_path[1], cur_path[2])
        elif len(cur_path) < 5:
            dirs = get_epochs(user, cur_path[1], cur_path[2], cur_path[3])
        elif len(cur_path) == 5:
            dirs = [os.path.basename(d.encode()) for d in get_datasets(user, cur_path[1], cur_path[2], cur_path[3], cur_path[4])]
        print 'READDIR: path=' + path + '; dirs=' + str(dirs)
        for e in ['.','..'] + dirs:
            yield fuse.Direntry(e)

    def open(self, path, flags):
        print 'OPEN ' + path
        # Only support for 'READ ONLY' flag
        access_flags = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if flags & access_flags != os.O_RDONLY:
            return -errno.EACCES
        else:
            context = self.GetContext()
            username = pwd.getpwuid(context['uid']).pw_name
            groupname = grp.getgrgid(context['gid']).gr_name
            user = User.get_by(uid=unicode(username))
            cur_path = path.split('/')
            if len(cur_path) == 6:
                files = get_datasets(user, cur_path[1], cur_path[2], cur_path[3], cur_path[4])
                fname = next((f for f in files if f.endswith(cur_path[5])), None)
                if fname:
                    self.file_size = os.path.getsize(fname)
                    self.fp = open(fname, 'rb')
                    print 'OPEN: path=' + path + '; fname=' + fname
            return 0

    def read(self, path, size, offset):
        print 'READ ' + path
        if self.fp:
            self.fp.seek(offset)
            buf = self.fp.read(size)
        else:
            buf = ''
        return buf

    def flush(self, fh=None):
        print 'FLUSH ' + str(fh)
        if self.fp:
            self.fp.close()

    def fgetattr(self, fh=None):
        return NimsfsStat(0, self.file_size, 0, 0)


if __name__ == '__main__':
    usage = ('nimsfs.py [mountpoint]\n'
            +'Mount the NIMS virtual filesystem tree at the specified mountpoint.\n'
            +'To unmount, use fusermount -u [mountpoint].\n\n'
            +Fuse.fusage)

    server = Nimsfs(version='%prog ' + fuse.__version__,
                 usage=usage,
                 dash_s_do='setsingle')

    # To use multithreading, we'd need to protect all methods of
    # NimsfsFile class with locks to prevent race conditions
    server.multithreaded = False

    server.parser.add_option(mountopt='root', metavar='PATH', default='/', help=usage)
    server.parse(values=server, errex=1)

    try:
        if server.fuse_args.mount_expected():
            os.chdir(server.root)
    except OSError:
        print >> sys.stderr, 'Error mounting NIMS.'
        sys.exit(1)

    server.main()

