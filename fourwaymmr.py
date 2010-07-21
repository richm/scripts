
import os
import sys
import ldap
import time
from dsadmin import DSAdmin, Entry
from subprocess import Popen

host1 = "localhost"
port1 = 1210
hostport = [(host1, xx) for xx in range(port1, 1250, 10)]
if len(sys.argv) > 1:
    hostport = []
    prevhost = ''
    port = port1
    for host in sys.argv[1:]:
        if host == prevhost:
            port += 10
        else:
            port = port1
        prevhost = host
        hostport.append((host, port))

basedn = 'o=sasl.net'
replbinddn = "cn=replrepl,cn=config"
replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': replbinddn,
	'bindcn': "replrepl",
	'bindpw': "replrepl"
}

srvs = []
rootdn = "cn=directory manager"
rootpw = 'password'
for (host, port) in hostport:
    srv = DSAdmin.createAndSetupReplica({
        'newrootpw': rootpw,
        'newhost': host,
        'newport': port,
        'newinst': '%s-%d' % (host, port),
        'newsuffix': basedn,
        'no_admin': True
        }, replargs)
    srvs.append(srv)

print "create agreements and init consumers"
srv = srvs[0]
for xx in srvs:
    for yy in srvs:
        if xx == yy: continue
        agmt = xx.setupAgreement(yy, replargs)
        if xx == srv:
            xx.startReplication(agmt)

print "on each master, add an entry - make sure the entry gets to all the other masters"
dns = []
for xx in srvs:
    ii = len(dns)
    dn = "cn=new_entry_%d,%s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValues('objectclass', 'extensibleObject')
    xx.add_s(ent)
    dns.append(dn)
    for yy in srvs:
        while True:
            try: ents = yy.search_s(dn, ldap.SCOPE_BASE)
            except ldap.NO_SUCH_OBJECT: ents = None
            if not ents or len(ents) < 1: time.sleep(1)
            else: break

print "delete test entry"
for (srv, dn) in zip(srvs, dns):
    srv.delete_s(dn)
    for yy in srvs:
        while True:
            try: ents = yy.search_s(dn, ldap.SCOPE_BASE)
            except ldap.NO_SUCH_OBJECT: break
            time.sleep(1)

print "mmr is running - begin ldclt"
WAITTIME=1
THREADS=10
ESTIMATE_RUNNING_TIME_PER_OPERATION=1
# 1,000 ops/thread = 1,000*10= 10,000 operations
OPERATIONS_PER_THREAD=1000
MAX_RUNNING_TIME_PER_THREAD=OPERATIONS_PER_THREAD*ESTIMATE_RUNNING_TIME_PER_OPERATION*10
MAX_ALLOW_ERRORS=OPERATIONS_PER_THREAD*THREADS+4
TOTAL_OPERATION=OPERATIONS_PER_THREAD*THREADS

pids = []
for (host, port) in hostport:
    tempout = "/var/tmp/ldclt.add.%s-%d.out" % (host, port)
    prog = '%s/bin/ldclt' % os.environ.get('PREFIX', '/usr')
    args = '%s -h %s -p %d -D \"%s\" -w \"%s\" -b \"%s\" -E \"%d\" -e add -e person,random -f \"cn=add.%s.XXXXX\"  -r 1 -R 99999 -I 68 -n %d -N %d -T %d -W %d' % (
        prog, host, port, rootdn, rootpw,
        basedn, MAX_ALLOW_ERRORS, host, THREADS,
        MAX_RUNNING_TIME_PER_THREAD, OPERATIONS_PER_THREAD,
        WAITTIME)
    pid = Popen(args + " > " + tempout + " 2>&1", shell=True).pid
    pids.append(pid)

while len(pids) > 0:
    m1 = srvs[0]
    m1ruv = m1.getRUV(basedn)
    uptodate = True
    for mmx in srvs[1:]:
        mmxruv = mmx.getRUV(basedn)
        (diff, diffstr) = m1ruv.getdiffs(mmxruv)
        print "%s compared to %s\n%s" % (m1, mmx, diffstr)
        if diff: uptodate = False
    if not uptodate:
        print "not all servers are up-to-date - sleeping", 60, "seconds . . ."
        time.sleep(60)

    pid = pids.pop()
    (opid, status) = os.waitpid(pid, os.WNOHANG)
    if os.WIFEXITED(status):
        print "ldclt exited with status", os.WEXITSTATUS(status)
    elif os.WIFSIGNALED(status):
        print "ldclt was signaled with", os.WTERMSIG(status)
    else:
        pids.append(pid) # still running
        
waittime = (10000 + 1) / 500
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

print "all servers are up to date - compare entries"
for srv in srvs:
    ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE)
    print "server", str(srv), "has", len(ents), "entries"
