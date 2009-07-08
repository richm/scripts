
import os
import sys
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

basedn = 'dc=company,dc=com'
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
os.environ['USE_GDB'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
    'no_admin': True
}, m1replargs
)
del os.environ['USE_GDB']

m2replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
    'no_admin': True
}, m2replargs
)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

#initfile = '/tmp/viewcrash.ldif'
#m1.importLDIF(initfile, '', "userRoot", True)

print "Add ou=people,", basedn
dn = "ou=people," + basedn
ent = Entry(dn)
ent.setValues('objectclass', 'top', 'organizationalUnit')
try: m1.add_s(ent)
except ldap.ALREADY_EXISTS: pass

print "add the nsview objectclass to %s" % basedn
dn = basedn
replace = [(ldap.MOD_ADD, 'objectclass', 'nsview')]
m1.modify_s(dn, replace)

print "add the nsview objectclass to ou=people"
dn = "ou=people," + basedn
replace = [(ldap.MOD_ADD, 'objectclass', 'nsview')]
m1.modify_s(dn, replace)

print "add the nsviewfilter objectclass to ou=people"
dn = "ou=people," + basedn
#replace = [(ldap.MOD_ADD, 'nsviewfilter', 'Cupertino')]
replace = [(ldap.MOD_ADD, 'nsviewfilter', '(l=Cupertino)')]
m1.modify_s(dn, replace)

print "add a dummy entry in ou=people"
dn = "cn=dummy,ou=people," + basedn
ent = Entry(dn)
ent.setValues('objectclass', 'top', 'extensibleObject')
ent.setValues('cn', "dummy")
m1.add_s(ent)

print "search for dummy"
ent = m1.getEntry(dn, ldap.SCOPE_BASE)
print "Entry: %s" % ent
