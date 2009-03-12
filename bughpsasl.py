
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "hound.dsdev.sjc2.redhat.com"
host2 = host1
cfgport = 1100
port1 = cfgport+10
port2 = cfgport+20
root1 = "cn=directory manager"
root2 = root1
rootpw1 = 'password'
rootpw2 = rootpw1
basedn = "dc=example,dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'bindmethod': 'SASL/DIGEST-MD5',
    'log'   : False
}

m1 = DSAdmin(host1, port1, root1, rootpw1)
m1.replicaSetupAll(m1replargs)

m2replargs = m1replargs
m2 = DSAdmin(host2, port2, root2, rootpw2)
m2.replicaSetupAll(m2replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(5)
m1.setLogLevel(1024)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
