
import os
import sys
import time
import tempfile
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
port1 = 1389
port2 = port1 + 10
basedn = 'dc=example,dc=com'

createargs = {
    'newrootpw': 'password',
    'newhost': host1,
    'newport': port1,
    'newinst': 'm1',
    'newsuffix': basedn,
    'no_admin': True
}

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

#os.environ['USE_DBX'] = "1"
#os.environ['USE_CALLGRIND'] = "1"
m1 = DSAdmin.createAndSetupReplica(createargs, m1replargs)
#del os.environ['USE_CALLGRIND']
#del os.environ['USE_DBX']

if 'USE_DRD' in os.environ:
    del os.environ['USE_DRD']
if 'USE_CALLGRIND' in os.environ:
    del os.environ['USE_CALLGRIND']

m2replargs = m1replargs
createargs['newhost'] = host2
createargs['newport'] = port2
createargs['newinst'] = 'm2'
#os.environ['USE_GDB'] = "1"
m2 = DSAdmin.createAndSetupReplica(createargs, m2replargs)
#del os.environ['USE_GDB']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "delete the ou=groups tree"
ents = m1.search_s('ou=groups,' + basedn, ldap.SCOPE_SUBTREE)
revents = ents
revents.reverse()
for ent in revents:
    m1.delete_s(ent.dn)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

nents = 5
m1ents = range(nents)

def doadds(m1):
    print "Add %d entries to m1" % len(m1ents)
    for ii in m1ents:
        dn = "cn=%d,%s" % (ii, basedn)
        ent = Entry(dn)
        ent.setValues('objectclass', 'person')
        ent.setValues('sn', 'testuser')
        m1.add_s(ent)

def domods(m1):
    ii = 0
    dn = "cn=%d,%s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m1.add_s(ent)
    print "Do %d mods to m1" % len(m1ents)
    for ii in m1ents:
        newval = "description" + str(ii)
        mod = [(ldap.MOD_REPLACE, 'description', newval)]
        m1.modify_s(dn, mod)

def dodeletes(m1):
    print "delete some entries"
    dn = "cn=%d,%s" % (1, basedn)
    m1.delete_s(dn)
    dn = "cn=%d,%s" % (nents-1, basedn)
    m1.delete_s(dn)

doadds(m1)

dodeletes(m1)

time.sleep(10)

while True:
	ruv1 = m1.getRUV(basedn)
	ruv2 = m2.getRUV(basedn)
	(rc, msg) = ruv1.getdiffs(ruv2)
	if rc:
		print "ruvs differ", msg
		time.sleep(5)
	else:
		break
