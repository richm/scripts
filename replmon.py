import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry
from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('-H', nargs='+', help='host:port')
parser.add_argument('-D', nargs='+', help='binddns')
parser.add_argument('-w', nargs='+', help='bindpws')
parser.add_argument('-b', nargs='+', help='suffixes')
parser.add_argument('-t', type=int, help='time for sleep in seconds', default=30)
parser.add_argument('-v', action='count', help='repeat for more verbosity', default=0)
args = parser.parse_args()

if not args.H:
    print "host:port are required"
    sys.exit(1)
if not args.D:
    print "binddn are required"
    sys.exit(1)
if not args.w:
    print "bindpw are required"
    sys.exit(1)

if len(args.H) != len(args.D) or len(args.H) != len(args.w):
    print "must provide the same number of host:port as binddn as bindpw"
    sys.exit(1)

sufary = args.b
suffixes = {}

conns = []
for ii in range(0, len(args.H)):
    ary = args.H[ii].split(':')
    host = ary[0]
    if len(ary) == 1:
        port = 389
    else:
        port = int(ary[1])
    conn = DSAdmin(host, port, args.D[ii], args.w[ii])
    conn.lastnumchanges = {}
    conn.avgrate = {}
    conn.count = {}
    conn.starttime = {}
    conn.endtime = {}
    conns.append(conn)
    sufary = args.b
    if not sufary:
        sufary = conn.getSuffixes()
    for suf in sufary:
        filt = '(nsds5replicaroot=' + suf + ')'
        agmts = conn.findAgreementDNs(filt)
        if not agmts:
            raise Exception("error: server " + str(conn) + " has no agreements for suffix " + suf)
        suffixes[DSAdmin.normalizeDN(suf)] = suf
        for agmt in agmts:
            conn.lastnumchanges[agmt] = 0

sleeptime = args.t # seconds
print "Press Enter when the update is started"
sys.stdin.readline()
for conn in conns:
    for suf in suffixes.values():
        conn.starttime[suf] = int(time.time())

running = True
while running:
    notconverged = 0
    for suf in suffixes.values():
        if not running: break
        for ii in range(1, len(conns)):
            if not running: break
            srv1 = conns[0]
            srv2 = conns[ii]
            ruv1 = srv1.getRUV(suf)
            ruv2 = srv2.getRUV(suf)
            rc, status = ruv1.getdiffs(ruv2)
            print "For suffix %s server1 %s server2 %s" % (suf, str(srv1), str(srv2))
            print status
            if args.v > 0:
                stats = srv1.getDBStats(suf)
                print "DB Stats for", str(srv1), suf
                print stats
                stats = srv2.getDBStats(suf)
                print "DB Stats for", str(srv2), suf
                print stats
            if rc == 0: # ruvs are equal
                # converged
                print "Servers are converged"
                if not suf in srv2.endtime:
                    srv2.endtime[suf] = int(time.time())
            else:
                notconverged += 1 # not yet converged
                if suf in srv2.endtime: del srv2.endtime[suf]
    if notconverged == 0: # all are converged
        running = False
        break
    for srv in conns:
        if not running: break
        for agmtdn in srv.lastnumchanges.keys():
            if not running: break
#            print srv.getReplStatus(agmtdn)
            numchanges = srv.getChangesSent(agmtdn)
            if numchanges:
                if not srv.lastnumchanges[agmtdn]:
                    srv.lastnumchanges[agmtdn] = numchanges
                diff = numchanges - srv.lastnumchanges[agmtdn]
                rate = diff*2
                avgrate = 0
                if rate > 0:
                    ii = srv.count.get(agmtdn, 0)
                    avgrate = ((ii * srv.avgrate.get(agmtdn, 0)) + rate) / (ii + 1)
                    srv.avgrate[agmtdn] = avgrate
                    srv.count[agmtdn] = ii + 1
                print "Agreement from", str(srv), agmtdn, "changes sent", numchanges, "current rate is", rate, "average rate is", avgrate
                srv.lastnumchanges[agmtdn] = numchanges
    time.sleep(sleeptime)

for suf in suffixes.values():
    for ii in range(1, len(conns)):
        conn = conns[ii]
        diff = conn.endtime[suf] - conn.starttime[suf]
        print "server", str(conn), "took", diff, "seconds to converge"
