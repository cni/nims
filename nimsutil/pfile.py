#!/usr/bin/env python

import os
import shlex
import argparse
import subprocess as sp

import numpy as np
import nibabel

import nimsutil
import pfheader


class Pfile:
    """
    Read pfile data and/or header.

    This class reads the data and/or header from a pfile, runs k-space reconstruction,
    and generates a NIfTI object, including header information.

    Example:
        from nimsutil import pfile
        pf = pfile.Pfile(pfilename='P56832.7')
        pf.to_nii(outbase='P56832.7')
    """

    def __init__(self, pfilename, log):
        self.pfilename = pfilename
        self.log = log
        self.load_header()
        self.image_data = None
        self.fm_data = None

    def load_header(self):
        self.header = pfheader.get_header(self.pfilename)
        # Pull out some common fields for convenience
        # *** CHECK THAT THESE ARE THE RIGHT FIELDS (ATSUSHI?)
        self.num_slices = self.header.rec.nslices
        self.num_receivers = self.header.rec.dab[0].stop_rcv - self.header.rec.dab[0].start_rcv + 1
        # You might think this is stored in self.header.rec.nframes, but for our spiral it's here:
        self.num_timepoints = int(self.header.rec.user0)
        self.num_echoes = self.header.rec.nechoes
        self.size_x = self.header.image.imatrix_X
        self.size_y = self.header.image.imatrix_Y
        self.deltaTE = self.header.rec.user15

    def to_nii(self, outbase, spirec='spirec', saveInOut=False):
        """Create NIfTI file from pfile."""
        if self.image_data is None:
            self.recon(spirec)

        mm_per_vox = np.array([self.header.image.pixsize_X,
                               self.header.image.pixsize_Y,
                               self.header.image.slthick+self.header.image.scanspacing])

        image_tlhc = np.array([self.header.image.tlhc_R, self.header.image.tlhc_A, self.header.image.tlhc_S])
        image_trhc = np.array([self.header.image.trhc_R, self.header.image.trhc_A, self.header.image.trhc_S])
        image_brhc = np.array([self.header.image.brhc_R, self.header.image.brhc_A, self.header.image.brhc_S])
        #image_cent = np.array([self.header.image.ctr_R,  self.header.image.ctr_A,  self.header.image.ctr_S])

        row_vec = (image_trhc-image_tlhc)/np.sqrt(np.dot(image_trhc-image_tlhc, image_trhc-image_tlhc))
        col_vec = -(image_trhc-image_brhc)/np.sqrt(np.dot(image_trhc-image_brhc, image_trhc-image_brhc))
        # The DICOM standard defines these two unit vectors in an LPS coordinate frame, but we'll
        # need RAS (+x is right, +y is anterior, +z is superior) for NIFTI. So, we compute them
        # such that row_vec points to the right and col_vec points up.
        # Not sure if we need to negate the slice_norm. From the NIFTI-1 header:
        #     The third column of R will be either the cross-product of the first 2 columns or
        #     its negative. It is possible to infer the sign of the 3rd column by examining
        #     the coordinates in DICOM attribute (0020,0032) "Image Position (Patient)" for
        #     successive slices. However, this method occasionally fails for reasons that I
        #     (RW Cox) do not understand.

        # can also get slice_norm from: slice_norm = np.cross(row_vec, col_vec)
        slice_norm = np.array([self.header.image.norm_R, self.header.image.norm_A, self.header.image.norm_S])
        slice_fov = np.abs(self.header.series.start_loc - self.header.series.end_loc)

        # This is either the first slice tlhc (image_tlhc) or the last slice tlhc. How to decide?
        # And is it related to wheather I have to negate the slice_norm?
        # Tuned this empirically by comparing spiral and EPI data with the sam Rx.
        # Everything seems reasonable, except the test for axial orientation (start_ras==S|I).
        # I have no idea why I need that! But the flipping only seems necessary for axials, not
        # coronals or the few obliques I've tested.
        # FIXME: haven't tested sagittals!
        if (self.header.series.start_ras=='S' or self.header.series.start_ras=='I') and self.header.series.start_loc > self.header.series.end_loc:
            pos = image_tlhc - slice_norm*slice_fov
            # FIXME: since we are reversing the slice order here, should we change the slice_order field below?
            self.image_data = self.image_data[:,:,-1:0:-1,]
            self.fm_data    = self.fm_data[:,:,-1:0:-1,]
        else:
            pos = image_tlhc

        qto_xyz = np.zeros((4,4))
        qto_xyz[0,0] = row_vec[0]
        qto_xyz[0,1] = col_vec[0]
        qto_xyz[0,2] = slice_norm[0]

        qto_xyz[1,0] = row_vec[1]
        qto_xyz[1,1] = col_vec[1]
        qto_xyz[1,2] = slice_norm[1]

        qto_xyz[2,0] = row_vec[2]
        qto_xyz[2,1] = col_vec[2]
        qto_xyz[2,2] = slice_norm[2]

        qto_xyz[:,3] = np.append(pos, 1).T
        qto_xyz[0:3,0:3] = np.dot(qto_xyz[0:3,0:3], np.diag(mm_per_vox))

        slices_per_volume = self.image_data.shape[2]
        num_volumes = self.image_data.shape[3]
        num_echoes = self.image_data.shape[4]

        nii_header = nibabel.Nifti1Header()
        nii_header.set_xyzt_units('mm', 'sec')
        nii_header.set_qform(qto_xyz, 'scanner')
        nii_header.set_sform(qto_xyz, 'scanner')

        nii_header['slice_start'] = 0
        nii_header['slice_end'] = slices_per_volume - 1
        # nifti slice order codes: 0 = unknown, 1 = sequential incrementing, 2 = seq. dec., 3 = alternating inc., 4 = alt. dec.
        slice_order = 0
        nii_header['slice_duration'] = self.header.image.tr / slices_per_volume / 1000
        # FIXME: check that this is correct.
        if   self.header.series.se_sortorder == 0:
            slice_order = 1  # or 2?
        elif self.header.series.se_sortorder == 1:
            slice_order = 3  # or 4?
        nii_header['slice_code'] = slice_order

        # Note: the freq/phase dir isn't meaningful for spiral trajectories.
        if self.header.image.freq_dir==1:
            nii_header.set_dim_info(freq=1, phase=0, slice=2)
        else:
            nii_header.set_dim_info(freq=0, phase=1, slice=2)

        # FIXME: There must be a cleaner way to set the TR! Maybe bug Matthew about it.
        nii_header.structarr['pixdim'][4] = self.header.image.tr/1e6
        nii_header.set_slice_duration(nii_header.structarr['pixdim'][4] / slices_per_volume)
        # We try to set the slope/intercept here, but nibabel will silently overwrite
        # anything we put here when the data are written out. (It thinks it's smarter
        # than us). Also, if we don't explicitly cast the data to int16, it sets these
        # to some crazy values rather than (1,0). Damn you Matthew! :)
        nii_header.set_slope_inter(1,0)
        nii_header.structarr['cal_max'] = 32767

        # scale and save as int16.
        nii_header.set_data_dtype(np.int16)
        dscale = 32767.0 / np.max(np.abs(self.image_data))
        if num_echoes == 1:
            nifti = nibabel.Nifti1Image(np.round(dscale*self.image_data).astype(np.int16), None, nii_header)
            nibabel.save(nifti, outbase + '.nii.gz')
        elif num_echoes == 2:
            if saveInOut:
                nifti = nibabel.Nifti1Image(np.round(dscale*self.image_data[:,:,:,:,0]).astype(np.int16), None, nii_header)
                nibabel.save(nifti, outbase + '_in.nii.gz')
                nifti = nibabel.Nifti1Image(np.round(dscale*self.image_data[:,:,:,:,1]).astype(np.int16), None, nii_header)
                nibabel.save(nifti, outbase + '_out.nii.gz')
            # FIXME: Do a more robust test for spiralio!
            # Assume spiralio, so do a weighted average of the two echos.
            # FIXME: should do a quick motion correction here
            w_in = np.mean(self.image_data[:,:,:,:,0], 3)
            w_out = np.mean(self.image_data[:,:,:,:,1], 3)
            inout_sum = w_in + w_out
            w_in = w_in / inout_sum
            w_out = w_out / inout_sum
            avg = np.zeros(self.image_data.shape[0:4])
            for tp in range(self.image_data.shape[3]):
                avg[:,:,:,tp] = w_in*self.image_data[:,:,:,tp,0] + w_out*self.image_data[:,:,:,tp,1]
            nifti = nibabel.Nifti1Image(np.round(avg/np.abs(avg).max()*32767.0).astype(np.int16), None, nii_header)
            nibabel.save(nifti, outbase + '.nii.gz')
            # w = out/(in+out)
        else:
            for echo in range(num_echoes):
                nifti = nibabel.Nifti1Image(np.round(dscale*self.image_data[:,:,:,:,echo]).astype(np.int16), None, nii_header)
                nibabel.save(nifti, outbase + '_echo%02d.nii.gz' % echo)

        nii_header.structarr['cal_max'] = np.ceil(self.fm_data.max() * 100.0)
        nii_header.structarr['cal_min'] = np.floor(self.fm_data.min() * 100.0)
        nifti = nibabel.Nifti1Image(np.round(self.fm_data * 100.0).astype(np.int16), None, nii_header)
        nibabel.save(nifti, outbase + '_B0.nii.gz')

    def load_fieldmap_files(self, basename, save_unified=True, data_type=np.float32):
        xyres = self.size_x
        if xyres != self.size_y:
            raise IndexError('non-square matrix: spiral recon requires a square matrix!')

        fm_freq = np.zeros([xyres,xyres,self.num_slices,self.num_echoes], dtype=data_type)
        fm_mask = np.zeros([xyres,xyres,self.num_slices,self.num_echoes], dtype=data_type)

        for echo in range(self.num_echoes):
            # loop over slices
            for cur_slice in range(self.num_slices):
                #print 'Combining field maps for slice %g, echo %g ....' % (cur_slice,echo)
                # Initialize arrays
                Sx   = np.zeros(xyres*xyres, dtype=data_type) # Sum of maps
                Sm   = np.zeros(xyres*xyres, dtype=data_type) # Sum of masks
                # Loop over receivers
                for recnum in range(self.num_receivers):
                    # build up file name
                    thisfilename = '%s.freq_%03d' % (basename,(recnum*self.num_slices+cur_slice)*self.num_echoes+echo)
                    with open(thisfilename ,'rb') as fp:
                        thisfile = np.fromfile(file = fp, dtype=data_type)
                    #os.remove(thisfilename)

                    thismaskname = '%s.mask_%03d' % (basename,(recnum*self.num_slices+cur_slice)*self.num_echoes+echo)
                    with open(thismaskname ,'rb') as fp:
                        thismask = np.fromfile(file = fp, dtype=data_type)
                    #os.remove(thismaskname)

                    Sx = Sx + thisfile*thismask
                    Sm = Sm + thismask

                fm_freq[:,:,cur_slice,echo] = (Sx/Sm).reshape(xyres,xyres) # take the mean
                fm_mask[:,:,cur_slice,echo] = Sm.reshape(xyres,xyres)

        if save_unified:
            # We always use the corresponding echo. Could change this to always use just one of the echoes.
            echo_to_use = range(self.num_echoes)
            for echo in range(self.num_echoes):
                for cur_slice in range(self.num_slices):
                    for recnum in range(self.num_receivers):
                        thisfilename = '%s.freq_%03d' % (basename,(recnum*self.num_slices+cur_slice)*self.num_echoes+echo)
                        with open(thisfilename ,'wb') as fp:
                            fm_freq[:,:,cur_slice,echo_to_use[echo]].tofile(file = fp)
                        thismaskname = '%s.mask_%03d' % (basename,(recnum*self.num_slices+cur_slice)*self.num_echoes+echo)
                        with open(thismaskname ,'wb') as fp:
                            np.sqrt(fm_mask[:,:,cur_slice,echo_to_use[echo]]).tofile(file = fp)

        return fm_freq, fm_mask

    def recon(self, spirec):
        """Do image reconstruction and populate self.image_data."""
        with nimsutil.TempDirectory() as tmp_dir:
            basename = 'recon'
            basepath = os.path.join(tmp_dir, basename)
            pfilename = os.path.abspath(self.pfilename)

            # run spirec once to get the fieldmap files (one for each coil and slice)
            cmd = spirec + ' -l --fmaponly --savefmap --rotate -90 -r ' + pfilename + ' -t ' + basename
            self.log.debug(cmd)
            sp.call(shlex.split(cmd), cwd=tmp_dir, stdout=open('/dev/null', 'w'))

            # combine the fieldmaps into one unified fieldmap
            [self.fm_data, fm_mask] = self.load_fieldmap_files(basepath, save_unified = True)

            # call spirec again, giving it our unified fieldmap, to produce an even better fieldmap
            cmd = spirec + ' -l --savetempfile --loadfmap --just 2 --rotate -90 -r ' + pfilename + ' -t ' + basename
            self.log.debug(cmd)
            sp.call(shlex.split(cmd), cwd=tmp_dir, stdout=open('/dev/null', 'w'))

            data_type = np.complex64
            #complex_image = np.zeros([size_x, size_y, num_slices, 2], dtype=data_type)
            fn = '%s.complex_float' % basepath
            # Why do we need 'F'ortran order for our reshape?!?!
            with open(fn, 'rb') as fp:
                complex_image = np.fromfile(file=fp, dtype=data_type).reshape([self.size_x,self.size_y,2,self.num_slices,self.num_receivers,self.num_echoes],order='F')
            sos_recdata2 = np.mean( np.conj(complex_image[:,:,0,:,:,:]) * complex_image[:,:,1,:,:,:], 3)
            self.fm_data = -np.angle(sos_recdata2[:,:,:,0])/(2*np.pi*(self.deltaTE/1e6))
            fm_mask = np.abs(sos_recdata2[:,:,:,0])

            # Now save the resulting fieldmaps (these are now as good as it gets)
            # Note the transpose in there. Apparently the data saved in the tempfile are
            # x,y flipped compared to the data in the individula field map files.
            for echo in range(self.num_echoes):
                for cur_slice in range(self.num_slices):
                    for cur_recv in range(self.num_receivers):
                        thisfilename = '%s.freq_%03d' % (basepath,(cur_recv*self.num_slices+cur_slice)*self.num_echoes+echo)
                        with open(thisfilename ,'wb') as fp:
                            self.fm_data[:,:,cur_slice].transpose().tofile(file = fp)
                        thismaskname = '%s.mask_%03d' % (basepath,(cur_recv*self.num_slices+cur_slice)*self.num_echoes+echo)
                        with open(thismaskname ,'wb') as fp:
                            np.sqrt(fm_mask[:,:,cur_slice].transpose()).tofile(file = fp)

            # Now recon the whole timeseries using the good fieldmaps that we just saved.
            cmd = spirec + ' -l --savetempfile --loadfmap --rotate -90 --b0navigator -r ' + pfilename + ' -t ' + basename
            self.log.debug(cmd)
            sp.call(shlex.split(cmd), cwd=tmp_dir, stdout=open('/dev/null', 'w'))

            # Compute the receive coil weightings (Should become 1 if only a single coil).
            # The values stored in the header are standard deviations from the coil calibration.
            # We load those and convert to the 1 / (mean-normalized variance) scale factor.
            # Apparently, this is also what GE does in their recon code.
            coil_weights = np.array(self.header.ps.rec_std[0:self.num_receivers])
            coil_weights = np.power(coil_weights / coil_weights.mean(), -2)

            fn = '%s.complex_float' % basepath
            num_values_per_slice = self.size_x*self.size_y*self.num_timepoints
            num_bytes_per_slice = num_values_per_slice*np.dtype(data_type).itemsize
            complex_image = np.zeros([self.size_x,self.size_y,self.num_timepoints,self.num_receivers,self.num_echoes], dtype=data_type)
            self.image_data = np.zeros([self.size_x,self.size_y,self.num_slices,self.num_timepoints,self.num_echoes], dtype=np.float32)
            with open(fn, 'rb') as fp:
                for sl in range(self.num_slices):
                    for recv in range(self.num_receivers):
                        for echo in range(self.num_echoes):
                            fp.seek(sl*num_bytes_per_slice + recv*self.num_slices*num_bytes_per_slice + echo*self.num_receivers*self.num_slices*num_bytes_per_slice)
                            complex_image[:,:,:,recv,echo] = np.fromfile(file=fp, dtype=data_type, count=num_values_per_slice).reshape([self.size_x,self.size_y,self.num_timepoints],order='F')
                        complex_image[:,:,:,recv,] = complex_image[:,:,:,recv,] * coil_weights[recv]
                    self.image_data[:,:,sl,:,:] = np.sqrt(np.mean(np.power(np.abs(complex_image),2),3))


def montage(x):
    """
    Convenience function for looking at image arrays.

    For example:
        pylab.imshow(np.flipud(np.rot90(montage(im))))
        pylab.axis('off')
        pylab.show()
    """
    m, n, count = np.shape(x)
    mm = int(np.ceil(np.sqrt(count)))
    nn = mm
    montage = np.zeros((mm * m, nn * n))
    image_id = 0
    for j in range(mm):
        for k in range(nn):
            if image_id >= count:
                break
            slice_m, slice_n = j * m, k * n
            montage[slice_n:slice_n + n, slice_m:slice_m + m] = x[:, :, image_id]
            image_id += 1
    return montage


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Recons a GE pfile to produce a NIfTI file and a B0 fieldmap."""
        self.add_argument('pfile', help='path to pfile')
        self.add_argument('outbase', nargs='?', help='basename for output files (default: pfile name)')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    log = nimsutil.get_logger(os.path.splitext(os.path.basename(__file__))[0])
    pf = Pfile(args.pfile, log)
    pf.to_nii(args.outbase or os.path.basename(args.pfile))
