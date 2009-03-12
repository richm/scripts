
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+10
secport1 = port1+1
port2 = cfgport+20
secport2 = port2+1
basedn = "dc=example,dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'starttls': True,
    'log'   : False
}
m2replargs = m1replargs

os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
del os.environ['USE_VALGRIND']

m2 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})

print "Putting m1 userRoot into read-only mode . . ."
mod = [(ldap.MOD_REPLACE, 'nsslapd-readonly', 'on')]
dn = "cn=userRoot,cn=ldbm database,cn=plugins,cn=config"
m1.modify_s(dn, mod)
print "Sleep for a second . . ."
time.sleep(1)
print "Try to modify something . . ."
mod = [(ldap.MOD_REPLACE, 'description', 'foo')]
dn = "ou=people," + basedn
try: m1.modify_s(dn, mod)
except ldap.LDAPError, e: print "Caught exception ", e

m1.replicaSetupAll(m1replargs)
m2.replicaSetupAll(m2replargs)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(5)
#m1.setLogLevel(1,8192)
#m2.setLogLevel(1,8192)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
