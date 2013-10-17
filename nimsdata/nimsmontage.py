#!/usr/bin/env python
#
# @author:  Bob Dougherty
#           Gunnar Schaefer

import os
import math
import Image
import logging
import sqlite3
import argparse
import cStringIO
import numpy as np

import nimsdata
import nimsutil
import nimsnifti

log = logging.getLogger('nimsmontage')


def get_tile(dbfile, z, x, y):
    """Get a specific image tile from an sqlite db."""
    con = sqlite3.connect(dbfile)
    with con:
        cur = con.cursor()
        cur.execute('SELECT image FROM tiles where z=? AND x=? AND y=?', (z, x, y))
        image = cur.fetchone()[0]
    return str(image)


def get_info(dbfile):
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


def generate_montage(niftipath, timepoints=[]):
    # Figure out the image dimensions and make an appropriate montage.
    # NIfTI images can have up to 7 dimensions. The fourth dimension is
    # by convention always supposed to be time, so some images (RGB, vector, tensor)
    # will have 5 dimensions with a single 4th dimension. For our purposes, we
    # can usually just collapse all dimensions above the 3rd.
    # TODO: we should handle data_type = RGB as a special case.
    # TODO: should we use the scaled data (getScaledData())? (We do some auto-windowing below)
    nifti = nimsnifti.NIMSNifti(niftipath)
    data = nifti.imagedata.squeeze()

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
        if len(timepoints)>0:
            data = data[...,timepoints]

    num_rows = int(np.ceil(float(data.shape[2])/float(num_cols)))
    montage = np.zeros((data.shape[0] * num_rows, data.shape[1] * num_cols), dtype=data.dtype)
    for im_num in range(data.shape[2]):
        slice_r, slice_c = im_num/num_cols * data.shape[0], im_num%num_cols * data.shape[1]
        montage[slice_r:slice_r + data.shape[0], slice_c:slice_c + data.shape[1]] = data[:, :, im_num]
    return NIMSMontage(None, montage, nifti)


class NIMSMontageError(nimsdata.NIMSDataError):
    pass


class NIMSMontage(nimsdata.NIMSData):

    datatype = u'montage'
    datakind = u'web'
    filetype = u'montage'

    def __init__(self, filepath=None, montage=None, metadata=None):
        # TODO: add metadata necessary for sorting to the pyramid db.
        self.pyramid = None
        if filepath is not None:
            # FIXME: parse montage
            raise NIMSMontageError('not implemented')
        elif montage is not None and metadata is not None:
            self.montage = montage
            self.metadata = metadata
        else:
            raise NIMSMontageError('must either pass in filepath or montage and metadata')

    def copy_as_int(self, bits16):
        # TODO: "percentile" is very slow for large arrays. Is there a short cut that we can use?
        # Maybe try taking a smaller subset of the array?
        data = self.montage.copy()
        if data.dtype == np.uint8 and bits16:
            data = np.cast['uint16'](data)
        elif data.dtype != np.uint8 or (data.dtype != np.uint16 and bits16):
            data = data.astype(np.float32)  # do scaling/clipping with floats
            clip_vals = np.percentile(data, (20.0, 99.0))   # auto-window the data by clipping
            data = data.clip(clip_vals[0], clip_vals[1]) - clip_vals[0]
            if bits16:
                data = np.cast['uint16'](np.round(data/(clip_vals[1]-clip_vals[0])*65535))
            else:
                data = np.cast['uint8'](np.round(data/(clip_vals[1]-clip_vals[0])*255.0))
        return data

    def generate_pyramid(self, montage, tile_size):
        """
        Slice up a NIfTI file into a multi-res pyramid of tiles.
        We use the file name convention suitable for PanoJS (http://www.dimin.net/software/panojs/):
        The zoom level (z) is an integer between 0 and n, where 0 is fully zoomed in and n is zoomed out.
        E.g., z=n is for 1 tile covering the whole world, z=n-1 is for 2x2=4 tiles, ... z=0 is the original resolution.
        """
        montage_image = Image.fromarray(montage, 'L')
        montage_image = montage_image.crop(montage_image.getbbox()) # crop away edges that contain only zeros
        sx, sy = montage_image.size
        if sx * sy < 1:
            raise NIMSMontageError('degenerate image size (%d, %d): no tiles will be created' % (sx, sy))
        if sx < tile_size and sy < tile_size: # Panojs chokes if the lowest res image is smaller than the tile size.
            tile_size = max(sx, sy)

        pyramid = {}
        divs = max(1, int(np.ceil(np.log2(float(max(sx,sy))/tile_size))) + 1)
        for z in range(divs):
            ysize = int(round(float(sy)/pow(2,z)))
            xsize = int(round(float(ysize)/sy*sx))
            xpieces = int(math.ceil(float(xsize)/tile_size))
            ypieces = int(math.ceil(float(ysize)/tile_size))
            log.debug('level %s, size %dx%d, splits %d,%d' % (z, xsize, ysize, xpieces, ypieces))
            # TODO: we don't need to use 'thumbnail' here. This function always returns a square
            # image of the requested size, padding and scaling as needed. Instead, we should resize
            # and chop the image up, with no padding, ever. panojs can handle non-square images
            # at the edges, so the padding is unnecessary and, in fact, a little wrong.
            im = montage_image.copy()
            im.thumbnail([xsize,ysize], Image.ANTIALIAS)
            im = im.convert('L')    # convert to grayscale
            for x in range(xpieces):
                for y in range(ypieces):
                    tile = im.copy().crop((x*tile_size, y*tile_size, min((x+1)*tile_size,xsize), min((y+1)*tile_size,ysize)))
                    buf = cStringIO.StringIO()
                    tile.save(buf, 'JPEG', quality=85)
                    pyramid[(z, x, y)] = buf
        return pyramid, montage_image.size

    def write_sqlite_pyramid(self, filepath, tile_size=512):
        """Generate a multi-resolution image pyramid and store the resulting jpeg files in an sqlite db."""
        if self.pyramid is None:
            montage = self.copy_as_int(bits16=False)
            self.pyramid, self.pyramid_size = self.generate_pyramid(montage, tile_size)
        if os.path.exists(filepath):
            os.remove(filepath)
        con = sqlite3.connect(filepath)
        with con:
            cur = con.cursor()
            cur.execute('CREATE TABLE info(tile_size INT, x_size INT, y_size INT)')
            cur.execute('CREATE TABLE tiles(z INT, x INT, y INT, image BLOB)')
            cur.execute('INSERT INTO info(tile_size,x_size,y_size) VALUES (?,?,?)', (tile_size,) + self.pyramid_size)
            for idx, tile_buf in self.pyramid.iteritems():
                cur.execute('INSERT INTO tiles(z,x,y,image) VALUES (?,?,?,?)', idx + (sqlite3.Binary(tile_buf.getvalue()),))

    def write_png_montage(self, filepath):
        montage = self.copy_as_int(bits16=False)
        Image.fromarray(montage).convert('L').save(filepath, optimize=True)

    def write_directory_pyramid(self, outpath, tile_size=256, panojs_url='https://cni.stanford.edu/nims/javascript/panojs/'):
        """Generate a multi-resolution image pyramid and store the resulting jpeg files in a directory."""
        if self.pyramid is None:
            montage = self.copy_as_int(bits16=False)
            self.pyramid, self.pyramid_size = self.generate_pyramid(montage, tile_size)
        image_path = os.path.join(outpath, 'images')
        if not os.path.exists(image_path):
            os.makedirs(image_path)
        for idx, tile_buf in self.pyramid.iteritems():
            with open(os.path.join(image_path, ('%03d_%03d_%03d.jpg' % idx)), 'wb') as fp:
                fp.write(tile_buf.getvalue())
        with open(os.path.join(outpath, 'pyramid.html'), 'w') as f:
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
            f.write('<script type="text/javascript">\nvar viewer = null;Ext.onReady(function () { createViewer( viewer, "viewer", "./images", "", %d, %d, %d ) } );\n</script>\n' % ((tile_size,) + self.pyramid_size))
            f.write('</head>\n<body>\n')
            f.write('<div style="width: 100%; height: 100%;"><div id="viewer" class="viewer" style="width: 100%; height: 100%;" ></div></div>\n')
            f.write('</body>\n</html>\n')


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Create a panojs-style image pyramid from a NIfTI file."""
        self.add_argument('file', help='path to NIfTI file')
        self.add_argument('out', help='output directory name or sqlite db filename')
        self.add_argument('-d', '--directory', action='store_true', help='store image tiles in a directory')
        self.add_argument('-t', '--tilesize', default=512, type=int, help='tile size (default is 512)')
        self.add_argument('-m', '--montage', action='store_true', help='save full-size montage image (not pyramid)')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    nimsutil.configure_log()
    montage = generate_montage(args.file)
    if args.montage:
        montage.write_png_montage(args.out)
    elif args.directory:
        montage.write_directory_pyramid(args.out, args.tilesize)
    else:
        montage.write_sqlite_pyramid(args.out, args.tilesize)
