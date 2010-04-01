
import os
import sys
import ldap
import time
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

basedn = 'dc=example,dc=com'
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
    'no_admin': True
}, m1replargs
)
del os.environ['USE_VALGRIND']

m2replargs = m1replargs
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
    'no_admin': True
}, m2replargs
)

initfile = os.environ['PREFIX'] + "/share/dirsrv/data/Example.ldif"
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

print "delete the first 5 users"
userdns = []
ents = m1.search_s(basedn, ldap.SCOPE_SUBTREE, "(uid=*)")
for ii in range(0, 5):
    userdns.append(ents[ii].dn)
    m1.delete_s(ents[ii].dn)

print "make sure those users have been deleted on the other server"
time.sleep(10)
for dn in userdns:
    while True:
        try: m2.search_s(dn, ldap.SCOPE_BASE, "(objectclass=*)")
        except ldap.NO_SUCH_OBJECT: break # was deleted
        time.sleep(1) # not yet deleted - try again
