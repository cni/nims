#!/usr/bin/env python
#
# @author:  Bob Dougherty

"""
Nimsfs uses FUSE to expose the NIMS database to users as a browseable filesystem.
Access control is implemented assuming that the operating system uid of the process
accessing nimsfs is correct, and that this uid maps to the correct NIMS username.
If all users are assigned their centrally-managed uids and only kerberos authentication
is permitted on the system, then these requirements should be met.

"""

import os, sys
import errno  # for error number codes (ENOENT, etc)
import stat   # for file properties
import time
import argparse
import pwd    # to translate uid to username
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

def get_user(username):
    # We could be given either a real username (string) or a numeric unix UID
    if isinstance(username,(int,long)):
        user = User.get_by(uid_number=username)
    else:
        user = User.get_by(uid=unicode(username))
    return user

@memoize()
def get_groups(username, rawdir=False):
    if username==None:
        experiments = (Experiment.query.all())
    else:
        user = get_user(username)
        experiments = (Experiment.query.join(Access)
                       .filter(Access.user==user)
                       .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read'))
                       .all())
    extra = ['README.txt']
    if rawdir:
        extra = extra + ['raw']
    return sorted(set([e.owner.gid.encode() for e in experiments])) + extra

@memoize()
def get_experiments(username, group_name, trash=False):
    q = (Experiment.query.join(Access)
         .join(ResearchGroup, Experiment.owner)
         .filter(ResearchGroup.gid.ilike(unicode(group_name))))
    if not trash:
        q = q.filter(Experiment.trashtime == None)
    if username!=None:
        user = get_user(username)
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
        user = get_user(username)
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
            user = get_user(username)
            q = (q.filter(Access.user==user)
                  .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read')))
        epoch_names = sorted([(e.name + '_' + e.description).encode() for e in q.all()])
    else:
        epoch_names = []
    return epoch_names

@memoize()
def get_datasets(username, group_name, exp_name, session_name, epoch_name, datapath, hide_raw=False, trash=False):
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
        if hide_raw:
            q = q.filter((Dataset.kind==u'peripheral') | (Dataset.kind==u'derived') | (Dataset.kind==u'qa'))
        if username!=None:
            user = get_user(username)
            q = (q.filter(Access.user==user)
                  .filter(Access.privilege>=AccessPrivilege.value(u'Anon-Read')))
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
                    # Filetype magic. You can get filenames based on the filetype by using %t for the epoch name. E.g.,
                    #  $ ls /nimsfs/cni/muxt1/20140116_1218_6120/%t
                    #     0002_01_calibration.nii.gz  0005_01_anatomy.nii.gz  0011_01_anatomy.nii.gz  0015_01_anatomy_t1w.nii.gz
                    if len(epoch_name)>1 and epoch_name[1]=='t':
                        if d.filetype==u'nifti':
                            display_name = '%04d_%02d_%s%s' % (d.container.series, d.container.acq, d.container.scan_type, f[ext_start_ind:])
                            datafiles.append((display_name.encode(), os.path.join(datapath,d.relpath,f).encode()))
                    else:
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

    def __init__(self, datapath, db_uri, god_mode=False, hide_raw=False, local_names=False):
        ''' datapath: the path to the nims data. All data must be readable by
                      the user running nimsfs.
            db_uri: the database URI for quering the nims db. The machine where
                    nimsfs runs must have permission to query the db.
            god_mode: a flag used mostly for debugging. All access control is disabled.
                      Obvioulsy, only superusers should have access to nimsfs running
                      in this mode.
            hide_raw: flag determining whether raw data files are shown. If true, the data
                      shown are comparable to what a user would get from a nims download
                      when "include raw" is unchecked.
            local_names: a flag indicating that we should use the local password file
                         to map uid's to usernames. If false, then the uid will be passed
                         straight to nims for the user look-up. This is useful when the
                         users accessing nimsfs don't have local accounts on the machine
                         running nimsfs (e.g., when nimsfs is run on a server and exported
                         over NFS). Note that we still count on the local machine's uid
                         being set correctly for security.

        '''
        self.datapath = datapath
        self.db_uri = db_uri
        self.god_mode = god_mode
        self.hide_raw = hide_raw
        self.local_names = local_names
        #self.rwlock = threading.Lock()
        self.gzfile = None
        self.readme_fname = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'user_guide.txt')

        init_model(sqlalchemy.create_engine(self.db_uri))

    def get_path(self, path):
        cur_path = path.split('/')
        if self.hide_raw and len(cur_path)>1 and cur_path[1]=='raw':
            cur_path.pop(1)
            hide_raw = False
        else:
            hide_raw = True
        return(cur_path,hide_raw)

    def get_username(self, uid):
        if self.god_mode:
            username = None
        elif self.local_names:
            username = pwd.getpwuid(uid).pw_name
        else:
            username = uid
        return username

    def getattr(self, path, fh=None):
        uid, gid, pid = fuse.fuse_get_context()
        if fh:
            fs = os.fstat(fh)
            at = fs.st_atime
            ct = fs.st_ctime
            mt = fs.st_mtime
            sz = fs.st_size
            mode = stat.S_IFREG | 0444
            nlink = 1
            # TODO: get the uncompressed size for gzip files.
        else:
            fn = path.split('/')[-1]
            is_dir = '%' in fn or not bool(os.path.splitext(fn)[1])
            at = ct = mt = int(time.time())
            if is_dir:
                sz = 0
                mode = stat.S_IFDIR | 0555
                nlink = 2
            else:
                mode = stat.S_IFREG | 0444
                nlink = 1
                username = self.get_username(uid)
                cur_path,hide_raw = self.get_path(path)
                sz = 1
                if len(cur_path) == 6:
                    files = get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath, hide_raw)
                    fname = next((f[1] for f in files if f[0]==cur_path[5]), None)
                    if fname:
                        sz = os.path.getsize(fname)
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
                                sz = struct.unpack('<I',fp.read())[0]
                        else:
                            raise fuse.FuseOSError(errno.ENOENT)
                    else:
                        raise fuse.FuseOSError(errno.ENOENT)
        return {'st_atime':at, 'st_ctime':ct, 'st_gid':gid, 'st_mode':mode, 'st_mtime':mt, 'st_nlink':nlink, 'st_size':sz, 'st_uid':uid}

    def readdir(self, path, fh):
        uid, gid, pid = fuse.fuse_get_context()
        username = self.get_username(uid)
        cur_path,hide_raw = self.get_path(path)
        if len(cur_path) < 2 or not cur_path[1]:
            dirs = get_groups(username, hide_raw)
        elif len(cur_path) < 3:
            dirs = get_experiments(username, cur_path[1])
        elif len(cur_path) < 4:
            dirs = get_sessions(username, cur_path[1], cur_path[2])
        elif len(cur_path) < 5:
            dirs = get_epochs(username, cur_path[1], cur_path[2], cur_path[3])
        elif len(cur_path) == 5:
            if cur_path[4][-1]=='?':
                dirs = [d[1] for d in get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4][:-1], self.datapath, hide_raw)]
            else:
                dirs = [d[0] for d in get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath, hide_raw)]
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
            cur_path,hide_raw = self.get_path(path)
            if len(cur_path) == 6:
                uid, gid, pid = fuse.fuse_get_context()
                username = self.get_username(uid)
                files = get_datasets(username, cur_path[1], cur_path[2], cur_path[3], cur_path[4], self.datapath, hide_raw)
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
            elif len(cur_path)==2 and cur_path[1]=='README.txt':
                fh = os.open(self.readme_fname, flags)
        return fh

    def release(self, path, fh):
        self.gzfile = None
        os.close(fh)

    # NOTE: the read function is implemented in fuse.py. Doing it there makes file reads 10x faster!
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
            at = fs.st_atime
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
        self.add_argument('-g', '--god', action='store_true', help='God mode-- NO ACCESS CONTROL! (implies hide_raw=False)')
        self.add_argument('-r', '--hide_raw', action='store_true', help='Don''t show or allow access to raw data (no effect for god mode)')
        self.add_argument('-l', '--localname', action='store_true', help='Use the local password file to map uid to NIMS username. (Otherwise, uids are sent straight to NIMS.)')
        uri = 'postgresql://nims:nims@cnifs.stanford.edu:5432/nims'
        self.add_argument('-u', '--uri', metavar='URI', default=uri, help='URI pointing to the NIMS database. (Default=%s)' % uri)
        self.add_argument('datapath', help='path to NIMS data')
        self.add_argument('mountpoint', help='mountpoint for NIMSfs')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    if args.god:
        print "WARNING: Starting god-mode. All access control disabled!"
        args.hide_raw = False
    fuse = fuse.FUSE(Nimsfs(datapath=args.datapath, db_uri=args.uri, god_mode=args.god, hide_raw=args.hide_raw, local_names=args.localname),
                     args.mountpoint,
                     debug=args.debug,
                     nothreads=True,
                     allow_other=(not args.no_allow_other))
#big_writes=True, max_read=2**17, max_write=2**17,
