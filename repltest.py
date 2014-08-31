
import os
import sys
import time
import ldap
import logging
from lib389 import DirSrv, Entry, tools
from lib389.tools import DirSrvTools
from lib389._constants import LOG_REPLICA

logging.getLogger('lib389').setLevel(logging.WARN)
logging.getLogger('lib389.tools').setLevel(logging.WARN)

basedn = 'dc=example,dc=com'
rootdn = "cn=directory manager"
rootpw = 'password'
replbinddn = "cn=replrepl,cn=config"
replbindpw = "replrepl"
host1 = "localhost"
host2 = host1
port1 = 1389
port2 = port1 + 1000
replid = 1

createargs = {
    'prefix': os.environ.get('PREFIX', None),
	'newrootpw': rootpw,
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
    'newinstance': 'm1',
	'newsuffix': basedn,
    'no_admin': True
}

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': replbinddn,
	'bindpw': replbindpw,
    'log': True,
    'id': replid
}
replid += 1

agmtargs = {
    'suffix': basedn,
    'binddn': replbinddn,
    'bindpw': replbindpw
}

#os.environ['USE_DBX'] = "1"
m1 = tools.DirSrvTools.createInstance(createargs)
#del os.environ['USE_DBX']
m1.replicaSetupAll(m1replargs)

m2replargs = m1replargs
m2replargs['id'] = replid
replid += 1

createargs['newhost'] = host2
createargs['newport'] = port2
createargs['newinst'] = 'm2'
createargs['newinstance'] = 'm2'
#os.environ['USE_DBX'] = 1
m2 = tools.DirSrvTools.createInstance(createargs)
#del os.environ['USE_DBX']
m2.replicaSetupAll(m2replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.agreement.create(basedn, m2.host, m2.port, agmtargs)
m1.replica.start_and_wait(agmtm1tom2)
agmtm2tom1 = m2.agreement.create(basedn, m1.host, m1.port, agmtargs)

nents = 5
m1ents = range(nents)
m2ents = range(len(m1ents), len(m1ents)+nents+1)
print "Add %d entries to m2" % len(m2ents)
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m2.add_s(ent)
    print "Added m2 entry", dn

print "Add %d entries to m1" % len(m1ents)
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m1.add_s(ent)
    print "Added m1 entry", dn

print "Sleep for 5 seconds to let changes propagate . . ."
time.sleep(5)

print "see if m1 entries made it to m2"
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    print "found m2 entry", ent

print "see if m2 entries made it to m1"
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    print "found m1 entry", ent

print "Now, reinit m1 from m2.  This should have the effect of wiping out the changelog"
m2.startReplication_async(agmtm2tom1)
print "waiting for init to finish"
m2.waitForReplInit(agmtm2tom1)

print "Now the m1 and m2 RUV for m2 should have CSNs for m2 that are not in the m2 changelog"
m2ents = range(m2ents[-1]+1, m2ents[-1]+1+nents)
m1ents = range(m2ents[-1]+1, m2ents[-1]+1+nents)

print "Add entries to m2 - see if they are replicated to m1"
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m2.add_s(ent)
    print "Added m2 entry", dn

print "Add entries to m1 - see if they are replicated to m2"
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    m1.add_s(ent)
    print "Added m1 entry", dn

print "Sleep for 5 seconds to let changes propagate . . ."
time.sleep(5)

print "see if m2 entries made it to m1"
for ii in m2ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m1.getEntry(dn, ldap.SCOPE_BASE)
    print "found m1 entry", ent

print "see if m1 entries made it to m2"
for ii in m1ents:
    dn = "cn=%d, %s" % (ii, basedn)
    ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    print "found m2 entry", ent
