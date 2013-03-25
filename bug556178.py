from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import ldap
import time

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

basedn = 'dc=example,dc=com'
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

m2replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
    'no_admin': True
}, m2replargs
)

initfile = os.environ['PREFIX'] + "/share/dirsrv/data/Example.ldif"
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

print "Add ou=people,", basedn
dn = "ou=people," + basedn
ent = Entry(dn)
ent.setValues('objectclass', 'top', 'organizationalUnit')
try: m1.add_s(ent)
except ldap.ALREADY_EXISTS: pass

print "add the ou=views to %s" % basedn
dn = "ou=views," + basedn
ent = Entry(dn)
ent.setValues('objectclass', 'top', 'organizationalUnit', "nsview")
m1.add_s(ent)

def createViews(m1):
    print "add the cupertino view to %s" % basedn
    dn = "ou=cupertino,ou=views," + basedn
    ent = Entry(dn)
    ent.setValues('objectclass', 'top', 'organizationalUnit', "nsview")
    ent.setValues('nsViewFilter', '(l=cupertino)')
    m1.add_s(ent)

    print "add the sunnyvale view to %s" % basedn
    dn = "ou=sunnyvale,ou=views," + basedn
    ent = Entry(dn)
    ent.setValues('objectclass', 'top', 'organizationalUnit', "nsview")
    ent.setValues('nsViewFilter', '(l=sunnyvale)')
    m1.add_s(ent)

    print "add the santa clara view to %s" % basedn
    dn = "ou=santa clara,ou=views," + basedn
    ent = Entry(dn)
    ent.setValues('objectclass', 'top', 'organizationalUnit', "nsview")
    ent.setValues('nsViewFilter', '(l=santa clara)')
    m1.add_s(ent)

def deleteViews(m1):
    print "delete the cupertino view"
    dn = "ou=cupertino,ou=views," + basedn
    m1.delete_s(dn)
    dn = "ou=sunnyvale,ou=views," + basedn
    m1.delete_s(dn)
    dn = "ou=santa clara,ou=views," + basedn
    m1.delete_s(dn)

while True:
    createViews(m1)
    time.sleep(5)
    deleteViews(m1)
    time.sleep(5)
