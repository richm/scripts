
import os
import sys
import ldap
import time
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
host2 = host1
port1 = 1200
port2 = port1 + 10

basedn = 'dc=example,dc=com'
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'pd': 5,
    'tpi': 5
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

print "adding a bunch of unnecessary indexes"
indexattrs = ['description', 'title', 'facsimileTelephoneNumber', 'street', 'postOfficeBox', 'roomNumber', 'postalCode', 'audio', 'departmentNumber', 'employeeNumber', 'homePhone', 'homePostalAddress', 'manager', 'secretary' ]
for attr in indexattrs:
    m1.addIndex(basedn, attr, ['pres', 'eq', 'sub'])
    m2.addIndex(basedn, attr, ['pres', 'eq', 'sub'])

binattr = "userCertificate;binary"
binval = ''.join([chr(ii % 256) for ii in xrange(0, 65536)])

basedn2 = "dc=example2,dc=com"
print "adding another suffix", basedn2
m1.addSuffix(basedn2)
m2.addSuffix(basedn2)

print "add several entries to", basedn2
ent = Entry(basedn2)
ent.setValues('objectclass', 'extensibleObject')
m1.add_s(ent)
m2.add_s(ent)

nusers = 100
print "add", nusers, "users to", basedn2
for ii in xrange(0, nusers):
    uid = "user%03d" % ii
    dn = "uid=%s,%s" % (uid, basedn2)
    ent = Entry(dn)
    ent.setValues('objectclass', 'inetOrgPerson')
    ent.setValues('sn', 'User%03d' % ii)
    ent.setValues('cn', 'Test User%03d' % ii)
    ent.setValues(binattr, binval)
    m1.add_s(ent)
    m2.add_s(ent)

initfile = os.environ['PREFIX'] + "/share/dirsrv/data/Example.ldif"
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

print "add a new entry parent"
dn = "cn=parent," + basedn
ent = Entry(dn)
ent.setValues('objectclass', 'extensibleObject')
m1.add_s(ent)
print "get the uuid of the parent"
ents = m1.search_s(dn, ldap.SCOPE_BASE, "objectclass=*", ['nsuniqueid'])
parentuuid = ents[0].nsuniqueid
print "parent uuid is", parentuuid

print "wait for repl to happen..."
time.sleep(5)

nusers = 100
print "add", nusers, "users"
for ii in xrange(0, nusers):
    uid = "user%03d" % ii
    dn = "uid=%s,cn=parent,%s" % (uid, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'inetOrgPerson')
    ent.setValues('sn', 'User%03d' % ii)
    ent.setValues('cn', 'Test User%03d' % ii)
    ent.setValues(binattr, binval)
    srv = (m1, m2)[ii % 2]
    srv.add_s(ent)

print "wait a few seconds for replication to happen . . ."
time.sleep(10)

print "delete newly added users"
for ii in xrange(0, nusers):
    uid = "user%03d" % ii
    dn = "uid=%s,cn=parent,%s" % (uid, basedn)
    srv = (m1, m2)[ii % 2]
    srv.delete_s(dn)
    time.sleep(2)

print "wait a few seconds for replication to happen . . ."
time.sleep(10)

print "delete the parent"
dn = "cn=parent," + basedn
m1.delete_s(dn)
print "wait a few seconds for replication to happen . . ."
time.sleep(2)

print "search for the deleted parent entry by uuid"
filt = '(&(nsUniqueId=%s)(objectclass=nsTombstone))' % parentuuid
done = False
while not done:
    ents = m1.search_s(basedn, ldap.SCOPE_SUBTREE, filt)
    if not ents:
        print filt, "not found, sleeping . . ."
        time.sleep(1)
    else:
        print "found tombstone entry", ents[0].dn
        done = True

print "delete some more entries"
ents = m1.search_s("ou=people," + basedn, ldap.SCOPE_ONELEVEL)
for ii in xrange(0, 50):
    dn = ents[ii].dn
    srv = (m1, m2)[ii % 2]
    srv.delete_s(dn)
    time.sleep(2)

print "parent entry was deleted and tombstoned - now see if it is reaped"
done = False
while not done:
    ents = m1.search_s(basedn, ldap.SCOPE_SUBTREE, filt)
    done = ents == None
    if not done:
        print "Entry", ents[0].dn, "still present, waiting . . ."
        time.sleep(1)
