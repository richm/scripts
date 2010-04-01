
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+10
port2 = cfgport+20
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

m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})

os.environ['USE_GDB'] = "1"
m2 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
del os.environ['USE_GDB']

m1.replicaSetupAll(m1replargs)
m2.replicaSetupAll(m2replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(2)
m1.startReplication(agmtm1tom2)
print "repl status after starting"
print m1.getReplStatus(agmtm1tom2)

agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

print "add entry on m1 . . ."
dn = 'uid=testuser,dc=example,dc=com'
ent = Entry(dn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', "1")
ent.setValues('sn', 'testuser')
m1.add_s(ent)
time.sleep(2)
print "search for entry on m2 . . ."
ents = m2.search_s(dn, ldap.SCOPE_BASE)
if not ents:
   time.sleep(2)
   ents = m2.search_s(dn, ldap.SCOPE_BASE)
if not ents:
    print "entry not found on m2"
    sys.exit(1)
else:
    print "entry found on m2"

print "modify entry on m1 . . ."
mod = [(ldap.MOD_ADD, 'cn', '2'),
       (ldap.MOD_REPLACE, 'cn', '3')]
m1.modify_s(dn, mod)
time.sleep(5)
print "search for entry on m2 . . ."
ents = m2.search_s(dn, ldap.SCOPE_BASE)
ent = ents[0]
print "cn =", ent.getValues('cn')
