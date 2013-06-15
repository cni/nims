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
import errno  # for error number codes (ENOENT, etc)
import stat   # for file properties
import time
import argparse
import pwd    # to translate uid to username
import grp    # to translate gid to groupname
import fuse

import sqlalchemy
from nimsgears.model import *

import threading
import collections
import functools


class memoize(object):
    '''Decorator to cache a function's return value each time it is called.
    If called later with the same arguments, the cached value is returned.
    '''
    def __init__(self, cachetime=5):
        # If there are decorator arguments, the decorated function is not passed to the constructor.
        # Instead, it's passed to __call__, which will get called only once upon decoration.
        self.cachetime = cachetime
        self.cache = {}
        self.lock = threading.Lock()
        self.garbage_collector = threading.Thread(target=self.collect_garbage)
        self.garbage_collector.daemon = True
        self.garbage_collector.start()

    def collect_garbage(self):
        while True:
            now = time.time()
            with self.lock:
                for key in self.cache.keys():
                    if self.cache[key][1] + self.cachetime < now:
                        del self.cache[key]
            time.sleep(self.cachetime * 2)

    def __call__(self, func):
        def wrapped_func(*args):
            # Ensure the args are hashable. If not, don't try to cache.
            if not isinstance(args, collections.Hashable):
                return func(*args)
            # Need to lock to keep the garbage collector from deleting something as we read it.
            with self.lock:
                if args in self.cache and self.cache[args][1] + self.cachetime > time.time():
                    value = self.cache[args][0]
                else:
                    value = func(*args)
                    self.cache[args] = (value,time.time())
            return value
        return wrapped_func

    def __repr__(self):
        '''Return the function's docstring.'''
        return self.func.__doc__

    def __get__(self, obj, objtype):
        '''Support instance methods.'''
        return functools.partial(self.__call__, obj)

@memoize()
def get_groups(username):
    user = User.get_by(uid=unicode(username))
    experiments = (Experiment.query.join(Access)
                   .filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
    return sorted(set([e.owner.gid.encode() for e in experiments]))


@memoize()
def get_experiments(username, group_name):
    user = User.get_by(uid=unicode(username))
    experiments = (Experiment.query.join(Access)
                   .join(ResearchGroup, Experiment.owner)
                   .filter(ResearchGroup.gid.ilike(unicode(group_name)))
                   .filter(Access.user==user)
                   .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                   .all())
    return sorted([e.name.encode() for e in experiments])

@memoize()
def get_sessions(username, group_name, exp_name):
    user = User.get_by(uid=unicode(username))
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

@memoize()
def get_epochs(username, group_name, exp_name, session_name):
    # FIXME: we should explicitly set the session name so that we can be sure the exam is there.
    user = User.get_by(uid=unicode(username))
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

@memoize()
def get_datasets(username, group_name, exp_name, session_name, epoch_name, datapath):
    user = User.get_by(uid=unicode(username))
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
            # return a flat structure with legacy-style filenames
            datafiles = []
            for d in datasets:
                # The 'series_container_acq_description' name isn't guaranteed to be unique. Sometimes there are multiple
                # files with different "extensions". We'll find the extensions here.
                if len(d.filenames) > 1:
                    ext_start_ind = max(0, len(os.path.commonprefix(d.filenames))-1)
                else:
                    ext_start_ind = len(d.filenames[0].split('.')[0])
                print 'DATASET ' + str(d)
                for f in d.filenames:
                    display_name = '%04d_%02d_%s%s' % (d.container.series, d.container.acq, d.container.description, f[ext_start_ind:])
                    datafiles.append((display_name.encode(), os.path.join(datapath,d.relpath,f).encode()))
                    print '   FILENAME=' + f + ' DISPLAY_NAME=' + display_name

        else:
            # Use the filename on disk
            datafiles = [(f.encode(), os.path.join(datapath,d.relpath,f).encode()) for d in datasets for f in d.filenames]
    else:
        datafiles = []
    return datafiles


class Nimsfs(fuse.LoggingMixIn, fuse.Operations):

    def __init__(self, datapath, db_uri):
        self.datapath = datapath
        self.rwlock = threading.Lock()
        self.db_uri = 'postgresql://nims:nims@nimsfs.stanford.edu:5432/nims'
        init_model(sqlalchemy.create_engine(self.db_uri))
        # not sure if it's a good idea to store these here. Is there a separate instance of this object for each
        # call to the fs? If so, then this is ok. But if this instance is shared, then we can't store specific info here.
        self.fp = None
        self.file_size = 0
        self.file_ts = 0

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse.fuse_get_context()
        fn = path.split('/')[-1]
        is_dir = '%' in fn or not bool(os.path.splitext(fn)[1])
        ts = int(time.time())
        if is_dir:
            size = 0
            mode = stat.S_IFDIR | 0555
            nlink = 2
        else:
            mode = stat.S_IFREG | 0444
            nlink = 1
            username = pwd.getpwuid(uid).pw_name
            groupname = grp.getgrgid(gid).gr_name
            cur_path = path.split('/')
            if len(cur_path) == 6:
                files = get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath)
                fname = next((f[1] for f in files if f[0] == cur_path[5]), None)
                if fname:
                    size = os.path.getsize(fname)
                    ts = os.path.getmtime(fname)
                else:
                    raise fuse.FuseOSError(errno.ENOENT)
        return {'st_atime':ts, 'st_ctime':ts, 'st_gid':gid, 'st_mode':mode, 'st_mtime':ts, 'st_nlink':nlink, 'st_size':size, 'st_uid':uid}

    def readdir(self, path, fh):
        uid, gid, pid = fuse.fuse_get_context()
        username = pwd.getpwuid(uid).pw_name
        groupname = grp.getgrgid(gid).gr_name
        cur_path = path.split('/')
        if len(cur_path) < 2 or not cur_path[1]:
            dirs = get_groups(username)
        elif len(cur_path) < 3:
            dirs = get_experiments(username, cur_path[1])
        elif len(cur_path) < 4:
            dirs = get_sessions(username, cur_path[1], cur_path[2])
        elif len(cur_path) < 5:
            dirs = get_epochs(username, cur_path[1], cur_path[2], cur_path[3])
        elif len(cur_path) == 5:
            dirs = [d[0] for d in get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath)]
        else:
            dirs = []
        return ['.','..'] + dirs

    def open(self, path, flags):
        # Only support 'READ ONLY' flag
        access_flags = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        fh = 0
        if flags & access_flags != os.O_RDONLY:
            raise fuse.FuseOSError(errno.EACCES)
        else:
            cur_path = path.split('/')
            if len(cur_path) == 6:
                uid, gid, pid = fuse.fuse_get_context()
                username = pwd.getpwuid(uid).pw_name
                groupname = grp.getgrgid(gid).gr_name
                files = get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath)
                fname = next((f[1] for f in files if f[0] == cur_path[5]), None)
                if fname:
                    self.file_size = os.path.getsize(fname)
                    self.file_ts = os.path.getmtime(fname)
                    fh = os.open(fname, flags)
                else:
                    raise fuse.FuseOSError(errno.ENOENT)
        return fh

    def read(self, path, size, offset, fh):
        with self.rwlock:
            os.lseek(fh, offset, 0)
            return os.read(fh, size)

    def fgetattr(self, fh=None):
        uid, gid, pid = fuse.fuse_get_context()
        mode = stat.S_IFREG | 0444
        return {'st_atime':self.file_ts, 'st_ctime':self.file_ts, 'st_gid':gid, 'st_mode':mode, 'st_mtime':self.file_ts, 'st_nlink':1, 'st_size':self.file_size, 'st_uid':uid}

    def flush(self, path, fh):
        os.fsync(fh)

class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Mount a NIMS filesystem. This exposes the NIMS file structure as a reqular filesystem using fuse."""
        self.add_argument('-n', '--no_allow_other', action='store_true', help='Use this flag to disable the "allow_other" option. (For normal use, be sure to enable allow_other in /etc/fuse.conf)')
        self.add_argument('-d', '--debug', action='store_true', help='Start the filesystem in debug mode')
        uri = 'postgresql://nims:nims@nimsfs.stanford.edu:5432/nims'
        self.add_argument('-u', '--uri', metavar='URI', default=uri, help='URI pointing to the NIMS database. (Default=%s)' % uri)
        self.add_argument('datapath', help='path to NIMS data')
        self.add_argument('mountpoint', help='mountpoint for NIMSfs')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    fuse = fuse.FUSE(Nimsfs(datapath=args.datapath, db_uri=args.uri),
                     args.mountpoint,
                     debug=args.debug,
                     allow_other=(not args.no_allow_other))

