import sys
import shutil
import errno
import re
import os, os.path
import ldap
import ldif
import time
from subprocess import Popen, PIPE, STDOUT
import olserver
import pprint

src = sys.argv[1]
srcport = int(sys.argv[2])
dest = sys.argv[3]
destport = int(sys.argv[4])
cafile = sys.argv[5]
cert = sys.argv[6]
key = sys.argv[7]
basedn = "dc=example,dc=com"
rootdn = "cn=manager," + basedn
rootpw = "secret"
hostname = "localhost.localdomain"

ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, cafile)

rootdir = os.path.dirname(os.path.dirname(os.path.dirname(src)))
startverbose = False

olserver.setupserver(rootdir, rootpw)
olserver.createscript(src, srcport, hostname)
olserver.startserver(src, srcport, startverbose)
print "wait for server to be up and listening"
sleeptime = 2
if ('USE_GDB' in os.environ) or ('USE_VALGRIND' in os.environ):
    sleeptime = 30
time.sleep(sleeptime)
print "open conection to server"
srv1url = "ldap://%s:%d" % (hostname, srcport)
srv1 = ldap.initialize(srv1url)
srv1.simple_bind_s("cn=config", rootpw)
olserver.addschema(srv1, rootdir, ['core', 'cosine', 'inetorgperson', 'openldap', 'nis'])
olserver.addbackend(srv1, rootdir, rootpw, basedn)
olserver.setuptls(srv1, cafile, None, cert, key)
olserver.addsyncprov(srv1, rootdir)
print "Add entries to", srv1url
srv1.start_tls_s()
srv1.simple_bind_s(rootdn, rootpw)
olserver.ldapadd(srv1, rootdir + "/Example.ldif")

olserver.setupserver(rootdir, rootpw, 2)
olserver.createscript(dest, destport, hostname)
#os.environ["USE_GDB"] = "1"
if ('USE_GDB' in os.environ) or ('USE_VALGRIND' in os.environ):
    sleeptime = 60
    startverbose = False
olserver.startserver(dest, destport, startverbose)
print "wait for server to be up and listening"
if ('USE_GDB' in os.environ) or ('USE_VALGRIND' in os.environ):
    sleeptime = 60
time.sleep(sleeptime)
print "open conection to server"
srv2url = "ldap://%s:%d" % (hostname, destport)
srv2 = ldap.initialize(srv2url)
srv2.simple_bind_s("cn=config", rootpw)
olserver.addschema(srv2, rootdir, ['core', 'cosine', 'inetorgperson', 'openldap', 'nis'])
olserver.addbackend(srv2, rootdir, rootpw, basedn, ii=2)
olserver.setuptls(srv2, cafile, None, cert, key)
olserver.setupsyncrepl(srv2, srv1url, basedn, rootdn, rootpw, cafile)

print "wait for sync to happen"
print "Verify entries on provider"
ents = srv1.search_s(basedn, ldap.SCOPE_SUBTREE)
print "Found", len(ents), "entries on provider"

print "Verify entries on consumer"
srv2.start_tls_s()
srv2.simple_bind_s(rootdn, rootpw)
waits = 90
for ent in ents:
    try:
        dn = ent[0]
        ents2 = srv2.search_s(dn, ldap.SCOPE_BASE)
        if not ents2 or not len(ents2):
            raise ldap.NO_SUCH_OBJECT
    except ldap.NO_SUCH_OBJECT:
        waits = waits - 1
        if not waits:
            raise ldap.NO_SUCH_OBJECT
        time.sleep(1)

print "create a bunch of entries on the provider"

userObjClasses = [
    'top', 'person', 'organizationalPerson', 'inetOrgPerson'
]
usersubtree = "ou=people"
def makeDSUserEnt(idnum):
    id = str(idnum)
    userid = 'testuser' + id
    dn = 'uid=%s,%s,%s' % (userid, usersubtree, basedn)
    attrs = []
    attrs.append(('objectclass', userObjClasses))
    attrs.append(('cn', ['Test User' + id]))
    attrs.append(('sn', ['User' + id]))
    attrs.append(('uid', [userid]))
    attrs.append(('userPassword', ['Password' + id]))
    attrs.append(('description', ['User added to DS']))
    return (dn, attrs)

newents = []
for ii in xrange(1, 1000):
    ent = makeDSUserEnt(ii)
    srv1.add_s(ent[0], ent[1])
    newents.append(ent)
waits = 90
for ent in newents:
    try:
        dn = ent[0]
        ents2 = srv2.search_s(dn, ldap.SCOPE_BASE)
        if not ents2 or not len(ents2):
            raise ldap.NO_SUCH_OBJECT
    except ldap.NO_SUCH_OBJECT:
        waits = waits - 1
        if not waits:
            raise ldap.NO_SUCH_OBJECT
        time.sleep(1)
