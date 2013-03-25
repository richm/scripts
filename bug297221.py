from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import ldap

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
})
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')

m1.importLDIF(initfile, '', "userRoot", True)

#m1.setLogLevel(65535)
print "Add the filtered group entry with bogus filter"
dn = "cn=TestDynamicGroup,dc=example,dc=com"
ent = Entry(dn)
ent.setValues('description', "Dynamic test group")
ent.setValues('objectclass', 'top', 'groupofuniquenames', 'groupofurls')
ent.setValues('memberurl', 'ldap:///dc=example,dc=com??sub?(&(objectclass=person)(uid=scart*)')
#ent.cn = 'TestDynamicGroup'
m1.add_s(ent)

print "Add the bogus aci for that group"
addmod = [(ldap.MOD_REPLACE, 'aci', '(targetattr = "*") (version 3.0;acl "Test Crash ACL";allow (all)(groupdn = "ldap:///cn=TestDynamicGroup,dc=example,dc=com");)')]
m1.modify_s("dc=example,dc=com", addmod)
#m1.setLogLevel(0)

print "Do a search binding as a member of the group"
conn = DSAdmin(host1, port1, "uid=scarter,ou=people,dc=example,dc=com", "sprain")
entries = conn.search_s("uid=scarter,ou=people,dc=example,dc=com", ldap.SCOPE_BASE, "objectclass=*");
