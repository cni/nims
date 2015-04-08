#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

import os
import abc
import glob
import time
import shutil
import signal
import logging
import tarfile
import argparse
import datetime
import threading
import numpy as np

import sqlalchemy
import transaction

import nimsutil
import nimsdata
import nimsdata.medimg.nimsdicom
import nimsdata.medimg.nimspfile
import nimsphysio

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
                        if ds.filetype == nimsdata.medimg.nimsdicom.NIMSDicom.filetype:
                            pipeline_class = DicomPipeline
                        elif ds.filetype == nimsdata.medimg.nimspfile.NIMSPFile.filetype:
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
        self.job.activity = u'started %s' % self.job.data_container.primary_dataset.filetype
        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()
        DBSession.add(self.job)
        try:
            if self.job.task == u'find&proc':
                self.process()  # process now includes find.
        except Exception as ex:
            self.job.status = u'failed'
            self.job.activity = (u'failed: %s' % ex)[:255]
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
    def find(self, slice_order, num_slices):
        """
        Locate physio and generate physio regressors.

        Find is called from within each pipeline's process() method after the file's slice_order
        and num_slices attributes have been set, but before preparing the data to be written out.
        This will use the num_slice and slice_order to create an array of the slice numbers in the
        sequence they were acquired. Nimsphysio will use both the current data containers metadata,
        like timestamp and duration, and metadata obtained by parsing the primary dataset file to
        determine if physio is valid.

        This method should never raise any exceptions.

        Parameters
        ----------
        slice_order : int
            integer that corresponds to the appropriate NIFTI slice order code. 0 for unknown.
        num_slices : int
            number of slices

        """
        self.clean(self.job.data_container, u'peripheral')
        transaction.commit()
        DBSession.add(self.job)

        if self.physio_path is None: return             # can't search w/o phys path
        if not slice_order or not num_slices: return    # need both slice order AND num_slices to create regressors
        if self.job.data_container.scanner_name == 'IRC MRC35068': return   # hack to ignore Davis files

        dc = self.job.data_container
        if dc.physio_recorded:
            # 2015.02.03 RFD: apparently the old rule was incorrect. The physio files are not timestamped
            # sometime after the Rxed duration, but rather sometime after the actual duration! We don't yet
            # know the actual duration, so we'll just make shit up and hope for the best.
            physio_lag = datetime.timedelta(seconds=30)
            physio_files = nimsutil.find_ge_physio(self.physio_path, dc.timestamp+physio_lag, dc.psd.encode('utf-8'))
            #physio_files = nimsutil.find_ge_physio(self.physio_path, dc.timestamp+dc.prescribed_duration, dc.psd.encode('utf-8'))
            if physio_files:
                physio = nimsphysio.NIMSPhysio(physio_files, dc.tr, dc.num_timepoints, nimsdata.medimg.medimg.get_slice_order(slice_order, num_slices))
                if physio.is_valid():
                    self.job.activity = u'valid physio found (%s...)' % os.path.basename(physio_files[0])
                    log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
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
                            self.job.activity = u'physio regressors %s written' % reg_filename
                            log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                        except nimsphysio.NIMSPhysioError:
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
        self.job.activity = u'reading data / preparing to run recon'
        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()
        DBSession.add(self.job)


class DicomPipeline(Pipeline):

    def find(self, slice_order, num_slices):
        return super(DicomPipeline, self).find(slice_order, num_slices)

    def process(self):
        """"
        Convert a dicom file.

        Parse a dicom file and load the data. If an error occurs during parsing, no exception gets raised,
        instead the exception is saved into dataset.failure_reason.  This is to allow find() to attempt to
        locate physio, even if the input dicom files could not be loaded.  After the locating physio has been
        attempted, the DicomPipeline will attempt to convert the dataset into various output files.

        Parameters
        ---------
        None : NoneType
            The DicomPipeline works has a job and dataset assigned to it.  No additional parameters are required.

        """
        super(DicomPipeline, self).process()

        ds = self.job.data_container.primary_dataset
        with nimsutil.TempDir(dir=self.tempdir) as outputdir:
            outbase = os.path.join(outputdir, ds.container.name)
            dcm_tgz = os.path.join(self.nims_path, ds.relpath, os.listdir(os.path.join(self.nims_path, ds.relpath))[0])
            dcm_acq = nimsdata.parse(dcm_tgz, filetype='dicom', load_data=True, ignore_json=True)   # store exception for later...

            # if physio was not found, wait 30 seconds and search again.
            # this should only run when the job activity is u'no physio files found'
            # if physio not recorded, or physio invalid, don't try again
            try:
                self.find(dcm_acq.slice_order, dcm_acq.num_slices)
            except Exception as e:
                # this catches some of the non-image scans that do not have
                # dcm_acq.slice_order and/or dcm_acq.num_slices
                log.info(str(e))  # do we need this logging message?
            if self.job.activity == u'no physio files found':
                self.job.activity = u'no physio files found; searching again in 30 seconds'
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                time.sleep(30)
                try:
                    self.find(dcm_acq.slice_order, dcm_acq.num_slices)
                except Exception as e:
                    # this catches some of the non-image scans that do not have
                    # dcm_acq.slice_order and/or dcm_acq.num_slices
                    log.info(str(e))  # do we need this logging message?

            if dcm_acq.failure_reason:   # implies dcm_acq.data = None
                # if dcm_acq.failure_reason is set, job has failed
                # raising an error should cause job.status should to end up 'failed'
                self.job.activity = (u'load dicom data failed; %s' % str(dcm_acq.failure_reason))
                transaction.commit()
                DBSession.add(self.job)
                raise dcm_acq.failure_reason

            if dcm_acq.is_non_image:    # implies dcm_acq.data = None
                # non-image is an "expected" outcome, job has succeeded
                # no error should be raised, job status should end up 'done'
                self.job.activity = (u'dicom %s is a non-image type' % dcm_tgz)
                transaction.commit()
            else:
                if dcm_acq.is_screenshot:
                    conv_files = nimsdata.write(dcm_acq, dcm_acq.data, outbase, filetype='png')
                    if conv_files:
                        outputdir_list = os.listdir(outputdir)
                        self.job.activity = (u'generated %s' % (', '.join([f for f in outputdir_list])))[:255]
                        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                        conv_ds = Dataset.at_path(self.nims_path, u'bitmap')
                        DBSession.add(self.job)
                        DBSession.add(self.job.data_container)
                        conv_ds.kind = u'derived'
                        conv_ds.container = self.job.data_container
                        conv_ds.container.size = dcm_acq.size
                        conv_ds.container.mm_per_vox = dcm_acq.mm_per_vox
                        conv_ds.container.num_slices = dcm_acq.num_slices
                        conv_ds.container.num_timepoints = dcm_acq.num_timepoints
                        conv_ds.container.duration = dcm_acq.duration
                        filenames = []
                        for f in outputdir_list:
                            filenames.append(f)
                            shutil.copy2(os.path.join(outputdir, f), os.path.join(self.nims_path, conv_ds.relpath))
                        conv_ds.filenames = filenames
                        transaction.commit()
                else:
                    conv_files = nimsdata.write(dcm_acq, dcm_acq.data, outbase, filetype='nifti')
                    if conv_files:
                        # if nifti was successfully created
                        outputdir_list = os.listdir(outputdir)
                        self.job.activity = (u'generated %s' % (', '.join([f for f in outputdir_list])))[:255]
                        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                        conv_ds = Dataset.at_path(self.nims_path, u'nifti')
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
                        pyramid_ds = Dataset.at_path(self.nims_path, u'img_pyr')
                        DBSession.add(self.job)
                        DBSession.add(self.job.data_container)
                        outpath = os.path.join(self.nims_path, pyramid_ds.relpath, self.job.data_container.name)
                        voxel_order = None if dcm_acq.is_localizer else 'LPS'
                        nims_montage = nimsdata.write(dcm_acq, dcm_acq.data, outpath, filetype='montage', voxel_order=voxel_order)
                        self.job.activity = (u'generated %s' % (', '.join([os.path.basename(f) for f in nims_montage])))[:255]
                        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                        pyramid_ds.kind = u'web'
                        pyramid_ds.container = self.job.data_container
                        pyramid_ds.filenames = os.listdir(os.path.join(self.nims_path, pyramid_ds.relpath))
                        transaction.commit()

            DBSession.add(self.job)

        DBSession.add(self.job)


class PFilePipeline(Pipeline):

    def find(self, slice_order, num_slices):
        return super(PFilePipeline, self).find(slice_order, num_slices)

    def process(self):
        """"
        Convert a pfile.

        Extracts a pfile.tgz into a temporary directory and full_parses the pfile.7.  If an error occurs
        during parsing, no exception gets raised, instead the exception is saved into dataset.failure_reason.
        This is to allow find() to attempt to locate physio, even if the input pfile not be loaded.  After
        locating physio has been attempted, the PFilePipeline will attempt to convert the dataset into

        a nifti, and then a montage.

        Parameters
        ---------
        None : NoneType
            The PFilePipeline works has a job and dataset assigned to it.  No additional parameters are required.

        """
        super(PFilePipeline, self).process()

        ds = self.job.data_container.primary_dataset

        with nimsutil.TempDir(dir=self.tempdir) as outputdir:
            log.debug('parsing')
            outbase = os.path.join(outputdir, ds.container.name)
            pfile_tgz = glob.glob(os.path.join(self.nims_path, ds.relpath, '*_pfile.tgz'))
            pfile_7gz = glob.glob(os.path.join(self.nims_path, ds.relpath, 'P?????.7*'))
            if pfile_tgz:
                log.debug('input format: tgz')
                with tarfile.open(pfile_tgz[0]) as archive:
                    archive.extractall(path=outputdir)
                temp_datadir = os.path.join(outputdir, os.listdir(outputdir)[0])
                input_pfile = os.path.join(temp_datadir, glob.glob(os.path.join(temp_datadir, 'P?????.7'))[0])
            elif pfile_7gz:
                log.debug('input format: directory')
                input_pfile = pfile_7gz[0]
            else:
                log.warning('no pfile input found in %s' % os.path.join(self.nims_path, ds.relpath))
                raise Exception('no pfile input found in %s' % os.path.join(self.nims_path, ds.relpath))

            # perform full parse, which doesn't attempt to load the data
            pf = nimsdata.parse(input_pfile, filetype='pfile', ignore_json=True, load_data=False, full_parse=True, tempdir=outputdir, num_jobs=self.max_recon_jobs)

            try:
                self.find(pf.slice_order, pf.num_slices)
            except Exception as exc:  # XXX, specific exceptions
                pass

            # MUX HACK, identify a group of aux candidates and determine the single best aux_file.
            # Certain mux_epi scans will return a dictionary of parameters to use as query filters to
            # help locate an aux_file that contains necessary calibration scans.
            criteria = pf.prep_convert()
            aux_file = None
            if criteria is not None:  # if criteria: this is definitely mux of some sort
                log.debug('pfile aux criteria %s' % str(criteria.keys()))
                q = Epoch.query.filter(Epoch.session==self.job.data_container.session).filter(Epoch.trashtime==None)
                for fieldname, value in criteria.iteritems():
                    q = q.filter(getattr(Epoch, fieldname)==unicode(value))  # filter by psd_name

                if pf.num_mux_cal_cycle >= 2:
                    log.debug('looking for num_bands = 1')
                    epochs = [e for e in q.all() if (e != self.job.data_container and e.num_bands == 1)]
                else:
                    log.debug('looking for num_mux_cal_cycle >= 2')
                    epochs = [e for e in q.all() if (e != self.job.data_container and e.num_mux_cal_cycle >= 2)]
                log.debug('candidates: %s' % str([e.primary_dataset.filenames for e in epochs]))

                # which epoch has the closest series number
                series_num_diff = np.array([e.series for e in epochs]) - pf.series_no
                closest = np.min(np.abs(series_num_diff))==np.abs(series_num_diff)
                # there may be more than one. We prefer the prior scan.
                closest = np.where(np.min(series_num_diff[closest])==series_num_diff)[0][0]
                candidate = epochs[closest]
                # auxfile could be either P7.gz with adjacent files or a pfile tgz
                aux_tgz = glob.glob(os.path.join(self.nims_path, candidate.primary_dataset.relpath, '*_pfile.tgz'))
                aux_7gz = glob.glob(os.path.join(self.nims_path, candidate.primary_dataset.relpath, 'P?????.7*'))
                if aux_tgz:
                    aux_file = aux_tgz[0]
                elif aux_7gz:
                    aux_file = aux_7gz[0]
                # aux_file = os.path.join(self.nims_path, candidate.primary_dataset.relpath, candidate.primary_dataset.filenames[0])
                log.debug('identified aux_file: %s' % os.path.basename(aux_file))

                self.job.activity = (u'Found aux file: %s' % os.path.basename(aux_file))[:255]
                log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))

            else:
                log.debug('no special criteria')
                aux_file = None

            pf.load_data(aux_file=aux_file)  # don't monopolize system resources
            if pf.failure_reason:   # implies pf.data = None
                self.job.activity = (u'error loading pfile: %s' % str(pf.failure_reason))
                transaction.commit()
                DBSession.add(self.job)
                raise pf.failure_reason

            # attempt to write nifti, if write fails, let exception bubble up to pipeline process()
            # exception will cause job to be marked as 'fail'
            if pf.is_non_image:    # implies dcm_acq.data = None
                # non-image is an "expected" outcome, job has succeeded
                # no error should be raised, job status should end up 'done'
                self.job.activity = (u'pfile %s is a non-image type' % input_pfile)
                transaction.commit()
            else:
                conv_file = nimsdata.write(pf, pf.data, outbase, filetype='nifti')
                if conv_file:
                    outputdir_list = [f for f in os.listdir(outputdir) if not os.path.isdir(os.path.join(outputdir, f))]
                    self.job.activity = (u'generated %s' % (', '.join([f for f in outputdir_list])))[:255]
                    log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                    dataset = Dataset.at_path(self.nims_path, u'nifti')
                    DBSession.add(self.job)
                    DBSession.add(self.job.data_container)
                    dataset.kind = u'derived'
                    dataset.container = self.job.data_container
                    dataset.container.size = pf.size
                    dataset.container.mm_per_vox = pf.mm_per_vox
                    dataset.container.num_slices = pf.num_slices
                    dataset.container.num_timepoints = pf.num_timepoints
                    dataset.container.duration = datetime.timedelta(seconds=pf.duration)
                    filenames = []
                    for f in outputdir_list:
                        filenames.append(f)
                        shutil.copy2(os.path.join(outputdir, f), os.path.join(self.nims_path, dataset.relpath))
                    dataset.filenames = filenames
                    transaction.commit()

                    pyramid_ds = Dataset.at_path(self.nims_path, u'img_pyr')
                    DBSession.add(self.job)
                    DBSession.add(self.job.data_container)
                    outpath = os.path.join(self.nims_path, pyramid_ds.relpath, self.job.data_container.name)
                    nims_montage = nimsdata.write(pf, pf.data, outpath, filetype='montage')
                    self.job.activity = u'generated image pyramid %s' % nims_montage
                    log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                    pyramid_ds.kind = u'web'
                    pyramid_ds.container = self.job.data_container
                    pyramid_ds.filenames = os.listdir(os.path.join(self.nims_path, pyramid_ds.relpath))
                    transaction.commit()

            DBSession.add(self.job)

        DBSession.add(self.job)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', metavar='URI', help='database URI')
        self.add_argument('nims_path', metavar='DATA_PATH', help='data location')
        self.add_argument('physio_path', metavar='PHYSIO_PATH', nargs='?', help='path to physio data')
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

