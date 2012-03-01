
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
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': cfgport+10,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
    'no_admin': True
}, m1replargs
)
#del os.environ['USE_DBX']

m2replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
#os.environ['USE_DBX'] = 1
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': cfgport+20,
	'newinst': 'm2',
	'newsuffix': 'dc=example,dc=com',
    'no_admin': True
}, m2replargs
)
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
#m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

basedn = "dc=example,dc=com"
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

print "Now, reinit m1 from m2.  This should have the effect of wiping out the changelog"
m2.startReplication_async(agmtm2tom1)
print "waiting for init to finish"
m2.waitForReplInit(agmtm2tom1)

print "Now the m1 and m2 RUV for m2 should have CSNs for m2 that are not in the m2 changelog"
m2ents = range(m2ents[-1]+1, m2ents[-1]+1+nents)
m1ents = range(m2ents[-1]+1, m2ents[-1]+1+nents)

print "Add entries to m2 - see if they are replicated to m1"
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m2.add_s(ent)
    print "Added m2 entry", dn

print "Add entries to m1 - see if they are replicated to m2"
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m1.add_s(ent)
    print "Added m1 entry", dn

print "Sleep for 5 seconds to let changes propagate . . ."
time.sleep(5)

print "see if m2 entries made it to m1"
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    print "found m1 entry", ent

print "see if m1 entries made it to m2"
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    print "found m2 entry", ent
