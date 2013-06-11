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
import time
import pwd    # to translate uid to username
import grp    # to translate gid to groupname
import fuse
from fuse import Fuse

import sqlalchemy
from nimsgears.model import *
db_uri = 'postgresql://nims:nims@nimsfs.stanford.edu:5432/nims'
init_model(sqlalchemy.create_engine(db_uri))

fuse.fuse_python_api = (0, 2)


import collections
import functools

class memoized(object):
    '''Decorator to cache a function's return value each time it is called.
    If called later with the same arguments, the cached value is returned.
    '''
    def __init__(self, func):
       self.func = func
       self.maxtime = 3
       self.cache = {}
       self.cachetime = {}
    def __call__(self, *args):
       if not isinstance(args, collections.Hashable):
           # uncacheable. a list, for instance.
           # better to not cache than blow up.
           return self.func(*args)
       if args in self.cache and time.time() - self.cachetime[args] < self.maxtime:
           return self.cache[args]
       else:
           value = self.func(*args)
           self.cache[args] = value
           self.cachetime[args] = time.time()
           return value
    def __repr__(self):
       '''Return the function's docstring.'''
       return self.func.__doc__
    def __get__(self, obj, objtype):
       '''Support instance methods.'''
       return functools.partial(self.__call__, obj)

@memoized
def get_groups(user):
    experiments = (Experiment.query.join(Access)
                   .filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
    return sorted(set([e.owner.gid.encode() for e in experiments]))

@memoized
def get_experiments(user, group_name):
    experiments = (Experiment.query.join(Access)
                   .join(ResearchGroup, Experiment.owner)
                   .filter(ResearchGroup.gid.ilike(unicode(group_name)))
                   .filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
    return sorted([e.name.encode() for e in experiments])

@memoized
def get_sessions(user, group_name, exp_name):
    sessions = (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .filter(ResearchGroup.gid.ilike(unicode(group_name)))
                .filter(Experiment.name.ilike(unicode(exp_name)))
                .filter(Access.user==user)
                .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                .all())
    return sorted([s.name.encode() for s in sessions])

@memoized
def get_epochs(user, group_name, exp_name, session_name):
    # FIXME: we should explicitly set the session name so that we can be sure the exam is there.
    sp = session_name.split('_')
    if len(sp)>2 or '%' in sp[0]:
        q = (Epoch.query
             .join(Session, Epoch.session)
             .join(Subject, Session.subject)
             .join(Experiment, Subject.experiment)
             .join(ResearchGroup, Experiment.owner)
             .filter(ResearchGroup.gid.ilike(unicode(group_name)))
             .filter(Experiment.name.ilike(unicode(exp_name))))
        if not '%' in sp[0]:
            q = q.filter(Session.exam==int(sp[2]))
        epochs = (q.filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
        epoch_names = sorted([(e.name + '_' + e.description).encode() for e in epochs])
    else:
        epoch_names = []
    return epoch_names

@memoized
def get_datasets(user, group_name, exp_name, session_name, epoch_name):
    # FIXME: we should explicitly set the epoch name
    ssp = session_name.split('_')
    if len(ssp)>2:
        exam = ssp[2]
    else:
        exam = ssp[0]
    esp = epoch_name.split('_')
    if len(esp)>2 or '%' in epoch_name:
        q = (Dataset.query
             .join(Epoch, Dataset.container)
             .join(Session, Epoch.session)
             .join(Subject, Session.subject)
             .join(Experiment, Subject.experiment)
             .join(ResearchGroup, Experiment.owner)
             .join(Access)
             .join(User, Access.user)
             .filter(ResearchGroup.gid.ilike(unicode(group_name)))
             .filter(Experiment.name.ilike(unicode(exp_name))))
        if not '%' in exam:
            q = q.filter(Session.exam==int(exam))
        if len(esp)>1 and not '%' in esp[1]:
            q = q.filter(Epoch.series==int(esp[1]))
        if len(esp)>2 and not '%' in esp[2]:
            q = q.filter(Epoch.acq==int(esp[2]))
        datasets = (q.filter(Access.user==user)
                     .filter((Access.privilege >= AccessPrivilege.value(u'Read-Only')) | ((Dataset.kind != u'primary') & (Dataset.kind != u'secondary')))
                     .all())
        if '%' in epoch_name:
            print 'DATASETS: %d' % len(datasets)
            # return a flat structure with legacy-style filenames
            datafiles = []
            for d in datasets:
                for f in d.filenames:
                    display_name = '%04d_%02d_%s.%s' % (d.container.series, d.container.acq, d.container.description, '.'.join(f.split('.')[1:]))
                    datafiles.append((display_name.encode(), os.path.join(server.datapath,d.relpath,f).encode()))
        else:
            # Use the filename on disk
            datafiles = [(f.encode(), os.path.join(server.datapath,d.relpath,f).encode()) for d in datasets for f in d.filenames]
    else:
        datafiles = []
    return datafiles


class NimsfsStat(fuse.Stat):
    """
    Class for Stat objects.
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
        self.datapath = '/_nimsfs'
        self.fp = None
        self.file_size = 0

    def getattr(self, path):
        #print 'GETATTR: path=' + path
        fn = path.split('/')[-1]
        is_dir = '%' in fn or not bool(os.path.splitext(fn)[1])
        size = 0
        if not is_dir:
            context = self.GetContext()
            username = pwd.getpwuid(context['uid']).pw_name
            groupname = grp.getgrgid(context['gid']).gr_name
            user = User.get_by(uid=unicode(username))
            cur_path = path.split('/')
            if len(cur_path) == 6:
                files = get_datasets(user, cur_path[1], cur_path[2], cur_path[3], cur_path[4])
                fname = next((f[1] for f in files if f[0] == cur_path[5]), None)
                if fname:
                    size = os.path.getsize(fname)
                else:
                    return -errno.ENOENT
        return NimsfsStat(is_dir, size, 0, 0)

    def readdir(self, path, offset):
        #print 'READDIR: path=' + path
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
            dirs = [d[0] for d in get_datasets(user, cur_path[1], cur_path[2], cur_path[3], cur_path[4])]
        else:
            dirs = []
        for e in ['.','..'] + dirs:
            yield fuse.Direntry(e)

    def open(self, path, flags):
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
                fname = next((f[1] for f in files if f[0] == cur_path[5]), None)
                if fname:
                    self.file_size = os.path.getsize(fname)
                    self.fp = open(fname, 'rb')
            return 0

    def read(self, path, size, offset):
        if self.fp:
            self.fp.seek(offset)
            buf = self.fp.read(size)
        else:
            buf = ''
        return buf

    def flush(self, fh=None):
        if self.fp:
            self.fp.close()

    def fgetattr(self, fh=None):
        return NimsfsStat(0, self.file_size, 0, 0)


if __name__ == '__main__':
    usage = ('nimsfs.py [mountpoint]\n'
            +'Mount the NIMS virtual filesystem tree at the specified mountpoint.\n'
            +'To unmount, use fusermount -u [mountpoint].\n\n'
            +Fuse.fusage)

    server = Nimsfs(version='%prog ' + fuse.__version__, usage=usage, dash_s_do='setsingle')

    # To use multithreading, we'd need to protect all methods of
    # NimsfsFile class with locks to prevent race conditions
    server.multithreaded = False

    server.parser.add_option(mountopt='datapath', metavar='PATH', default=server.datapath,
                             help="nims data path. [default=%default]")
    server.parse(values=server, errex=1)

    try:
        server.fuse_args.mount_expected()
    except OSError:
        print >> sys.stderr, 'Error mounting NIMS.'
        sys.exit(1)

    server.main()

