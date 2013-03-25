from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1200
port1 = cfgport+10
port2 = cfgport+20
basedn = "dc=testdomain,dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'bindmethod': 'SASL/GSSAPI',
    'starttls': True,
    'log'   : False
}

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': False,
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
	'newsuffix': basedn,
	'verbose': False,
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
try: agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
except ldap.LDAPError, e: print "caught exception", e
del m2replargs['starttls']
m2replargs['bindmethod'] = 'SSLCLIENTAUTH'
try: agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
except ldap.LDAPError, e: print "caught exception", e
