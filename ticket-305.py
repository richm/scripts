
import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
port1 = 1389
port2 = port1+10
basedn = "dc=example,dc=com"

createargs = {
    'newrootpw': 'password',
    'newhost': host1,
    'newport': port1,
    'newinst': 'ds',
    'newsuffix': basedn,
    'no_admin': True
}

os.environ['USE_VALGRIND'] = "1"
ds = DSAdmin.createInstance(createargs)
del os.environ['USE_VALGRIND']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (ds.sroot,ds.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
ds.importLDIF(initfile, '', "userRoot", True)

userdn = "uid=scarter,ou=people," + basedn
userpw = "sprain"

print "Allow local password policy"
p = {'nsslapd-pwpolicy-local':'on'}
ds.setPwdPolicy(p)
print "Set up password policy . . ."
nattempts = 5
pwdpolicy = {
    'passwordMaxAge': 7776000,
    'passwordMustChange': 'on',
    'passwordExp': 'on',
    'passwordHistory': 'on',
    'passwordMinAge': 172800,
    'passwordWarning': 864000,
    'passwordInHistory': 5,
    'passwordCheckSyntax': 'on',
    'passwordGraceLimit': 3,
    'passwordLockoutDuration': 1800,
    'passwordResetFailureCount': 1800,
    'passwordMaxFailure': nattempts,
    'passwordLockout': 'on'
}
ds.subtreePwdPolicy(basedn, pwdpolicy)
pwdpolicy['passwordMaxFailure'] = nattempts-1
ds.subtreePwdPolicy("ou=people," + basedn, pwdpolicy)
pwdpolicy['passwordMaxFailure'] = nattempts-2
ds.userPwdPolicy(userdn, pwdpolicy)

print "get pwpolicy settings"
ents = ds.search_s(basedn, ldap.SCOPE_SUBTREE, '(&(objectclass=ldapsubentry)(objectclass=passwordpolicy))')
poldns = [ent.dn for ent in ents]
print "policy entries: " + str(poldns)
otherdn = "uid=alutz,ou=people," + basedn

cmpattrs = ["pwdpolicysubentry", 'nsrole']
#cmpattrs = ["pwdpolicysubentry"]
cmpvals = poldns
#cmpvals = poldns[0:1]
dns = [userdn, otherdn, "ou=people," + basedn, basedn]
#dns = [userdn]

for iters in xrange(0,1):
    msgids = []
    for dn in dns:
        for attr in cmpattrs:
            for val in cmpvals:
                print "send compare for %s %s %s" % (dn, attr, val)
                msgid = ds.compare(dn, attr, val)
                msgids.append((msgid,dn,attr,val))
    for msgid,dn,attr,val in msgids:
        print "read result for %s %s %s %d" % (dn, attr, val, msgid)
        try:
            rtype, rdata = ds.result(msgid)
        except ldap.COMPARE_TRUE:
            print "COMPARE TRUE for val [%s] for attr [%s] in DN [%s]" % (val, attr, dn)
        except ldap.COMPARE_FALSE:
            print "COMPARE FALSE for val [%s] for attr [%s] in DN [%s]" % (val, attr, dn)
        except ldap.NO_SUCH_ATTRIBUTE:
            print "NOT FOUND for val [%s] for attr [%s] in DN [%s]" % (val, attr, dn)
