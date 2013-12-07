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
import gzip
import struct

import sqlalchemy
from nimsgears.model import *

import threading
import collections
import functools


class memoize(object):
    '''
    Decorator to cache a function's return value each time it is called.
    If called later with the same arguments, the cached value is returned.
    Includes a garbage collector thread that purges the cache of old items.
    and a lock to ensure that the cache isn't purged while values are read.
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
            for key in self.cache.keys():
                if self.cache[key][1] + self.cachetime < now:
                    # We don't need to lock before the conditional because no other thread will delete.
                    with self.lock:
                        del self.cache[key]
            time.sleep(self.cachetime * 1.1)

    def __call__(self, func):
        self.func = func

        def wrapped_func(*args):
            # Ensure the args are hashable. If not, don't try to cache.
            if not isinstance(args, collections.Hashable):
                return self.func(*args)
            # Lock to keep the garbage collector from deleting something after found but before read.
            with self.lock:
                if args in self.cache and self.cache[args][1] + self.cachetime > time.time():
                    value_set = True
                    value = self.cache[args][0]
                else:
                    value_set = False
            # This could have been implemented more simply as an else clause in the above conditional.
            # However, in that case, the lock would have been held for the whole time that the
            # value was computed, which could be significant for a large query. So for good
            # concurrency performance the lock is kept only around what is absolutely necessary.
            if not value_set:
                value = self.func(*args)
                # TODO: ensure that inserting in a dict is thread-safe. Otherwise, throw a lock around this.
                self.cache[args] = (value,time.time())
            return value

        return wrapped_func

        # TODO: These don't work. Figure out how to pass-through the doc string.
        def __repr__(self):
            '''Return the function's docstring.'''
            return self.func.__doc__

        def __get__(self, obj, objtype):
            '''Support instance methods.'''
            return functools.partial(self.__call__, obj)

@memoize()
def get_groups(username):
    if username==None:
        experiments = (Experiment.query.all())
    else:
        user = User.get_by(uid=unicode(username))
        experiments = (Experiment.query.join(Access)
                       .filter(Access.user==user)
                       .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                       .all())
    return sorted(set([e.owner.gid.encode() for e in experiments]))

@memoize()
def get_experiments(username, group_name, trash=False):
    q = (Experiment.query.join(Access)
         .join(ResearchGroup, Experiment.owner)
         .filter(ResearchGroup.gid.ilike(unicode(group_name))))
    if not trash:
        q = q.filter(Experiment.trashtime == None)
    if username!=None:
        user = User.get_by(uid=unicode(username))
        q = (q.filter(Access.user==user)
              .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read')))
    return sorted([e.name.encode() for e in q.all()])

@memoize()
def get_sessions(username, group_name, exp_name, trash=False):
    q = (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .filter(ResearchGroup.gid.ilike(unicode(group_name)))
                .filter(Experiment.name.ilike(unicode(exp_name))))
    if not trash:
        q = q.filter(Session.trashtime == None)
    if username!=None:
        user = User.get_by(uid=unicode(username))
        q = (q.filter(Access.user==user)
              .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read')))
    return sorted([s.name.encode() for s in q.all()])

@memoize()
def get_epochs(username, group_name, exp_name, session_name, trash=False):
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
        if not trash:
            q = q.filter(Epoch.trashtime == None)
        if username!=None:
            user = User.get_by(uid=unicode(username))
            q = (q.filter(Access.user==user)
                  .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read')))
        epoch_names = sorted([(e.name + '_' + e.description).encode() for e in q.all()])
    else:
        epoch_names = []
    return epoch_names

@memoize()
def get_datasets(username, group_name, exp_name, session_name, epoch_name, datapath, trash=False):
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
        if not trash:
            q = q.filter(Dataset.trashtime == None)
        if username!=None:
            user = User.get_by(uid=unicode(username))
            q = (q.filter(Access.user==user)
                  .filter((Access.privilege >= AccessPrivilege.value(u'Read-Only'))
                       | ((Dataset.kind != u'primary') & (Dataset.kind != u'secondary'))))
        if '%' in epoch_name:
            # return a flat structure with legacy-style filenames
            datafiles = []
            for d in q.all():
                # The 'series_container_acq_description' name isn't guaranteed to be unique. Sometimes there are multiple
                # files with different "extensions". We'll find the extensions here.
                if len(d.filenames) > 1:
                    ext_start_ind = max(0, len(os.path.commonprefix(d.filenames))-1)
                else:
                    ext_start_ind = len(d.filenames[0].split('.')[0])
                #print 'DATASET ' + str(d)
                for f in d.filenames:
                    display_name = '%04d_%02d_%s%s' % (d.container.series, d.container.acq, d.container.description, f[ext_start_ind:])
                    datafiles.append((display_name.encode(), os.path.join(datapath,d.relpath,f).encode()))
                    #print '   FILENAME=' + f + ' DISPLAY_NAME=' + display_name
        else:
            # Use the filename on disk
            datafiles = [(f.encode(), os.path.join(datapath,d.relpath,f).encode()) for d in q.all() for f in d.filenames]
    else:
        datafiles = []
    return datafiles


class Nimsfs(fuse.LoggingMixIn, fuse.Operations):

    def __init__(self, datapath, db_uri, god_mode=False):
        self.datapath = datapath
        self.db_uri = db_uri
        self.god_mode = god_mode
        #self.rwlock = threading.Lock()
        self.gzfile = None
        self.path = ''
        init_model(sqlalchemy.create_engine(self.db_uri))

    def getattr(self, path, fh=None):
        print 'getattr: ' + path
        if self.path==path:
            ts = self.ts
            gid = self.gid
            mode = self.mode
            nlink = self.nlink
            size = self.size
            uid = self.uid
        else:
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
                username = pwd.getpwuid(uid).pw_name if not self.god_mode else None
                groupname = grp.getgrgid(gid).gr_name
                cur_path = path.split('/')
                size = 1
                if len(cur_path) == 6:
                    files = get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath)
                    fname = next((f[1] for f in files if f[0]==cur_path[5]), None)
                    if fname:
                        size = os.path.getsize(fname)
                        ts = os.path.getmtime(fname)
                    elif cur_path[5].endswith('ugz'):
                        # Check to see if we're being asked about a gzipped file
                        fn = cur_path[5][:-3] +'gz'
                        fname = next((f[1] for f in files if f[0]==fn), None)
                        if fname:
                            ts = os.path.getmtime(fname)
                            # Apparently there's no way to get the uncompressed size except by reading the last four bytes.
                            # TODO: consider saving this (as well as the timestamp) in the db.
                            with open(fname, 'r') as fp:
                                fp.seek(-4,2)
                                size = struct.unpack('<I',fp.read())[0]
                        else:
                            raise fuse.FuseOSError(errno.ENOENT)
                    else:
                        raise fuse.FuseOSError(errno.ENOENT)
                self.path = path
                self.ts = ts
                self.gid = gid
                self.mode = mode
                self.nlink = nlink
                self.size = size
                self.uid = uid
        return {'st_atime':ts, 'st_ctime':ts, 'st_gid':gid, 'st_mode':mode, 'st_mtime':ts, 'st_nlink':nlink, 'st_size':size, 'st_uid':uid}

    def readdir(self, path, fh):
        uid, gid, pid = fuse.fuse_get_context()
        username = pwd.getpwuid(uid).pw_name if not self.god_mode else None
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
            if cur_path[4][-1]=='?':
                dirs = [d[1] for d in get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4][:-1], self.datapath)]
            else:
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
                username = pwd.getpwuid(uid).pw_name if not self.god_mode else None
                groupname = grp.getgrgid(gid).gr_name
                files = get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath)
                fname = next((f[1] for f in files if f[0]==cur_path[5]), None)
                if fname:
                    self.gzfile = None
                    fh = os.open(fname, flags)
                elif cur_path[5].endswith('ugz'):
                    # Check to see if we're being asked about a gzipped file
                    fn = cur_path[5][:-3] +'gz'
                    fname = next((f[1] for f in files if f[0]==fn), None)
                    if fname:
                        self.gzfile = gzip.open(fname,'r')
                        fh = self.gzfile.fileno()
                    else:
                        raise fuse.FuseOSError(errno.ENOENT)
                else:
                    raise fuse.FuseOSError(errno.ENOENT)
        return fh

    def release(self, path, fh):
        self.gzfile = None
        os.close(fh)

    def read(self, path, size, offset, fh):
        #with self.rwlock:
        if self.gzfile:
            self.gzfile.seek(offset, 0)
            return self.gzfile.read(size)
        else:
            os.lseek(fh, offset, 0)
            return os.read(fh, size)

    def fgetattr(self, fh=None):
        uid, gid, pid = fuse.fuse_get_context()
        # mode is always read-only
        mode = stat.S_IFREG | 0444
        if fh:
            fs = os.fstat(fh)
            at = os.st_atime
            ct = fs.st_ctime
            mt = fs.st_mtime
            sz = fs.st_size
        else:
            at,ct,mt = time.time()
            sz = 0
        return {'st_atime':at, 'st_ctime':ct, 'st_mtime':mt, 'st_gid':gid, 'st_mode':mode, 'st_nlink':1, 'st_size':sz, 'st_uid':uid}

    def flush(self, path, fh):
        if self.gzfile:
            self.gzfile.flush()
        else:
            os.fsync(fh)

class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Mount a NIMS filesystem. This exposes the NIMS file structure as a reqular filesystem using fuse."""
        self.add_argument('-n', '--no_allow_other', action='store_true', help='Use this flag to disable the "allow_other" option. (For normal use, be sure to enable allow_other in /etc/fuse.conf)')
        self.add_argument('-d', '--debug', action='store_true', help='start the filesystem in debug mode')
        self.add_argument('-g', '--god', action='store_true', help='God mode-- NO ACCESS CONTROL!')
        uri = 'postgresql://nims:nims@cnifs.stanford.edu:5432/nims'
        self.add_argument('-u', '--uri', metavar='URI', default=uri, help='URI pointing to the NIMS database. (Default=%s)' % uri)
        self.add_argument('datapath', help='path to NIMS data')
        self.add_argument('mountpoint', help='mountpoint for NIMSfs')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    if args.god:
        print "WARNING: Starting god-mode. All access control disabled!"
    fuse = fuse.FUSE(Nimsfs(datapath=args.datapath, db_uri=args.uri, god_mode=args.god),
                     args.mountpoint,
                     debug=args.debug,
                     big_writes=True, max_read=2**17, max_write=2**17, nothreads=True,
                     allow_other=(not args.no_allow_other))

