import os
import sys
import time
import ldap
from ldap.ldapobject import SimpleLDAPObject
import pprint
import base64, hashlib
import struct
from dsadmin import DSAdmin, Entry
from ldap.controls import LDAPControl

host1 = "vmhost.testdomain.com"
port1 = 1200
secport1 = port1+1
rootdn = "cn=directory manager"
rootpw = "password"

basedn = 'dc=example,dc=com'
newinst = 'ds'
os.environ['USE_GDB'] = "1"

srv = DSAdmin.createInstance({
	'newrootpw': rootpw,
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

print "create new objectclass"
oc = "objectClasses: ( 9.99.999.9999.99999 NAME 'myAuxOc' DESC 'for the owner attribute' SUP top AUXILIARY MAY ( owner ) X-ORIGIN 'me' )"
srv.addObjClass(oc)

print "create usera"
dn = "uid=usera,ou=people," + basedn
useradn = dn
ent = Entry(dn)
ent.setValues('objectclass', ['inetOrgPerson', 'myAuxOc'])
ent.setValues('cn', 'User A')
ent.setValues('sn', 'A')
ent.setValues('givenName', 'User')
userapw = 'usera'
ent.setValues('userPassword', userapw)
srv.add_s(ent)

print "create userb"
dn = "uid=userb,ou=people," + basedn
userbdn = dn
ent = Entry(dn)
ent.setValues('objectclass', ['inetOrgPerson', 'myAuxOc'])
ent.setValues('cn', 'User B')
ent.setValues('sn', 'B')
ent.setValues('givenName', 'User')
userbpw = 'userb'
ent.setValues('userPassword', userbpw)
ent.setValues('owner', useradn)
srv.add_s(ent)

print "create aci to allow usera to set password in userb"
aci = '(targetattr="userPassword")(version 3.0; acl "Owners can set passwords"; allow(write) userattr="owner#USERDN";)'
mod = [(ldap.MOD_REPLACE, 'aci', aci)]
srv.modify_s(basedn, mod)

print "bind as usera"
aconn = SimpleLDAPObject('ldap://%s:%d' % (host1, port1))
aconn.simple_bind_s(useradn, userapw)

print "user a will modify user b userPassword"
userbpw = 'anewpassword'
mod = [(ldap.MOD_REPLACE, 'userPassword', userbpw)]
aconn.modify_s(userbdn, mod)

print "userb will attempt to bind with new password"
bconn = SimpleLDAPObject('ldap://%s:%d' % (host1, port1))
bconn.simple_bind_s(userbdn, userbpw)
