#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import signal

import numpy as np

import dicom
import nibabel

import png
import nimsutil
import processor
from nimsgears import model

# FIXME: add kwargs to process()
data_path = '/tmp/gating'

PHYSIO_EXT = '.physio'

class PhysioFinder(processor.Worker):

    taskname = u'find_physio'
    res_type = model.MRIPhysioData

    @property
    def result_datatype(self):
        return self.res_type

    def process(self, nifti_filename, output_basepath, **kwargs):
        print kwargs
        #candidates = self._find_physio_with_datetime(data_path, self.timestamp)
        #candidates += self._find_physio_with_datetime(data_path, self.timestamp + DAY_TIMEDELTA)
        #datetime_strings = [RE_DATETIME_STR.match(fn).groupdict()['datetime'] for fn in candidates]
        #datetimes = [datetime.datetime.strptime(dts, '%m%d%Y%H_%M_%S_%f') for dts in datetime_strings]
        #physio_dict = {}
        #for physio_datetime, physio_filename in zip(datetimes, candidates):
        #    physio_dict.setdefault(physio_datetime, []).append(physio_filename)
        #valid_keys = filter(lambda physio_datetime: physio_datetime >= self.timestamp, physio_dict)
        #physio_files = physio_dict[min(valid_keys)] if valid_keys else []

        #outfile_path = output_basepath + PHYSIO_EXT
        #os.makedir(outfile_path)
        #if physio_files:
        #    self.log.info('Physio found %s' % self)
        #    for pf in physio_files:
        #        shutil.copy2(pf, outfile_path)
        #else:
        #    self.log.info('Physio NOT found %s' % self)
        #    # TODO: create file with name 'no physio data found'

        return (self.result_dataset(), [])
        return (self.result_dataset(), outfile_path)

    def _find_physio_with_datetime(self, data_path, datetime_):
        return glob.glob(os.path.join(data_path, '*_%s_%s*' % (self.psd_name, datetime_.strftime('%m%d%Y'))))


if __name__ == "__main__":
    arg_parser = processor.ArgumentParser()
    arg_parser.add_argument('physio_path', help='path to physio data')
    args = arg_parser.parse_args()
    #args = processor.ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)

    proc = processor.Processor(args.db_uri, args.nims_path, PhysioFinder, log, args.sleeptime, physio_path=args.physio_path)

    def term_handler(signum, stack):
        proc.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    proc.run()
    log.warning('Process halted')
