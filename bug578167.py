from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import ldap
import time

host1 = "localhost.localdomain"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
host2 = host1
host3 = host2
host4 = host3
port1 = 1200
port2 = port1 + 10
port3 = port2 + 10
port4 = port3 + 10

basedn = 'dc=example,dc=com'
replargs = {}
srvs = []
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
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
replargs[m1] = m1replargs
srvs.append(m1)

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
replargs[m2] = m2replargs
srvs.append(m2)

if False:
    m3replargs = m2replargs
    m3 = DSAdmin.createAndSetupReplica({
        'newrootpw': 'password',
        'newhost': host3,
        'newport': port3,
        'newinst': 'm3',
        'newsuffix': basedn,
        'no_admin': True
        }, m3replargs)
    replargs[m3] = m3replargs
    srvs.append(m3)

if False:
    m4replargs = m3replargs
    m4 = DSAdmin.createAndSetupReplica({
        'newrootpw': 'password',
        'newhost': host4,
        'newport': port4,
        'newinst': 'm4',
        'newsuffix': basedn,
        'no_admin': True
        }, m4replargs)
    replargs[m4] = m4replargs
    srvs.append(m4)

initfile = os.environ['PREFIX'] + "/share/dirsrv/data/Example.ldif"
m1.importLDIF(initfile, '', "userRoot", True)

print "create all of the agreements and init the masters"
for mmx in srvs:
    for mmy in srvs:
        if mmx == mmy: continue
        agmtdn = mmx.setupAgreement(mmy, replargs[mmx])
        if mmx == m1:
            mmx.startReplication(agmtdn)
        print mmx.getReplStatus(agmtdn)

print "stop replication"
m1.stopReplication(m1.agmt[m2])
m2.stopReplication(m2.agmt[m1])

print "get a list of dns"
ents = m1.search_s(basedn, ldap.SCOPE_SUBTREE, "(uid=*)")
dn1 = ents[0].dn
dn2 = ents[1].dn
dn3 = ents[2].dn
binattr = "userCertificate;binary"
binval = ''.join([chr(ii % 256) for ii in xrange(0, 4096)])

asciiattr = "description"
svattr = "employeeNumber"
asciival = "value 0"
vals1 = ["value 0", "value 1", "value 2"]
vals2 = ["value 3", "value 4", "value 5"]
vals3 = ["value 6", "value 7", "value 8"]

if False:
    print "send update to m2"
    asciival = "value 0"
    mod = [(ldap.MOD_REPLACE, asciiattr, asciival),
           (ldap.MOD_REPLACE, svattr, asciival),
           (ldap.MOD_REPLACE, binattr, binval)]
    m2.modify_s(dn1, mod)
    print "sleep 5 seconds . . ."
    time.sleep(5)

    print "send updates to m1"
    asciival = "value 1"
    mod = [(ldap.MOD_REPLACE, asciiattr, asciival),
           (ldap.MOD_REPLACE, svattr, asciival),
           (ldap.MOD_REPLACE, binattr, binval)]
    m1.modify_s(dn1, mod)
    print "sleep 2 seconds . . ."
    time.sleep(2)

    asciival = "value 2"
    mod = [(ldap.MOD_REPLACE, asciiattr, asciival),
           (ldap.MOD_REPLACE, svattr, asciival),
           (ldap.MOD_REPLACE, binattr, binval)]
    m1.modify_s(dn1, mod)
    print "sleep 2 seconds . . ."
    time.sleep(2)

if False:
    print "second entry"
    mod = [(ldap.MOD_REPLACE, asciiattr, vals1),
           (ldap.MOD_DELETE, asciiattr, vals1),
           (ldap.MOD_REPLACE, asciiattr, vals2),
           (ldap.MOD_DELETE, asciiattr, vals2),
           (ldap.MOD_ADD, asciiattr, vals3)]
    m1.modify_s(dn2, mod)
    print "sleep 5 seconds . . ."
    time.sleep(5)

    print "mod remote"
    mod = [(ldap.MOD_REPLACE, asciiattr, "value 0")]
    m2.modify_s(dn2, mod)

print "third entry"
mod = [(ldap.MOD_REPLACE, asciiattr, vals1),
       (ldap.MOD_DELETE, asciiattr, vals1),
       (ldap.MOD_REPLACE, asciiattr, vals2),
       (ldap.MOD_DELETE, asciiattr, vals2),
       (ldap.MOD_ADD, asciiattr, vals3)]
m2.modify_s(dn3, mod)
print "sleep 4 seconds . . ."
time.sleep(4)
mod = [(ldap.MOD_REPLACE, asciiattr, "value 0")]
m1.modify_s(dn3, mod)

print "restart replication"
m1.restartReplication(m1.agmt[m2])
m2.restartReplication(m2.agmt[m1])

time.sleep(2)

ents = m1.search_s(dn1, ldap.SCOPE_BASE, "(objectclass=*)", ['nscpEntryWsi'])
print ents[0]
ents = m2.search_s(dn1, ldap.SCOPE_BASE, "(objectclass=*)", ['nscpEntryWsi'])
print ents[0]
ents = m1.search_s(dn2, ldap.SCOPE_BASE, "(objectclass=*)", ['nscpEntryWsi'])
print ents[0]
ents = m2.search_s(dn2, ldap.SCOPE_BASE, "(objectclass=*)", ['nscpEntryWsi'])
print ents[0]
ents = m1.search_s(dn3, ldap.SCOPE_BASE, "(objectclass=*)", ['nscpEntryWsi'])
print ents[0]
ents = m2.search_s(dn3, ldap.SCOPE_BASE, "(objectclass=*)", ['nscpEntryWsi'])
print ents[0]
