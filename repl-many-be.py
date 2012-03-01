
import os
import sys
import time
import tempfile
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
port1 = 1389
port2 = port1 + 10

createargs = {
    'newrootpw': 'password',
    'newhost': host1,
    'newport': port1,
    'newinst': 'm1',
    'newsuffix': 'dc=example,dc=com',
    'no_admin': True
}

m1replargs = {
	'suffix': "dc=example,dc=com",
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

ldiftemp = """
dn: cn=%(be)s,cn=ldbm database,cn=plugins,cn=config
objectclass: top
objectclass: extensibleObject
objectclass: nsBackendInstance
nsslapd-suffix: %(suf)s
cn: %(be)s

dn: cn=encrypted attribute keys,cn=%(be)s,cn=ldbm database,cn=plugins,cn=config
objectClass: top
objectClass: extensibleObject
cn: encrypted attributes keys

dn: cn=encrypted attributes,cn=%(be)s,cn=ldbm database,cn=plugins,cn=config
objectClass: top
objectClass: extensibleObject
cn: encrypted attributes

dn: cn="%(suf)s",cn=mapping tree,cn=config
objectclass: top
objectclass: extensibleObject
objectclass: nsMappingTree
cn: %(suf)s
cn: "%(suf)s"
nsslapd-state: backend
nsslapd-backend: %(be)s

"""

nbe = 8
belist = []
suflist = []
cfgfd = tempfile.NamedTemporaryFile(delete=False)
for ii in xrange(0,nbe):
    be = 'suffix' + str(ii)
    suf = 'o=' + be
    cfgfd.write(ldiftemp % {'be':be,'suf':suf})
    belist.append(be)
    suflist.append(suf)
cfgfd.write("""
dn: cn=config
changetype: modify
replace: nsslapd-threadnumber
nsslapd-threadnumber: 2

""")
cfgfd.close()
os.chmod(cfgfd.name, 0644)

createargs['ConfigFile'] = [cfgfd.name]
createargs['InstallLdifFile'] = 'none'

#os.environ['USE_DBX'] = "1"
#os.environ['USE_CALLGRIND'] = "1"
print "create and setup m1"
m1 = DSAdmin.createInstance(createargs)
#del os.environ['USE_CALLGRIND']
#del os.environ['USE_DBX']

m2replargs = m1replargs
createargs['newhost'] = host2
createargs['newport'] = port2
createargs['newinst'] = 'm2'
#os.environ['USE_GDB'] = "1"
print "create and setup m2"
m2 = DSAdmin.createInstance(createargs)
#del os.environ['USE_GDB']

os.unlink(cfgfd.name)

print "add entries to each suffix"
for suf in suflist:
    ent = Entry(suf)
    ent.setValues('objectclass', ['top', 'extensibleObject'])
    m1.add_s(ent)

print "setup replication"
replargs = m1replargs
for srv,ii in ((m1, 1),(m2, 2)):
    for be,suf in zip(belist,suflist):
        replargs['suffix'] = suf
        replargs['bename'] = be
        replargs['id'] = ii
        srv.replicaSetupAll(replargs)
m1agmts = []
m2agmts = []
print "create agreements and init consumers"
for srv,oth,agmts in ((m1, m2, m1agmts),(m2, m1, m2agmts)):
    for be,suf in zip(belist,suflist):
        replargs['suffix'] = suf
        replargs['bename'] = be
        agmt = srv.setupAgreement(oth, replargs)
        agmts.append(agmt)
        if srv == m1:
            print "doing repl init for", agmt
            srv.startReplication(agmt)

for suf in suflist:
    print "checking status of", suf
    while True:
        ruv1 = m1.getRUV(suf)
        ruv2 = m2.getRUV(suf)
        (rc, msg) = ruv1.getdiffs(ruv2)
        if rc:
            print "ruvs differ", msg
            time.sleep(5)
        else:
            break

def domods(srv,suflist):
    for ii in xrange(0, 100):
        for suf in suflist:
            mod = [(ldap.MOD_REPLACE, "description", "description " + str(ii))]
            srv.modify_s(suf, mod)

while True:
    m2.stop()
    domods(m1,suflist)
    m1.stop()
    m2.start()
    m1.start()
    for suf in suflist:
        print "checking status of", suf
        while True:
            ruv1 = m1.getRUV(suf)
            ruv2 = m2.getRUV(suf)
            (rc, msg) = ruv1.getdiffs(ruv2)
            if rc:
                print "ruvs differ", msg
                time.sleep(5)
            else:
                break
