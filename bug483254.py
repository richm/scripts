from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+10
port2 = cfgport+20
root1 = "cn=directory manager"
root2 = root1
rootpw1 = 'password'
rootpw2 = rootpw1
suffix = "dc=example,dc=com"
scope = ldap.SCOPE_SUBTREE
filt = '(objectclass=*)'

os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createInstance({
    'newrootpw': rootpw1,
    'newhost': host1,
    'newport': port1,
    'newinst': 'm1',
    'newsuffix': suffix,
    'verbose': False,
    'no_admin': True
})

dn = "ou=virtualviews," + suffix
ent = Entry(dn)
ent.setValues('objectclass', 'organizationalUnit')
print "Create view ou", dn
m1.add_s(ent)

mod = [(ldap.MOD_REPLACE, 'objectclass', ['top', 'organizationalUnit', 'nsView'])]
print "add nsview to", dn
m1.modify_s(dn, mod)

dn = "ou=LPP,ou=VirtualViews," + suffix
ent = Entry(dn)
ent.setValues('objectclass', 'organizationalUnit', 'nsView')
ent.setValues('nsViewFilter', "(ou=ou=lpp,ou=lab,ou=organisation," + suffix + ")")
ent.setValues('description', 'Test LPP')
print "Create view ou", dn
m1.add_s(ent)

ents = m1.search_s(suffix, scope)
for ent in ents:
    print "Entry:", ent

dn = "ou=virtualviews," + suffix
mod = [(ldap.MOD_REPLACE, 'objectclass', ['top', 'organizationalUnit'])]
print "remove nsview to", dn
m1.modify_s(dn, mod)

ents = m1.search_s(suffix, scope)
for ent in ents:
    print "Entry:", ent

dn = "ou=LPP,ou=VirtualViews," + suffix
mod = [(ldap.MOD_REPLACE, 'nsViewFilter', '(ou=#ou=lpp,ou=lab,ou=organisation,' + suffix + ')')]
print "modify view in", dn
m1.modify_s(dn, mod)

ents = m1.search_s(suffix, scope)
for ent in ents:
    print "Entry:", ent
