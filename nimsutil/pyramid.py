#!/usr/bin/env python

"""
The CNI Image Mapper (ImMap) uses PanoJS for the front-end.
See: http://www.dimin.net/software/panojs/
"""

import nibabel
import numpy
import math
import os
import argparse
import Image

class ImagePyramidError(Exception):
    pass


class ImagePyramid(object):

    """
    Generate a panojs-style image pyramid of a 2D montage of slices from a >=3D dataset (usually a NIFTI file).

    Example:
        import pyramid
        pyr = pyramid.ImagePyramid()
        pyr.generate(infile='t1.nii.gz', outdir='t1')
    """

    def __init__(self, tile_size=256, log=None):
        self.tile_size = tile_size
        self.data = None
        montage_array = None
        self.log = log

    def generate(self, infile, outdir, panojs_url = 'http://cni.stanford.edu/js/panojs/'):
        """
        Generate a multi-resolution image pyramid (using the generate_pyramid method) and
        the corresponding viewer HTML file (using the generate_viewer method) on the data
        file. The pyramid will be in a directory called [outbase].pyr and the viewer in an
        HTML file called [outbase].html.
        """
        self.load_data(infile)
        self.generate_montage()
        self.generate_pyramid(outdir)
        self.generate_viewer(os.path.join(outdir,'index.html'), panojs_url)

    def load_data(self, infile):
        try:
            nim = nibabel.load(infile)
        except:
            # If there are problems loading the image, just log it, and continue by returning an empty buffer
            # TODO: proper error-handling here.
            return;
        # TODO: crop to remove any zero-padding.
        self.data = nim.get_data()

    def generate_pyramid(self, outdir):
        """
        Slice up a NIFTI file into a multi-res pyramid of tiles.
        We use the file name convention suitable for PanoJS (http://www.dimin.net/software/panojs/):
        The zoom level (z) is an integer between 0 and n, where 0 is fully zoomed in and n is zoomed out.
        E.g., z=n is for 1 tile covering the whole world, z=n-1 is for 2x2=4 tiles, ... z=0 is the original resolution.
        """
        if(self.montage==None):
            self.generate_montage()
        sx,sy = self.montage.size
        divs = int(numpy.ceil(numpy.log2(max(sx,sy)/self.tile_size)))
        if not os.path.exists(outdir): os.makedirs(outdir)
        for iz in range(divs+1):
            z = divs - iz
            ysize = int(round(float(sy)/pow(2,iz)))
            xsize = int(round(float(ysize)/sy*sx))
            xpieces = int(math.ceil(float(xsize)/self.tile_size))
            ypieces = int(math.ceil(float(ysize)/self.tile_size))
            print 'level', z, 'size =',xsize,ysize, 'splits =', xpieces, ypieces
            # TODO: we don't need to use 'thumbnail' here. This function always returns a square
            # image of the requested size, padding and scaling as needed. Instead, we should resize
            # and chop the image up, with no padding, ever. panojs can handle non-square images
            # at the edges, so the padding is unnecessary and, in fact, a little wrong.
            im = self.montage.copy()
            im.thumbnail([xsize,ysize], Image.ANTIALIAS)
            # Convert the image to grayscale
            im = im.convert("L")
            for x in range(xpieces):
                for y in range(ypieces):
                    tile = im.copy().crop((x*self.tile_size, y*self.tile_size, min((x+1)*self.tile_size,xsize), min((y+1)*self.tile_size,ysize)))
                    tile.save(os.path.join(outdir, ('%03d_%03d_%03d.jpg' % (iz,x,y))), "JPEG", quality=85)

    def generate_viewer(self, outfile, panojs_url):
        """
        Creates a baisc html file for viewing the image pyramid with panojs.
        """
        (x_size,y_size) = self.montage.size
        with open(outfile, 'w') as f:
            f.write('<head>\n<meta http-equiv="imagetoolbar" content="no"/>\n')
            f.write('<style type="text/css">@import url(' + panojs_url + 'styles/panojs.css);</style>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'extjs/ext-core.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/utils.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/PanoJS.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/controls.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/pyramid_imgcnv.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/control_thumbnail.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/control_info.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'panojs/control_svg.js"></script>\n')
            f.write('<script type="text/javascript" src="' + panojs_url + 'viewer.js"></script>\n')
            f.write('<style type="text/css">body { font-family: sans-serif; margin: 0; padding: 10px; color: #000000; background-color: #FFFFFF; font-size: 0.7em; } </style>\n')
            f.write('<script type="text/javascript">\nvar viewer = null;Ext.onReady(function () { createViewer( viewer, "viewer", ".", "", '+str(self.tile_size)+', '+str(x_size)+', '+str(y_size)+' ) } );\n</script>\n')
            f.write('</head>\n<body>\n')
            f.write('<div style="width: 100%; height: 100%;"><div id="viewer" class="viewer" style="width: 100%; height: 100%;" ></div></div>\n')
            f.write('</body>\n</html>\n')

    def generate_montage(self):
        """Full-sized montage of the entire numpy data array."""
        # Figure out the image dimensions and make an appropriate montage.
        # NIFTI images can have up to 7 dimensions. The fourth dimension is
        # by convention always supposed to be time, so some images (RGB, vector, tensor)
        # will have 5 dimensions with a single 4th dimension. For our purposes, we
        # can usually just collapse all dimensions above the 3rd.
        # TODO: we should handle data_type = RGB as a special case.
        # TODO: should we use the scaled data (getScaledData())? (We do some auto-windowing below)

        # This transpose (usually) makes the resulting images come out in a more standard orientation.
        # TODO: we could look at the qto_xyz to infer the optimal transpose for any dataset.
        self.data = self.data.transpose(numpy.concatenate(([1,0],range(2,self.data.ndim))))
        num_images = numpy.prod(self.data.shape[2:])

        self.data = self.data.squeeze()

        if self.data.ndim < 2:
            raise exc.BadNiftiFile()
        elif self.data.ndim == 2:
            # a single slice: no need to do anything
            num_cols = 1;
            self.data = numpy.atleast_3d(self.data)
        elif self.data.ndim == 3:
            # a simple (x, y, z) volume- set num_cols to produce a square(ish) montage.
            rows_to_cols_ratio = float(self.data.shape[0])/float(self.data.shape[1])
            self.num_cols = int(math.ceil(math.sqrt(float(num_images)) * math.sqrt(rows_to_cols_ratio)))
        elif self.data.ndim >= 4:
            # timeseries (x, y, z, t) or more
            self.num_cols = self.data.shape[2]
            self.data = self.data.transpose(numpy.concatenate(([0,1,3,2],range(4,self.data.ndim)))).reshape(self.data.shape[0], self.data.shape[1], num_images)

        r, c, count = numpy.shape(self.data)
        self.num_rows = int(numpy.ceil(float(count)/float(self.num_cols)))
        montage_array = numpy.zeros((r * self.num_rows, c * self.num_cols))
        image_id = 0
        for k in range(self.num_rows):
            for j in range(self.num_cols):
                if image_id >= count:
                    break
                slice_c, slice_r = j * c, k * r
                montage_array[slice_r:slice_r + r, slice_c:slice_c + c] = self.data[:, :, image_id]
                image_id += 1

        # Auto-window the data by clipping values above and below the following thresholds, then scale to unit8.
        clip_vals = numpy.percentile(montage_array, (20.0, 99.0))
        montage_array = montage_array.clip(clip_vals[0], clip_vals[1])
        montage_array = montage_array-clip_vals[0]
        montage_array = numpy.cast['uint8'](numpy.round(montage_array/(clip_vals[1]-clip_vals[0])*255.0))
        self.montage = Image.fromarray(montage_array)
        # NOTE: the following will crop away edges that contain only zeros. Not sure if we want this.
        self.montage = self.montage.crop(self.montage.getbbox())


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Takes a NIFTI file as input and creates a panojs-style image pyramid from it."""
        self.add_argument('-p', '--panojs_url', help='URL for the panojs javascript.')
        self.add_argument('infile', help='path to NIFTI file')
        self.add_argument('outbase', nargs='?', help='basename for output files (default: pyramid)')

if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    #log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    if args.outbase == None:
        args.outbase = os.path.basename(os.path.splitext(os.path.splitext(args.infile)[0])[0])
    pyr = ImagePyramid()
    if args.panojs_url == None:
        pyr.generate(args.infile, args.outbase+'.pyr')
    else:
        pyr.generate(args.infile, args.outbase+'.pyr', args.panojs_url)
