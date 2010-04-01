
import os
import sys
import ldap
import time
from dsadmin import DSAdmin, Entry, LEAF_TYPE

def verifyUpdateSent(mmx, mmy, meth, methargs, dn, attrvals):
    '''verify that an update was sent from mmx to mmy'''
    print "mmx: status before sending"
    print mmx.getReplStatus(mmx.agmt[mmy])
    print "get begin changes sent"
    beforenum = mmx.getChangesSent(mmx.agmt[mmy])
    print "mmx: perform update"
    msgid = meth(*methargs) # meth of mmx
    print "mmx: got result", mmx.result(msgid)
    print "mmx: verify entry and values"
    attrs = [ary[0] for ary in attrvals]
    verents = mmx.search_s(dn, ldap.SCOPE_BASE, "objectclass=*", attrs)
    if not verents or len(verents) != 1:
        raise "mmx: Error: entry " + dn + " not found"
    verent = verents[0]
    for (attr,val) in attrvals:
        if not verent.hasValue(attr, val):
            print verent
            raise "mmx: Error: entry " + dn + " has bogus value " + attr + ":" + str(verent.getValue(attr)) + " instead of " + str(val)
    print "mmx: status after sending"
    print mmx.getReplStatus(mmx.agmt[mmy])
    while beforenum >= mmx.getChangesSent(mmx.agmt[mmy]):
        print "waiting for update to be sent"
        time.sleep(1)
    print "mmy: verify entry and value"
    verents = mmy.search_s(dn, ldap.SCOPE_BASE, "objectclass=*", attrs)
    if not verents or len(verents) != 1:
        raise "mmy: Error: entry " + dn + " not found"
    verent = verents[0]
    for (attr,val) in attrvals:
        if not verent.hasValue(attr, val):
            print verent
            raise "mmy: Error: entry " + dn + " has bogus value " + attr + ":" + str(verent.getValue(attr)) + " instead of " + str(val)
    print "mmx: final status"
    print mmx.getReplStatus(mmx.agmt[mmy])

def newEntry(entrycnt, mmx):
    userid = "user%d %s" % (entrycnt, mmx)
    dn = "uid=%s,ou=people,%s" % (userid, basedn)
    ent = Entry(dn)
    ent.setValues("objectclass", "inetOrgPerson")
    ent.setValues("cn", "Test " + userid)
    ent.setValues("sn", userid)
    msgid = mmx.add(ent)
    return (ent, msgid)

host1 = "localhost.localdomain"
if len(sys.argv) > 1:
    host1 = sys.argv[1]
host2 = host1
host3 = host2
host4 = host3
port1 = 1200
port2 = port1 + 10
port3 = port2 + 10
port4 = port3 + 10

basedn = 'dc=example,dc=com'
replargs = {}
srvs = []
m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}
os.environ['USE_GDB'] = "1"
m1 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
    'no_admin': True
}, m1replargs
)
del os.environ['USE_GDB']
replargs[m1] = m1replargs
srvs.append(m1)

m2replargs = m1replargs
m2 = DSAdmin.createAndSetupReplica({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
    'no_admin': True
}, m2replargs
)
replargs[m2] = m2replargs
srvs.append(m2)

if True:
    m3replargs = m2replargs
    m3 = DSAdmin.createAndSetupReplica({
        'newrootpw': 'password',
        'newhost': host3,
        'newport': port3,
        'newinst': 'm3',
        'newsuffix': basedn,
        'no_admin': True
        }, m3replargs)
    replargs[m3] = m3replargs
    srvs.append(m3)

if True:
    m4replargs = m3replargs
    m4 = DSAdmin.createAndSetupReplica({
        'newrootpw': 'password',
        'newhost': host4,
        'newport': port4,
        'newinst': 'm4',
        'newsuffix': basedn,
        'no_admin': True
        }, m4replargs)
    replargs[m4] = m4replargs
    srvs.append(m4)

print "create all of the agreements and init the masters"
for mmx in srvs:
    for mmy in srvs:
        if mmx == mmy: continue
        agmtdn = mmx.setupAgreement(mmy, replargs[mmx])
        if mmx == m1:
            mmx.startReplication(agmtdn)
        print mmx.getReplStatus(agmtdn)

print "test to make sure replication is working"
for (ii, mmx) in enumerate(srvs):
    dn = "cn=user%d,ou=people,%s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues("objectclass", "extensibleObject")
    mmx.add_s(ent)
    time.sleep(2)
    for mmy in srvs:
        while True:
            try: ents = mmy.search_s(dn, ldap.SCOPE_BASE)
            except ldap.NO_SUCH_OBJECT: ents = []
            if len(ents) < 1:
                print "waiting for", dn, "on", str(mmy)
                time.sleep(1)
            elif ents[0]:
                print "found", dn, "on", str(mmy)
                break
    mmx.delete_s(dn)
    time.sleep(2)
    for mmy in srvs:
        while True:
            try: ents = mmy.search_s(dn, ldap.SCOPE_BASE)
            except ldap.NO_SUCH_OBJECT:
                print dn, "was deleted on", str(mmy)
                break
            print "waiting for delete of", dn, "on", str(mmy)
            time.sleep(1)

binattr = "userCertificate;binary"
binval = ''.join([chr(ii % 256) for ii in xrange(0, 4096)])

asciiattr = "description"
svattr = "employeeNumber"

print "send a lot of updates"
msgids = []
dndict = {}
dnlist = []
count = 0
maxval = 99999
useasync = True
nsrvs = len(srvs)
nsrvs2 = 2 * nsrvs

for ii in xrange(0, maxval+1):
    mmx = srvs[count % nsrvs]
    count += 1
    (ent, msgid) = newEntry(ii, mmx)
    msgids.append((mmx, msgid))
    dndict[ent.dn] = False # not modified
    dnlist.append(ent.dn)
    # every n ops do a mod
    if (ii >= nsrvs) and (ii % nsrvs) == 0:
        num = ii - nsrvs
        asciival = "value " + str(num)
        mod = [(ldap.MOD_REPLACE, asciiattr, asciival),
               (ldap.MOD_REPLACE, svattr, asciival),
               (ldap.MOD_REPLACE, binattr, binval)]
        dn = dnlist[num]
        msgid = mmx.modify(dn, mod)
#        print "modifying", dn
        msgids.append((mmx, msgid))
        dndict[dn] = asciival # modified
    # every n*2 ops do a del
    if (ii >= nsrvs2) and (ii % nsrvs2) == 0:
        dn = dnlist[ii - nsrvs2]
        msgid = mmx.delete(dn)
        msgids.append((mmx, msgid))
#        print "deleting", dn
        del dndict[dn]

print "sent", len(msgids), "messages"
while len(msgids) > 0:
    (mmx, msgid) = msgids.pop(0)
#    print "getting result of message", msgid, "from", str(mmx)
    res = mmx.result(msgid)
#    print "got result", res

print "got all results"

waittime = (maxval + 1) / 500
uptodate = False
while not uptodate:
    uptodate = True
    m1 = srvs[0]
    m1ruv = m1.getRUV(basedn)
    for mmx in srvs[1:]:
        mmxruv = mmx.getRUV(basedn)
        (diff, diffstr) = m1ruv.getdiffs(mmxruv)
        print "%s compared to %s\n%s" % (m1, mmx, diffstr)
        if diff: uptodate = False
    if not uptodate:
        print "not all servers are up-to-date - sleeping", waittime, "seconds . . ."
        time.sleep(waittime)

print "all servers are up-to-date"
print "check replication status"
for mmx in srvs:
    for mmy in srvs:
        if mmx == mmy: continue
        print mmx.getReplStatus(mmx.agmt[mmy])

print "search entries to see if they are all up-to-date"
verattrs = [asciiattr, binattr, svattr, 'nscpentrywsi']
for mmx in srvs:
    print "checking server", str(mmx)
    for dn in dndict.keys():
        verents = mmx.search_s(dn, ldap.SCOPE_BASE, "objectclass=*", verattrs)
        if not verents or len(verents) != 1:
            raise "Error: entry " + dn + " not found"
        if not dndict[dn]: continue # not modified
        asciival = dndict[dn]
        verent = verents[0]
        for verattr in verattrs:
            if not verent.hasAttr(verattr):
                raise "Error: entry " + dn + " missing attribute " + verattr
        verent.setValue(binattr, '') # clear out for printing
        if not verent.hasValue(asciiattr, asciival):
            print verent
            raise "Error: entry " + dn + " has bogus value " + asciiattr + ":" + str(verent.getValue(asciiattr)) + " instead of " + asciival
        if not verent.hasValue(svattr, asciival):
            print verent
            raise "Error: entry " + dn + " has bogus value " + svattr + ":" + str(verent.getValue(svattr)) + " instead of " + asciival
