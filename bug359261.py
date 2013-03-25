from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap

host1 = "localhost.localdomain"
host2 = host1
cfgport = 389
port1 = cfgport+30
port2 = cfgport+40

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
	'verbose': True,
    'have_admin': True
}, m1replargs)
#del os.environ['USE_DBX']

#os.environ['USE_DBX'] = 1
m2replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = "1"
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
	'verbose': True,
    'have_admin': True
}, m2replargs)
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers . . ."
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
print "starting replication . . ."
m1.startReplication(agmtm1tom2)
print "Replication started"

print "add a ou=Clovis entry"
dn = "ou=Clovis,dc=example,dc=com"
ent = Entry(dn)
ent.setValues('objectclass', 'top', 'organizationalUnit', 'nsView')
ent.setValues('nsviewfilter', '(l=Clovis)')
m1.add_s(ent)

m2.waitForEntry(ent)

print "add a ou=Finance entry"
dn = "ou=Finance,ou=Clovis,dc=example,dc=com"
ent = Entry(dn)
ent.setValues('objectclass', 'top', 'organizationalUnit', 'nsView')
ent.setValues('nsviewfilter', '(departmentNumber=finance)')
m1.add_s(ent)

m2.waitForEntry(ent)

print "Delete ou=Finance"
m1.delete_s(dn)

print "wait for delete to propagate"
time.sleep(5)

print "Search for ou=finance on m2"

try:
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
except ldap.NO_SUCH_OBJECT:
    print "Entry %s was deleted" % dn
