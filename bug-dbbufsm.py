
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
suffix = "dc=example,dc=com"

m1replargs = {
	'suffix': suffix,
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
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': suffix,
	'verbose': True,
    'no_admin': True
}, m1replargs
)
#del os.environ['USE_DBX']

m2replargs = m1replargs
#os.environ['USE_DBX'] = 1
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': suffix,
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

# the attribute value must be larger
# than 1024 * 32 bytes in order to
# trigger the clcache buffer resize
size = 1024 * 32 + 1
val1 = "description1" + ("#" * size)
val2 = "description1" + ("#" * size)
nents = 2

print "Add %d entries alternately . . ." % nents
svrs = (m1, m2)
vals = (val1, val2)
nsvrs = len(svrs)
for ii in range(0,nents):
    dn = "cn=%d, %s" % (ii, suffix)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    ent.setValues('description', vals[ii % nsvrs])
    svr = svrs[ii % nsvrs]
    svr.add_s(ent)
    print "Added %s to %s" % (dn, svr)

print "see if all entries are on both servers . . ."
time.sleep(5)
for ii in range(0,nents):
    dn = "cn=%d, %s" % (ii, suffix)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
