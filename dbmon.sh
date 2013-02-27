#!/bin/sh

DURATION=${DURATION:-0}
INCR=${INCR:-1}
HOST=${HOST:-localhost}
PORT=${PORT:-389}
BINDDN=${BINDDN:-"cn=directory manager"}
BINDPW=${BINDPW:-"secret"}
DBLIST=${DBLIST:-userRoot}
ldbmdn="cn=ldbm database,cn=plugins,cn=config"
VERBOSE=${VERBOSE:-0}

dodbmon() {
    while [ 1 ] ; do
        date
        ldapsearch -xLLL -h $HOST -p $PORT -D "$BINDDN" -w "$BINDPW" -b "$ldbmdn" '(|(cn=config)(cn=database)(cn=monitor))' \
        | awk -v dblist="$DBLIST" -vverbose=$VERBOSE -F '[:,= ]+' '
        BEGIN {
            pagesize=8192 ; CONVFMT="%.3f" ; OFMT=CONVFMT
            split(dblist, dbnames) ; for (key in dbnames) { val=dbnames[key] ; dbnames[tolower(val)]=val; delete dbnames[key] }
            fn="entcur entmax entcnt dncur dnmax dncnt"
            split(fn, fields)
            havednstats=0
            maxdbnamelen=0
        }
        /^nsslapd-dbcachesize/ { dbcachesize=$2 }
        /^nsslapd-db-page-size/ { pagesize=$2 }
        /^dbcachehitratio/ { dbhitratio=$2 }
        /^nsslapd-db-page-ro-evict-rate/ { dbroevict=$2 }
        /^nsslapd-db-pages-in-use/ { dbpages=$2 }
        /^dn: cn=monitor, *cn=[a-zA-Z0-9][a-zA-Z0-9]*, *cn=ldbm database, *cn=plugins, *cn=config/ {
            dbname=tolower($5)
            if (dbname in dbnames) {
                len=length(dbname) ; if (len > maxdbnamelen) { maxdbnamelen=len }
            }
        }
        /^currententrycachesize/ { stats[dbname,"entcur"]=$2 }
        /^maxentrycachesize/ { stats[dbname,"entmax"]=$2 }
        /^currententrycachecount/ { stats[dbname,"entcnt"]=$2 }
        /^currentdncachesize/ { stats[dbname,"dncur"]=$2 ; havednstats=1 }
        /^maxdncachesize/ { stats[dbname,"dnmax"]=$2 }
        /^currentdncachecount/ { stats[dbname,"dncnt"]=$2 }
        END {
            free=(dbcachesize-(pagesize*dbpages))
            freeratio=free/dbcachesize
            if (verbose > 1) {
                print "# dbcachefree - free bytes in dbcache"
                print "# free% - percent free in dbcache"
                print "# roevicts - number of read-only pages dropped from cache to make room for other pages"
                print "#            if this is non-zero, it means the dbcache is maxed out and there is page churn"
                print "# hit% - percent of requests that are served by cache"
            }
            print "dbcachefree", free, "free%", (freeratio*100), "roevicts", dbroevict, "hit%", dbhitratio
            if (verbose > 1) {
                print "# dbname - name of database instance - the row shows the entry cache stats"
                print "# count - number of entries in cache"
                print "# free - number of free bytes in cache"
                print "# free% - percent free in cache"
                print "# size - average size of date in cache in bytes (current size/count)"
                if (havednstats) {
                    print "# DNcache - the line below the entry cache stats are the DN cache stats"
                    print "# count - number of dns in dn cache"
                    print "# free - number of free bytes in dn cache"
                    print "# free% - percent free in dn cache"
                    print "# size - average size of dn in dn cache in bytes (currentdncachesize/currentdncachecount)"
                }
            }
            if (verbose > 0) {
                if (maxdbnamelen < 7) { maxdbnamelen=7 }
                fmtstr = sprintf("%%%d.%ds %%10.10s %%13.13s %%6.6s %%7.7s\n", maxdbnamelen, maxdbnamelen)
                printf fmtstr, "dbname", "count", "free", "free%", "size"
            }
            for (dbn in dbnames) {
                cur=stats[dbn,"entcur"]
                max=stats[dbn,"entmax"]
                cnt=stats[dbn,"entcnt"]
                free=max-cur
                freep=free/max*100
                size=cur/cnt
                fmtstr = sprintf("%%%d.%ds %%10d %%13d %%6.1f %%7.1f\n", maxdbnamelen, maxdbnamelen)
                printf fmtstr, dbnames[dbn], cnt, free, freep, size
                if (havednstats) {
                    dcur=stats[dbn,"dncur"]
                    dmax=stats[dbn,"dnmax"]
                    dcnt=stats[dbn,"dncnt"]
                    dfree=dmax-dcur
                    dfreep=dfree/dmax*100
                    dsize=dcur/dcnt
                    printf fmtstr, "DNcache", dcnt, dfree, dfreep, dsize
                }
            }
        }
        '
        echo ""
        sleep $INCR
    done
}

dodbmon
