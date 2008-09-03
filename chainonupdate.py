
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry, LEAF_TYPE

host1 = "localhost.localdomain"
host2 = host1
cfgport = 28549
port1 = cfgport+30
port2 = cfgport+40

#os.environ['USE_DBX'] = "1"
m1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'chain' : True
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

#os.environ['USE_DBX'] = 1
c1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'type'  : LEAF_TYPE
}

#os.environ['USE_DBX'] = "1"
c1 = DSAdmin.createAndSetupReplica({
	'cfgdshost': host2,
	'cfgdsport': cfgport,
	'cfgdsuser': 'admin',
	'cfgdspwd': 'admin',
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'c1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True
}, c1replargs)
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers . . ."
agmtm1toc1 = m1.setupAgreement(c1, m1replargs)
print "starting replication . . ."
m1.startReplication(agmtm1toc1)
print "Replication started"

print "Press Enter to continue . . ."
foo = sys.stdin.readline()

print "modify entry on m1"
dn = "uid=scarter,ou=people,dc=example,dc=com"
mod = [(ldap.MOD_ADD, 'description', 'description')]
m1.modify_s(dn, mod)
c1.waitForEntry(dn, 10, 'description')

print "Modify entry on c1"
dn = "uid=jvedder,ou=people,dc=example,dc=com"
cc1 = DSAdmin(host2, port2, dn, "befitting")
mod = [(ldap.MOD_REPLACE, 'telephonenumber', '123456789')]
cc1.modify_s(dn, mod)
print "Wait for mod to show up on m1"
time.sleep(10)

ents = m1.search_s(dn, ldap.SCOPE_BASE, '(objectclass=*)', ['telephonenumber'])
ent = ents[0]
if ent.telephonenumber == '123456789':
    print "m1 success - telephonenumber changed"
else:
    print "m1 failed - value is still " + ent.telephonenumber
ents = c1.search_s(dn, ldap.SCOPE_BASE, '(objectclass=*)', ['telephonenumber'])
ent = ents[0]
if ent.telephonenumber == '123456789':
    print "c1 success - telephonenumber changed"
else:
    print "c1 failed - value is still " + ent.telephonenumber
