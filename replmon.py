import os
import sys
import time
import ldap
from dsadmin import DSAdmin, Entry

host1, port1, dn1, pw1, host2, port2, dn2, pw2 = sys.argv[1:]

srv1 = DSAdmin(host1, int(port1), dn1, pw1)
srv2 = DSAdmin(host2, int(port2), dn2, pw2)

agmts1to2 = srv1.findAgreementDNs()
agmts2to1 = srv2.findAgreementDNs()

suffixes = {}
srv1.lastnumchanges = {}
srv2.lastnumchanges = {}
srv1.avgrate = {}
srv2.avgrate = {}
srv1.count = {}
srv2.count = {}
repls = {}
for dn in agmts1to2:
    ents = srv1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', ['nsDS5ReplicaRoot'])
    ndn = DSAdmin.normalizeDN(dn)
    nrr = DSAdmin.normalizeDN(ents[0].nsDS5ReplicaRoot)
    suffixes[nrr] = dn
    srv1.lastnumchanges[ndn] = 0
    rdns = ldap.explode_dn(dn, 0)
    ndn = DSAdmin.normalizeDN(','.join(rdns[1:]))
    repls[ndn] = ndn
for dn in agmts2to1:
    ents = srv2.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', ['nsDS5ReplicaRoot'])
    ndn = DSAdmin.normalizeDN(dn)
    nrr = DSAdmin.normalizeDN(ents[0].nsDS5ReplicaRoot)
    suffixes[nrr] = dn
    srv2.lastnumchanges[ndn] = 0
    rdns = ldap.explode_dn(dn, 0)
    ndn = DSAdmin.normalizeDN(','.join(rdns[1:]))
    repls[ndn] = ndn

#for dn in repls.keys():
#    for srv in (srv1, srv2):
#        ents = srv.search_s(dn, ldap.SCOPE_BASE)
#        print "replica", dn, "config from", str(srv)
#        for ent in ents:
#            print str(ent)

sleeptime = 30 # seconds

while True:
    for suf in suffixes.keys():
        ruv1 = srv1.getRUV(suf)
        ruv2 = srv2.getRUV(suf)
        rc, status = ruv1.getdiffs(ruv2)
        print "For suffix %s server1 %s server2 %s" % (suf, str(srv1), str(srv2))
        print status
        stats = srv1.getDBStats(suf)
        print "DB Stats for", str(srv1), suf
        print stats
        stats = srv2.getDBStats(suf)
        print "DB Stats for", str(srv2), suf
        print stats
    for srv, agmts in ((srv1, agmts1to2),(srv2,agmts2to1)):
        for agmtdn in agmts:
#            print srv.getReplStatus(agmtdn)
            nagmtdn = DSAdmin.normalizeDN(agmtdn)
            numchanges = srv.getChangesSent(agmtdn)
            if numchanges:
                if not srv.lastnumchanges[nagmtdn]:
                    srv.lastnumchanges[nagmtdn] = numchanges
                diff = numchanges - srv.lastnumchanges[nagmtdn]
                rate = diff*2
                avgrate = 0
                if rate > 0:
                    ii = srv.count.get(nagmtdn, 0)
                    avgrate = ((ii * srv.avgrate.get(nagmtdn, 0)) + rate) / (ii + 1)
                    srv.avgrate[nagmtdn] = avgrate
                    srv.count[nagmtdn] = ii + 1
                print "Agreement", agmtdn, "changes sent", numchanges, "current rate is", rate, "average rate is", avgrate
                srv.lastnumchanges[nagmtdn] = numchanges
    time.sleep(sleeptime)
