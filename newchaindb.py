
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry, LEAF_TYPE

host1 = "vmf8i386.testdomain.com"
host2 = "vmf9x8664.testdomain.com"
port1 = 389
port2 = 389
rootdn1 = "cn=directory manager"
rootpw1 = 'secret12'
rootdn2 = "cn=directory manager"
rootpw2 = 'secret12'

mux = DSAdmin(host1, port1, rootdn1, rootpw1)
farm = DSAdmin(host2, port2, rootdn2, rootpw2)

suffix = 'dc=chaintest'
# add the suffix
farm.addSuffix(suffix)
# add the suffix entry
dn = suffix
ent = Entry(dn)
ent.setValues('objectclass', 'domain')
farm.add_s(ent)

# setup chaining
mux.setupChaining(farm, suffix, False)

# add ctuser on farm
dn = 'uid=ctuser,' + suffix
ent = Entry(dn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', 'Chain Testuser')
ent.setValues('sn', 'Testuser')
ent.setValues('givenName', 'Chain')

farm.add_s(ent)
