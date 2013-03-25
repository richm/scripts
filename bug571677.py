from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry, LEAF_TYPE


import os
import sys
import ldap
import time

host1 = "localhost.localdomain"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
host2 = host1
host3 = host2
port1 = 1200
port2 = port1 + 10
port3 = port2 + 10

basedn = 'dc=example,dc=com'
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
#os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
    'no_admin': True
}, m1replargs
)
#del os.environ['USE_VALGRIND']

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

c1replargs = m1replargs
c1replargs['type'] = LEAF_TYPE

c1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host3,
	'newport': port3,
	'newinst': 'c1',
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

agmtm1toc1 = m1.setupAgreement(c1, m1replargs)
m1.startReplication_async(agmtm1toc1)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1toc1)

agmtm2toc1 = m2.setupAgreement(c1, m2replargs)

print "disable replication"
m1.stopReplication(agmtm1tom2)
m2.stopReplication(agmtm2tom1)

print "generate some repl conflict entries"
for ii in range(1, 6):
    dn = "uid=add%d,ou=people,%s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues("objectclass", "extensibleObject")
    m1.add_s(ent)
    m2.add_s(ent)

print "enable replication"
m1.restartReplication(agmtm1tom2)
m2.restartReplication(agmtm2tom1)

time.sleep(5)

print "look for conflict entries"
m1ents = m1.search_s(basedn, ldap.SCOPE_SUBTREE, "(nsds5ReplConflict=*)")
for ent in m1ents:
    print "found m1 repl conflict entry"
    print ent

m2ents = m2.search_s(basedn, ldap.SCOPE_SUBTREE, "(nsds5ReplConflict=*)")
for ent in m2ents:
    print "found m2 repl conflict entry"
    print ent

c1ents = c1.search_s(basedn, ldap.SCOPE_SUBTREE, "(nsds5ReplConflict=*)")
for ent in c1ents:
    print "found c1 repl conflict entry"
    print ent

print "delete the conflict entries in m1"
for ent in m1ents:
    m1.delete_s(ent.dn)

print "delete the conflict entries in m2"
for ent in m2ents:
    try: m2.delete_s(ent.dn)
    except ldap.NO_SUCH_OBJECT: print ent.dn, "already deleted from m2"

c1ents = c1.search_s(basedn, ldap.SCOPE_SUBTREE, "(nsds5ReplConflict=*)")
for ent in c1ents:
    print "found c1 repl conflict entry"
    print ent

print "done"
