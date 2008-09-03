
import os
import time
import ldap
import thread
import threading
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

#os.environ['USE_DBX'] = "1"
m1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

m1 = DSAdmin.createAndSetupReplica({
	'cfgdshost': host1,
	'cfgdsport': cfgport,
	'cfgdsuser': 'admin',
	'cfgdspwd': 'admin',
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True
}, m1replargs)
#del os.environ['USE_DBX']

m2replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = 1
m2 = DSAdmin.createAndSetupReplica({
	'cfgdshost': host2,
	'cfgdsport': cfgport,
	'cfgdsuser': 'admin',
	'cfgdspwd': 'admin',
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True
}, m2replargs)
#del os.environ['USE_DBX']

# initfile = ''
# if os.environ.has_key('SERVER_ROOT'):
#     initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
# else:
#     initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
# m1.importLDIF(initfile, '', "userRoot", True)

def starttest(*args):
    dn = "ou=test, dc=example, dc=com"
    newrdn = "ou=test2"
    dn2 = newrdn + ", dc=example, dc=com"
    server = args[0]
    print "starting starttest with " + str(server)
    while True:
        try:
            entry = Entry(dn)
            entry.setValues('objectclass', 'top', 'organizationalUnit')
            entry.setValues('ou', 'test')
            server.add_s(entry)
            time.sleep(0.100)
        except ldap.ALREADY_EXISTS:
            pass
        except ldap.LDAPError, e:
            print "Could not add test entry to server " + str(server), e
            raise
        try:
            server.rename_s(dn, newrdn)
            time.sleep(0.050)
        except ldap.ALREADY_EXISTS: # replicated from the other server
            pass
        except ldap.NO_SUCH_OBJECT: # deleted by the other server
            pass
        except ldap.LDAPError, e:
            print "Could not delete test entry from server " + str(server), e
            raise
        try:
            server.delete_s(dn2)
            time.sleep(0.050)
        except ldap.NO_SUCH_OBJECT:
            pass
        except ldap.LDAPError, e:
            print "Could not delete test entry from server " + str(server), e
            raise
    print "finished starttest with " + str(server)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
print "start replication"
m1.startReplication(agmtm1tom2)

print "now keep looping on add and delete of same entry"
print "number of active threads = " + str(threading.activeCount())
thread.start_new_thread(starttest, (m1,))
time.sleep(1)
print "number of active threads = " + str(threading.activeCount())
thread.start_new_thread(starttest, (m2,))
time.sleep(1)
print "number of active threads = " + str(threading.activeCount())


while True:
    print "waiting for threads to complete"
    time.sleep(10)
