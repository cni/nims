#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

import os
import abc
import time
import shutil
import signal
import logging
import tarfile
import argparse
import datetime
import threading

import sqlalchemy
import transaction

import nimsutil
import nimsdata
from nimsgears.model import *

log = logging.getLogger('processor')


class Processor(object):

    def __init__(self, db_uri, nims_path, physio_path, task, filters, max_jobs, max_recon_jobs, reset, sleeptime, tempdir, newest):
        super(Processor, self).__init__()
        self.nims_path = nims_path
        self.physio_path = physio_path
        self.task = unicode(task) if task else None
        self.filters = filters
        self.max_jobs = max_jobs
        self.max_recon_jobs = max_recon_jobs
        self.sleeptime = sleeptime
        self.tempdir = tempdir
        self.newest = newest

        self.alive = True
        init_model(sqlalchemy.create_engine(db_uri))
        if reset: self.reset_all()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            if threading.active_count()-1 < self.max_jobs:
                query = Job.query.join(DataContainer).join(Epoch)
                if self.task:
                    query = query.filter(Job.task==self.task)
                for f in self.filters:
                    query = query.filter(eval(f))
                if self.newest:
                    job = query.filter(Job.status==u'pending').order_by(Job.id.desc()).with_lockmode('update').first()
                else:
                    job = query.filter(Job.status==u'pending').order_by(Job.id).with_lockmode('update').first()

                if job:
                    if isinstance(job.data_container, Epoch) and job.data_container.primary_dataset!=None:
                        ds = job.data_container.primary_dataset
                        if ds.filetype == nimsdata.nimsdicom.NIMSDicom.filetype:
                            pipeline_class = DicomPipeline
                        elif ds.filetype == nimsdata.nimsraw.NIMSPFile.filetype:
                            pipeline_class = PFilePipeline

                        pipeline = pipeline_class(job, self.nims_path, self.physio_path, self.tempdir, self.max_recon_jobs)
                        job.status = u'running'
                        transaction.commit()
                        pipeline.start()
                    else:
                        job.status = u'failed'
                        job.activity = u'failed: not an Epoch or no primary dataset.'
                        log.warning(u'%d %s %s ' % (job.id, job, job.activity))
                        transaction.commit()
                else:
                    log.debug('Waiting for work...')
                    time.sleep(self.sleeptime)
            else:
                log.debug('Waiting for jobs to finish...')
                time.sleep(self.sleeptime)

    def reset_all(self):
        """Reset all running of failed jobs to pending."""
        job_query = Job.query.filter((Job.status == u'running') | (Job.status == u'failed'))
        if self.task:
            job_query = job_query.filter(Job.task==self.task)
        for job in job_query.all():
            job.status = u'pending'
            job.activity = u'reset to pending'
            log.info(u'%d %s %s' % (job.id, job, job.activity))
        transaction.commit()


class Pipeline(threading.Thread):

    __metaclass__ = abc.ABCMeta

    def __init__(self, job, nims_path, physio_path, tempdir, max_recon_jobs):
        super(Pipeline, self).__init__()
        self.job = job
        self.nims_path = nims_path
        self.physio_path = physio_path
        self.tempdir = tempdir
        self.max_recon_jobs = max_recon_jobs

    def run(self):
        DBSession.add(self.job)
        self.job.activity = u'started'
        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()
        DBSession.add(self.job)
        try:
            if self.job.task == u'find&proc':
                self.find()
                self.process()
            elif self.job.task == u'find':
                self.find()
            elif self.job.task == u'proc':
                self.process()
        except Exception as ex:
            self.job.status = u'failed'
            self.job.activity = u'failed: %s' % ex
            log.warning(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        else:
            self.job.status = u'done'
            self.job.activity = u'done'
            log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()

    def clean(self, data_container, kind):
        for ds in Dataset.query.filter_by(container=data_container).filter_by(kind=kind).all():
            shutil.rmtree(os.path.join(self.nims_path, ds.relpath))
            ds.delete()

    @abc.abstractmethod
    def find(self):
        self.clean(self.job.data_container, u'peripheral')
        transaction.commit()
        DBSession.add(self.job)

        dc = self.job.data_container
        ds = self.job.data_container.primary_dataset
        if dc.physio_recorded:
            physio_files = nimsutil.find_ge_physio(self.physio_path, dc.timestamp+dc.prescribed_duration, dc.psd.encode('utf-8'))
            if physio_files:
                physio = nimsdata.nimsphysio.NIMSPhysio(physio_files, dc.tr, dc.num_timepoints)
                if physio.is_valid():
                    self.job.activity = u'valid physio found'
                    log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                    # Computing the slice-order can be expensive, so we didn't do it when we instantiated.
                    # But now that we know physio is valid, we need to do it.
                    ni = nimsdata.parse(os.path.join(self.nims_path, ds.primary_file_relpath))
                    physio.slice_order = ni.get_slice_order() # TODO: should probably write a set method
                    dataset = Dataset.at_path(self.nims_path, u'physio')
                    DBSession.add(self.job)
                    DBSession.add(self.job.data_container)
                    dataset.kind = u'peripheral'
                    dataset.container = self.job.data_container
                    with nimsutil.TempDir(dir=self.tempdir) as tempdir_path:
                        arcdir_path = os.path.join(tempdir_path, '%s_physio' % self.job.data_container.name)
                        os.mkdir(arcdir_path)
                        for f in physio_files:
                            shutil.copy2(f, arcdir_path)
                        filename = '%s_physio.tgz' % self.job.data_container.name
                        dataset.filenames = [filename]
                        with tarfile.open(os.path.join(self.nims_path, dataset.relpath, filename), 'w:gz', compresslevel=6) as archive:
                            archive.add(arcdir_path, arcname=os.path.basename(arcdir_path))
                        try:
                            reg_filename = '%s_physio_regressors.csv.gz' % self.job.data_container.name
                            physio.write_regressors(os.path.join(self.nims_path, dataset.relpath, reg_filename))
                        except nimsdata.nimsphysio.NIMSPhysioError:
                            self.job.activity = u'error generating regressors from physio data'
                            log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                        else:
                            dataset.filenames += [reg_filename]
                else:
                    self.job.activity = u'invalid physio found and discarded'
                    log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
            else:
                self.job.activity = u'no physio files found'
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        else:
            self.job.activity = u'physio not recorded'
            log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()
        DBSession.add(self.job)

    @abc.abstractmethod
    def process(self):
        self.clean(self.job.data_container, u'derived')
        self.clean(self.job.data_container, u'web')
        self.clean(self.job.data_container, u'qa')
        self.job.data_container.qa_status = u'rerun'
        self.job.activity = u'generating NIfTI / running recon'
        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()
        DBSession.add(self.job)


class DicomPipeline(Pipeline):

    def find(self):
        return super(DicomPipeline, self).find()

    def process(self):
        super(DicomPipeline, self).process()

        ds = self.job.data_container.primary_dataset
        with nimsutil.TempDir(dir=self.tempdir) as outputdir:
            outbase = os.path.join(outputdir, ds.container.name)
            dcm_tgz = os.path.join(self.nims_path, ds.relpath, os.listdir(os.path.join(self.nims_path, ds.relpath))[0])
            dcm_acq = nimsdata.nimsdicom.NIMSDicom(dcm_tgz)
            conv_type, conv_file = dcm_acq.convert(outbase)

            if conv_type:
                outputdir_list = os.listdir(outputdir)
                self.job.activity = (u'generated %s' % (', '.join([f for f in outputdir_list])))[:255]
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                conv_ds = Dataset.at_path(self.nims_path, unicode(conv_type))
                DBSession.add(self.job)
                DBSession.add(self.job.data_container)

                conv_ds.kind = u'derived'
                conv_ds.container = self.job.data_container
                filenames = []
                for f in outputdir_list:
                    filenames.append(f)
                    shutil.copy2(os.path.join(outputdir, f), os.path.join(self.nims_path, conv_ds.relpath))
                conv_ds.filenames = filenames
                transaction.commit()

            if conv_type == 'nifti':
                pyramid_ds = Dataset.at_path(self.nims_path, u'img_pyr')
                DBSession.add(self.job)
                DBSession.add(self.job.data_container)
                nims_montage = nimsdata.nimsmontage.generate_montage(conv_file)
                nims_montage.write_sqlite_pyramid(os.path.join(self.nims_path, pyramid_ds.relpath, self.job.data_container.name+'.pyrdb'))
                self.job.activity = u'image pyramid generated'
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                pyramid_ds.kind = u'web'
                pyramid_ds.container = self.job.data_container
                pyramid_ds.filenames = os.listdir(os.path.join(self.nims_path, pyramid_ds.relpath))
                transaction.commit()

            if conv_type == 'bitmap':
                # Hack to make sure screen-saves go to the end of the time-sorted list
                DBSession.add(self.job)
                DBSession.add(self.job.data_container)
                self.job.data_container.timestamp = datetime.datetime.combine(date=self.job.data_container.timestamp.date(), time=datetime.time(23,59, 59))
                transaction.commit()

        DBSession.add(self.job)


class PFilePipeline(Pipeline):

    def find(self):
        return super(PFilePipeline, self).find()

    def process(self):
        super(PFilePipeline, self).process()

        ds = self.job.data_container.primary_dataset
        with nimsutil.TempDir(dir=self.tempdir) as outputdir:
            pf = None
            pfiles = [f for f in os.listdir(os.path.join(self.nims_path, ds.relpath)) if not f.startswith('_') and 'refscan' not in f]
            # Try them in numerical order.
            # FIXME: if there are >1 pfiles, what to do? Try them all?
            for pfile in sorted(pfiles):
                try:
                    pf = nimsdata.nimsraw.NIMSPFile(os.path.join(self.nims_path, ds.relpath, pfile))
                except nimsdata.nimsraw.NIMSPFileError:
                    pf = None
                else:
                    break

            if pf is not None:
                criteria = pf.prep_convert()
                if criteria != None:
                    q = Epoch.query.filter(Epoch.session==self.job.data_container.session).filter(Epoch.trashtime == None)
                    for fieldname,value in criteria.iteritems():
                        q = q.filter(getattr(Epoch,fieldname)==unicode(value))
                    epochs = [e for e in q.all() if e!=self.job.data_container]
                    aux_files = [os.path.join(self.nims_path, e.primary_dataset.relpath, f) for e in epochs for f in e.primary_dataset.filenames if f.startswith('P')]
                    self.job.activity = (u'Found %d aux files: %s' % (len(aux_files), (', '.join([os.path.basename(f) for f in aux_files]))))[:255]
                    log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                else:
                    aux_files = None

                conv_type, conv_file = pf.convert(os.path.join(outputdir, ds.container.name), self.tempdir, self.max_recon_jobs, aux_files)

            if conv_file:
                outputdir_list = os.listdir(outputdir)
                self.job.activity = (u'generated %s' % (', '.join([f for f in outputdir_list])))[:255]
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                dataset = Dataset.at_path(self.nims_path, u'nifti')
                DBSession.add(self.job)
                DBSession.add(self.job.data_container)
                dataset.kind = u'derived'
                dataset.container = self.job.data_container
                filenames = []
                for f in outputdir_list:
                    filenames.append(f)
                    shutil.copy2(os.path.join(outputdir, f), os.path.join(self.nims_path, dataset.relpath))
                dataset.filenames = filenames
                transaction.commit()

                pyramid_ds = Dataset.at_path(self.nims_path, u'img_pyr')
                DBSession.add(self.job)
                DBSession.add(self.job.data_container)
                nims_montage = nimsdata.nimsmontage.generate_montage(conv_file)
                nims_montage.write_sqlite_pyramid(os.path.join(self.nims_path, pyramid_ds.relpath, self.job.data_container.name+'.pyrdb'))
                self.job.activity = u'image pyramid generated'
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                pyramid_ds.kind = u'web'
                pyramid_ds.container = self.job.data_container
                pyramid_ds.filenames = os.listdir(os.path.join(self.nims_path, pyramid_ds.relpath))
                transaction.commit()

        DBSession.add(self.job)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', metavar='URI', help='database URI')
        self.add_argument('nims_path', metavar='DATA_PATH', help='data location')
        self.add_argument('physio_path', metavar='PHYSIO_PATH', help='path to physio data')
        self.add_argument('-T', '--task', help='find|proc  (default is all)')
        self.add_argument('-e', '--filter', default=[], action='append', help='sqlalchemy filter expression')
        self.add_argument('-j', '--jobs', type=int, default=1, help='maximum number of concurrent threads')
        self.add_argument('-k', '--reconjobs', type=int, default=8, help='maximum number of concurrent recon jobs')
        self.add_argument('-r', '--reset', action='store_true', help='reset currently active (crashed) jobs')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep between db queries')
        self.add_argument('-t', '--tempdir', help='directory to use for temporary files')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='log level (default: info)')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')
        self.add_argument('-n', '--newest', action='store_true', default=False, help='do newest jobs first')


if __name__ == '__main__':
    # workaround for http://bugs.python.org/issue7980
    import datetime # used in nimsutil
    datetime.datetime.strptime('0', '%S')

    args = ArgumentParser().parse_args()
    nimsutil.configure_log(args.logfile, not args.quiet, args.loglevel)
    processor = Processor(args.db_uri, args.nims_path, args.physio_path, args.task, args.filter, args.jobs, args.reconjobs, args.reset, args.sleeptime, args.tempdir, args.newest)

    def term_handler(signum, stack):
        processor.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    processor.run()
    log.warning('Process halted')
