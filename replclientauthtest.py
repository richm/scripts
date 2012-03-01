
import os
import sys
import ldap
import time
from dsadmin import DSAdmin, Entry

host1 = "vmhost.testdomain.com"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
host2 = host1
port1 = 1200
port2 = port1 + 10
secport1 = port1 + 1
secport2 = port2 + 1

basedn = 'dc=example,dc=com'
#os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
    'no_admin': True,
    'InstallLdifFile': os.environ.get('PREFIX', '/usr') + "/share/dirsrv/data/Example.ldif"
})
#del os.environ['USE_VALGRIND']

#os.environ['USE_VALGRIND'] = "1"
m2 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
    'no_admin': True
})
#del os.environ['USE_VALGRIND']

if len(sys.argv) > 1:
    m1.setupSSL(secport1, None, {'nsSSLPersonalitySSL':'localhost.localdomain'})
    m2.setupSSL(secport2, None, {'nsSSLPersonalitySSL':'localhost.localdomain'})
else:
    m1.setupSSL(secport1)
    m2.setupSSL(secport1)

print "create entry to map cert to"
certdn = "cn=%s,cn=config" % host1
ent = Entry(certdn)
ent.setValues("objectclass", "extensibleObject")
m1.add_s(ent)
m2.add_s(ent)

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': certdn,
	'bindcn': host1,
	'bindpw': "replrepl",
    'starttls': True,
    'bindmethod': 'SSLCLIENTAUTH'
}
m2replargs = m1replargs

m1.replicaSetupAll(m1replargs)
m2.replicaSetupAll(m2replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)


print "add some entries"
nent = 100
for ii in xrange(0, nent):
    cn = "user%d" % ii
    dn = "cn=%s,ou=people,%s" % (cn, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'extensibleObject')
    srv = (m1, m2)[ii % 2]
    srv.add_s(ent)

print "wait a few seconds"
time.sleep(15)

for ii in xrange(0, nent):
    cn = "user%d" % ii
    dn = "cn=%s,ou=people,%s" % (cn, basedn)
    m1.search_s(dn, ldap.SCOPE_BASE)
    m2.search_s(dn, ldap.SCOPE_BASE)

print "all entries found"
