
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "USEFQDN"
port1 = 1200
secport1 = port1+1
basedn = "dc=example,dc=com"

#os.environ['USE_DBX'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'srv',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
#del os.environ['USE_DBX']

srv.setupSSL(secport1, os.environ['SECDIR'],
            {'nsslapd-security': 'on'})

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
m2.setLogLevel(1,8192)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
