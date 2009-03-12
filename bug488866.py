
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+10
secport1 = port1+1
port2 = cfgport+20
secport2 = port2+1
basedn = "dc=example,dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'log'   : False
}
m2replargs = m1replargs

os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
#del os.environ['USE_VALGRIND']

m2 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})

m1.replicaSetupAll(m1replargs)
m2.replicaSetupAll(m2replargs)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(5)
#print "turn on repl logging on m2 - should slow it down"
#m2.setLogLevel(8192)
m1.startReplication_async(agmtm1tom2)
print "repl status after starting"
print m1.getReplStatus(agmtm1tom2)
print "shutdown m2 . . ."
m2.stop()
time.sleep(1)
if m1.waitForReplInit(agmtm1tom2):
    print "repl init failed"
    print m1.getReplStatus(agmtm1tom2)
    time.sleep(1)
    print "try repl init again"
    m2.start()
    time.sleep(5)
    m1.startReplication(agmtm1tom2)
else:
    m2.start()
    print "repl init succeeded!!!!!"
    print m1.getReplStatus(agmtm1tom2)

agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

print "Add a bunch of entries to queue up the changelog . . ."
for ii in xrange(0,2000):
    cn = "test user%d" % ii
    dn = "cn=%s,ou=people,%s" % (cn, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('cn', cn)
    ent.setValues('sn', 'user' + str(ii))
    m1.add_s(ent)
#     mod = [(ldap.MOD_REPLACE, 'description', 'description change')]
#     m1.modify_s(dn, mod)
#     m1.delete_s(dn)

time.sleep(1)
print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)

print "shutdown m2 . . ."
m2.stop()

time.sleep(1)
print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)

time.sleep(1)
print "start m2 . . ."
m2.start()

time.sleep(20)
print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)
