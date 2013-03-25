from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap

host1 = "localhost.localdomain"
host2 = host1
port1 = 1130
port2 = port1+10
rootdn1 = "cn=directory manager"
rootpw1 = 'password'
rootdn2 = rootdn1
rootpw2 = rootpw1
suffix = "dc=example,dc=com"

mux = DSAdmin.createInstance({
	'newrootpw': rootpw1,
	'newhost': host1,
	'newport': port1,
	'newinst': 'mux',
	'newsuffix': 'dc=notused',
    'no_admin': True
})

os.environ['USE_GDB'] = "1"
farm = DSAdmin.createInstance({
	'newrootpw': rootpw2,
	'newhost': host2,
	'newport': port2,
	'newinst': 'farm',
	'newsuffix': 'dc=notused',
    'no_admin': True
})

# add the suffix
farm.addSuffix(suffix)
# add the suffix entry
dn = suffix
ent = Entry(dn)
ent.setValues('objectclass', 'domain')
farm.add_s(ent)

# setup chaining
mux.setupChaining(farm, suffix, False)

# add an administrative user on the mux
admindn = 'uid=ttestuser,cn=config'
adminpw = "adminpw"
ent = Entry(admindn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', 'Chain Admin User')
ent.setValues('sn', 'Chain')
ent.setValues('givenName', 'Admin User')
ent.setValues('userPassword', "adminpw")
mux.add_s(ent)

# add an aci for this user on the farm
mod = [(ldap.MOD_ADD, 'aci', '(targetattr = "*") (version 3.0; acl "Administration User ACL";allow (all)(userdn = "ldap:///uid=ttestuser,cn=config");)')]
farm.modify_s(suffix, mod)

admin = DSAdmin(host1, port1, admindn, adminpw)

# add a new user using the admin account, first without user password
dn = "uid=chainuser," + suffix
ent = Entry(dn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', 'Chain User')
ent.setValues('sn', 'Chain')
ent.setValues('givenName', 'User')
admin.add_s(ent)
print "added entry", dn

# next, try it with userPassword
dn = "uid=chainuser2," + suffix
ent = Entry(dn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', 'Chain User')
ent.setValues('sn', 'Chain')
ent.setValues('givenName', 'User')
ent.setValues('userPassword', "password")
admin.add_s(ent)

# search for user on farm
ents = farm.search_s(dn, ldap.SCOPE_BASE)
if not ents:
    print "entry", dn, "not found on farm"
else:
    print "entry", dn, "found on farm"

# search for user on mux
ents = mux.search_s(dn, ldap.SCOPE_BASE)
if not ents:
    print "entry", dn, "not found on mux"
else:
    print "entry", dn, "found on mux"
