from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import sys
import os
import time
import ldap
import ldapurl
import ldif
import pprint

host1 = "localhost.localdomain"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
port1 = 1200
basedn = 'dc=example,dc=com'

#os.environ['USE_GDB'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'srv',
	'newsuffix': basedn,
    'no_admin': True
})
#del os.environ['USE_GDB']

val1 = 'PRC (China)Limited company'
val2 = 'PRC (China) Limited company'
rdn1 = "ou=" + val1
rdn2 = "ou=" + val2
filt1 = '(ou=*\\28China\\29Limited*)'
filt2 = '(ou=*\\28China\\29*)'
filt3 = '(businessCategory=*\\29Limited*)'

dn1 = rdn1 + "," + basedn
dn2 = rdn2 + "," + basedn

ent = Entry(dn1)
ent.setValues('objectclass', 'extensibleObject')
ent.setValues('businessCategory', val1)
srv.add_s(ent)

ent = Entry(dn2)
ent.setValues('objectclass', 'extensibleObject')
ent.setValues('businessCategory', val2)
srv.add_s(ent)

ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt1)
print "filter", filt1, "returns the following"
for ent in ents: print ent

ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt2)
print "filter", filt2, "returns the following"
for ent in ents: print ent

ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt3)
print "filter", filt3, "returns the following"
for ent in ents: print ent
