#!/usr/bin/env python

import subprocess as sp
import shlex
import tempfile
import sys
import os

import numpy as np
import nibabel

#sys.path.append('/home/bobd/github/nims')
#from nimsutil import pfheader, nimsutil, pfile
import pfheader
import nimsutil

class Pfile:
    """
    A class for reading the data and/or header from a p-file, running a k-space reconstruction,
    and generating a NIFTI object from the p-file header info.
    Example:
        from nimsutil import pfile
        pf = pfile.Pfile(rawfile='/scratch/spirec_test/shim_test/P56832.7', outfile='P56832.7')
        pf.recon()
        pf.to_nii()

    """

    def __init__(self, rawfile, outfile = None, verbose = False):
        self.rawfile = rawfile
        if outfile == None:
            self.outfile = rawfile+"_recon"
        else:
            self.outfile = outfile
        self.header = None
        self.image_data = None
        self.fm_data = None
        self.spirec = os.path.join('/home/bobd/github/nims/nimsutil/','spirec')
        self.verbose = verbose

    def load_header(self, force_reload=False):
        if force_reload or self.header == None:
            self.header = pfheader.get_header(self.rawfile)
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

    def to_nii(self, saveInOut = False):
        """Create a nifti file from a p-file, given the p-file header and the reconstructed data."""
        # Make sure we have what we need
        self.load_header()
        if self.image_data == None:
            self.recon()

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
            fps_dim = [1, 0, 2]
        else:
            fps_dim = [0, 1, 2]
        nii_header.set_dim_info(*fps_dim)

        # FIXME: There must be a cleaner way to set the TR! Maybe bug Matthew about it.
        nii_header.structarr['pixdim'][4] = self.header.image.tr/1000.0

        if num_echoes == 1:
            nifti = nibabel.Nifti1Image(self.image_data, None, nii_header)
            nibabel.save(nifti, self.outfile + '.nii.gz')
        elif num_echoes == 2:
            if saveInOut:
                nifti = nibabel.Nifti1Image(self.image_data[:,:,:,:,0], None, nii_header)
                nibabel.save(nifti, self.outfile + '_in.nii.gz')
                nifti = nibabel.Nifti1Image(self.image_data[:,:,:,:,1], None, nii_header)
                nibabel.save(nifti, self.outfile + '_out.nii.gz')
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
            max_val = np.max(avg)
            if max_val>32768:
                avg = 32768.0/max_val * avg
            nifti = nibabel.Nifti1Image(avg, None, nii_header)
            nibabel.save(nifti, self.outfile + '.nii.gz')
            # w = out/(in+out)
        else:
            for echo in range(num_echoes):
                nifti = nibabel.Nifti1Image(self.image_data[:,:,:,:,0], None, nii_header)
                nibabel.save(nifti, self.outfile + "_echo%02d.nii.gi.gzz" % echo)

        nifti = nibabel.Nifti1Image(self.fm_data * 100, None, nii_header)
        nibabel.save(nifti, self.outfile + '_B0.nii.gz')



    def load_fieldmap_files(self, basename, save_unified = True, data_type = np.float32):
        xyres = self.size_x
        if xyres != self.size_y:
            raise IndexError("non-square matrix: spiral recon requires a square matrix!")

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



    def recon(self):
        self.load_header()

        with nimsutil.TempDirectory() as tmp_dir:
            basename = os.path.join(tmp_dir,'recon')

            # Run spirec once to get the fieldmap files (one for each coil and slice)
            #sp.check_call([spirec,"-X","-l","--loadfmap","--savefmap","--rotate","-90","--b0navigator","-r",self.rawfile,"-t","recon"],cwd=tmp_dir)
            cmd = self.spirec + " -l --fmaponly --savefmap --rotate -90 -r " + self.rawfile + " -t recon"
            print(cmd)
            sp.call(shlex.split(cmd), cwd=tmp_dir)

            # combine these fieldmaps into one unified fieldmap
            [self.fm_data, fm_mask] = self.load_fieldmap_files(basename, save_unified = True)

            # call spirec again, giving it our unified fieldmap. This will produce an even better fieldmap
            cmd = self.spirec + " -l --savetempfile --loadfmap --just 2 --rotate -90 -r " + self.rawfile + " -t recon"
            print(cmd)
            sp.call(shlex.split(cmd), cwd=tmp_dir)

            data_type = np.complex64
            #complex_image = np.zeros([size_x, size_y, num_slices, 2], dtype=data_type)
            fn = "%s.complex_float" % basename
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
                        thisfilename = '%s.freq_%03d' % (basename,(cur_recv*self.num_slices+cur_slice)*self.num_echoes+echo)
                        with open(thisfilename ,'wb') as fp:
                            self.fm_data[:,:,cur_slice].transpose().tofile(file = fp)
                        thismaskname = '%s.mask_%03d' % (basename,(cur_recv*self.num_slices+cur_slice)*self.num_echoes+echo)
                        with open(thismaskname ,'wb') as fp:
                            np.sqrt(fm_mask[:,:,cur_slice].transpose()).tofile(file = fp)

            # Now recon the whole timeseries using the good fieldmaps that we just saved.
            cmd = self.spirec + " -l --savetempfile --loadfmap --rotate -90 --b0navigator -r " + self.rawfile + " -t recon"
            print(cmd)
            sp.call(shlex.split(cmd), cwd=tmp_dir)

            max_array_bytes = 4*1024*1024*1024
            fn = "%s.complex_float" % basename
            num_values_per_slice = self.size_x*self.size_y*self.num_timepoints
            num_bytes_per_slice = num_values_per_slice*np.dtype(data_type).itemsize
            if numBytes_per_slice*self.num_slices < max_array_bytes:
                # This actually isn't much faster than looping over slices for smaller files.
                with open(fn, 'rb') as fp:
                    complex_image = np.fromfile(file=fp, dtype=data_type).reshape([self.size_x,self.size_y,self.num_timepoints,self.num_slices,self.num_receivers,self.num_echoes],order='F')
                for cur_recv in range(self.num_receivers):
                    complex_image[:,:,:,:,cur_recv,] = complex_image[:,:,:,:,cur_recv,] / self.header.ps.rec_std[cur_recv]
                self.image_data = np.sqrt(np.mean(np.power(np.abs(complex_image),2),4)).transpose([0,1,3,2,4])
            else:
                complex_image = np.zeros([self.size_x,self.size_y,self.num_timepoints,self.num_receivers,self.num_echoes], dtype=data_type)
                with open(fn, 'rb') as fp:
                    for sl in range(self.num_slices):
                        for recv in range(self.num_receivers):
                            for echo in range(self.num_echoes):
                                fp.seek(sl*num_bytes_per_slice + recv*self.num_slices*num_bytes_per_slice + echo*self.num_receivers*self.num_slices*num_bytes_per_slice)
                                complex_image[:,:,:,recv,echo] = np.fromfile(file=fp, dtype=data_type, count=num_values_per_slice).reshape([self.size_x,self.size_y,self.num_timepoints],order='F')
                        # FIXME: CHECK THAT WE ARE DOING THE RIGHT THING HERE!
                        # Coil standard deviations (one scalar per coil) are in self.header.ps.rec_std.
                            complex_image[:,:,:,recv,] = complex_image[:,:,:,recv,] / self.header.ps.rec_std[recv]
                        #self.image_data = np.abs(np.mean(complex_image,4)).transpose([0,1,3,2,4])
                        self.image_data[:,:,sl,:,:] = np.sqrt(np.mean(np.power(np.abs(complex_image),2),3))




    # A convenience function for looking at image arrays.
    # For example:
    #    pylab.imshow(np.flipud(np.rot90(montage(im))))
    #    pylab.axis('off')
    #    pylab.show()
    # FIXME: put this in a generic utils module.
    def montage(self, X):
        m, n, count = np.shape(X)
        mm = int(np.ceil(np.sqrt(count)))
        nn = mm
        M = np.zeros((mm * m, nn * n))
        image_id = 0
        for j in range(mm):
            for k in range(nn):
                if image_id >= count:
                    break
                sliceM, sliceN = j * m, k * n
                M[sliceN:sliceN + n, sliceM:sliceM + m] = X[:, :, image_id]
                image_id += 1
        return M

# for p in `pwd`/P*.7 ; do /home/bobd/github/nims/nimsutil/pfile.py $p ${p##*/} ; done
if __name__ == "__main__":
    verbose = False

    if len(sys.argv)!=3:
        print "Must provide a single argument (p-file name) and an output file base name."
        sys.exit(1)

    data_filename = sys.argv[1]
    out_filename = sys.argv[2]
    pf = Pfile(data_filename, out_filename)
    pf.to_nii()

    print 'Finished.'
    exit(0)

