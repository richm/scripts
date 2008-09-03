
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
host3 = host2
cfgport = 1100

mreplargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = "1"
m = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': cfgport+10,
	'newinst': 'm',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
}, mreplargs
)
#del os.environ['USE_DBX']

hreplargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'type'  : dsadmin.HUB_TYPE
}
#os.environ['USE_DBX'] = 1
h = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': cfgport+20,
	'newinst': 'h',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
}, hreplargs
)
#del os.environ['USE_DBX']

creplargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'type'  : dsadmin.LEAF_TYPE
}
#os.environ['USE_DBX'] = 1
c = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host3,
	'newport': cfgport+30,
	'newinst': 'c',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
}, creplargs
)
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m.sroot,m.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm2h = m.setupAgreement(h, mreplargs)
m.startReplication_async(agmtm2h)
print "waiting for init to finish"
m.waitForReplInit(agmtm2h)
agmth2c = h.setupAgreement(c, hreplargs)

basedn = "dc=example,dc=com"
nents = 100
ments = range(nents)
print "Add %d entries to m" % len(ments)
for ii in ments:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m.add_s(ent)
    print "Added m entry", dn

print "Sleep for 5 seconds to let changes propagate . . ."
time.sleep(5)

print "see if m entries made it to h"
for ii in ments:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = h.getEntry(dn, ldap.SCOPE_BASE)
    print "found h entry", dn

print "exporting replica init file from h"
initfile = "/tmp/init.ldif"
h.exportLDIF("/tmp/init.ldif", basedn, True, True)

ments = range(nents,nents+nents)
print "add more entries to m and see if they get to h"
print "Add %d entries to m" % len(ments)
for ii in ments:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m.add_s(ent)
    print "Added m entry", dn

print "Sleep for 5 seconds to let changes propagate . . ."
time.sleep(5)

print "see if m entries made it to h"
for ii in ments:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = h.getEntry(dn, ldap.SCOPE_BASE)
    print "found h entry", dn

print "init replica c from the replica init file"
c.importLDIF(initfile, basedn, None, True)
