# @author:  Gunnar Schaefer

import gzip
import struct


class PFileError(Exception):
    pass


def parse(filepath, is_compressed=False):
    fp = gzip.open(filepath, 'rb') if is_compressed else open(filepath, 'rb')
    version_bytes = fp.read(4)
    fp.seek(0)
    try:
        if version_bytes == 'V\x0e\xa0A':
            import pfile23 as pfile
        elif version_bytes == 'J\x0c\xa0A':
            import pfile22 as pfile
        #elif version_bytes == '\x00\x000A':
        #    import pfile12 as pfile
        else:
            raise PFileError('%s is not a valid PFile or of an unsupported version')
    except ImportError as e:
        raise ImportError('%s\nrun mkpfile.py without arguments for generation instructions' % str(e))
    try:
        pool_header = pfile.POOL_HEADER(fp)
    except struct.error:
        raise PFileError('error reading header field in PFile %s' % fp.name)
    else:
        logo = pool_header.rec.logo.strip('\x00')
        if logo != 'GE_MED_NMR' and logo != 'INVALIDNMR':
            raise PFileError('%s is not a valid PFile' % fp.name)
    fp.close()
    return pool_header
