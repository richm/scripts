
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
	'bindpw': "replrepl",
    'log'   : True
}

os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': cfgport+10,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
}, m1replargs
)
del os.environ['USE_VALGRIND']

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
	'verbose': True,
    'no_admin': True
}, m2replargs
)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
#m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(5)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

basedn = "dc=example,dc=com"

print "Add an entry with several values for an attribute"
dn = "cn=testentry," + basedn
ent = Entry(dn)
ent.setValues('objectclass', 'extensibleObject')
ent.setValues('cn', ['foo', 'bar', 'baz', 'biff', 'barg', 'garb'])
ent.setValues('description', ['foo', 'bar', 'baz', 'biff', 'barg', 'garb'])
m1.add_s(ent)

for ii in range(0,100):
    print "Modify the entry to delete some of those values"
    mod = [(ldap.MOD_DELETE, 'cn', ['bar', 'baz', 'biff', 'barg', 'garb'])]
    m1.modify_s(dn, mod)

    print "Now, add back those values"
    mod = [(ldap.MOD_ADD, 'cn', ['bar', 'baz', 'biff', 'barg', 'garb'])]
    m1.modify_s(dn, mod)
