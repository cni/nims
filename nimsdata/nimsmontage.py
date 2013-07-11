#!/usr/bin/env python
#
# @author:  Bob Dougherty
#           Gunnar Schaefer

"""
The CNI pyramid viewer uses PanoJS for the front-end.
See: http://www.dimin.net/software/panojs/
"""

import os
import math
import logging
import sqlite3
import argparse
import cStringIO

import nimsdata
import nimsutil

log = logging.getLogger('nimsmontage')


def tile_from_db(dbfile, z, x, y):
    """Get a specific image tile from an sqlite db."""
    con = sqlite3.connect(dbfile)
    with con:
        cur = con.cursor()
        cur.execute('SELECT image FROM tiles where z=? AND x=? AND y=?', (z, x, y))
        image = cur.fetchone()[0]
    return str(image)


def info_from_db(dbfile):
    """Returns the tile_size, x_size, and y_size from the sqlite pyramid db."""
    try:
        con = sqlite3.connect(dbfile)
        with con:
            cur = con.cursor()
            cur.execute('SELECT * FROM info')
            tile_size, x_size, y_size = cur.fetchone()
    except NIMSMontageError as e:
        log.warning(e.message)
    return tile_size, x_size, y_size


def tile_from_hdf5(hdf5file, z, x, y):
    """Get a specific image tile from an hdf5 file."""
    import h5py
    with h5py.File(hdf5file, 'r') as f:
        image = f['/tiles/%d/%d/%d' % (z, x, y)].value
    # image should be a 1d numpy array of type uint8. Dump it to the StringIO.
    return image.tostring()


def info_from_hdf5(hdf5file):
    """Returns the tile_size, x_size, and y_size from the hdf5 pyramid."""
    import h5py
    with h5py.File(hdf5file, 'r') as f:
        tile_size = f['/tile_x_y_size'][0]
        x_size = f['/tile_x_y_size'][1]
        y_size = f['/tile_x_y_size'][2]
    return tile_size, x_size, y_size


class NIMSMontageError(nimsdata.NIMSDataError):
    pass


class NIMSMontage(nimsdata.NIMSData):

    """
    Generate a panojs-style image pyramid of a 2D montage of slices from a >=3D dataset (usually a NIfTI file).

    You can pass in a filename (any type of file that nibabel can make sense of) or a np.ndarray of raw image data.

    Example:
        import nimsmontage
        pyr = nimsmontage.NIMSMontage('t1.nii.gz')
        pyr.generate()
    """

    # TODO: add metadata necessary for sorting to the pyramid db.
    def __init__(self, image, tile_size=512):
        import nibabel
        import numpy as np
        self.tile_size = tile_size
        self.montage = None
        self.image_dir = 'pyramid'
        if isinstance(image, basestring):
            try:
                self.data = nibabel.load(image).get_data()
            except Exception as e:
                raise NIMSMontageError(e)
        elif isinstance(image, np.ndarray):
            self.data = image
        else:
            raise NIMSMontageError('argument must be a filename or a numpy ndarray.')
        super(NIMSMontage, self).__init__()

    def write_montage_as_png(self, filename, bits16=True):
        import png
        if self.montage==None:
            self.generate_montage(bits16=bits16)
        with open(filename, 'wb') as fd:
            if bits16:
                png.Writer(size=self.montage.shape[::-1], greyscale=True, bitdepth=16).write(fd, self.montage)
            else:
                png.Writer(size=self.montage.shape[::-1], greyscale=True, bitdepth=8).write(fd, self.montage)

    def generate_hdf5(self, hdf5file):
        """Generate a multi-resolution image pyramid and save all the resulting jpeg files in an hdf5 file."""
        import h5py
        self.generate_montage()
        try:
            # Open in write mode-- will rudely clobber the file if it exists. User beware!
            with h5py.File(hdf5file, 'w') as f:
                tiles = f.create_group('tiles')
                self.generate_pyramid(h5py_tiles = tiles)
                # It's important to get the pyramid metadata *after* the pyramid is generated.
                # E.g., the montage might be cropped and the tile size adjusted in there.
                x_size, y_size = self.montage.size
                f.create_dataset('tile_x_y_size', (3,), dtype='i')[:] = (self.tile_size, x_size, y_size)
        except NIMSMontageError as e:
            log.warning(e.message)

    def generate_sqlite(self, dbfile):
        """Generate a multi-resolution image pyramid and save all the resulting jpeg files in an sqlite db."""
        self.generate_montage()
        try:
            # Rudely clobber the file if it exists. User beware!
            if os.path.exists(dbfile):
                os.remove(dbfile)
            con = sqlite3.connect(dbfile)
            with con:
                cur = con.cursor()
                cur.execute('CREATE TABLE info(tile_size INT, x_size INT, y_size INT)')
                cur.execute('CREATE TABLE tiles(z INT, x INT, y INT, image BLOB)')
                self.generate_pyramid(dbcur=cur)
                # It's important to get the pyramid metadata *after* the pyramid is generated.
                # E.g., the montage might be cropped and the tile size adjusted in there.
                x_size, y_size = self.montage.size
                cur.execute('INSERT INTO info(tile_size,x_size,y_size) VALUES (?,?,?)', (self.tile_size, x_size, y_size))
        except NIMSMontageError as e:
            log.warning(e.message)

    def generate_dir(self, outdir, panojs_url='https://cni.stanford.edu/js/panojs/'):
        """Generate a multi-resolution image pyramid and corresponding HTML viewer file."""
        self.generate_montage()
        viewer_file = os.path.join(outdir, 'pyramid.html')
        try:
            image_dir = os.path.join(outdir, self.image_dir)
            os.makedirs(image_dir)
            self.generate_pyramid(outdir=image_dir)
        except NIMSMontageError as e:
            log.warning(e.message)
            with open(viewer_file, 'w') as f:
                f.write('<body>\n<center>Image viewer could not be generated for this dataset. (' + e.message + ')</center>\n</body>\n')
        else:
            self.generate_viewer(viewer_file, panojs_url)

    def generate_pyramid(self, outdir=None, dbcur=None, h5py_tiles=None):
        """
        Slice up a NIfTI file into a multi-res pyramid of tiles.
        We use the file name convention suitable for PanoJS (http://www.dimin.net/software/panojs/):
        The zoom level (z) is an integer between 0 and n, where 0 is fully zoomed in and n is zoomed out.
        E.g., z=n is for 1 tile covering the whole world, z=n-1 is for 2x2=4 tiles, ... z=0 is the original resolution.
        """
        import Image
        import numpy as np
        if not outdir and not dbcur and not h5py_tiles:
            raise NIMSMontageError('at least one of outdir, dbcur, and h5py_tiles must be supplied')
        if outdir and not os.path.exists(outdir): os.makedirs(outdir)
        # Convert the montage to an Image
        self.montage = Image.fromarray(self.montage)
        # NOTE: the following will crop away edges that contain only zeros. Not sure if we want this.
        self.montage = self.montage.crop(self.montage.getbbox())
        sx,sy = self.montage.size
        if sx*sy<1:
            raise NIMSMontageError('degenerate image size (%d,%d); no tiles will be created' % (sx, sy))
        # Panojs seems to choke if the lowest res image is smaller than the tile size.
        if sx<self.tile_size and sy<self.tile_size:
            self.tile_size = max(sx,sy)

        divs = max(1, int(np.ceil(np.log2(float(max(sx,sy))/self.tile_size))) + 1)
        for iz in range(divs):
            if h5py_tiles:
                h5py_zdir = h5py_tiles.create_group('%d' % iz)
            z = divs - iz
            ysize = int(round(float(sy)/pow(2,iz)))
            xsize = int(round(float(ysize)/sy*sx))
            xpieces = int(math.ceil(float(xsize)/self.tile_size))
            ypieces = int(math.ceil(float(ysize)/self.tile_size))
            log.debug('level %s, size %dx%d, splits %d,%d' % (z, xsize, ysize, xpieces, ypieces))
            # TODO: we don't need to use 'thumbnail' here. This function always returns a square
            # image of the requested size, padding and scaling as needed. Instead, we should resize
            # and chop the image up, with no padding, ever. panojs can handle non-square images
            # at the edges, so the padding is unnecessary and, in fact, a little wrong.
            im = self.montage.copy()
            im.thumbnail([xsize,ysize], Image.ANTIALIAS)
            # Convert the image to grayscale
            im = im.convert('L')
            for x in range(xpieces):
                if h5py_tiles:
                    h5py_xdir = h5py_zdir.create_group('%d' % x)
                for y in range(ypieces):
                    tile = im.copy().crop((x*self.tile_size, y*self.tile_size, min((x+1)*self.tile_size,xsize), min((y+1)*self.tile_size,ysize)))
                    buf = cStringIO.StringIO()
                    tile.save(buf, 'JPEG', quality=85)
                    if outdir:
                        with open(os.path.join(outdir, ('%03d_%03d_%03d.jpg' % (iz,x,y))), 'wb') as fp:
                            fp.write(buf.getvalue())
                    if dbcur:
                        dbcur.execute('INSERT INTO tiles(z,x,y,image) VALUES (?,?,?,?)', (iz, x, y, sqlite3.Binary(buf.getvalue())))
                    if h5py_tiles:
                        h5py_xdir.create_dataset('%d' % y, data=buf.getvalue())
                    buf.close()

    def generate_viewer(self, outfile, panojs_url):
        """Create a basic html file for viewing the image pyramid with panojs."""
        (x_size,y_size) = self.montage.size
        with open(outfile, 'w') as f:
            f.write('<html>\n<head>\n<meta http-equiv="imagetoolbar" content="no"/>\n')
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
            f.write('<script type="text/javascript">\nvar viewer = null;Ext.onReady(function () { createViewer( viewer, "viewer", "./' + self.image_dir + '", "", '+str(self.tile_size)+', '+str(x_size)+', '+str(y_size)+' ) } );\n</script>\n')
            f.write('</head>\n<body>\n')
            f.write('<div style="width: 100%; height: 100%;"><div id="viewer" class="viewer" style="width: 100%; height: 100%;" ></div></div>\n')
            f.write('</body>\n</html>\n')

    def generate_montage(self, bits16 = False):
        """Full-sized montage of the entire numpy data array."""
        # Figure out the image dimensions and make an appropriate montage.
        # NIfTI images can have up to 7 dimensions. The fourth dimension is
        # by convention always supposed to be time, so some images (RGB, vector, tensor)
        # will have 5 dimensions with a single 4th dimension. For our purposes, we
        # can usually just collapse all dimensions above the 3rd.
        # TODO: we should handle data_type = RGB as a special case.
        # TODO: should we use the scaled data (getScaledData())? (We do some auto-windowing below)

        import numpy as np
        data = self.data.squeeze()
        # TODO: "percentile" is very slow for large arrays. Is there a short cut that we can use?
        # Maybe try taking a smaller subset of the array?
        if data.dtype == np.uint8 and bits16:
            data = np.cast['uint16'](data)
        elif data.dtype != np.uint8 or (data.dtype != np.uint16 and bits16):
            # Make sure we do our scaling/clipping with floats:
            data = data.astype(np.float32)
            # Auto-window the data by clipping values above and below the following thresholds, then scale to unit8|16.
            clip_vals = np.percentile(data, (20.0, 99.0))
            data = data.clip(clip_vals[0], clip_vals[1]) - clip_vals[0]
            if bits16:
                data = np.cast['uint16'](np.round(data/(clip_vals[1]-clip_vals[0])*65535))
            else:
                data = np.cast['uint8'](np.round(data/(clip_vals[1]-clip_vals[0])*255.0))
        # This transpose (usually) makes the resulting images come out in a more standard orientation.
        # TODO: we could look at the qto_xyz to infer the optimal transpose for any dataset.
        data = data.transpose(np.concatenate(([1,0],range(2,data.ndim))))
        num_images = np.prod(data.shape[2:])

        if data.ndim < 2:
            raise NIMSMontageError('NIfTI file must have at least 2 dimensions')
        elif data.ndim == 2:
            # a single slice: no need to do anything
            num_cols = 1;
            data = np.atleast_3d(data)
        elif data.ndim == 3:
            # a simple (x, y, z) volume- set num_cols to produce a square(ish) montage.
            rows_to_cols_ratio = float(data.shape[0])/float(data.shape[1])
            num_cols = int(math.ceil(math.sqrt(float(num_images)) * math.sqrt(rows_to_cols_ratio)))
        elif data.ndim >= 4:
            # timeseries (x, y, z, t) or more
            num_cols = data.shape[2]
            data = data.transpose(np.concatenate(([0,1,3,2],range(4,data.ndim)))).reshape(data.shape[0], data.shape[1], num_images)

        num_rows = int(np.ceil(float(data.shape[2])/float(num_cols)))
        if bits16:
            self.montage = np.zeros((data.shape[0] * num_rows, data.shape[1] * num_cols), dtype=np.uint16)
        else:
            self.montage = np.zeros((data.shape[0] * num_rows, data.shape[1] * num_cols), dtype=np.uint8)
        for im_num in range(data.shape[2]):
            slice_r, slice_c = im_num/num_cols * data.shape[0], im_num%num_cols * data.shape[1]
            self.montage[slice_r:slice_r + data.shape[0], slice_c:slice_c + data.shape[1]] = data[:, :, im_num]

    def get_montage(self, bits16 = False):
        """
        Sometimes we just want to use this class as a convenient way to get a montage.
        E.g.,
        import nimsmontage
        pylab.imshow(nimsmontage.NIMSMontage('foo.nii.gz').get_montage(), figure=pylab.figure(figsize=(24,24)))
        """
        self.generate_montage(bits16)
        return self.montage


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Create a panojs-style image pyramid from a NIfTI file."""
        self.add_argument('-p', '--panojs_url', metavar='URL', help='URL for the panojs javascript.')
        self.add_argument('-t', '--tilesize', default = 256, type=int, help='tile size (default is 256)')
        self.add_argument('-m', '--montage', action='store_true', help='Save the full-size montage image (full pyramid will not be generated)')
        self.add_argument('-d', '--directory', action='store_true', help='Store image tiles in a directory')
        self.add_argument('-s', '--sqlite', action='store_true', help='Store image tiles in an sqlite db')
        self.add_argument('-f', '--hdf5', action='store_true', help='Store image tiles in an hdf5 file')
        self.add_argument('filename', help='path to NIfTI file')
        self.add_argument('out', nargs='?', help='output directory name or sqlite db filename')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    nimsutil.configure_log()
    pyr = NIMSMontage(args.filename, tile_size = args.tilesize)
    if args.montage:
        outfile = (args.out or os.path.basename(os.path.splitext(os.path.splitext(args.filename)[0])[0])) + '.png'
        pyr.write_montage_as_png(outfile, bits16=False)
    else:
        if args.sqlite:
            pyr.generate_sqlite(args.out)
        if args.hdf5:
            pyr.generate_hdf5(args.out)
        if args.directory:
            outdir = args.out or os.path.basename(os.path.splitext(os.path.splitext(args.filename)[0])[0]) + '.pyr'
            pyr.generate_dir(outdir, args.panojs_url) if args.panojs_url else pyr.generate_dir(outdir)
