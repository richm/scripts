from nose import *
from nose.tools import *
from dsadmin import DSAdmin, Entry
from dsadmin import NoSuchEntryError
import dsadmin
import ldap


class config(object):
    auth = {'host': 'localhost',
            'port': 389,
            'binddn': 'cn=directory manager',
            'bindpw': 'password'}


class MockDSAdmin(object):
    host = 'localhost'
    port = 389
    sslport = 0

    def __str__(self):
        if self.sslport:
            return 'ldaps://%s:%s' % (self.host, self.sslport)
        else:
            return 'ldap://%s:%s' % (self.host, self.port)


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


def setupBackend_ok_test():
    be = conn.setupBackend('o=backend1')
    assert be


def setupBackend_double_test():
    be1 = conn.setupBackend('o=backend1')
    be11 = conn.setupBackend('o=backend1')
    assert be1
    assert be11
    assert be1 == be11


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


@SkipTest
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


def setupChangelog_full_test():
    assert conn.setupChangelog(dbname="/tmp/mockChangelogDb") == 0


def prepare_master_replica_test():
    user = {
        'binddn': 'uid=rmanager,cn=config',
        'bindpw': 'password'
    }
    conn.enableReplLogging()
    conn.setupBindDN(**user)
    # only for Writable
    conn.setupChangelog()


def setupAgreement_test():

    consumer = MockDSAdmin()
    args = {
        'suffix': "o=addressbook6",
        #'bename': "userRoot",
        'binddn': "uid=rmanager,cn=config",
        'bindpw': "password",
        'type': dsadmin.MASTER_TYPE
    }
    conn.setupReplica(args)
    dn_replica = conn.setupAgreement(consumer, args)
    print dn_replica


def setLogLevel_test():
    vals = 1 << 0, 1 << 1, 1 << 5
    assert conn.setLogLevel(*vals) == sum(vals)


def setLogLevel_test():
    vals = 1 << 0, 1 << 1, 1 << 5
    assert conn.setAccessLogLevel(*vals) == sum(vals)


@raises(NoSuchEntryError)
def getMTEntry_missing_test():
    e = conn.getMTEntry('o=MISSING')


def getMTEntry_present_test():
    suffix = 'o=addressbook6'
    e = conn.getMTEntry(suffix)
    assert e, "Entry should be present %s" % suffix
