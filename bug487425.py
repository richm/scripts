
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
del os.environ['USE_VALGRIND']

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
#m1.setLogLevel(1,8192)
#m2.setLogLevel(1,8192)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

print "Add a bunch of entries to queue up the changelog . . ."
for ii in xrange(0,100):
    cn = "test user%d" % ii
    dn = "cn=%s,ou=people,%s" % (cn, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('cn', cn)
    ent.setValues('sn', 'user' + str(ii))
    m1.add_s(ent)

time.sleep(1)
print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)

#print "Pause replication . . ."
#m1.stopReplication(agmtm1tom2)

#time.sleep(1)
#print "Check replication status - note number of changes sent, in progress . . ."
#print m1.getReplStatus(agmtm1tom2)

dn = "cn=changelog5, cn=config"
newdir = os.environ.get('PREFIX', '') + "/var/lib/dirsrv/slapd-m1/newcldb"
mod = [(ldap.MOD_REPLACE, "nsslapd-changelogdir", newdir)]
#m1.setLogLevel(8192)
print "Change the changelog directory at ", time.asctime()
m1.modify_s(dn, mod)
print "Change the changelog directory finished at ", time.asctime()

#print "Restart replication . . ."
#m1.restartReplication(agmtm1tom2)

print "Re-init the consumer . . ."
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)

print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)

print "Add a bunch of entries to queue up the changelog . . ."
for ii in xrange(100,200):
    cn = "test user%d" % ii
    dn = "cn=%s,ou=people,%s" % (cn, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('cn', cn)
    ent.setValues('sn', 'user' + str(ii))
    m1.add_s(ent)
    m1.setLogLevel(0)

time.sleep(1)
print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)

print "Change the changelog directory at ", time.asctime()
dn = "cn=changelog5, cn=config"
newdir = os.environ.get('PREFIX', '') + "/var/lib/dirsrv/slapd-m1/newcldb2"
mod = [(ldap.MOD_REPLACE, "nsslapd-changelogdir", newdir)]
m1.modify_s(dn, mod)
print "Change the changelog directory finished at ", time.asctime()

print "Re-init the consumer . . ."
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)

print "Check replication status - note number of changes sent, in progress . . ."
print m1.getReplStatus(agmtm1tom2)
