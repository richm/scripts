
import os
import time
import ldap
import ldif
import tempfile
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
port1 = 1110
basedn = 'dc=example,dc=com'

os.environ['USE_GDB'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'srv',
	'newsuffix': basedn,
    'no_admin': True
})
del os.environ['USE_GDB']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (srv.sroot,srv.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')

print "import the ldif file"
srv.importLDIF(initfile, '', "userRoot", True)

time.sleep(1)

filt = '(mail=ScArTeR@ExAmPlE.cOm)'
print "see if case insensitive search of mail works", filt

ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt)
for ent in ents:
    print "found entry", ent

filt = '(mail=scarter@example.com)'
print "see if case insensitive search of mail works", filt

ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt)
for ent in ents:
    print "found entry", ent

#srv.setLogLevel(1)

print "add matching rule for mail case insensitive"
mod = [(ldap.MOD_ADD, 'nsMatchingRule', '1.3.6.1.4.1.1466.115.121.1.15')]
srv.modIndex(basedn, 'mail', mod)

filt = '(mail=ScArTeR@ExAmPlE.cOm)'
print "see if case insensitive search of mail works", filt

ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt)
found = False
for ent in ents:
    print "found entry", ent
    found = True

if not found:
    print "no entries found - try re-indexing"
    srv.createIndex(basedn, 'mail')
    filt = '(mail=ScArTeR@ExAmPlE.cOm)'
    print "see if case insensitive search of mail works", filt

    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, filt)
    for ent in ents:
        print "found entry", ent
