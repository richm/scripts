import sys
import shutil
import errno
import re
import os, os.path
import ldap
import ldif
import time
from subprocess import Popen, PIPE, STDOUT

def ldapadd(conn, ldiffile):
    lfd = open(ldiffile)
    ldrl = ldif.LDIFRecordList(lfd)
    ldrl.parse()
    lfd.close()
    for dn, entry in ldrl.all_records:
        mylist = []
        for attr, vals in entry.iteritems():
            mylist.append((attr, vals))
        try: conn.add_s(dn, mylist)
        except ldap.ALREADY_EXISTS: pass
        except ldap.UNDEFINED_TYPE: pass

def setupserver(rootdir,pwd,ii=0,verbose=False):
    strii = ''
    if ii > 0:
        strii = str(ii)
    slapdd = "%s/etc/openldap/slapd%s.d" % (rootdir, strii)
    rundir = "%s/var/run" % rootdir
    if not os.path.isdir(rundir):
        os.makedirs(rundir)
    try:
        shutil.rmtree(slapdd)
        print "removed old tree from", slapdd
    except OSError, e:
        if e.errno == errno.ENOENT: pass
        else: raise e
    os.makedirs(slapdd)
    cmd = ["slapadd", "-F", slapdd, "-n", "0"]
    configldif = """dn: cn=config
objectClass: olcGlobal
cn: config
olcArgsFile: %s/slapd%s.args
olcPidFile: %s/slapd%s.pid

dn: olcDatabase={0}config,cn=config
objectClass: olcDatabaseConfig
olcDatabase: {0}config
olcRootPW: %s

""" % (rundir, strii, rundir, strii, pwd)
    if verbose: print configldif
    pipe = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
    pipe.stdin.write(configldif)
    pipe.stdin.close()
    for line in pipe.stdout:
        if verbose: sys.stdout.write(line)
    pipe.stdout.close()
    exitCode = pipe.wait()
    if verbose:
        print "%s returned exit code %s" % (cmd, exitCode)
    return exitCode

def addbackend(conn, rootdir, pwd, basedn, rootdn=None, dbtype="bdb", ii=0):
    strii = ''
    if ii > 0:
        strii = str(ii)
    if not rootdn:
        rootdn = "cn=Manager," + basedn
    dbdir = "%s/var/openldap-data%s" % (rootdir, strii)
    if not os.path.isdir(dbdir):
        os.makedirs(dbdir)
    dn = "olcDatabase={1}%s,cn=config" % dbtype
    entry = [('objectClass', ['olcDatabaseConfig', 'olc%sConfig' % dbtype]),
             ('olcDatabase', "{1}%s" % dbtype),
             ('olcRootDN', rootdn),
             ('olcRootPW', pwd),
             ('olcSuffix', basedn),
             ('olcDbDirectory', "%s/var/openldap-data%s" % (rootdir, strii)),
             ('olcDbCheckpoint', "1024 5")]
    try: conn.add_s(dn, entry)
    except ldap.ALREADY_EXISTS: pass

def addschema(conn, rootdir, namelist):
    schemadir = os.environ.get('SLAPDSCHEMADIR', rootdir + "/etc/openldap/schema")
    for name in namelist:
        sf = schemadir + "/" + name + ".ldif"
        ldapadd(conn, sf)

def setuptls(conn, cafile='', cadir='', cert='', key=''):
    mod = []
    if cafile:
        mod.append((ldap.MOD_REPLACE, 'olcTLSCACertificateFile', cafile))
    if cadir:
        mod.append((ldap.MOD_REPLACE, 'olcTLSCACertificatePath', cadir))
    if cert:
        mod.append((ldap.MOD_REPLACE, 'olcTLSCertificateFile', cert))
    if key:
        mod.append((ldap.MOD_REPLACE, 'olcTLSCertificateKeyFile', key))
    mod.append((ldap.MOD_REPLACE, 'olcTLSVerifyClient', 'allow'))
    if not len(mod): return
    conn.modify_s('cn=config', mod)

rid=0
def setupsyncrepl(conn, provider, basedn, binddn, cred, cafile='', cadir='', cert='', key=''):
    global rid
    rid = rid + 1
    mod = []
    dn = 'olcDatabase={1}bdb,cn=config'
    val = 'rid=%d provider=%s searchbase=%s bindmethod=simple binddn=%s credentials=%s type=refreshAndPersist retry="1 +"' % (rid, provider, basedn, binddn, cred)
    if cafile or cadir or cert or key:
        val = val + ' starttls=critical'
    if cafile:
        val = val + ' tls_cacert=' + cafile
    if cadir:
        val = val + ' tls_cacertdir=' + cadir
    if cert:
        val = val + ' tls_cert=' + cert
    if key:
        val = val + ' tls_key=' + key
    mod = [(ldap.MOD_REPLACE, 'olcSyncrepl', val)]
    conn.modify_s(dn, mod)

def createscript(src, port, hostname="localhost.localdomain"):
    scriptdir = os.path.dirname(os.path.dirname(os.path.dirname(src)))
    script = scriptdir + "/slapd-" + str(port)
    slapdexec = os.environ.get('SLAPDEXEC', scriptdir + "/libexec/slapd")
    if not os.path.exists(script):
        sf = open(script, 'w')
        sf.write("""#!/bin/sh
if [ ! -d %s/var/log/slapd ] ; then mkdir -p %s/var/log ; fi
if [ -n "$USE_GDB" ] ; then
    GDB="xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb --args"
fi
if [ -f /tmp/valgrind.supp ] ; then
    VGSUPPRESS="--suppressions=/tmp/valgrind.supp"
fi
if [ -n "$USE_VALGRIND" ] ; then
    CHECKCMD="valgrind -q --tool=memcheck --leak-check=yes --leak-resolution=high $VGSUPPRESS --num-callers=50 --log-file=%s/var/log/slapd-%d.vg"
fi
$GDB $CHECKCMD %s -F %s -h ldap://%s:%d/ $@ > %s/var/log/slapd-%d 2>&1 &
""" % (scriptdir, scriptdir, scriptdir, port, slapdexec, src, hostname, port, scriptdir, port))
        sf.close()
        os.chmod(script, 0700)

def startserver(src, port, verbose=False):
    scriptdir = os.path.dirname(os.path.dirname(os.path.dirname(src)))
    script = scriptdir + "/slapd-" + str(port)
    cmd = [script]
    if verbose:
        cmd.append('-d')
        cmd.append('-1')
    elif "USE_GDB" in os.environ:
        cmd.append('-d')
        cmd.append('0')
    pipe = Popen(cmd, stdin=None, stdout=PIPE, stderr=STDOUT)
    for line in pipe.stdout:
        if verbose: sys.stdout.write(line)
    pipe.stdout.close()
    exitCode = pipe.wait()
    if verbose:
        print "%s returned exit code %s" % (cmd, exitCode)
    return exitCode

def addsyncprov(conn, rootdir, db="{1}bdb"):
    print "load the syncprov module and overlay"
    dn = "cn=module,cn=config"
    entry = [('objectClass', 'olcModuleList'),
             ('cn', 'module'),
             ('olcModulePath', rootdir + "/libexec/openldap"),
             ('olcModuleLoad', 'syncprov.la')]
    try: conn.add_s(dn, entry)
    except ldap.ALREADY_EXISTS: pass
    dn = 'olcOverlay=syncprov,olcDatabase=%s,cn=config' % db
#             ('olcSpCheckpoint', '1 1'),
#             ('olcSpSessionlog', '100')]
    entry = [('objectClass', ['olcOverlayConfig', 'olcSyncProvConfig']),
             ('olcOverlay', 'syncprov')]
    try: conn.add_s(dn, entry)
    except ldap.ALREADY_EXISTS: pass

def main():
    src = sys.argv[1]
    srchostname = sys.argv[2]
    srcport = int(sys.argv[3])
    basedn = "dc=example,dc=com"
    rootdn = "cn=manager," + basedn
    rootpw = "secret"

    rootdir = os.path.dirname(os.path.dirname(os.path.dirname(src)))

    setupserver(rootdir, rootpw)
    createscript(src, srcport, srchostname)
    startserver(src, srcport, True)
    print "wait for server to be up and listening"
    time.sleep(1)
    print "open conection to server"
    srv1url = "ldap://%s:%d" % (srchostname, srcport)
    srv1 = ldap.initialize(srv1url)
    srv1.simple_bind_s("cn=config", rootpw)
    addschema(srv1, rootdir, ['core', 'cosine', 'inetorgperson', 'openldap', 'nis'])
    addbackend(srv1, rootdir, rootpw, basedn)

if __name__ == '__main__':
    main()
