import os
import sys
import time
import ldap
from ldap.ldapobject import SimpleLDAPObject
import pprint
import base64, hashlib
from dsadmin import DSAdmin, Entry
from dirsyncctrl import DirSyncCtrl

host1 = "vmhost.testdomain.com"
port1 = 1200
secport1 = port1+1
rootdn = "cn=directory manager"
rootpw = "password"

basedn = 'dc=example,dc=com'
newinst = 'ds'
os.environ['USE_VALGRIND'] = "1"

srv = DSAdmin.createInstance({
	'newrootpw': rootpw,
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

print "turn on syntax checking and trivial words checking"
attr = "passwordCheckSyntax"
mod = [(ldap.MOD_REPLACE, attr, "on")]
srv.modify_s("cn=config", mod)

print "add a user with a password"
dn = "uid=scarter,dc=example,dc=com"
bindpw = "SPrain12"
ent = Entry(dn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', 'Sam Carter')
ent.setValues('sn', 'Carter')
ent.setValues('givenName', 'Sam')
ent.setValues('userPassword', bindpw)
srv.add_s(ent)
