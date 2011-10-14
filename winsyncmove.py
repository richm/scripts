
import os
import sys
import time
import ldap
import tempfile
from ldap.controls import LDAPControl
import struct
from dsadmin import DSAdmin, Entry
from dirsyncctrl import DirSyncCtrl

if os.environ.has_key('WINSYNC_USE_DS'):
    useds = True
else:
    useds = False
    # require SSL to talk to AD
    ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, os.environ["SECDIR"])

ipawinsync = False
if 'IPAWINSYNCROOT' in os.environ:
    ipawinsync = True

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
    adusersubtree = "cn=Test"
#    adusersubtree = "cn=Users"
port1 = 1200
secport1 = 1201
root1 = "cn=directory manager"
rootpw1 = "password"

scope = ldap.SCOPE_SUBTREE
filter = "(objectclass=*)"
dsattrs = ['*', 'nsAccountLock', 'memberOf']

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
    host2 = 'w2k8x8664.testdomain.com'
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
    ipawinsyncroot = os.environ.get('IPAWINSYNCROOT', os.environ.get('PREFIX', '') + '/usr/local')
    configfile = ipawinsyncroot + '/share/ipa/ipa-winsync-conf.ldif'
    plugin = ipawinsyncroot + '/lib/dirsrv/plugins/libipa_winsync.so'
    cfgfd = tempfile.NamedTemporaryFile(delete=False)
    cfgin = file(configfile, 'r')
    for line in cfgin:
        if line.startswith('nsslapd-pluginpath:'):
            cfgfd.write('nsslapd-pluginpath: ' + plugin + "\n")
        elif line.lower().startswith('ipawinsyncuserattr: gidnumber'):
            pass # skip it
        else:
            cfgfd.write(line)
    cfgfd.write("ipaWinSyncUserAttr: title unknown\n")
    cfgfd.close()
    cfgin.close()
    os.chmod(cfgfd.name, 0644)
    configfile = [cfgfd.name]
    schemafile = ['/share/freeipa/freeipa/install/share/60ipaconfig.ldif',
                  '/share/freeipa/freeipa/install/share/60kerberos.ldif']
#                  '/share/freeipa/freeipa/install/share/60radius.ldif']
else:
    configfile = []
    schemafile = []
    cfgfd = None

os.environ['USE_GDB'] = "1"
ds = DSAdmin.createInstance({
	'newrootpw': rootpw1,
	'newhost': host1,
	'newport': port1,
	'newinst': 'ds',
	'newsuffix': suffix,
	'verbose': False,
        'no_admin': True,
        'ConfigFile': configfile,
        'SchemaFile': schemafile
})
if cfgfd:
    os.unlink(cfgfd.name)

ds.setupSSL(secport1)

ds.replicaSetupAll(replargs)

if ipawinsync:
    print "Enable the memberof plugin . . ."
    dn = "cn=MemberOf Plugin,cn=plugins,cn=config"
    mod = [(ldap.MOD_REPLACE, 'nsslapd-pluginenabled', 'on')]
    ds.modify_s(dn, mod)
    ds.stop()
    ds.start()

    ds.importLDIF(ipainit, suffix, verbose=True)

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
    ad = DSAdmin(host2, port2, nobind=True)
    # require TLS/SSL for password updates
    ad.start_tls_s()
    ad.simple_bind_s(root2, rootpw2)

# the list of users we want to check to see if they were synced
userids = {}

# All IPA users must have these objectclasses - they should be
# the same as in the cn=ipaConfig ipaUserObjectClasses list
# ntUser either by the winsync code, or when you want an
# existing IPA user to be synced with AD
userObjClasses = [
    'top', 'person', 'organizationalPerson', 'inetOrgPerson', 'ntUser'
]

if ipawinsync:
    userObjClasses.extend(['inetUser', 'posixAccount', 'krbPrincipalAux'])

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

windows_subtree = adusersubtree + "," + suffix
active_user_cont = "cn=active users"
deleted_user_cont = "cn=deleted users"
active_user_subtree = active_user_cont + "," + windows_subtree
deleted_user_subtree = deleted_user_cont + "," + windows_subtree

def makeDSUserEnt(idnum):
    id = str(idnum)
    userid = 'testuser' + id
    dn = 'uid=%s,%s,%s,%s' % (userid, active_user_cont, usersubtree, suffix)
    ent = Entry(dn)
    ent.setValues('objectclass', userObjClasses)
    ent.setValues('cn', 'Test User' + id)
    ent.setValues('sn', 'User' + id)
    ent.setValues('uid', userid)
    ent.setValues('userPassword', 'Password' + id)
    ent.setValues('ntUserDomainId', userid)
    ent.setValues('userPassword', 'Ornette1')
    if ipawinsync:
        ent.setValues('krbPrincipalName', '%s@%s' % (userid, realm))
        ent.setValues('uidNumber', str(500+idnum))
        ent.setValues('gidNumber', '1002')
        ent.setValues('homeDirectory', '/home/' + userid)
        if idnum % 2:
            ent.setValues('description', 'User added disabled to DS')
            ent.setValues('nsAccountLock', 'TRUE')
        else:
            ent.setValues('description', 'User added enabled to DS')
    else:
        ent.setValues('description', 'User added to DS')
        ent.setValues('ntUserCreateNewAccount', 'TRUE')
        ent.setValues('ntUserDeleteAccount', 'TRUE')
    return ent

def setWindowsPwd(ad,dn):
    pwd = '"Ornette1"'
    val = pwd.encode('utf_16_le')
    mod = [(ldap.MOD_REPLACE, 'unicodePwd', val)]
    ad.modify_s(dn, mod)

def makeADUserEnt(idnum):
    id = str(idnum)
    userid = 'testuser' + id
    cn = 'Test User' + id
    dn = 'cn=%s,%s' % (cn, active_user_subtree)
    ent = Entry(dn)
    ent.setValues('objectclass', aduserObjClasses)
    ent.setValues('cn', cn)
    ent.setValues('sn', 'User' + id)
    ent.setValues('userPrincipalName', '%s@%s' % (userid, realm))
    ent.setValues('sAMAccountName', userid)
    return ent

def entriesAreEqual(ds, ad):
    dslocked = bool(ds.nsaccountlock and (ds.nsaccountlock == 'TRUE'))
    adlocked = (int(ad.useraccountcontrol) & 0x2) != 0
    retval = True
    if not dslocked == adlocked:
        print "account lock not in sync"
        print "ds", ds.nsaccountlock, "ad", ad.useraccountcontrol
        retval = False
    if not ad.title == ds.title:
        print "title not in sync"
        print "ds", ds.title, "ad", ad.title
        retval = False
    return retval

#ds.setLogLevel(0)
#ds.setLogLevel(8192)
#ds.setLogLevel(65536)

subtrees = ((ad,windows_subtree),(ad,active_user_subtree),(ad,deleted_user_subtree),
            (ds, active_user_cont + "," + usersubtree + ',' + suffix),
            (ds, deleted_user_cont + "," + usersubtree + ',' + suffix))

for srv,subtree in subtrees:
    try:
        ent = Entry(subtree)
        rdn = ldap.explode_dn(subtree)[0].split('=')
        if srv == ad:
            ent.setValues('objectclass', ['top', 'container'])
        else:
            ent.setValues('objectclass', ['top', 'nsContainer'])
        ent.setValues(rdn[0], rdn[1])
        srv.add_s(ent)
        print "Created", subtree, "on", str(srv)
    except ldap.ALREADY_EXISTS: pass

replargs['binddn'] = root2
replargs['bindpw'] = rootpw2
replargs['win_subtree'] = adusersubtree + "," + suffix
replargs['ds_subtree'] = usersubtree + ',' + suffix
syncinterval = 30
replargs['interval'] = str(syncinterval)
replargs['starttls'] = True

agmtdn = ds.setupAgreement(ad, replargs)

time.sleep(5)

print "repl status:", ds.getReplStatus(agmtdn)

ds.startReplication(agmtdn)

time.sleep(5)

print "repl status:", ds.getReplStatus(agmtdn)

for ii in xrange(1,6):
    ent = makeADUserEnt(ii)
    try: ad.add_s(ent)
    except ldap.ALREADY_EXISTS:
        print "AD entry", ent.dn, "already exists"
    setWindowsPwd(ad, ent.dn)
    kk = ii % len(userAcctVals)
    mod = []
    for attr, val in userAcctVals[kk].iteritems():
        mod.append((ldap.MOD_REPLACE, attr, str(val)))
    ad.modify_s(ent.dn, mod)

for ii in xrange(6,11):
    ent = makeDSUserEnt(ii)
    try: ds.add_s(ent)
    except ldap.ALREADY_EXISTS:
        print "DS entry", ent.dn, "already exists"

print "Wait for sync to happen . . ."
time.sleep(syncinterval+1)

print "with ipa, new ds users are not added to AD - so we must add them now to AD in order for them to sync . . ."
for ii in xrange(6,11):
    ent = makeADUserEnt(ii)
    try: ad.add_s(ent)
    except ldap.ALREADY_EXISTS:
        print "AD entry", ent.dn, "already exists"
    setWindowsPwd(ad, ent.dn)
    # need the password, but skip the accountcontrol stuff

print "Wait for sync to happen . . ."
time.sleep(syncinterval+1)

adents = []
dsents = []
print "make sure all entries are in AD . . ."
for ii in xrange(1,11):
    filt = "(samaccountname=testuser%d)" % ii
    ents = ad.search_s(adusersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt)
    if not ents or len(ents) == 0 or not ents[0]:
        raise "error: " + filt + " not found in AD"
    adents.append(ents[0])

print "make sure all entries are in DS . . ."
for ii in xrange(1,11):
    filt = "(uid=testuser%d)" % ii
    ents = ds.search_s(usersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt, dsattrs)
    if not ents or len(ents) == 0 or not ents[0]:
        raise "error: " + filt + " not found in DS"
    dsents.append(ents[0])

for dsent, adent in zip(dsents, adents):
    if not entriesAreEqual(dsent, adent):
        print "entries are not equal", dsent.dn, adent.dn

print "move an AD entry to", deleted_user_cont
newsup = "%s,%s" % (deleted_user_cont, windows_subtree)
rdn = ldap.explode_dn(adents[0].dn)[0]
ad.rename_s(adents[0].dn, rdn, newsup)

print "Wait for sync to happen . . ."
time.sleep(syncinterval+1)

print "find the DS entry"
filt = "(uid=testuser%d)" % 1
ents = ds.search_s(usersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt, dsattrs)
if not ents or len(ents) == 0 or not ents[0]:
    raise Exception("error: " + filt + " not found in DS")
print "found renamed DS entry", ents[0].dn

print "move a DS entry to", deleted_user_cont
newsup = "%s,%s,%s" % (deleted_user_cont, usersubtree, suffix)
rdn = ldap.explode_dn(dsents[1].dn)[0]
ds.rename_s(dsents[1].dn, rdn, newsup)

print "Wait for sync to happen . . ."
time.sleep(1)

print "find the AD entry"
filt = "(samaccountname=testuser%d)" % 2
ents = ad.search_s(windows_subtree, ldap.SCOPE_SUBTREE, filt)
if not ents or len(ents) == 0 or not ents[0]:
    raise Exception("error: " + filt + " not found in AD")
print "found renamed AD entry", ents[0].dn
