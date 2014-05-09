
import os
import sys
import time
import tempfile
import ldap
import logging
from dsadmin import DSAdmin, Entry
from dsadmin import DSAdmin, Entry, tools
from dsadmin.tools import DSAdminTools
from dsadmin._constants import (LOG_REPLICA, MASTER_TYPE)

logging.getLogger('dsadmin').setLevel(logging.WARN)
logging.getLogger('dsadmin.tools').setLevel(logging.WARN)

host1 = "localhost.localdomain"
host2 = host1
port1 = 1389
port2 = port1 + 10
suffix = "dc=example,dc=com"
replbinddn = "cn=replrepl,cn=config"
replbindpw = "replrepl"
bename = "userRoot"
rootpw = "password"

createargs = {
    'newrootpw': rootpw,
    'newsuffix': suffix,
    'no_admin': True,
    'prefix': os.environ.get('PREFIX', None),
}

replargs = {
    'suffix': suffix,
    'binddn': replbinddn,
    'bindpw': replbindpw
}

agmtargs = replargs
    # 'fractional': fracval,
    # 'fractional_total': fracval_total,
    # 'stripattrs': stripval

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

nbe = 80
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
nsslapd-threadnumber: 16

""")
cfgfd.close()
os.chmod(cfgfd.name, 0644)

createargs['ConfigFile'] = [cfgfd.name]
createargs['InstallLdifFile'] = 'none'

os.environ['USE_VALGRIND'] = "1"
#os.environ['USE_CALLGRIND'] = "1"
print "create and setup m1"
createargs['newhost'] = host1
createargs['newport'] = port1
createargs['newinst'] = 'm1'
m1 = DSAdminTools.createInstance(createargs)
#del os.environ['USE_CALLGRIND']
#del os.environ['USE_DBX']

createargs['newhost'] = host2
createargs['newport'] = port2
createargs['newinst'] = 'm2'
#os.environ['USE_GDB'] = "1"
print "create and setup m2"
m2 = DSAdminTools.createInstance(createargs)
#del os.environ['USE_GDB']

os.unlink(cfgfd.name)

print "add entries to each suffix"
for suf in suflist:
    ent = Entry(suf)
    ent.setValues('objectclass', ['top', 'extensibleObject'])
    m1.add_s(ent)

def addrepluser(srv, repArgs):
    attrs = [repArgs.get('binddn'), repArgs.get('bindpw')]
    attrs.append({
            'nsIdleTimeout': '0',
            'passwordExpirationTime': '20381010000000Z'
            })
    srv.setupBindDN(*attrs)

print "setup replicas"
ii = 1
for srv in (m1, m2):
    srv.replica.changelog()
    addrepluser(srv, replargs)
    for suf in suflist:
        replargs['suffix'] = suf
        replargs['rid'] = ii
        replargs['rtype'] = MASTER_TYPE
        srv.replica.add(**replargs)
        ii += 1
m1agmts = []
m2agmts = []
print "create agreements and init consumers"
for srv,oth,agmts in ((m1, m2, m1agmts),(m2, m1, m2agmts)):
    for suf in suflist:
        agmtargs['suffix'] = suf
        if 'rid' in agmtargs: del agmtargs['rid']
        if 'rtype' in agmtargs: del agmtargs['rtype']
        agmt = srv.replica.agreement_add(oth, **agmtargs)
        agmts.append(agmt)
        if srv == m1:
            print "doing repl init for", agmt
            srv.startReplication(agmt)

for suf in suflist:
    print "checking status of", suf
    while True:
        ruv1 = m1.replica.ruv(suf)
        ruv2 = m2.replica.ruv(suf)
        (rc, msg) = ruv1.getdiffs(ruv2)
        if rc:
            print "ruvs differ", msg
            time.sleep(5)
        else:
            break

def domods(srv,suflist):
    for ii in xrange(0, 2):
        for suf in suflist:
            mod = [(ldap.MOD_REPLACE, "description", "description " + str(ii))]
            srv.modify_s(suf, mod)

while True:
    domods(m1,suflist)
    for suf in suflist:
        print "checking status of", suf
        while True:
            ruv1 = m1.replica.ruv(suf)
            ruv2 = m2.replica.ruv(suf)
            (rc, msg) = ruv1.getdiffs(ruv2)
            if rc:
                print "ruvs differ", msg
                time.sleep(5)
            else:
                break
