#!/usr/bin/env python

import xml.etree.ElementTree as xml
from datetime import datetime

logfile = '/net/cnimr/export/home/service/log/paramdata/tnsCnts.xml'

def get_notches(logfile):
    tree = xml.parse(logfile)
    log = tree.getroot()
    msg = log.find('message')

    dat = msg.find('detail').find('parametricdata').find('data').find('group').find('parameter')

    start = []
    duration = []
    notches = []
    for val in dat.getchildren():
        start.append(datetime.strptime(val.get('starttime'),'%m-%d-%Y %H:%M:%S.%f'))
        stop_str = val.get('stoptime')
        if stop_str:
            duration.append((datetime.strptime(stop_str,'%m-%d-%Y %H:%M:%S.%f')-start[-1]).total_seconds())
        else:
            duration.append(0.)
        notches.append(int(val.text))

    return start,duration,notches

if __name__ == "__main__":
    import argparse
    import os
    import sys

    arg_parser = argparse.ArgumentParser()
    arg_parser.description = """Parse the GE TNS log."""
    arg_parser.add_argument('infile', help='path to TNS log file (usually in /export/home/service/log/paramdata/tnsCnts.xml')
    arg_parser.add_argument('outfile', nargs='?', help='path to output file (default=./[infile].txt)')
    arg_parser.add_argument('-d', '--min_duration', type=float, default=10., metavar='[10.]', help='Minimum duration scan (in seconds) to show.')
    args = arg_parser.parse_args()
    if not args.outfile:
        fn,ext1 = os.path.splitext(args.infile)
        fn,ext0 = os.path.splitext(fn)
        outfile = fn + '.txt'
    else:
        outfile = args.outfile

    if os.path.exists(outfile):
        print('Output file "' + outfile + '" exists. Exiting...')
        sys.exit(1)

    start,duration,notches = get_notches(args.infile)
    for s,d,n in zip(start,duration,notches):
        if d>args.min_duration:
            print '%s (%6.3f min): %d notches' % (str(s),d/60.,n)

