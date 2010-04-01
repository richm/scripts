
import os
import time
import ldap
import ldapurl
import ldif
import tempfile
from dsadmin import DSAdmin, Entry
from ldap.ldapobject import SimpleLDAPObject
import pprint

host1 = "localhost.localdomain"
port1 = 1110
basedn = 'dc=example,dc=com'

ldapifilepath = os.environ.get('PREFIX', "") + "/var/run/slapd-srv.socket"

os.environ['USE_GDB'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'srv',
	'newsuffix': basedn,
    'no_admin': True,
    'ldapifilepath': ldapifilepath
})
del os.environ['USE_GDB']

ldapiurl = ldapurl.LDAPUrl(None, "ldapi", ldapifilepath)

conn = SimpleLDAPObject(ldapiurl.initializeUrl())
print "connecting to", ldapiurl.initializeUrl()

conn.simple_bind_s("cn=directory manager", "password")
ents = conn.search_s("", ldap.SCOPE_BASE)
pprint.pprint(ents)
