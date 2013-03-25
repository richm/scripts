from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap

host1 = "el4i386"
host2 = "el5i386"
port1 = 389
port2 = 389
rootdn1 = "cn=directory manager"
rootdn2 = rootdn1
rootpw1 = "password"
rootpw2 = rootpw1

basedn = "dc=testdomain, dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin(host1, port1, rootdn1, rootpw1)
m1.replicaSetupAll(m1replargs)

m2replargs = m1replargs
#os.environ['USE_DBX'] = 1
m2 = DSAdmin(host2, port2, rootdn2, rootpw2)
m2.replicaSetupAll(m2replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

nents = 5
m1ents = range(nents)
m2ents = range(len(m1ents), len(m1ents)+nents+1)
print "Add %d entries to m2" % len(m2ents)
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m2.add_s(ent)
    print "Added m2 entry", dn

print "Add %d entries to m1" % len(m1ents)
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m1.add_s(ent)
    print "Added m1 entry", dn

print "Sleep for 5 seconds to let changes propagate . . ."
time.sleep(5)

print "see if m1 entries made it to m2"
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    print "found m2 entry", ent

print "see if m2 entries made it to m1"
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    print "found m1 entry", ent
