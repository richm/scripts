
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100

m1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = "1"
os.environ['USE_CALLGRIND'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': cfgport+10,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
    'no_admin': True
}, m1replargs
)
#del os.environ['USE_CALLGRIND']
#del os.environ['USE_DBX']

m2replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': cfgport+20,
	'newinst': 'm2',
	'newsuffix': 'dc=example,dc=com',
    'no_admin': True
}, m2replargs
)
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
#m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

basedn = "dc=example,dc=com"
nents = 10000
m1ents = range(nents)

print "Add %d entries to m1" % len(m1ents)
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m1.add_s(ent)
    print "Added m1 entry", dn

time.sleep(10)

while True:
	ruv1 = m1.getRUV(basedn)
	ruv2 = m2.getRUV(basedn)
	(rc, msg) = ruv1.getdiffs(ruv2)
	if rc:
		print "ruvs differ", msg
		time.sleep(5)
	else:
		break
m1.stop()
m2.stop()
