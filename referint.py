import os
import sys
import time
import ldap
import tempfile
import shutil
from dsadmin import DSAdmin, Entry

print "start"
host1 = "localhost.localdomain"
port1 = 1389
basedn = "dc=example,dc=com"
dom = 'example.com'
dnsdom = 'localdomain'

cfgfd = tempfile.NamedTemporaryFile(delete=False)
print "enable referint"
dn1 = "cn=referential integrity postoperation,cn=plugins,cn=config"
dn2 = "cn=config,cn=ldbm database,cn=plugins,cn=config"
cfgfd.write("""dn: %s
changetype: modify
replace: nsslapd-pluginEnabled
replace: nsslapd-pluginType
nsslapd-pluginEnabled: on
nsslapd-pluginType: betxnpostoperation

dn: %s
changetype: modify
replace: nsslapd-db-logbuf-size
nsslapd-db-logbuf-size: 10000000
""" % (dn1, dn2))
cfgfd.close()
os.chmod(cfgfd.name, 0644)

#os.environ['USE_VALGRIND'] = '1'
ds = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'ds',
	'newsuffix': basedn,
	'no_admin': True,
        'ConfigFile': [cfgfd.name]
})
os.unlink(cfgfd.name)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (ds.sroot,ds.inst)
else:
    initfilesrc = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
    initfile = "%s/var/lib/dirsrv/slapd-%s/ldif/Example.ldif" % (os.environ.get('PREFIX', ''), 'ds')
    shutil.copy(initfilesrc, initfile)
print "importing database"
ds.importLDIF(initfile, '', "userRoot", False)

print "get the list of all users"
ents = ds.search_s(basedn, ldap.SCOPE_SUBTREE, "objectclass=inetorgperson")
for ii in xrange(0, 5):
    groupdn = "cn=testgroup%d,ou=groups,%s" % (ii, basedn)
    print "add a bunch of users to the group", groupdn
    ent = Entry(groupdn)
    ent.setValues('objectclass', 'groupOfNames')
    ent.setValues('member', [ee.dn for ee in ents])
    ds.add_s(ent)

#print "delete some users"
#for ent in ents:
#    print "deleting user", ent.dn
#    ds.delete_s(ent.dn)
