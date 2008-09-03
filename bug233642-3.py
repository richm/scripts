
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

#os.environ['USE_DBX'] = "1"
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
	'verbose': True,
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
time.sleep(5)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

basedn = "dc=example,dc=com"
nents = 2

print "Add %d entries alternately . . ." % nents
svrs = (m1, m2)
nsvrs = len(svrs)
for ii in range(0,nents):
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    svr = svrs[ii % nsvrs]
    svr.add_s(ent)
    print "Added %s to %s" % (dn, svr)

print "see if all entries are on both servers . . ."
time.sleep(5)
for ii in range(0,nents):
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)

print """
Do add description, modify description, delete description to each entry alternately . . .
"""
dn = "cn=%d, %s" % (0, basedn)
for ii in range(0,100):
    descstr = "this is description %d" % ii
    modadd = [(ldap.MOD_ADD, 'description', descstr)]
    moddel = [(ldap.MOD_DELETE, 'description', descstr)]
    m1.modify_s(dn, modadd)
    time.sleep(1)
    m2.modify_s(dn, moddel)

ent = m1.getEntry(dn, ldap.SCOPE_BASE)
if ent.description:
    print "Error: m1 has description attribute: %s" % str(ent.getValues("description"))
ent = m2.getEntry(dn, ldap.SCOPE_BASE)
if ent.description:
    print "Error: m2 has description attribute: %s" % str(ent.getValues("description"))
