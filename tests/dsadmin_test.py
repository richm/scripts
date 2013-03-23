from nose import *
from nose.tools import *
from dsadmin import DSAdmin, Entry
import dsadmin
import ldap


class config(object):
    auth = {'host': 'localhost',
            'port': 389,
            'binddn': 'cn=directory manager',
            'bindpw': 'password'}


conn = None


def dfilter(my_dict, keys):
    return dict([(k, v) for k, v in my_dict.iteritems() if k in keys])


def setup():
    global conn
    conn = DSAdmin(**config.auth)
    conn.verbose = True


def bind_test():
    print "conn: %s" % conn


def addbackend_harn(conn, name):
    suffix = "o=%s" % name
    e = Entry((suffix, {
               'objectclass': ['top', 'organization'],
               'o': 'name'
               }))

    ret = conn.addSuffix(suffix, name)
    conn.add(e)


def addsuffix_test():
    addbackend_harn(conn, 'addressbook6')


def addreplica_write_test():
    name = 'ab3'
    user = {
        'binddn': 'uid=rmanager,cn=config',
        'bindpw': 'password'
    }
    replica = {
        'suffix': 'o=%s' % name,
        'type': dsadmin.MASTER_TYPE,
        'id': 124
    }
    replica.update(user)
    addbackend_harn(conn, name)
    ret = conn.replicaSetupAll(replica)
    assert ret == 0, "Error in setup replica: %s" % ret


def setupSSL_test():
    ssl_args = {
        'secport': 636,
        'sourcedir': None,
        'secargs': {'nsSSLPersonalitySSL': 'localhost'},
    }
    conn.setupSSL(**ssl_args)


def setupBindDN_UID_test():
    # TODO change returning the entry instead of 0
    user = {
        'binddn': 'uid=rmanager1,cn=config',
        'bindpw': 'password'
    }
    assert conn.setupBindDN(**user) == 0
    e = conn.getEntry(user['binddn'], ldap.SCOPE_BASE)
    assert e


def setupBindDN_CN_test():
    # TODO change returning the entry instead of 0
    user = {
        'binddn': 'cn=rmanager1,cn=config',
        'bindpw': 'password'
    }
    assert conn.setupBindDN(**user) == 0
    e = conn.getEntry(user['binddn'], ldap.SCOPE_BASE)
    assert e


def setupChangelog_test():
    assert conn.setupChangelog(dbname="mockChangelogDb") == 0


def prepare_master_replica_test():
    user = {
        'binddn': 'uid=rmanager,cn=config',
        'bindpw': 'password'
    }
    conn.enableReplLogging()
    conn.setupBindDN(**user)
    # only for Writable
    conn.setupChangelog()
