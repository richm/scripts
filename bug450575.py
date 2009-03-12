
import os
import sys
import time
import ldap
from ldap.controls import LDAPControl
from ldap.ldapobject import LDAPObject
from dsadmin import DSAdmin, Entry
import pprint

class TestCtrl(LDAPControl):
    """
    A dummy control
    """
    controlType = "1.2.3.4.5.6.7.8.9.0"

    def __init__(self,criticality=True):
        LDAPControl.__init__(self,TestCtrl.controlType,criticality)

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+10
secport1 = port1+1
port2 = cfgport+20
secport2 = port2+1
basedn = "dc=example,dc=com"
binddn = "cn=directory manager"
bindpw = "password"

#basedn = "dc=testdomain,dc=com"
#host1 = 'el4i386'
#port1 = 389
#m1 = DSAdmin(host1, port1, binddn, bindpw)

#os.environ['USE_VALGRIND'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
#del os.environ['USE_VALGRIND']

# initfile = ''
# if os.environ.has_key('SERVER_ROOT'):
#     initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
# else:
#     initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
# m1.importLDIF(initfile, '', "userRoot", True)

print "show active connections . . ."
ents = m1.search_s("cn=monitor", ldap.SCOPE_BASE, '(objectclass=*)', ['currentconnections', 'connection'])
for ent in ents:
    print ent
print "start search request . . ."
scope = ldap.SCOPE_SUBTREE;
filter = '(|(objectclass=*)(objectclass=nsTombstone))'
serverctrls = [TestCtrl()]
ents = m1.search_s(basedn, scope, filter)
print "search returned %d entries" % len(ents)
print "send abandon with controls . . ."
m1.abandon_ext(999, serverctrls)
print "send abandon without controls . . ."
msgid2 = m1.abandon_ext(999)
print "send unbind with controls . . ."
# for some reason, unbind_ext_s is not passing
# controls passed in - so have to set_option
m1.set_option(ldap.OPT_SERVER_CONTROLS, serverctrls)
m1.unbind_ext_s(serverctrls)
print "try a search after the unbind . . ."
try:
    ents = m1.search_s(basedn, scope, filter)
except ldap.LDAPError, e:
    print "caught exception", e

print "open new connection . . ."
m1 = DSAdmin(host1, port1, binddn, bindpw)
print "show active connections . . ."
ents = m1.search_s("cn=monitor", ldap.SCOPE_BASE, '(objectclass=*)', ['currentconnections', 'connection'])
for ent in ents:
    print ent
