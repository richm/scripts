import os
import sys
import time
import ldap
import logging

from dsadmin import DSAdmin, Entry, tools
from dsadmin.tools import DSAdminTools

logging.getLogger('dsadmin').setLevel(logging.WARN)
logging.getLogger('dsadmin.tools').setLevel(logging.WARN)

host1 = "localhost.localdomain"
host2 = host1
host3 = host2
port1 = 1389
port2 = port1+10
port3 = port2+10
basedn = "dc=example,dc=com"
realm = "TESTDOMAIN.COM"

sasldir = os.environ['SASLDIR']
sysconffile = os.environ.get('PREFIX', '') + '/etc/sysconfig/dirsrv'
print "configure", sysconffile, "for kerberos"
f = file(sysconffile)
needkrb = True
lines = []
for line in f:
    if line.startswith('export KRB5_KTNAME'):
        needkrb = False
f.close()
if needkrb:
    f = file(sysconffile, "a")
    f.write('export KRB5_KTNAME=%s/ldap.%s.keytab\n' % (sasldir, host1))
    f.write('export HACK_PRINCIPAL_NAME=ldap/%s@%s\n' % (host1, realm))
    f.write('export KRB5CCNAME=FILE:bogus-mcbogus\n')
    f.write('export KRB5_CONFIG=/etc/krb5.conf.testdomain\n')
    f.write('export HACK_SASL_NOCANON=1\n')
    f.close()
else:
    print sysconffile, "already configured for kerberos"

configfile = [sasldir + '/replsaslmaps.ldif']

hostargs = {
    'newrootpw': 'password',
    'newhost': host1,
    'newport': port1,
    'newinst': 'm1',
    'newsuffix': basedn,
    'verbose': False,
    'ConfigFile': configfile,
    'prefix': os.environ.get('PREFIX', None),
    'no_admin': True
}

replid = 1
m1replargs = {
    'suffix': basedn,
    'bename': "userRoot",
    'binddn': "cn=replrepl,cn=config",
    'bindcn': "replrepl",
    'bindpw': "replrepl",
    'id': replid,
    'bindmethod': 'SASL/GSSAPI',
    'log'   : False
}

#os.environ['USE_GDB'] = "1"
m1 = tools.DSAdminTools.createAndSetupReplica(hostargs, m1replargs)
#del os.environ['USE_GDB']

hostargs['newhost'] = host2
hostargs['newport'] = port2
hostargs['newinst'] = 'm2'
m2replargs = m1replargs
replid += 1
m2replargs['id'] = replid

m2 = tools.DSAdminTools.createAndSetupReplica(hostargs, m2replargs)

hostargs['newhost'] = host3
hostargs['newport'] = port3
hostargs['newinst'] = 'm3'
m3replargs = m2replargs
replid += 1
m3replargs['id'] = replid

m3 = tools.DSAdminTools.createAndSetupReplica(hostargs, m3replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(5)
m1.startReplication(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

agmtm1tom3 = m1.setupAgreement(m3, m1replargs)
time.sleep(5)
m1.startReplication(agmtm1tom3)
agmtm3tom1 = m3.setupAgreement(m1, m3replargs)

agmtm2tom3 = m2.setupAgreement(m3, m2replargs)
agmtm3tom2 = m3.setupAgreement(m2, m3replargs)

for srv, agmts in ((m1, (agmtm1tom2, agmtm1tom3)), (m2, (agmtm2tom1, agmtm2tom3)), (m3, (agmtm3tom1, agmtm3tom2))):
    for agmt in agmts:
        print srv.getReplStatus(agmt)

srvs = (m1, m2, m3)
for ii in xrange(1,2000):
    srv = srvs[ii % len(srvs)]
    dn = "cn=user%d,%s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'user')
    srv.add_s(ent)

for srv, agmts in ((m1, (agmtm1tom2, agmtm1tom3)), (m2, (agmtm2tom1, agmtm2tom3)), (m3, (agmtm3tom1, agmtm3tom2))):
    for agmt in agmts:
        print srv.getReplStatus(agmt)
