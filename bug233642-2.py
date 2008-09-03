
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry, NoSuchEntryError

host1 = "vmf8i386"
host2 = "vmf9x8664"
port1 = 389
port2 = port1
rootpw = "secret12"

m1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
#    'log'   : False
}
m2replargs = m1replargs

m1 = DSAdmin(host1, port1, "cn=directory manager", rootpw)
m2 = DSAdmin(host2, port2, "cn=directory manager", rootpw)

m1.replicaSetupAll(m1replargs)
m2.replicaSetupAll(m2replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

sys.exit(0)

basedn = "dc=example,dc=com"
nents = 20000

myiter = xrange(0, nents)
for ii in myiter:
    dn = "cn=%d, %s" % (ii, basedn)
    svr = (m1,m2)[ii % 2]
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    ent.setValues('description', 'added description')
    svr.add_s(ent)
    print "Added", dn

print "Sleep for 20 seconds to let changes propagate . . ."
time.sleep(20)
print "Verify all entries are present in both servers . . ."
for ii in myiter:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    if not ent: raise "Entry %s not found in %s" % (dn, m1)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    if not ent: raise "Entry %s not found in %s" % (dn, m2)

print "Delete description attr in all entries . . ."
for ii in myiter:
    dn = "cn=%d, %s" % (ii, basedn)
    jj = ii + 1
    svr = (m1,m2)[jj % 2]
    delit = [(ldap.MOD_DELETE, 'description', None)]
    svr.modify_s(dn, delit)
    print "Modified", dn

print "Sleep for 20 seconds to let changes propagate . . ."
time.sleep(20)
print "Verify all entries are modified . . ."
for ii in myiter:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    if ent.hasValue('description', 'added description'): raise "Entry %s in %s has description" % (dn, m1)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    if ent.hasValue('description', 'added description'): raise "Entry %s in %s has description" % (dn, m2)

print "Delete all entries . . ."
for ii in myiter:
    dn = "cn=%d, %s" % (ii, basedn)
    jj = ii + 1
    svr = (m1,m2)[jj % 2]
    svr.delete_s(dn)
    print "Deleted", dn

print "Sleep for 20 seconds to let changes propagate . . ."
time.sleep(20)
print "Verify all entries are deleted . . ."
for ii in myiter:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = None
    try: ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    except NoSuchEntryError: pass
    except ldap.NO_SUCH_OBJECT: pass
    if ent: raise "Entry %s in %s still exists" % (dn, m1)
    ent = None
    try: ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    except NoSuchEntryError: pass
    except ldap.NO_SUCH_OBJECT: pass
    if ent: raise "Entry %s in %s still exists" % (dn, m2)
