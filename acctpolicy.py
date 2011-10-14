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
inactivetime = 120 # seconds
inactivetime2 = 5 # seconds

basedn = 'dc=example,dc=com'
newinst = 'ds'
#os.environ['USE_VALGRIND'] = "1"

srv = DSAdmin.createInstance({
	'newrootpw': rootpw,
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

print "load user ldif file"
initfile = os.environ['PREFIX'] + "/share/dirsrv/data/Example.ldif"
srv.importLDIF(initfile, '', "userRoot", True)

print "enable account policy"
mod = [(ldap.MOD_REPLACE, 'nsslapd-pluginenabled', 'on')]
srv.modify_s('cn=Account Policy Plugin,cn=plugins,cn=config', mod)

print "configure account policy"
mod = [(ldap.MOD_REPLACE, 'alwaysrecordlogin', 'yes'),
       (ldap.MOD_REPLACE, 'stateattrname', 'lastLoginTime'),
       (ldap.MOD_REPLACE, 'altstateattrname', 'createTimestamp'),
       (ldap.MOD_REPLACE, 'specattrname', 'acctPolicySubentry'),
       (ldap.MOD_REPLACE, 'limitattrname', 'accountInactivityLimit')]
srv.modify_s('cn=config,cn=Account Policy Plugin,cn=plugins,cn=config', mod)

print "restart server for changes to take effect"
srv.stop()
srv.start()

print "find scarter"
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=scarter', ['lastLoginTime', 'createTimestamp'])
userdn = ents[0].dn
pprint.pprint(ents[0])

print "bind as", userdn
conn = SimpleLDAPObject('ldap://%s:%d' % (host1, port1))
try:
    conn.simple_bind_s(userdn, 'sprain')
except ldap.CONSTRAINT_VIOLATION:
    print "user is prevented from logging in after", inactivetime, "seconds of inactivity"
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=scarter', ['lastLoginTime', 'createTimestamp'])
    print "lastLoginTime:", ents[0].lastLoginTime

print "sleep for a while . . ."
time.sleep(inactivetime)
print "bind as", userdn, "again - see if there is any account policy"
conn = SimpleLDAPObject('ldap://%s:%d' % (host1, port1))
try:
    conn.simple_bind_s(userdn, 'sprain')
except ldap.CONSTRAINT_VIOLATION:
    print "user is prevented from logging in after", inactivetime, "seconds of inactivity"
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=scarter', ['lastLoginTime', 'createTimestamp'])
    print "lastLoginTime:", ents[0].lastLoginTime

print "now configure global account policy"
mod = [(ldap.MOD_REPLACE, 'accountInactivityLimit', str(inactivetime))]
srv.modify_s('cn=config,cn=Account Policy Plugin,cn=plugins,cn=config', mod)

print "restart server for changes to take effect"
srv.stop()
srv.start()

print "bind as",userdn
conn = SimpleLDAPObject('ldap://%s:%d' % (host1, port1))
try:
    conn.simple_bind_s(userdn, 'sprain')
except ldap.CONSTRAINT_VIOLATION:
    print "user is prevented from logging in after", inactivetime, "seconds of inactivity"
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=scarter', ['lastLoginTime', 'createTimestamp'])
    print "lastLoginTime:", ents[0].lastLoginTime
time.sleep(1)

print "the entry with lastLoginTime"
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=scarter', ['lastLoginTime', 'createTimestamp'])
pprint.pprint(ents)

print "sleep", inactivetime
time.sleep(inactivetime)

print "bind as", userdn
try:
    conn.simple_bind_s(userdn, 'sprain')
except ldap.CONSTRAINT_VIOLATION:
    print "user is prevented from logging in after", inactivetime, "seconds of inactivity"
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=scarter', ['*', 'lastLoginTime', 'createTimestamp'])
    print "lastLoginTime:", ents[0].lastLoginTime

print "add account policy subentry"
acctdn = 'cn=AccountPolicy,' + basedn
ent = Entry(acctdn)
ent.setValues('objectClass', ['top', 'ldapsubentry', 'extensibleObject', 'accountpolicy'])
ent.setValues('accountInactivityLimit', str(inactivetime2))
srv.add_s(ent)

print "find another user"
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, "uid=mward")
userdn2 = ents[0].dn

print "add", acctdn, "to acctPolicySubentry in", userdn2
mod = [(ldap.MOD_REPLACE, 'acctPolicySubentry', acctdn)]
srv.modify_s(userdn2, mod)

print "bind as", userdn2
conn = SimpleLDAPObject('ldap://%s:%d' % (host1, port1))
try:
    conn.simple_bind_s(userdn2, 'normal')
except ldap.CONSTRAINT_VIOLATION:
    print "user is prevented from logging in after", inactivetime2, "seconds of inactivity"
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=mward', ['lastLoginTime', 'createTimestamp'])
    print "lastLoginTime:", ents[0].lastLoginTime
time.sleep(1)

print "the entry with lastLoginTime"
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=mward', ['lastLoginTime', 'createTimestamp'])
pprint.pprint(ents)

print "sleep", inactivetime2
time.sleep(inactivetime2)

print "bind as", userdn2
try:
    conn.simple_bind_s(userdn2, 'normal')
except ldap.CONSTRAINT_VIOLATION:
    print "user is prevented from logging in after", inactivetime2, "seconds of inactivity"
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, 'uid=mward', ['*', 'lastLoginTime', 'createTimestamp'])
    print "lastLoginTime:", ents[0].lastLoginTime
conn.unbind_s()
