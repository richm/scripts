from nose import *
from nose.tools import *
from dsadmin import DSAdmin, Entry


class config(object):
    auth = {'host': 'localhost',
            'port': 389,
            'binddn': 'cn=directory manager',
            'bindpw': 'password'}


def bind_test():
    conn = DSAdmin(**config.auth)
    print "conn: %s" % conn


def addbackend_test():
    conn = DSAdmin(**config.auth)
    conn.verbose = True
    ret = conn.addSuffix(suffix="o=addressbook1", bename="addressbook1")

    e = Entry(('o=addressbook1', {
               'objectclass': ['top', 'organization'],
               'o': 'addressbook1'
               }))
    conn.add(e)
