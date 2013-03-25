from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport+10
port2 = cfgport+20
basedn = "dc=example,dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'log'   : True
}

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': True,
    'no_admin': True
}, m1replargs
)
#del os.environ['USE_DBX']

m2replargs = m1replargs

#os.environ['USE_DBX'] = 1
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
	'verbose': True,
    'no_admin': True
}, m2replargs
)
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
m1.importLDIF(initfile, '', "userRoot", True)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(5)
m1.startReplication_async(agmtm1tom2)
print "waiting for init to finish"
time.sleep(5)
m1.waitForReplInit(agmtm1tom2)
agmtm2tom1 = m2.setupAgreement(m1, m2replargs)

userdn = "uid=scarter,ou=people," + basedn
print "do a mod to see if replication is working . . ."
mymod = [(ldap.MOD_REPLACE, "description", "changed")]
m1.modify_s(userdn, mymod)
time.sleep(5)
ent = m2.getEntry(userdn, ldap.SCOPE_BASE)
if ent.description == "changed":
    print "replication is working"
else:
    print "replication is not working"
    sys.exit(1)

print "Set up password policy . . ."
nattempts = 5
pwdpolicy = {
    'passwordMaxAge': 7776000,
    'passwordMustChange': 'on',
    'passwordExp': 'on',
    'passwordHistory': 'on',
    'passwordMinAge': 172800,
    'passwordWarning': 864000,
    'nsslapd-pwpolicy-local': 'on',
    'passwordInHistory': 5,
    'passwordCheckSyntax': 'on',
    'passwordGraceLimit': 3,
    'passwordLockoutDuration': 1800,
    'passwordResetFailureCount': 1800,
    'passwordMaxFailure': nattempts,
    'passwordLockout': 'on'
}
m1.setPwdPolicy(pwdpolicy)
m2.setPwdPolicy(pwdpolicy)
#m1.setPwdPolicy(passwordLockout="on", passwordisglobalpolicy="on")
#m2.setPwdPolicy(passwordLockout="on", passwordisglobalpolicy="on")

opattrs = [ 'passwordRetryCount', 'retryCountResetTime', 'accountUnlockTime', 'passwordExpirationTime', 'modifyTimestamp', 'modifiersName' ]
print "Do %d attempts to bind with incorrect password . . ." % nattempts
userconn = DSAdmin(host1, port1)
for xx in range(0, nattempts+1):
    try:
        userconn.simple_bind_s(userdn, "boguspassword")
    except ldap.INVALID_CREDENTIALS: print "password was not correct"
    except ldap.CONSTRAINT_VIOLATION: print "too many password attempts"
    print "m1 pwd attrs"
    print "%s" % m1.getEntry(userdn, ldap.SCOPE_BASE, "(objectclass=*)", opattrs)
    print "m2 pwd attrs"
    print "%s" % m2.getEntry(userdn, ldap.SCOPE_BASE, "(objectclass=*)", opattrs)
    mymod = [(ldap.MOD_REPLACE, "description", "changed %d" % xx)]
    m1.modify_s(userdn, mymod)
userconn.unbind()

print "sleep to let repl propagate . . ."
time.sleep(5)

print "do a mod to see if replication is still working . . ."
mymod = [(ldap.MOD_REPLACE, "description", "changed back")]
m1.modify_s(userdn, mymod)
time.sleep(5)
ent = m2.getEntry(userdn, ldap.SCOPE_BASE)
if ent.description == "changed back":
    print "replication is still working"
else:
    print "replication is not working any longer"
    sys.exit(1)

nents = 1000
svrs = (m1, m2)
nsvrs = len(svrs)
print "Add %d entries alternately . . ." % nents
for ii in range(0,nents):
    dn = "cn=%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'testuser')
    svr = svrs[ii % nsvrs]
    svr.add_s(ent)
    print "Added %s to %s" % (dn, svr)

print "see if all entries are on both servers . . ."
time.sleep(10)
for ii in range(0,nents):
    dn = "cn=%d, %s" % (ii, basedn)
    try:
        ent = m1.getEntry(dn, ldap.SCOPE_BASE)
        ent = m2.getEntry(dn, ldap.SCOPE_BASE)
    except:
        print "Could not read entry", dn
        raise
