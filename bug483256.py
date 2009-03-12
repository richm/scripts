
import os
import sys
import time
import ldap
from ldap.controls import LDAPControl
import struct
from dsadmin import DSAdmin, Entry
from dirsyncctrl import DirSyncCtrl

if os.environ.has_key('WINSYNC_USE_DS'):
    useds = True
else:
    useds = False

ipawinsync = False
if ipawinsync:
    usersubtree = "cn=users,cn=accounts"
else:
    usersubtree = "ou=people"

if useds:
    host1 = 'localhost'
    suffix = "dc=example,dc=com"
    realm = 'EXAMPLE.COM'
    adusersubtree = "ou=People"
else:
    host1 = 'vmhost'
    suffix = "dc=testdomain,dc=com"
    realm = 'TESTDOMAIN.COM'
    adusersubtree = "cn=Users"
port1 = 1200
root1 = "cn=directory manager"
rootpw1 = "secret12"

scope = ldap.SCOPE_SUBTREE
filter = "(objectclass=*)"
attrs = ['*', 'nsAccountLock', 'memberOf']

# need to base64 encode several AD attributes
Entry.base64_attrs.extend(['objectGUID', 'objectSid', 'parentGUID',
                           'userCertificate', 'nTSecurityDescriptor',
                           'logonHours'])
ipainit = ''
if useds:
    host2 = host1
    port2 = port1+10
    root2 = root1
    rootpw2 = rootpw1
    if ipawinsync:
        ipainit = '/share/dswinsyncipa/ipainit.ldif'
else:
    host2 = 'win2k3svr'
    port2 = 389
    root2 = "cn=administrator,cn=users,DC=testdomain,DC=com"
    rootpw2 = "Ornette1"
    if ipawinsync:
        ipainit = '/share/dswinsyncipa/ipainittestdomain.ldif'

replargs = {
	'suffix': suffix,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
    'winsync': True,
    'log': False
}

if ipawinsync:
    configfile = ['/share/dswinsyncipa/testipawinsyncplugin.ldif']
    schemafile = ['/share/freeipa/freeipa/ipa-server/ipa-install/share/60ipaconfig.ldif',
                  '/share/freeipa/freeipa/ipa-server/ipa-install/share/60kerberos.ldif',
                  '/share/freeipa/freeipa/ipa-server/ipa-install/share/60radius.ldif']
else:
    configfile = []
    schemafile = []

os.environ['USE_VALGRIND'] = "1"
ds = DSAdmin.createAndSetupReplica({
	'newrootpw': rootpw1,
	'newhost': host1,
	'newport': port1,
	'newinst': 'ds',
	'newsuffix': suffix,
	'verbose': False,
    'no_admin': True,
    'ConfigFile': configfile,
    'SchemaFile': schemafile
}, replargs
)
os.environ['USE_VALGRIND'] = ''
os.environ.pop('USE_VALGRIND')
try:
    foo = os.environ['USE_VALGRIND']
except KeyError:
    print "should no longer have USE_VALGRIND env. var"

if ipawinsync:
    print "Enable the memberof plugin . . ."
    dn = "cn=MemberOf Plugin,cn=plugins,cn=config"
    mod = [(ldap.MOD_REPLACE, 'nsslapd-pluginenabled', 'on')]
    ds.modify_s(dn, mod)
    ds.stop()
    ds.start()

    ds.importLDIF(ipainit, suffix)

if useds:
    ad = DSAdmin.createInstance({
        'newrootpw': rootpw2,
        'newhost': host2,
        'newport': port2,
        'newinst': 'ad',
        'newsuffix': suffix,
        'verbose': False,
        'no_admin': True
    })
    print "Fake AD needs extra schema . . ."
    oidnum = 10000000
    ad.addAttr("( 2.16.840.1.113730.3.1.%d NAME 'samAccountName' DESC 'AD uid attribute' SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE )" % oidnum)
    oidnum = oidnum + 1
    ad.addAttr("( 2.16.840.1.113730.3.1.%d NAME 'objectGUID' DESC 'AD uuid attribute' SYNTAX 1.3.6.1.4.1.1466.115.121.1.5 SINGLE-VALUE )" % oidnum)
    oidnum = oidnum + 1
    ad.addAttr("( 2.16.840.1.113730.3.1.%d NAME 'userAccountControl' DESC 'AD user account control' SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )" % oidnum)
    oidnum = oidnum + 1
    ad.addObjClass("( 2.16.840.1.113730.3.2.%d NAME 'adPerson' DESC 'AD person mixin' SUP top AUXILIARY MAY ( samAccountName $ objectGUID $ name $ userAccountControl ) )" % oidnum)
    oidnum = oidnum + 1
    ad.addAttr("( 2.16.840.1.113730.3.1.%d NAME 'groupType' DESC 'AD group type' SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE X-ORIGIN 'Netscape NT Synchronization' )" % oidnum)
    oidnum = oidnum + 1
    ad.addObjClass("( 2.16.840.1.113730.3.2.%d NAME 'group' DESC 'AD group' SUP top STRUCTURAL MAY ( samAccountName $ groupType $ objectGUID $ name $ member $ ou $ cn $ description ) )" % oidnum)
    oidnum = oidnum + 1
    aduserObjClasses = ['adPerson']
else:
    aduserObjClasses = ['top', 'person', 'organizationalperson', 'user']
    ad = DSAdmin(host2, port2, root2, rootpw2)

# the list of users we want to check to see if they were synced
userids = {}

# All IPA users must have these objectclasses - they should be
# the same as in the cn=ipaConfig ipaUserObjectClasses list
# ntUser either by the winsync code, or when you want an
# existing IPA user to be synced with AD
userObjClasses = [
    'top', 'person', 'organizationalPerson', 'inetOrgPerson'
]

if ipawinsync:
    useObjClasses.extend(['inetUser', 'posixAccount', 'krbPrincipalAux', 'radiusprofile'])

# array of hashes
userAcctVals = [
    {'description': 'normal, regular AD account',
     'userAccountControl': 512},
    {'description': 'normal, regular AD account disabled',
     'userAccountControl': 512 + 2},
    {'description': 'normal, regular AD account, do not expire password',
     'userAccountControl': 512 + 65536},
    {'description': 'normal, regular AD account disabled, do not expire password',
     'userAccountControl': 512 + 2 + 65536}
]

userids_disabled = {}
if useds:
    print "Create sub-ou's on the AD side and add users . . ."
    ii = 0
    dns = ['ou=people,' + suffix,
           'ou=1,ou=people,' + suffix, 'ou=2,ou=people,' + suffix,
           'ou=11,ou=1,ou=people,' + suffix,
           'ou=12,ou=1,ou=people,' + suffix]
    for dn in dns:
        ent = Entry(dn)
        ent.setValues('objectclass', 'organizationalUnit')
        try: ad.add_s(ent)
        except ldap.ALREADY_EXISTS: pass
        print "Add users to", dn
        for jj in range(0,5):
            strii = str(ii)
            userdn = 'cn=Test User' + strii + ',' + dn
            ent = Entry(userdn)
            userid = 'userid' + strii
            ent.setValues('objectclass', ['person', 'adPerson'])
            ent.setValues('sn', 'User' + strii)
            ent.setValues('samAccountName', userid)
            ent.setValues('objectGUID', struct.pack('B', ii))
            ent.setValues('name', 'Test User' + strii) # same as cn
            kk = ii % len(userAcctVals)
            for attr, val in userAcctVals[kk].iteritems():
                ent.setValues(attr, str(val))
                if str(val).find("account disabled") > -1:
                    userids_disabled[userid] = userid
            try: ad.add_s(ent)
            except ldap.ALREADY_EXISTS: pass
            userids[userid] = userdn
            ii += 1

    groupids = []
    print "Create an AD group entry"
    groupid = ii
    groupdn = "ou=Group%d,ou=people,%s" % (groupid, suffix)                                      
    ent = Entry(groupdn)
    ent.setValues('objectclass', 'group')
    ent.setValues('groupType', '2')
    ent.setValues('objectGUID', struct.pack('B', groupid))
    ent.setValues('member', 'cn=Test User0, ou=people,' + suffix)
    ent.setValues('description', 'should not be synced to DS')
    try: ad.add_s(ent)
    except ldap.ALREADY_EXISTS: pass
    groupids.append(ii)
    ii += 1
else:
    print "Search the AD to get the entries which will be returned with the dirsync control"
    ents = ad.search_ext_s(suffix, scope, '(objectclass=user)',
                           None, 0, [DirSyncCtrl(1, 0, -1)])
    for ent in ents:
        print "Entry", ent.dn
        if not ent.userAccountControl:
            print "\thas no userAccountControl - skipping"
            continue
        val = int(ent.userAccountControl)
        if val & 0x20: # PASSWD_NOTREQD
            print "\tis marked as no password required - skipping"
            continue            
        if val & 0x200: # a normal account
            ent.setValues('nTSecurityDescriptor', '')
            if ent.isCriticalSystemObject:
                print "\tisCriticalSystemObject - skipping"
                continue
            if ent.samaccountname.startswith("SUPPORT_"):
                print "\tis special entry", ent.samaccountname, "- skipping"
                continue
            userids[ent.samaccountname] = ent.dn
            if val & 0x2: # account is disabled
                userids_disabled[ent.samaccountname] = ent.samaccountname
                print "\tis disabled", val
            else:
                print "\tis enabled", val
        else:
            print "\tis not a normal account - val", ent.userAccountControl
            continue

idnum = 0
def makeDSUserEnt():
    global idnum
    id = str(idnum)
    userid = 'testuser' + id
    dn = 'uid=%s,%s,%s' % (userid, usersubtree, suffix)
    ent = Entry(dn)
    ent.setValues('objectclass', userObjClasses)
    ent.setValues('cn', 'Test User' + id)
    ent.setValues('sn', 'User' + id)
    ent.setValues('uid', userid)
    ent.setValues('userPassword', 'Password' + id)
    if ipawinsync:
        ent.setValues('krbPrincipalName', '%s@%s' % (userid, realm))
        ent.setValues('uidNumber', str(500+idnum))
        ent.setValues('gidNumber', '1002')
        ent.setValues('homeDirectory', '/home/' + userid)
        if jj % 2:
            ent.setValues('description', 'User added disabled to DS')
        else:
            ent.setValues('description', 'User added enabled to DS')
    idnum += 1
    return ent

def makeADUserEnt():
    global idnum
    id = str(idnum)
    userid = 'testuser' + id
    cn = 'Test User' + id
    dn = 'cn=%s,%s,%s' % (cn, adusersubtree, suffix)
    ent = Entry(dn)
    ent.setValues('objectclass', aduserObjClasses)
    ent.setValues('cn', cn)
    ent.setValues('sn', 'User' + id)
    ent.setValues('userPrincipalName', '%s@%s' % (userid, realm))
    ent.setValues('sAMAccountName', userid)
    idnum += 1
    return ent

telnum1 = '888 555-1212'
telnum2 = '800 555-1212'
print "Add initial users to the DS side . . ."
enabled_ds_users = {}
disabled_ds_users = {}
if useds:
    for jj in xrange(0, ii):
        if not jj % 3: continue
        strjj = str(jj)
        userid = "userid" + strjj
        if not userids.has_key(userid): continue
        dn = "uid=%s,%s,%s" % (userid, usersubtree, suffix)
        ent = Entry(dn)
        ent.setValues('objectclass', userObjClasses)
        if ipawinsync:
            ent.setValues('krbPrincipalName', '%s@%s' % (userid, realm))
            ent.setValues('uidNumber', str(500+jj))
            ent.setValues('gidNumber', '1002')
            ent.setValues('homeDirectory', '/home/' + userid)
        ent.setValues('cn', 'Test User' + strjj)
        ent.setValues('sn', 'User' + strjj)
        ent.setValues('ou', 'people')
        if jj % 2:
            ent.setValues('description', 'User added disabled to DS')
        else:
            ent.setValues('description', 'User added enabled to DS')
        try: ds.add_s(ent)
        except ldap.ALREADY_EXISTS: pass
        if ipawinsync and (jj % 2):
            print "Add user to inactive group"
            groupdn = 'cn=inactivated,cn=account inactivation,cn=accounts,' + suffix
            disabled_ds_users[userid] = dn
            mod = [(ldap.MOD_ADD, 'member', dn)]
            ds.modify_s(groupdn, mod)
        else:
            print "User is activated by default"
            enabled_ds_users[userid] = dn
else:
    for userid in ['testuser', 'testuser2', 'testuser5']:
        dn = "uid=%s,%s,%s" % (userid, usersubtree, suffix)
        ent = Entry(dn)
        if userid == 'testuser':
            foo = userObjClasses[:] # makes a copy
            foo.append('ntUser')
            ent.setValues('objectclass', foo)
            ent.setValues('ntUserDomainId', userid)
        else:
            ent.setValues('objectclass', userObjClasses)
        if ipawinsync:
            ent.setValues('krbPrincipalName', '%s@%s' % (userid, realm))
            ent.setValues('uidNumber', '99999')
            ent.setValues('gidNumber', '1002')
            ent.setValues('homeDirectory', '/home/' + userid)
        ent.setValues('cn', 'Test User' + userid)
        ent.setValues('sn', 'User' + userid)
        ent.setValues('ou', 'people')
        ent.setValues('telephoneNumber', telnum1)
        if userid == 'testuser':
            ent.setValues('description', 'User added disabled to DS')
        else:
            ent.setValues('description', 'User added enabled to DS')
        try: ds.add_s(ent)
        except ldap.ALREADY_EXISTS: pass
        if ipawinsync and (userid == 'testuser'):
            print "Add user to inactive group"
            groupdn = 'cn=inactivated,cn=account inactivation,cn=accounts,' + suffix
            disabled_ds_users[userid] = dn
            mod = [(ldap.MOD_ADD, 'member', dn)]
            ds.modify_s(groupdn, mod)
        else:
            print "User is active by default"
            enabled_ds_users[userid] = dn

ds.setLogLevel(0)
ds.setLogLevel(8192)
#ds.setLogLevel(65536)

replargs['binddn'] = root2
replargs['bindpw'] = rootpw2
replargs['win_subtree'] = adusersubtree + "," + suffix
replargs['ds_subtree'] = usersubtree + ',' + suffix
replargs['interval'] = '10'

agmtdn = ds.setupAgreement(ad, replargs)

time.sleep(5)

print "repl status:", ds.getReplStatus(agmtdn)

ds.startReplication(agmtdn)

time.sleep(5)

print "repl status:", ds.getReplStatus(agmtdn)

idnum = 6
userObjClasses.append('ntuser')
ent = makeDSUserEnt()
ent.dn = 'cn=' + ent.cn + ',' + usersubtree + "," + suffix
ent.setValues('ntUserDomainId', ent.uid)
ent.setValues('ntUserCreateNewAccount', 'true')
dn1 = ent.dn
print "Add user", dn1
ds.add_s(ent)

uid = "testuser7"
ent.dn = "cn=Test User7," + dn1
ent.setValues('cn', 'Test User7')
ent.setValues('uid', uid)
ent.setValues('ntUserDomainId', uid)
print "Add user", ent.dn
ds.add_s(ent)
dn2 = ent.dn

dn = "cn=testgroup," + usersubtree + "," + suffix
ent = Entry(dn)
ent.setValues('objectclass', ['top', 'groupOfUniqueNames', 'ntgroup'])
ent.setValues('uniquemember', [dn1, dn2])
ent.setValues('ntUserDomainId', 'testgroup')
ent.setValues('ntGroupCreateNewGroup', 'true')
print "Add group", ent.dn
ds.add_s(ent)

print "modify", dn2
mod = [(ldap.MOD_ADD, 'description', 'a description')]
ds.modify_s(dn2, mod)

print "Wait for the magic to happen . . ."
time.sleep(5)
print "repl status:", ds.getReplStatus(agmtdn)

print "AD testuser6 entry:"
ents = ad.search_s(suffix, scope, "(samaccountname=testuser6)")
print ents[0]
print "AD testuser7 entry:"
ents = ad.search_s(suffix, scope, "(samaccountname=testuser7)")
print ents[0]
print "AD testgroup entry:"
ents = ad.search_s(suffix, scope, "(samaccountname=testgroup)")
print ents[0]
