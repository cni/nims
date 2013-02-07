#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

import os
import re
import sys
import argparse
import xml.etree.ElementTree as et

ACCEPTABLE_TYPES = [
    'PointerType',
    'Field',
    'ArrayType',
    'FundamentalType',
    'Struct',
    'Union',
    'Typedef',
    ]
FORMAT_CHARS = {
    'pointer': 'i', # encode pointers as ints - don't think they wind up being relevant for anything
    'short unsigned int': 'H',
    'short int': 'h',
    'int': 'i',
    'double': 'd',
    'float': 'f',
    'long unsigned int': 'Q', # typically this would actually be L, but it's a hack due to a bug in gccxml
    'char': 's', # we only really look at char arrays, so use s instead of c
    'signed char': 'b',
    'unsigned int': 'I'
    }
NODE_DICT = {}
OBJECT_DICT = {}


class Member:

    def __init__(self, node):
        self.node = node
        self.name = node.attrib['name'].replace('rdb_hdr_','')
        if not re.match('[a-zA-Z]', self.name[0]):
            self.name = 'rdb_hdr_' + self.name
        self.type = get_type(NODE_DICT[node.attrib['type']])

    def __repr__(self):
        return 'Member(node=%r, name=%s, type=%r)\n' % (self.node, self.name, self.type)

    def instantiation_str(self, member_name=None):
        return 'self.%s = %s' % (self.name, self.type.instantiation_str(self.name))


class BasicType:

    def __init__(self, node):
        self.node = node
        self.type_name = node.attrib['name'] if 'name' in node.attrib else None
        self.is_type_def = False
        self._size = None

    def __repr__(self):
        return 'BasicType(node=%r, type_name=%r, size=%d)\n' % (self.node, self.type_name, self.get_size())

    def get_size(self):
        if not self._size:
            if self.type_name == 'long unsigned int':
                self._size = 8 # bug in gccxml forces us to hard code this size
            else:
                self._size = int(self.node.attrib['size']) / 8
        return self._size

    def instantiation_str(self, member_name=None):
        return 'struct.unpack("{0}", fp.read(struct.calcsize("{0}")))[0]'.format(FORMAT_CHARS[self.type_name])


class ArrayType(BasicType):

    def __init__(self, node):
        BasicType.__init__(self, node)
        self.elem_type = get_type(NODE_DICT[node.attrib['type']])
        num_elems = node.attrib['max'][:-1]
        self.num_elems = int(num_elems) + 1 if num_elems else 0

    def __repr__(self):
        return 'ArrayType(node=%r, elem_type=%r, num_elems=%d)\n' % (self.node, self.elem_type, self.get_size())

    def get_size(self):
        if not self._size:
            self._size = self.elem_type.get_size()
            self._size *= self.num_elems
        return self._size

    def instantiation_str(self, member_name=None):
        if isinstance(self.elem_type, BasicType) and not isinstance(self.elem_type, (ArrayType, StructType)):
            string = 'struct.unpack("{1}{0}", fp.read(struct.calcsize("{1}{0}")))'.format(FORMAT_CHARS[self.elem_type.type_name], self.num_elems)
            if self.elem_type.type_name == 'char': string += '[0]'
        else:
            string = """[]
        for i in range({0}):
            self.{1}.append({2})""".format(self.num_elems, member_name, self.elem_type.instantiation_str(member_name))
        return string


class StructType(BasicType):

    def __init__(self, node):
        BasicType.__init__(self, node)
        member_ids = self.node.attrib['members'].split(None)
        member_ids = filter(lambda id_: id_ in NODE_DICT, member_ids)
        self.members = [Member(NODE_DICT[id_]) for id_ in member_ids]
        # When it's a union, just take the largest field and roll with it
        if node.tag == 'Union':
            self.members = [max(self.members, key=lambda member: member.type.get_size())]

    def get_size(self):
        if not self._size:
            self._size = 0
            for member in self.members:
                self._size += member.type.get_size()
        return self._size

    def __repr__(self):
        return 'StructType(node=%r, members=%r, size=%d)\n' % (self.node, self.members, self.get_size())

    def instantiation_str(self, member_name=None):
        return '%s(fp)' % self.type_name


def get_type(node):
    id_ = node.attrib['id']
    if id_ in OBJECT_DICT:
        object_ = OBJECT_DICT[id_]
    else:
        if node.tag == 'FundamentalType':
            object_ = BasicType(node)
        elif node.tag == 'ArrayType':
            object_ = ArrayType(node)
        elif node.tag == 'Struct' or node.tag == 'Union':
            object_ = StructType(node)
        elif node.tag == 'Typedef':
            object_ = get_type(NODE_DICT[node.attrib['type']]) # ignore the name of typedef, jump to its base type
            object_.is_type_def = True
        elif node.tag == 'PointerType':
            node.attrib['name'] = 'pointer' # pointers don't wind up with name fields, so i'm setting it manually and handling it downstream
            object_ = BasicType(node)
        else:
            raise Exception, node
        OBJECT_DICT[id_] = object_
    return object_


def get_pool_header(xml_path):
    all_children = list(et.parse(xml_path).iter())
    acceptable_children = filter(lambda element: element.tag in ACCEPTABLE_TYPES, all_children)
    pool_header_node = None
    for child in acceptable_children:
        id_ = child.attrib['id']
        NODE_DICT[id_] = child
        if 'name' in child.attrib and child.attrib['name'] == 'POOL_HEADER':
            pool_header_node = child
    pool_header = get_type(pool_header_node)
    pool_header.get_size() # force recursing to cache sizes
    return pool_header


def print_parser(pool_header, object_dict):
    objects = list(object_dict.itervalues())
    structs = set(filter(lambda object_: isinstance(object_, StructType), objects))
    print '\n"""AUTO-GENERATED FILE. DO NOT EDIT. USE %s"""\n' % os.path.basename(__file__)
    print 'import os'
    print 'import struct'
    print '\n'
    print 'class PFHeaderError(Exception):'
    print '    pass'

    for struct in structs:
        print '\n'
        print 'class %s:\n' % struct.type_name
        print '    def __init__(self, fp):'
        for member in struct.members:
            print '        %s' % member.instantiation_str()

    print '\n'
    print 'def get_header(file_object):'
    print '    if isinstance(file_object, basestring):'
    print '        close_file_on_exit = True'
    print '        file_object = open(file_object, "rb")'
    print '    else:'
    print '        close_file_on_exit = False'
    print ''
    print '    try:'
    print '        pool_header = POOL_HEADER(file_object)'
    print '    except struct.error:'
    print '        pool_header = None'
    print '        raise PFHeaderError, "Error reading header field in pfile %s" % file_object.name'
    print '    else:'
    print '        logo = pool_header.rec.logo.strip("\\x00")'
    print '        if logo != "GE_MED_NMR" and logo != "INVALIDNMR":'
    print '            raise PFHeaderError, "%s is not a valid pfile" % file_object.name'
    print '    finally:'
    print '        if close_file_on_exit:'
    print '            file_object.close()'
    print '    return pool_header'


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__(formatter_class=argparse.RawTextHelpFormatter)
        self.description  = 'Emits Python code to access pfile header information. The code is generated from XML,\n'
        self.description += 'which is the result of gccxml compilation of a proprietary GE C program.\n\n'
        self.description += 'To generate XML, run:\n'
        self.description += '    gccxml -fxml=pfheader.xml -include unistd.h -I../../include -DREVxx writeathdr23.c\n'
        self.description += 'where REVxx is, e.g., REV12 or REV22.'
        self.add_argument('xml_file', help='path to xml file')

    def error(self, message):
        self.print_help()
        sys.exit(2)


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    pool_header = get_pool_header(args.xml_file)
    print_parser(pool_header, OBJECT_DICT)
