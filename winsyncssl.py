
import os
import sys
import time
import ldap
import tempfile
import copy
from ldap.controls import LDAPControl
import struct
from lib389 import DirSrv, Entry, tools
from lib389.tools import DirSrvTools
from lib389._constants import LOG_REPLICA
from dirsyncctrl import DirSyncCtrl

if os.environ.has_key('WINSYNC_USE_DS'):
    useds = True
else:
    useds = False
    # require SSL to talk to AD
#    ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, os.environ["SECDIR"])
    ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, os.environ["SECDIR"] + "/w2k8x8664-ca.cer")

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
    host1 = 'cel5x8664.testdomain.com'
    suffix = "dc=testdomain,dc=com"
    realm = 'TESTDOMAIN.COM'
    adusersubtree = "cn=testusers"
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
    'bindpw': "replrepl",
    'log': False,
    'id': 1
}

agmtargs = copy.copy(replargs)
agmtargs.update({'winsync': True})

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

#os.environ['USE_GDB'] = "1"
ds = tools.DirSrvTools.createInstance({
	'newrootpw': rootpw1,
	'newhost': host1,
	'newport': port1,
	'newinstance': 'ds',
	'newsuffix': suffix,
	'verbose': False,
    'no_admin': True,
    'ConfigFile': configfile,
    'SchemaFile': schemafile,
    'prefix': os.environ.get('PREFIX')
})
if cfgfd:
    os.unlink(cfgfd.name)

tools.DirSrvTools.setupSSL(ds, secport1, os.environ['SECDIR'])

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
    ad = tools.DirSrvTools.createInstance({
        "newhost": host2, "newport": port2, "newrootdn": root2,
        "newrootpw": rootpw2, "newinstance": "ad",
        "newsuffix": suffix, 'no_admin': True
    })
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

def makeDSUserEnt(idnum):
    id = str(idnum)
    userid = 'testuser' + id
    dn = 'uid=%s,%s,%s' % (userid, usersubtree, suffix)
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
    dn = 'cn=%s,%s,%s' % (cn, adusersubtree, suffix)
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

windows_subtree = adusersubtree + "," + suffix
print "Create adusersubtree entry if missing", windows_subtree
try:
    ents = ad.search_s(windows_subtree, ldap.SCOPE_BASE)
except ldap.NO_SUCH_OBJECT:
    ent = Entry(windows_subtree)
    rdn = ldap.explode_dn(windows_subtree)[0].split('=')
    ent.setValues('objectclass', ['top', 'container'])
    ent.setValues(rdn[0], rdn[1])
    ad.add_s(ent)

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

agmtargs['binddn'] = root2
agmtargs['bindpw'] = rootpw2
agmtargs['win_subtree'] = adusersubtree + "," + suffix
agmtargs['ds_subtree'] = usersubtree + ',' + suffix
syncinterval = 30
agmtargs['interval'] = str(syncinterval)
agmtargs['starttls'] = True

agmtdn = ds.createAgreement(ad, agmtargs)

time.sleep(5)

print "repl status:", ds.agreement.status(agmtdn)

#ds.config.loglevel((LOG_REPLICA,))
print "attach debugger now and press Enter . . ."
sys.stdin.readline()

ds.startReplication(agmtdn)

time.sleep(5)

print "repl status:", ds.agreement.status(agmtdn)

if ipawinsync:
    print "with ipa, new ds users are not added to AD - so we must add them now to AD in order for them to sync . . ."
    for ii in xrange(6,11):
        ent = makeADUserEnt(ii)
        try: ad.add_s(ent)
        except ldap.ALREADY_EXISTS:
            print "AD entry", ent.dn, "already exists"
        setWindowsPwd(ad, ent.dn)
        # need the password, but skip the accountcontrol stuff

print "Wait for sync to happen . . ."
time.sleep(20)

adents = []
dsents = []
print "make sure all entries are in AD . . ."
for ii in xrange(1,11):
    filt = "(samaccountname=testuser%d)" % ii
    ents = ad.search_s(adusersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt)
    if not ents or len(ents) == 0 or not ents[0]:
        raise Exception("error: " + filt + " not found in AD")
    adents.append(ents[0])
    if ii > 5:
        print "try binding with AD entries"
        pwd = "Ornette1"
        conn = ldap.initialize("ldap://%s" % host2)
        try:
            conn.simple_bind_s(ents[0].dn, pwd)
            conn.unbind_s()
            print "bind succeeded"
        except:
            print "bind failed"
            print str(ents[0])

print "hit Enter"
sys.stdin.readline()

print "make sure all entries are in DS . . ."
for ii in xrange(1,11):
    filt = "(uid=testuser%d)" % ii
    ents = ds.search_s(usersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt, dsattrs)
    if not ents or len(ents) == 0 or not ents[0]:
        raise Exception("error: " + filt + " not found in DS")
    dsents.append(ents[0])

for dsent, adent in zip(dsents, adents):
    if not entriesAreEqual(dsent, adent):
        print "entries are not equal", dsent.dn, adent.dn

print "change title for all entries in AD . . ."
for ii in xrange(1,11):
    title = 'changed title %d in AD' % ii
    mod = [(ldap.MOD_REPLACE, "title", title)]
    ent = adents[ii-1]
    ad.modify_s(ent.dn, mod)
    ents = ad.search_s(ent.dn, ldap.SCOPE_BASE)
    ent = ents[0]
    adents[ii-1] = ent

print "wait for changes to propagate . . ."
time.sleep(20)

print "check entries in DS - see if they have title and enabled state correct"
for ii in xrange(1,11):
    filt = "(uid=testuser%d)" % ii
    ents = ds.search_s(usersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt, dsattrs)
    if not ents or len(ents) == 0 or not ents[0]:
        raise Exception("error: " + filt + " not found in DS")
    dsent = ents[0]
    adent = adents[ii-1]
    if not entriesAreEqual(dsent, adent):
        print "entries are not equal", dsent.dn, adent.dn

print "delete all entries in AD - at the same time, modify an entry in DS . . ."
for ent in adents:
    ad.delete_s(ent.dn)
ad.delete_s(adusersubtree + "," + suffix)
time.sleep(1)
mod = [(ldap.MOD_REPLACE, 'userPassword', 'Ornette1')]
ds.modify_s(dsents[0].dn, mod)

print "delete all entries in DS"
for ent in dsents:
    try: ds.delete_s(ent.dn)
    except ldap.NO_SUCH_OBJECT: print ent.dn, "already deleted"

print "add back the deleted container"
ent = Entry(windows_subtree)
rdn = ldap.explode_dn(windows_subtree)[0].split('=')
ent.setValues('objectclass', ['top', 'container'])
ent.setValues(rdn[0], rdn[1])
ad.add_s(ent)

if ipawinsync:
    sys.exit(0)

print "add an entry to the DS"
idnum = 100
ent = makeDSUserEnt(idnum)
ds.add_s(ent)
print "wait for sync to happen, to get the guid in the users entry"
time.sleep(syncinterval+5)
print "verify entry was added to AD"
filt = "(samaccountname=testuser%d)" % idnum
ents = ad.search_s(adusersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt)
if not ents or len(ents) == 0 or not ents[0]:
    raise Exception("error: " + filt + " not found in AD")
adent = ents[0]

print "verify DS entry has ntUniqueID"
filt = "(uid=testuser%d)" % idnum
ents = ds.search_s(usersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt)
if not ents or len(ents) == 0:
    raise Exception("could not find entry for " + filt + " " + suffix)
print filt, "ntuniqueid is", ents[0].ntuniqueid

print "delete the user in AD"
ad.delete_s(adent.dn)
print "see if the entry was really deleted from AD"
ents = ad.search_s(adusersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt)
if ents and len(ents) > 0:
    raise Exception("error: " + filt + " not deleted from AD")

print "wait for delete to sync to DS"
time.sleep(syncinterval)
print "see if the entry was really deleted from DS"
filt = "(uid=testuser%d)" % idnum
ents = ds.search_s(usersubtree + "," + suffix, ldap.SCOPE_SUBTREE, filt)
if ents and len(ents) > 0:
    raise Exception("error: " + filt + " not deleted from DS")
