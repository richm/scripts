from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry

import os
import sys
import time
import ldap
import pprint
import base64, hashlib

host1 = "localhost.localdomain"
cfgport = 1100
port1 = cfgport + 30

basedn = 'dc=example,dc=com'
newinst = 'ds'
os.environ['USE_GDB'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

userdn = "ou=people," + basedn

# make password
password = "password"
sha = hashlib.sha1(password)
hashedpw = "{SHA}" + base64.b64encode(sha.digest()) + '\n' # add extra bogus newline

# add user entry
dn = "cn=foo," + userdn
ent = Entry(dn)
ent.setValues('objectclass', 'person')
ent.setValues('sn', 'Foo')
ent.setValues('userPassword', hashedpw)
srv.add_s(ent)

# attempt to bind as user
user = ldap.ldapobject.SimpleLDAPObject('ldap://%s:%d' % (host1,port1))
user.simple_bind_s(dn, password)
user.unbind_s()

# add another user entry
dn = "cn=bar," + userdn
ent = Entry(dn)
ent.setValues('objectclass', 'person')
ent.setValues('sn', 'Foo')
ent.setValues('userPassword', password)
srv.add_s(ent)

# attempt to bind as user
user = ldap.ldapobject.SimpleLDAPObject('ldap://%s:%d' % (host1,port1))
user.simple_bind_s(dn, password)
user.unbind_s()
