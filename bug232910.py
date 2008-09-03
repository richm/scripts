
import os
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
})
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')

m1.importLDIF(initfile, '', "userRoot", True)
