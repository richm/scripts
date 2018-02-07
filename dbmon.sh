#!/bin/sh

DURATION=${DURATION:-0}
INCR=${INCR:-1}
HOST=${HOST:-localhost}
PORT=${PORT:-389}
BINDDN=${BINDDN:-"cn=directory manager"}
BINDPW=${BINDPW:-"secret"}
DBLIST=${DBLIST:-all}
ldbmdn="cn=ldbm database,cn=plugins,cn=config"
VERBOSE=${VERBOSE:-0}
FORMAT=${FORMAT:-default}
DELIMITER=${DELIMITER:-" "}
# format column - prints all data as single line, first line is column header
#   column uses space as delimiter - can specify DELIMITER for e.g. CSV output
# format keyvalue - prints all data as single line in format KEY=VALUE

parseldif() {
    awk -v delimiter="$DELIMITER" -v format=$FORMAT -v headers="${2:-no}" -v ts="$1" -v dblist="$DBLIST" -v verbose=$VERBOSE -v indexlist="$INDEXLIST" -F '[:,= ]+' '
        function printary(ary) {
            for (ii in ary) { print ii, "=", ary[ii] }
        }
        BEGIN {
            pagesize=8192 ; CONVFMT="%.3f" ; OFMT=CONVFMT ; SUBSEP=","
            alldb=0
            if (dblist == "all") {
                alldb=1
            } else {
                split(dblist, dbnames)
                for (key in dbnames) { val=dbnames[key] ; dbnames[tolower(val)]=val; delete dbnames[key] }
            }
            allindex=0
            if (indexlist == "all") {
                allindex=1
            } else {
                split(indexlist, idxnames)
                for (key in idxnames) { val=idxnames[key] ; idxnames[tolower(val)]=val; delete idxnames[key] }
            }
            fn="entcur entmax entcnt dncur dnmax dncnt"
            split(fn, fields)
            havednstats=0
            maxdbnamelen=0
        }
        /^[^ ]|^$/ {origline = $0; $0 = unwrapline; unwrapline = origline}
        /^ / {sub(/^ /, ""); unwrapline = unwrapline $0; next}
        /^nsslapd-dbcachesize/ { dbcachesize=$2 }
        /^nsslapd-db-page-size/ { pagesize=$2 }
        /^dbcachehitratio/ { dbhitratio=$2 }
        /^dbcachepagein/ { dbcachepagein=$2 }
        /^dbcachepageout/ { dbcachepageout=$2 }
        /^nsslapd-db-page-ro-evict-rate/ { dbroevict=$2 }
        /^nsslapd-db-pages-in-use/ { dbpages=$2 }
        /^dn: cn=monitor, *cn=[a-zA-Z0-9][a-zA-Z0-9_\.\-]*, *cn=ldbm database, *cn=plugins, *cn=config/ {
            idxnum=-1
            idxname=""
            dbname=tolower($5)
            if ((dbname in dbnames) || alldb) {
                len=length(dbname) ; if (len > maxdbnamelen) { maxdbnamelen=len }
                if (!(dbname in dbnames)) { dbnames[dbname] = dbname }
            }
        }
        /^currententrycachesize/ { stats[dbname,"entcur"]=$2 }
        /^maxentrycachesize/ { stats[dbname,"entmax"]=$2 }
        /^currententrycachecount/ { stats[dbname,"entcnt"]=$2 }
        /^currentdncachesize/ { stats[dbname,"dncur"]=$2 ; havednstats=1 }
        /^maxdncachesize/ { stats[dbname,"dnmax"]=$2 }
        /^currentdncachecount/ { stats[dbname,"dncnt"]=$2 }
        /^dbfilename-/ {
            #rhds
            #dbfilename-3: userRoot/id2entry.db4
            #sunds
            #dbfilename-id2entry: /full/path/to/db/dbname/dbname_id2entry.dbX
            if (dbname in dbnames) {
                split($0, idxline, /[ :/.-]+/)
                idxname=tolower(idxline[4])
                dbn=tolower(idxline[3])
                ilen=length(idxline)
                sundbn=tolower(idxline[ilen-2])
                sunidxname=tolower(idxline[2]) 
                if ((dbn == dbname) && (allindex || (idxname in idxnames))) {
                    idxnum=idxline[2]
                    if (!(idxname in idxnames)) { idxnames[idxname] = idxname }
                    len = length(idxname)
                    if (len > idxmaxlen[dbn]) { idxmaxlen[dbn] = len }
                } else if ((sundbn == dbname) && (allindex || (sunidxname in idxnames))) {
                    idxname=sunidxname
                    idxnum=1 # no index number just index name
                    if (!(idxname in idxnames)) { idxnames[idxname] = idxname }
                    len = length(idxname)
                    if (len > idxmaxlen[sundbn]) { idxmaxlen[sundbn] = len }
                } else {
                    # print "index", idxline[4], "not in idxnames"
                }
            } else {
                # print "dbname", dbname, "not in dbnames"
            }
        }
        /^dbfilepagein-/ { if (idxnum >= 0) { idxstats[dbname,idxname,"pagein"] = $2 } }
        /^dbfilepageout-/ { if (idxnum >= 0) { idxstats[dbname,idxname,"pageout"] = $2 } }
        END {
            free=(dbcachesize-(pagesize*dbpages))
            freeratio=free/dbcachesize
            freepct=sprintf("%.1f", freeratio*100)
            if (verbose > 1) {
                print "# dbcachefree - free bytes in dbcache"
                print "# free% - percent free in dbcache"
                print "# roevicts - number of read-only pages dropped from cache to make room for other pages"
                print "#            if this is non-zero, it means the dbcache is maxed out and there is page churn"
                print "# hit% - percent of requests that are served by cache"
                print "# pagein - number of pages read into the cache"
                print "# pageout - number of pages dropped from the cache"
            }
            if (format == "default") {
                print "dbcachefree", free, "free%", freepct, "roevicts", dbroevict, "hit%", dbhitratio, "pagein", dbcachepagein, "pageout", dbcachepageout
            }
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
                    print "# under each db are the list of selected indexes specified with INDEXLIST"
                }
            }
            if (havednstats) { # make sure there is enough room for dbname:ent and dbname:dn
                maxdbnamelen += 4 # :ent
                dbentext = ":ent"
                dbdnext = ":dn "
            } else {
                dbentext = ""
                dbdnext = ""
            }
            if (maxdbnamelen < 6) { # len of "dbname"
                maxdbnamelen = 6
            }

            if (format == "default") {
                if (verbose > 0) {
                    fmtstr = sprintf("%%%d.%ds %%10.10s %%13.13s %%6.6s %%7.7s\n", maxdbnamelen, maxdbnamelen)
                    printf fmtstr, "dbname", "count", "free", "free%", "size"
                }
                for (dbn in dbnames) {
                    cur=stats[dbn,"entcur"]
                    max=stats[dbn,"entmax"]
                    cnt=stats[dbn,"entcnt"]
                    free=max-cur
                    freep=free/max*100
                    size=(cnt == 0) ? 0 : cur/cnt
                    fmtstr = sprintf("%%%d.%ds %%10d %%13d %%6.1f %%7.1f\n", maxdbnamelen, maxdbnamelen)
                    printf fmtstr, dbnames[dbn] dbentext, cnt, free, freep, size
                    if (havednstats) {
                        dcur=stats[dbn,"dncur"]
                        dmax=stats[dbn,"dnmax"]
                        dcnt=stats[dbn,"dncnt"]
                        dfree=dmax-dcur
                        dfreep=dfree/dmax*100
                        dsize=(dcnt == 0) ? 0 : dcur/dcnt
                        printf fmtstr, dbnames[dbn] dbdnext, dcnt, dfree, dfreep, dsize
                    }
                    if (indexlist) {
                        len = idxmaxlen[dbn]
                        fmtstr = sprintf("%%%d.%ds %%%d.%ds pagein %%8d pageout %%8d\n", maxdbnamelen, maxdbnamelen, len, len)
                        for (idx in idxnames) {
                            ipi = idxstats[dbn,idx,"pagein"]
                            ipo = idxstats[dbn,idx,"pageout"]
                            # not every db will have every index
                            if (ipi != "" && ipo != "") {
                                printf fmtstr, "+", idxnames[idx], ipi, ipo
                            }
                        }
                    }
                }
            }
            if (format == "column") {
                if (headers != "no") {
                    headerstr="timestamp" delimiter "db:free" delimiter "db:freepct" delimiter "db:roevicts" delimiter "db:hitratio" delimiter "db:cachepagein" delimiter "db:cachepageout"
                    for (dbn in dbnames) {
                        headerstr=headerstr delimiter dbn ":ent:entries" delimiter dbn ":ent:freebytes" delimiter dbn ":ent:freepct" delimiter dbn ":ent:entrysize"
                        if (havednstats) {
                            headerstr=headerstr delimiter dbn ":dn:entries" delimiter dbn ":dn:freebytes" delimiter dbn ":dn:freepct" delimiter dbn ":dn:entrysize"
                        }
                    }
                    print headerstr
                }
                datastr=ts delimiter free delimiter freepct delimiter dbroevict delimiter dbhitratio delimiter dbcachepagein delimiter dbcachepageout
                for (dbn in dbnames) {
                    cur=stats[dbn,"entcur"]
                    max=stats[dbn,"entmax"]
                    cnt=stats[dbn,"entcnt"]
                    free=max-cur
                    freep=sprintf("%.1f", free/max*100)
                    size=(cnt == 0) ? "0" : sprintf("%.1f", cur/cnt)
                    datastr=datastr delimiter cnt delimiter free delimiter freep delimiter size
                    if (havednstats) {
                        dcur=stats[dbn,"dncur"]
                        dmax=stats[dbn,"dnmax"]
                        dcnt=stats[dbn,"dncnt"]
                        dfree=dmax-dcur
                        dfreep=sprintf("%.1f", dfree/dmax*100)
                        dsize=(dcnt == 0) ? "0" : sprintf("%.1f", dcur/dcnt)
                        datastr=datastr delimiter dcnt delimiter dfree delimiter dfreep delimiter dsize
                    }
                }
                print datastr
            }
            if (format == "keyvalue") {
                datastr="timestamp=" ts " db:free=" free " db:freepct=" freepct " db:roevicts=" dbroevict " db:hitratio=" dbhitratio " db:cachepagein=" dbcachepagein " db:cachepageout=" dbcachepageout
                for (dbn in dbnames) {
                    cur=stats[dbn,"entcur"]
                    max=stats[dbn,"entmax"]
                    cnt=stats[dbn,"entcnt"]
                    free=max-cur
                    freep=sprintf("%.1f", free/max*100)
                    size=(cnt == 0) ? "0" : sprintf("%.1f", cur/cnt)
                    datastr=datastr " " dbn ":ent:entries=" cnt " " dbn ":ent:freebytes=" free " " dbn ":ent:freepct=" freep " " dbn ":ent:entrysize=" size
                    if (havednstats) {
                        dcur=stats[dbn,"dncur"]
                        dmax=stats[dbn,"dnmax"]
                        dcnt=stats[dbn,"dncnt"]
                        dfree=dmax-dcur
                        dfreep=sprintf("%.1f", dfree/dmax*100)
                        dsize=(dcnt == 0) ? "0" : sprintf("%.1f", dcur/dcnt)
                        datastr=datastr " " dbn ":dn:entries=" dcnt " " dbn ":dn:freebytes=" dfree " " dbn ":dn:freepct=" dfreep " " dbn ":dn:entrysize=" dsize
                    }
                }
                print datastr
            }
            if (format == "json") {
                datastr="{\"timestamp\":\"" ts "\",\"db:free\":" free ",\"db:freepct\":" freepct ",\"db:roevicts\":" dbroevict ",\"db:hitratio\":" dbhitratio ",\"db:cachepagein\":" dbcachepagein ",\"db:cachepageout\":" dbcachepageout
                for (dbn in dbnames) {
                    cur=stats[dbn,"entcur"]
                    max=stats[dbn,"entmax"]
                    cnt=stats[dbn,"entcnt"]
                    free=max-cur
                    freep=sprintf("%.1f", free/max*100)
                    size=(cnt == 0) ? "0" : sprintf("%.1f", cur/cnt)
                    datastr=datastr ",\"" dbn ":ent:entries\":" cnt ",\"" dbn ":ent:freebytes\":" free ",\"" dbn ":ent:freepct\":" freep ",\"" dbn ":ent:entrysize\":" size
                    if (havednstats) {
                        dcur=stats[dbn,"dncur"]
                        dmax=stats[dbn,"dnmax"]
                        dcnt=stats[dbn,"dncnt"]
                        dfree=dmax-dcur
                        dfreep=sprintf("%.1f", dfree/dmax*100)
                        dsize=(dcnt == 0) ? "0" : sprintf("%.1f", dcur/dcnt)
                        datastr=datastr ",\"" dbn ":dn:entries\":" dcnt ",\"" dbn ":dn:freebytes\":" dfree ",\"" dbn ":dn:freepct\":" dfreep ",\"" dbn ":dn:entrysize\":" dsize
                    }
                }
                print datastr "}"
            }
        }
        '
}

allowAnonAccess() {
    ldapmodify -x -h $HOST -p $PORT -D "$BINDDN" -w "$BINDPW" <<EOF
dn: $ldbmdn
changetype: modify
add: aci
aci: (targetattr = "*")(targetfilter = "(|(cn=config)(cn=database)(cn=monitor))")(version 3.0; acl "allow anon access for db cache monitor"
 ; allow (read,search) userdn = "ldap:///anyone";)
EOF
}

allowMonitorUserAccess() {
    ldapmodify -x -h $HOST -p $PORT -D "$BINDDN" -w "$BINDPW" <<EOF
dn: $ldbmdn
changetype: modify
add: aci
aci: (targetattr = "*")(targetfilter = "(|(cn=config)(cn=database)(cn=monitor))")(version 3.0; acl "allow monitor user access for db cache monitor"
 ; allow (read,search) userdn = "ldap:///$1";)
EOF
}

ldsrch() {
    if [ -n "${ANON:-}" ] ; then
        ldapsearch -xLLL -h $HOST -p $PORT -b "$ldbmdn" '(|(cn=config)(cn=database)(cn=monitor))'
    else
        ldapsearch -xLLL -h $HOST -p $PORT -D "$BINDDN" -w "$BINDPW" -b "$ldbmdn" '(|(cn=config)(cn=database)(cn=monitor))'
    fi
}

dodbmon() {
    headers=${HEADERS:-yes}
    elapsed=0
    while [ 1 ] ; do
        if [ "$FORMAT" = "default" ] ; then
            date
        fi
        ts=$( date +%Y-%m-%dT%H:%M:%S.%6N )
        ldsrch | parseldif $ts $headers
        headers=no
        if [ "$FORMAT" = "default" ] ; then
            echo ""
        fi
        elapsed=$( expr $elapsed + $INCR )
        if [ $DURATION -ne 0 -a $elapsed -ge $DURATION ] ; then
            break
        fi
        sleep $INCR
    done
}

dodbmon
