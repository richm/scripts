
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry, LEAF_TYPE

host1 = "localhost.localdomain"
host2 = host1
port1 = 1389
secport1 = port1+1
port2 = port1+1000
secport2 = port2+1
basedn = "dc=example,dc=com"

#os.environ['USE_DBX'] = "1"
m1createargs = {
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'no_admin': True
}
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
        'starttls': True,
        'chain' : True
}

m1 = DSAdmin.createAndSetupReplica(m1createargs, m1replargs)
#del os.environ['USE_DBX']

#os.environ['USE_DBX'] = 1
# copy c1 args from m1
c1createargs = dict([(key,val) for key,val in m1createargs.iteritems()])
c1['newhost'] = host2
c1['newport'] = port2
c1['newinst'] = 'c1'
c1replargs = dict([(key,val) for key,val in m1replargs.iteritems()])
c1replargs['type'] = LEAF_TYPE
clreplargs['chainargs'] = {'nsUseStartTLS': 'TRUE'}

#os.environ['USE_DBX'] = "1"
c1 = DSAdmin.createAndSetupReplica(c1createargs, c1replargs)
#del os.environ['USE_DBX']

sslargs = {'nsSSLPersonalitySSL':'localhost-cert'}
m1.setupSSL(secport1, sslargs)
c1.setupSSL(secport2, sslargs)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers . . ."
agmtm1toc1 = m1.setupAgreement(c1, m1replargs)
print "starting replication . . ."
m1.startReplication(agmtm1toc1)
print "Replication started"

print "Press Enter to continue . . ."
foo = sys.stdin.readline()

print "modify entry on m1"
dn = "uid=scarter,ou=people,dc=example,dc=com"
mod = [(ldap.MOD_ADD, 'description', 'description')]
m1.modify_s(dn, mod)
c1.waitForEntry(dn, 10, 'description')

print "Modify entry on c1"
dn = "uid=jvedder,ou=people,dc=example,dc=com"
cc1 = DSAdmin(host2, port2, dn, "befitting")
mod = [(ldap.MOD_REPLACE, 'telephonenumber', '123456789')]
cc1.modify_s(dn, mod)
print "Wait for mod to show up on m1"
time.sleep(10)

ents = m1.search_s(dn, ldap.SCOPE_BASE, '(objectclass=*)', ['telephonenumber'])
ent = ents[0]
if ent.telephonenumber == '123456789':
    print "m1 success - telephonenumber changed"
else:
    print "m1 failed - value is still " + ent.telephonenumber
ents = c1.search_s(dn, ldap.SCOPE_BASE, '(objectclass=*)', ['telephonenumber'])
ent = ents[0]
if ent.telephonenumber == '123456789':
    print "c1 success - telephonenumber changed"
else:
    print "c1 failed - value is still " + ent.telephonenumber
