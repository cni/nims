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
import tempfile
import re

import sqlalchemy
import transaction

import numpy as np
import nimsutil
import nimsdata
import nibabel
from nimsdata import nimspng, nimsimage, nimsnifti, nimsdicom
from nibabel.nicom import dicomreaders
from nimsgears.model import *
from dcmstack.dcmmeta import NiftiWrapper

log = logging.getLogger('processor')


class Processor(object):

    def __init__(self, db_uri, nims_path, physio_path, task, filters, max_jobs, max_recon_jobs, reset, sleeptime, tempdir):
        super(Processor, self).__init__()
        self.nims_path = nims_path
        self.physio_path = physio_path
        self.task = unicode(task) if task else None
        self.filters = filters
        self.max_jobs = max_jobs
        self.max_recon_jobs = max_recon_jobs
        self.sleeptime = sleeptime
        self.tempdir = tempdir

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
                job = query.filter(Job.status==u'pending').order_by(Job.id).with_lockmode('update').first()

                if job:
                    if isinstance(job.data_container, Epoch):
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
        conv_type = None

        try:
            if self.job.task == u'find&proc':
                self.find()
                conv_type = self.process()
            elif self.job.task == u'find':
                self.find()
            elif self.job.task == u'proc':
                conv_type = self.process()
        except Exception as ex:
             self.job.status = u'failed'
             self.job.activity = u'failed: %s' % ex
             log.warning(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        else:
            self.job.activity = u'done'
            if conv_type == 'nifti' and self.is_qmr_job():
                self.job.status = u'qmr-pending'
            else:
                self.job.status = u'done'

            log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
        transaction.commit()

    def clean(self, data_container, kind):
        for ds in Dataset.query.filter_by(container=data_container).filter_by(kind=kind).all():
            shutil.rmtree(os.path.join(self.nims_path, ds.relpath))
            ds.delete()

    def is_qmr_job(self):
        experiment_name = self.job.data_container.session.experiment.name
        return 'qmr' in experiment_name

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

            if not dcm_acq.image_type:
                log.warning('dicom conversion failed for %s: ImageType not set in dicom header' % os.path.basename(outbase))
                return

            if dcm_acq.image_type == nimsdicom.TYPE_SCREEN:
                conv_type, conv_file = self.convert_screen(dcm_acq, outbase)
            elif not 'PRIMARY' in dcm_acq.image_type:
                # Ignore non-primary epochs
                conv_type, conv_file = None, None
            elif 'SIEMENS' in dcm_acq.scanner_type:
                conv_type, conv_file = self.convert_siemens(dcm_acq, outbase)
            else:
                conv_type, conv_file = self.convert_primary_default(dcm_acq, outbase)

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
            else:
                log.warning('dicom conversion failed for %s: no applicable conversion defined' % os.path.basename(outbase))

            print 'conv_file:', conv_file


            if conv_type == 'nifti':
                if type(conv_file) is str:
                    conv_file = [conv_file]

                for file in conv_file:
                    try:
                        pyramid_ds = Dataset.at_path(self.nims_path, u'img_pyr')
                        DBSession.add(self.job)
                        DBSession.add(self.job.data_container)
                        nims_montage = nimsdata.nimsmontage.generate_montage(file)
                        print 'nims_montage', nims_montage
                        nims_montage.write_sqlite_pyramid(os.path.join(self.nims_path, pyramid_ds.relpath, self.job.data_container.name+'.pyrdb'))
                        self.job.activity = u'image pyramid generated'
                        log.info(u'%d %s %s' % (self.job.id, self.job, self.job.activity))
                        pyramid_ds.kind = u'web'
                        pyramid_ds.container = self.job.data_container
                        pyramid_ds.filenames = os.listdir(os.path.join(self.nims_path, pyramid_ds.relpath))
                        transaction.commit()
                    except Exception as e:
                        log.warn('Error creating montage file. %s' % e)


            DBSession.add(self.job)
            return conv_type

    def convert_screen(self, dcm_acq, outbase):
        self.load_dicoms()
        for i, dcm in enumerate(self.dcm_list):
            result = ('bitmap', nimspng.NIMSPNG.write(dcm_acq, dcm.pixel_array, outbase + '_%d' % (i+1)))
        return result


    def convert_primary_default(self, dcm_acq, outbase):
        imagedata = dcm_acq.get_imagedata()
        return ('nifti', nimsnifti.NIMSNifti.write(dcm_acq, imagedata, outbase, dcm_acq.notes))

    def convert_siemens(self, dcm_acq, outbase):
        # Extract tgz file into a temporary directory
        tmpdir = tempfile.mkdtemp()
        tar = tarfile.open(dcm_acq.filepath)
        tar.extractall(tmpdir)
        dcm_files_path = os.path.join(tmpdir, dcm_acq.filepath.split('/')[-1].rsplit('.', 1)[0])

        niftis = []
        is_current_nifti_multicoil = False

        if 'MOSAIC' in dcm_acq.image_type:
            imagedata, dcm_acq.qto_xyz, dcm_acq.bvals, dcm_acq.bvecs = dicomreaders.read_mosaic_dir(dcm_files_path)
            niftis.append(nimsnifti.NIMSNifti.write(dcm_acq, imagedata, outbase, dcm_acq.notes))
        else:
            if re.match('H[0-3]?[0-9]', dcm_acq.coil_string):
                print '--- Multichannel process nifti'
                is_current_nifti_multicoil = True
                time_order = 'CoilString'
                niftis.append(nimsnifti.NIMSNifti.write_siemens(time_order, dcm_acq, dcm_files_path, outbase, dcm_acq.notes ))
            else:
                print '---Normal siemens nifti'
                time_order = None
                niftis.append(nimsnifti.NIMSNifti.write_siemens(time_order, dcm_acq, dcm_files_path, outbase, dcm_acq.notes ))

        # Try to find the paired multi-coil combined dataset (if any)
        print 'Acquisition time:', dcm_acq.acquisition_time
        dataset = Dataset.from_mrfile(dcm_acq, None)
        print 'Id:', dataset.id, 'DatacontainerId', dataset.container_id
        pair_ds = Dataset.query.filter(Dataset.acquisition_time == dcm_acq.acquisition_time, Dataset.id != dataset.id).first()
        if not pair_ds:
            log.debug("Multi-coil combined dataset not found")
        else:
            log.info('Found multi-coil combined dataset: %d datacontainer_id: %d' % (pair_ds.id, pair_ds.container_id) )

            nifti_combined = niftis[0]
            print 'nifti_combined: ', nifti_combined

            #Multicoil
            nifti_multicoil = Dataset.query.filter(Dataset.container_id == pair_ds.container_id, Dataset.filetype == 'nifti').first()
            if not nifti_multicoil:
                log.info('Multi-coil combined dataset does not have a nifti yet. dataset:%d datacontainer_id: %d' % (pair_ds.id, pair_ds.container_id) )
            else:
                filename2 = nifti_multicoil.filenames[0]

                nifti_multicoil_in_db = os.path.join(self.nims_path, nifti_multicoil.relpath,filename2)

                log.info('Generating combined nifti from %s --- %s' % (nifti_combined, nifti_multicoil_in_db) )

                #Use dcmstack to get a wrapper of NIfTI
                nw_combined = NiftiWrapper.from_filename(nifti_combined)
                nw_multicoil = NiftiWrapper.from_filename(nifti_multicoil_in_db)

                if is_current_nifti_multicoil:
                    # Swap the 2 niftis so that we merge them always in the same order
                    nw_combined, nw_multicoil = nw_multicoil, nw_combined

                #Get data from wrapper
                matrix_combined = nw_combined.nii_img.get_data()
                matrix_multicoil = nw_multicoil.nii_img.get_data()

                #Get a numpy matrix to merge both
                matrix_combined_np = np.array(matrix_combined)
                matrix_multicoil_np = np.array(matrix_multicoil)

                #Add one dimension to combined data to be able to concatenate
                matrix_combined_extended_dim = matrix_combined_np[...,None]

                merged = np.concatenate((matrix_multicoil_np, matrix_combined_extended_dim), axis=3)

                # Build a new Nifti using Nibabel
                nibabel_nifti = nibabel.load(nifti_multicoil_in_db)
                nibabel_header_multicoil = nibabel_nifti.get_header()
                nibabel_affine_multicoil = nibabel_nifti.get_affine()
                built_merged_nifti = nibabel.Nifti1Image(np.array(merged), nibabel_affine_multicoil, nibabel_header_multicoil)

                print 'outbase: ', outbase
                filepath = outbase + '_merged.nii.gz'

                #Save the niftis into the DB
                nibabel.save(built_merged_nifti, filepath)
                niftis.append(filepath)

                #Change the description of the epoch in which the 'combined' is located
                combined_ds = Dataset.query.filter(Dataset.id == dataset.id).first()
                epoch_object = Epoch.query.filter(Epoch.datacontainer_id == combined_ds.container_id).first()
                if not epoch_object.description.endswith(' [merged]'):
                    epoch_object.description += ' [merged]'


        shutil.rmtree(tmpdir)
        print 'niftis: ', niftis
        return ('nifti', niftis)

class PFilePipeline(Pipeline):

    def find(self):
        return super(PFilePipeline, self).find()

    def process(self):
        super(PFilePipeline, self).process()

        ds = self.job.data_container.primary_dataset
        with nimsutil.TempDir(dir=self.tempdir) as outputdir:
            pf = None
            for pfile in os.listdir(os.path.join(self.nims_path, ds.relpath)):
                if not pfile.startswith('_') and 'refscan' not in pfile:
                    try:
                        pf = nimsdata.nimsraw.NIMSPFile(os.path.join(self.nims_path, ds.relpath, pfile))
                    except nimsdata.nimsraw.NIMSPFileError:
                        pf = None
                    else:
                        break

            if pf is not None:
                criteria = pf.prep_convert()
                if criteria != None:
                    q = Epoch.query.filter(Epoch.session==self.job.data_container.session)
                    for fieldname,value in criteria.iteritems():
                        q = q.filter(getattr(Epoch,fieldname)==unicode(value))
                    epochs = q.all()
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


if __name__ == '__main__':
    # workaround for http://bugs.python.org/issue7980
    import datetime # used in nimsutil
    datetime.datetime.strptime('0', '%S')

    args = ArgumentParser().parse_args()
    nimsutil.configure_log(args.logfile, not args.quiet, args.loglevel)
    processor = Processor(args.db_uri, args.nims_path, args.physio_path, args.task, args.filter, args.jobs, args.reconjobs, args.reset, args.sleeptime, args.tempdir)

    def term_handler(signum, stack):
        processor.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    processor.run()
    log.warning('Process halted')
