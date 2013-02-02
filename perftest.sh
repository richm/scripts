#!/bin/sh

DIR=${DIR:-`dirname $0`}
if [ -z "$DIR" ] ; then
    DIR=.
fi

PERFTESTCONF=${PERFTESTCONF:-$DIR/perftest.conf}

if [ -f $PERFTESTCONF ] ; then
    . $PERFTESTCONF
fi

PREFIX=${PREFIX:-$HOME/389srv}
INST=${INST:-perftest}
DURATION=${DURATION:-600}
INTERVAL=${INTERVAL:-1}
STARTNUM=${STARTNUM:-1}
ENDNUM=${ENDNUM:-100000}
NENTRIES=${NENTRIES:-`expr $ENDNUM - $STARTNUM + 1`}
# one X for each digit in NENTRIES
NDIGITS=${NDIGITS:-6}
LDCLTFLT1=${LDCLTFLT1:-uid=XXXXXX}
LDCLTFLT2=${LDCLTFLT2:-$LDCLTFLT1}
INCR=${INCR:-1001}

HOST=${HOST:-localhost.localdomain}
PORT=${PORT:-13890}
ROOTDN=${ROOTDN:-"cn=directory manager"}
LDCLTDN=${LDCLTDN:-"$ROOTDN"}
ROOTPW=${ROOTPW:-Secret123}
LDCLTPW=${LDCLTPW:-"$ROOTPW"}
ROOTSUF=${ROOTSUF:-dc=example,dc=com}
DB1=${DB1:-one}
DB2=${DB2:-two}
SUF1=${SUF1:-"ou=$DB1,$ROOTSUF"}
SUF2=${SUF2:-"ou=$DB2,$ROOTSUF"}
MODSUF1=${MODSUF1:-"ou=People,$SUF1"}
MODSUF2=${MODSUF2:-"ou=People,$SUF2"}
RAMDISK=${RAMDISK:-$PREFIX/ramdisk}
GPFONT=/usr/share/fonts/default/Type1/n022003l.pfb
if [ -f /usr/share/fonts/liberation/LiberationSans-Regular.ttf ] ; then
    GPFONT=/usr/share/fonts/liberation/LiberationSans-Regular.ttf
fi

LDCLT=${LDCLT:-$PREFIX/bin/ldclt-bin}
S1NPROCS=${S1NPROCS:-4}
S1THREADS=${S1THREADS:-8}
S2NPROCS=${S2NPROCS:-12}
S2THREADS=${S2NTHREADS:-8}
MPROCS=${MPROCS:-1}
MTHREADS=${MTHREADS:-8}
NTHREADS=${NTHREADS:-8}
USEINCR=${USEINCR:-1}

SETUP_CONF_FILE=$DIR/setup-config.ldif
SETUP_SCHEMA_FILE=
# can't change dbhome env. during setup - yet
POST_SETUP_CONF_FILE=$DIR/post-setup-config.ldif

dbdn="cn=ldbm database,cn=plugins,cn=config"
dbconfdn="cn=config,$dbdn"

setupds() {
    setupargs="-l /dev/null -s -f $DIR/setupperftest.inf slapd.ServerPort=$PORT slapd.RootDNPwd=$ROOTPW slapd.Suffix=$ROOTSUF General.FullMachineName=$HOST slapd.ServerIdentifier=$INST"
    if [ -f "$SETUP_CONF_FILE" ] ; then
        setupargs="$setupargs slapd.ConfigFile=$SETUP_CONF_FILE"
    fi
    if [ -f "$SETUP_SCHEMA_FILE" ] ; then
        setupargs="$setupargs slapd.SchemaFile=$SETUP_SCHEMA_FILE"
    fi
    $PREFIX/sbin/setup-ds.pl $setupargs
    if [ -f "$POST_SETUP_CONF_FILE" ] ; then
        ldapmodify -x -h localhost -p $PORT -D "$ROOTDN" -w "$ROOTPW" -f $POST_SETUP_CONF_FILE
    fi
    # calculate entry cache size based on entry size of 8k per entry in RAM
    ecsize=`expr 8192 \* $NENTRIES`
    # dn cache size based on 200 bytes per entry
    dncsize=`expr 200 \* $NENTRIES`
    # db cache size based on 2k per entry
    dbcsize=`expr 2 \* $NENTRIES \* 2048`
    ldapmodify -x -h localhost -p $PORT -D "$ROOTDN" -w "$ROOTPW" <<EOF
dn: cn=$DB1,$dbdn
changetype: modify
replace: nsslapd-cachememsize
nsslapd-cachememsize: $ecsize
-
replace: nsslapd-dncachememsize
nsslapd-dncachememsize: $dncsize

dn: cn=$DB2,$dbdn
changetype: modify
replace: nsslapd-cachememsize
nsslapd-cachememsize: $ecsize
-
replace: nsslapd-dncachememsize
nsslapd-dncachememsize: $dncsize

dn: $dbconfdn
changetype: modify
replace: nsslapd-dbcachesize
nsslapd-dbcachesize: $dbcsize

EOF

    attr="nsslapd-db-home-directory"
    attrval="$attr: $RAMDISK"
    stopds
    sed -i '/^dn: '"$dbconfdn"'/,/^$/ { /^'"$attr"'/d ; /^$/s,$,'"$attrval"'\n, }' $PREFIX/etc/dirsrv/slapd-$INST/dse.ldif
    rm -f $RAMDISK/*
    startds
}

dogenldif() {
    rm -f $DIR/$1.ldif $DIR/$1.ldif.bz
    {
        echo dn: $2
        echo objectclass: organizationalUnit
        echo ""
        echo dn: ou=People,$2
        echo objectclass: organizationalUnit
        echo ""
        $PREFIX/bin/dbgen.pl -o - -n $NENTRIES -b 1 -j $NDIGITS -s "$2" -x -y
    } | bzip2 > $DIR/$1.ldif.bz2
}

genldif() {
    dogenldif $DB1 "$SUF1"
    dogenldif $DB2 "$SUF2"
}

doloaddb() {
    bzip2 -dc $DIR/$1.ldif.bz2 | $PREFIX/lib/dirsrv/slapd-$INST/ldif2db -n $1 -i -
}

loaddb() {
    doloaddb $DB1
    doloaddb $DB2
}

stopds() {
    $PREFIX/sbin/stop-dirsrv $INST
}

startds() {
    $PREFIX/sbin/start-dirsrv $INST
}

restartds() {
    $PREFIX/sbin/restart-dirsrv $INST
}

cleanup() {
    $PREFIX/sbin/remove-ds.pl -i slapd-$INST
}

#	    -e timestamp,esearch,random,srchnentries=1,sampinterval=$INTERVAL \
dosearch() {
    opts=esearch,random
    if [ "$USEINCR" = 1 ] ; then
        opts="incr=$INCR,commoncounter"
    fi
    $GDB $LDCLT -h $HOST -p $PORT -D "$LDCLTDN" -w "$LDCLTPW" \
        $ASYNC \
	    -e timestamp,esearch,$opts,srchnentries=1,sampinterval=$INTERVAL \
        $EXTRALDCLTOPTS \
	    -r${STARTNUM:-1} -R${ENDNUM:-$NENTRIES} \
	    -n$NTHREADS \
	    -f $LDCLTFLT -b "$1" \
	    -v -q &
    sleep $DURATION
    kill -2 %1
}

domod() {
    opts=random
    if [ "$USEINCR" = 1 ] ; then
        opts="incr=$INCR,commoncounter"
    fi
    $LDCLT -h $HOST -p $PORT -D "$LDCLTDN" -w "$LDCLTPW" \
        $ASYNC \
	    -e timestamp,$opts,attreplace=givenName:valueXXXXXXXXXX,sampinterval=$INTERVAL \
        $EXTRALDCLTOPTS \
	    -r${STARTNUM:-1} -R${ENDNUM:-$NENTRIES} \
	    -n$NTHREADS \
	    -f $LDCLTFLT -b "$1" \
	    -q &
    sleep $DURATION
    kill -2 %1
}

dosearch1() { LDCLTFLT=${LDCLTFLT:-$LDCLTFLT1} dosearch "$SUF1" ; }
dosearch2() { LDCLTFLT=${LDCLTFLT:-$LDCLTFLT2} dosearch "$SUF2" ; }

domod1() { LDCLTFLT=${LDCLTFLT:-$LDCLTFLT1} domod "$MODSUF1" ; }
domod2() { LDCLTFLT=${LDCLTFLT:-$LDCLTFLT2} domod "$MODSUF2" ; }

gnuplotheader='
set terminal png font "'$GPFONT'" 12 size 1700,1800
set xlabel "Time"
set xdata time
set timefmt "%s"
set format x "%H:%M:%S"
set grid'

doplot() {
    graphout=$1 ; shift
    extradat=$1 ; shift
    gpstr="plot"
    gpnext=""
    while [ $1 ] ; do
        gpoutf=$1 ; shift
        field=$1 ; shift
        gpstr="${gpstr}$gpnext "'"'$gpoutf'" using 1:2 title "'"$field"'" with lines'
        gpnext=", "
        # get stats
        statstr="$statstr"'
plot "'$gpoutf'" u 1:2
'$field'_min = GPVAL_DATA_Y_MIN
'$field'_max = GPVAL_DATA_Y_MAX
f(x) = '$field'_mean
fit f(x) "'$gpoutf'" u 1:2 via '$field'_mean
'$field'_dev = sqrt(FIT_WSSR / (FIT_NDF + 1 ))
labelstr = labelstr . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'$field'", '$field'_mean, '$field'_min, '$field'_max, '$field'_dev)'
    done

    # output of fit command goes to stderr - no way to turn it off :P
    gnuplot <<EOF 2> /dev/null
extradat = system("cat $extradat")
set fit logfile "/dev/null"
set terminal unknown
labelstr = ""
$statstr
$gnuplotheader
set label 1 labelstr at screen 0.6,0.99
set label 2 extradat at screen 0.01,0.99
set key at screen 1.0,1.0
set output "$graphout"
set title "Ops/Second by Time"
set ylabel "ops/sec (linear)"
set multiplot
set size 1.0,0.45
set origin 0.0,0.45
set mytics 2
$gpstr
unset label 1
unset label 2
unset title
set mytics default
set size 1.0,0.45
set origin 0.0,0.0
set logscale y
set ylabel "ops/sec (logarithmic)"
replot
unset multiplot
EOF
}

doplot2() {
    graphout=$1 ; shift
    extradat=$1 ; shift
    gpstr="plot"
    gpnext=""
    while [ $1 ] ; do
        gpoutf=$1 ; shift
        col=$1 ; shift
        field=$1 ; shift
        gpstr="${gpstr}$gpnext "'"'$gpoutf'" using 1:'$col' title "'"$field"'" with lines'
        gpnext=", "
        # get stats
        statstr="$statstr"'
plot "'$gpoutf'" u 1:'$col'
'$field'_min = GPVAL_DATA_Y_MIN
'$field'_max = GPVAL_DATA_Y_MAX
f(x) = '$field'_mean
fit f(x) "'$gpoutf'" u 1:'$col' via '$field'_mean
'$field'_dev = sqrt(FIT_WSSR / (FIT_NDF + 1 ))
labelstr = labelstr . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'$field'", '$field'_mean, '$field'_min, '$field'_max, '$field'_dev)'
    done

    # output of fit command goes to stderr - no way to turn it off :P
    gnuplot <<EOF
extradat = system("cat $extradat")
set fit logfile "/dev/null"
set terminal unknown
labelstr = ""
$statstr
$gnuplotheader
set label 1 labelstr at screen 0.4,0.99
set label 2 extradat at screen 0.01,0.99
set key at screen 1.0,1.0
set output "$graphout"
set title "Ops/Second by Time"
set ylabel "ops/sec (linear)"
set multiplot
set size 1.0,0.45
set origin 0.0,0.45
set mytics 2
$gpstr
unset label 1
unset label 2
unset title
set mytics default
set size 1.0,0.45
set origin 0.0,0.0
set logscale y
set ylabel "ops/sec (logarithmic)"
$gphead
replot
unset multiplot
EOF
}

cnvtldcltoutput() {
    # convert
    #1357916905|ldclt[5054]: Average rate:   42.12/thr  ( 337.00/sec), total:    337
    # to
    #1357916905 337
    # throw away ldclt header and footer data
    # sum counts during same time period
    gawk -F '[|]ldclt.*Average.*total: *' 'NF > 1 {
        sums[$1] += $2
        if (NR == 1) next
        if (lastone != $1) {
            print lastone, sums[lastone]; delete sums[lastone]; lastone = $1
        }
    }
    END { print lastone, sums[lastone] }
'
}

# get the beginning and ending timestamp from a converted ldclt output, or any type of file where the
# timestamp is in the first column
getstartendts()
{
    awk -v end=$1 'BEGIN {firsttime=1} ; { ts = $1; if ($1 && firsttime && !end) { print ts ; firsttime = 0 } } ; END {if (end) {print ts}}'
}

cnvtiostatoutput()
{
#01/25/2013 10:46:26 PM
#    awk -v hroff=4 -F '[T /:-]' '
    awk -v hroff=-8 -v secoff=-9 -v startts=$1 -v endts=$2 -F '[T /:-]+' '
#    BEGIN { print "hroff=" hroff }
    /^[0-9][0-9][/][0-9][0-9][/][0-9][0-9][0-9][0-9] [0-9][0-9][:][0-9][0-9][:][0-9][0-9]/ {
        origts=$0
        if ($7 == "AM") { if ($4 == 12) { ampm=12 } else { ampm=0 } } # convert 12 am to 00
        if ($7 == "PM") { if ($4 == 12) { ampm=0 } else { ampm=-12 } } # convert 1 pm to 13
        ts=mktime($3 " " $1 " " $2 " " ($4-ampm) " " $5 " " $6)
#        print "rawts=" ts
        ts=ts + (hroff * 3600) + secoff
#        print "convertedts=" ts
    }
    /^[0-9][0-9][0-9][0-9][-][0-9][0-9][-][0-9][0-9]T[0-9][0-9][:][0-9][0-9][:][0-9][0-9][-][0-9][0-9][0-9][0-9]/ {
        ts=mktime($1 " " $2 " " $3 " " $4 " " $5 " " $6)
        ts=ts + ($7/100 * 3600) + secoff
    }
    $1 == "sda" { if ((ts >= startts) && (ts <= endts)) { print ts " " $3 " " $4 " " origts } }
'
}

cnvtdbmonoutput()
{
#Fri Jan 25 22:46:23 CET 2013
# posix version - except with --posix can't use mktime :P
# posix - adding nice regex features but taking away useful time functions :P
#    /^([[:alpha:]]{3} ){2}[[:digit:]]+ [[:digit:]]{2}[:][[:digit:]]{2}[:][[:digit:]]{2} [[:alpha:]]+ [[:digit:]]{4}/ {
    awk -v hroff=-8 -v secoff=0 -v startts=$1 -v endts=$2 -F '[: ]+' '
    BEGIN {
        x="Jan 01 Feb 02 Mar 03 Apr 04 May 05 Jun 06 Jul 07 Aug 08 Sep 09 Oct 10 Nov 11 Dec 12"
        split(x,data)
        for(i = 1 ; i < 25 ; i += 2) {
            mon[data[i]]=data[i+1]
        }
        d2="nsslapd-db-cache-hit nsslapd-db-cache-try nsslapd-db-page-ro-evict-rate nsslapd-db-page-read-rate currententrycachesize"
        split(d2,attrlist)
        lastattr=""
        for (attr in attrlist) { n=attrlist[attr] ; attrs[n] = 0 ; lastattr = tolower(n) ; scalefactor[n] = 1 }
        scalefactor["nsslapd-db-cache-try"] = 0.1
        scalefactor["nsslapd-db-cache-hit"] = 0.1
        scalefactor["currententrycachesize"] = 0.001
    }
    /^[a-zA-Z][a-zA-Z][a-zA-Z] [a-zA-Z][a-zA-Z][a-zA-Z] [0-9][0-9]* [0-9][0-9][:][0-9][0-9][:][0-9][0-9] [a-zA-Z][a-zA-Z]* [0-9][0-9][0-9][0-9]/ {
        m=mon[$2]
        ts=mktime($8 " " m " " $3 " " $4 " " $5 " " $6)
        ts=ts + (hroff * 3600) + secoff
    }
    {
        if (tolower($1) in attrs) {
#            print
            key = tolower($1)
            attrs[key] = $2 * scalefactor[key]
            if ((key == lastattr) && (ts >= startts) && (ts <= endts)) {
                printf "%d", ts
                for (ii = 1; ii in attrlist; ++ii) {
#                    print "ii=" ii
                    n = tolower(attrlist[ii])
#                    print "n=" n
                    v = attrs[n] - lastattrs[n]
                    # reduce churn
                    if ((n == "currententrycachesize") && (v < 50)) {
                        v = 50
                    }
                    printf " %d", v
                    lastattrs[n] = attrs[n]
                }
                printf "\n"
            }
        }
    }
'
}

cnvtfreeoutput()
{
# 1359414078
#              total       used       free     shared    buffers     cached
# Mem:      24604420    1217468   23386952          0       8000     763724
# -/+ buffers/cache:     445744   24158676
# Swap:            0          0          0
    awk -v hroff=0 -v secoff=-9 -v startts=$1 -v endts=$2 '
    BEGIN { prevts=0 }
    /^[0-9][0-9]*/ {
        ts=$1+secoff
        if (prevts && (ts != prevts) && (ts >= startts) && (ts <= endts)) {
            print prevts " " buf " " cache
        }
        prevts=ts
    }
    /^Mem:/ { buf=$6 ; cache=$7/5000 }
'
}

cnvtiotopoutput()
{
# Total DISK READ: 0.00 K/s | Total DISK WRITE: 0.00 K/s
#     TIME  TID  PRIO  USER     DISK READ  DISK WRITE  SWAPIN      IO    COMMAND
# 00:01:13 26634 be/4 nobody      0.00 K/s    0.00 K/s  0.00 %  0.00 % ns-slapd -D /etc/dirsrv/slapd-389 -i /var/run/dirsrv/slapd-389.pid -w /var/run/dirsrv/slapd-389.startpid
    awk -v hroff=-8 -v secoff=-9 -v startts=$1 -v endts=$2 -F '[ :]*' '
    BEGIN { yr = strftime("%Y", startts) ; mon = strftime("%m", startts) ; day = strftime("%d", startts) }
    /^Total DISK READ:/ { totalr=$4 ; totalw=$10; doprint=1 }
    /ns-slapd/ {
        if (doprint) {
            origts=$1 ":" $2 ":" $3
            ts=mktime(yr " " mon " " day " " $1 " " $2 " " $3)+(hroff*3600)+secoff
            if ((ts >= startts) && (ts <= endts)) {
                print ts " " totalr " " totalw " " $7 " " $9 " " origts
            } else {
#                diff=ts - startts
#                hrs=diff/3600
#                print "ts diff is " diff " hrs " hrs
            }
            doprint = 0
        }
    }
'
}

comptimedata()
{
    graphout=$1 ; shift
    # first, get the start/end time for each data set
    gpstr="plot"
    gpnext=""
    while [ $1 ] ; do
        fn=$1 ; shift
        field=$1 ; shift
        startts=`getstartendts < $fn`
        gpstr="$gpstr$gpnext "'"'$fn'" using (timecolumn(1)-'$startts'):2 title "'$field'" with lines'
        gpnext=", "
        # get stats
        statstr="$statstr"'
plot "'$fn'" u 1:2
'$field'_min = GPVAL_DATA_Y_MIN
'$field'_max = GPVAL_DATA_Y_MAX
f(x) = '$field'_mean
fit f(x) "'$fn'" u 1:2 via '$field'_mean
'$field'_dev = sqrt(FIT_WSSR / (FIT_NDF + 1 ))
labelstr = labelstr . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'$field'", '$field'_mean, '$field'_min, '$field'_max, '$field'_dev)'
    done
    gnuplot <<EOF
set fit logfile "/dev/null"
set terminal unknown
labelstr = ""
$statstr
$gnuplotheader
set label 1 labelstr at screen 0.4,0.99
set output "$graphout"
set title "Ops/Second by Time"
set ylabel "ops/sec (linear)"
set multiplot
set size 1.0,0.45
set origin 0.0,0.45
set mytics 2
$gpstr
unset label 1
unset label 2
unset title
set mytics default
set size 1.0,0.45
set origin 0.0,0.0
set logscale y
set ylabel "ops/sec (logarithmic)"
replot
unset multiplot
EOF
}

run() {
    OUTD=`mktemp -d --tmpdir=$DIR`
    EXTRA=$OUTD/extra.dat
    S1OUT=$OUTD/s1.out
    S2OUT=$OUTD/s2.out
    MOUT=$OUTD/mod.out
    S1DAT=$OUTD/s1.dat
    S2DAT=$OUTD/s2.dat
    MDAT=$OUTD/mod.dat

    startts=`date --rfc-3339=seconds`
    ver=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "" "objectclass=*" vendorVersion | grep vendorVersion`
    nthr=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=config" "objectclass=*" nsslapd-threadnumber | grep threadnumber`
    dbcache=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=config,cn=ldbm database,cn=plugins,cn=config" "objectclass=*" nsslapd-dbcachesize | grep dbcachesize`
    cache1=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=monitor,cn=$DB1,$dbdn" currententrycachesize maxentrycachesize currententrycachecount currentdncachesize maxdncachesize currentdncachecount | grep -v '^$'`
    cache2=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=monitor,cn=$DB2,$dbdn" currententrycachesize maxentrycachesize currententrycachecount currentdncachesize maxdncachesize currentdncachecount | grep -v '^$'`

    ii=$S1NPROCS
    echo starting $ii search1 procs
    # each proc needs a non-overlapping range of values
    range=`expr $NENTRIES / $S1NPROCS`
    if [ $range -le $INCR ] ; then
        echo Error: range $range for $NENTRIES / $S1NPROCS is less than the increment $INCR
        exit 1
    fi
    start=1
    end=$range
    while [ $ii -gt 0 ] ; do
        NTHREADS=$S1THREADS STARTNUM=$start ENDNUM=$end ASYNC="-a 10" dosearch1 > $S1OUT.$ii 2>&1 &
        ii=`expr $ii - 1`
        start=`expr $start + $range`
        end=`expr $end + $range`
    done
    ii=$S2NPROCS
    echo starting $ii search2 procs 
    # each proc needs a non-overlapping range of values
    range=`expr $NENTRIES / $S2NPROCS`
    if [ $range -le $INCR ] ; then
        echo Error: range $range for $NENTRIES / $S2NPROCS is less than the increment $INCR
        exit 1
    fi
    start=1
    end=$range
    while [ $ii -gt 0 ] ; do
        NTHREADS=$S2THREADS STARTNUM=$start ENDNUM=$end ASYNC="-a 10" dosearch2 > $S2OUT.$ii 2>&1 &
        ii=`expr $ii - 1`
        start=`expr $start + $range`
        end=`expr $end + $range`
    done

    echo starting mods
    NTHREADS=$MTHREADS domod1 > $MOUT 2>&1 &
    wait

    endts=`date --rfc-3339=seconds`
    spaces="                             "
    cat <<EOF >> $EXTRA
Test Duration $DURATION seconds Start $startts End $endts
search1: procs=$S1NPROCS threads=$S1THREADS async=10 search2: procs=$S2NPROCS threads=$S2THREADS async=10 mod: procs=1 threads=$MTHREADS
$ver $nthr
numentries: $NENTRIES $dbcache
EOF
    echo $cache1 | fmt -100 >> $EXTRA
    echo $cache2 | fmt -100 >> $EXTRA
    echo converting search1 data
    sort -n $S1OUT.* | cnvtldcltoutput > $S1DAT
    echo converting search2 data
    sort -n $S2OUT.* | cnvtldcltoutput > $S2DAT
    echo converting mods data
    cnvtldcltoutput < $MOUT > $MDAT

    echo plotting data
    doplot $OUTD/graph.png $EXTRA $S1DAT search1 $S2DAT search2 $MDAT mod
}

ldapdbmon()
{
    while [ 1 ] ; do
        date +"%s"
        ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=database,cn=monitor,cn=ldbm database,cn=plugins,cn=config"
        ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=monitor,cn=$1,cn=ldbm database,cn=plugins,cn=config"
        sleep $INTERVAL
    done
}

ldapdbmon1() { ldapdbmon "$DB1"; }
ldapdbmon2() { ldapdbmon "$DB2"; }

run2plots()
{
    OUTD=$1 ; shift
    EXTRA=$OUTD/extra.dat
    SOUT=$OUTD/srch.out
    SDAT=$OUTD/srch.dat
    MONOUT=$OUTD/mon.out
    MONDAT=$OUTD/mon.dat
    IOOUT=$OUTD/iostat.out
    IODAT=$OUTD/iostat.dat
    FOUT=$OUTD/free.out
    FDAT=$OUTD/free.dat
    IOTOUT=$OUTD/iotop.out
    IOTDAT=$OUTD/iotop.dat

    if [ ! -f $SDAT ] ; then
        echo converting search data
        sort -n $SOUT* | cnvtldcltoutput > $SDAT
    fi
    startts=`getstartendts < $SDAT`
    endts=`getstartendts 1 < $SDAT`
    if [ -f $IOOUT -a ! -f $IODAT ] ; then
        echo convert iostat output between $startts and $endts
        cnvtiostatoutput $startts $endts < $IOOUT > $IODAT
    fi
    if [ -f $MONOUT -a ! -f $MONDAT ] ; then
        echo convert dbmon output between $startts and $endts
        cnvtdbmonoutput $startts $endts < $MONOUT > $MONDAT
    fi
    if [ -f $FOUT -a ! -f $FDAT ] ; then
        echo convert free output between $startts and $endts
        cnvtfreeoutput $startts $endts < $FOUT > $FDAT
    fi
    if [ -f $IOTOUT -a ! -f $IOTDAT ] ; then
        echo convert iotop output between $startts and $endts
        cnvtiotopoutput $startts $endts < $IOTOUT > $IOTDAT
    fi

    echo plotting data
    args="$OUTD/graph.png $EXTRA $SDAT 2 search"
    if [ -f $IODAT ] ; then
        args="$args $IODAT 2 sda_blkreads_k_per_sec"
    fi
    if [ -f $MONDAT ] ; then
        args="$args $MONDAT 2 db_cache_hits_n_per_sec $MONDAT 3 db_cache_tries_n_per_sec $MONDAT 4 db_ro_evict_n_per_secs $MONDAT 5 db_page_read_n_per_secs $MONDAT 6 entrycache_mbytes"
    fi
    if [ -f $FDAT ] ; then
        args="$args $FDAT 3 fs_cache_mbytes"
    fi
    if [ -f $IOTDAT ] ; then
        args="$args $IOTDAT 4 slapdread_kbytes_per_sec"
    fi
    doplot2 $args
}

mod2plots()
{
    OUTD=$1 ; shift
    EXTRA=$OUTD/extra.dat
    MOUT=$OUTD/mod.out
    MDAT=$OUTD/mod.dat
    MONOUT=$OUTD/mon.out
    MONDAT=$OUTD/mon.dat
    IOOUT=$OUTD/iostat.out
    IODAT=$OUTD/iostat.dat
    FOUT=$OUTD/free.out
    FDAT=$OUTD/free.dat
    IOTOUT=$OUTD/iotop.out
    IOTDAT=$OUTD/iotop.dat

    if [ ! -f $MDAT ] ; then
        echo converting search data
        sort -n $MOUT* | cnvtldcltoutput > $MDAT
    fi
    startts=`getstartendts < $MDAT`
    endts=`getstartendts 1 < $MDAT`
    if [ -f $IOOUT -a ! -f $IODAT ] ; then
        echo convert iostat output between $startts and $endts
        cnvtiostatoutput $startts $endts < $IOOUT > $IODAT
    fi
    if [ -f $MONOUT -a ! -f $MONDAT ] ; then
        echo convert dbmon output between $startts and $endts
        cnvtdbmonoutput $startts $endts < $MONOUT > $MONDAT
    fi
    if [ -f $FOUT -a ! -f $FDAT ] ; then
        echo convert free output between $startts and $endts
        cnvtfreeoutput $startts $endts < $FOUT > $FDAT
    fi
    if [ -f $IOTOUT -a ! -f $IOTDAT ] ; then
        echo convert iotop output between $startts and $endts
        cnvtiotopoutput $startts $endts < $IOTOUT > $IOTDAT
    fi

    echo plotting data
    args="$OUTD/graph.png $EXTRA $MDAT 2 mods_per_sec"
    if [ -f $IODAT ] ; then
        args="$args $IODAT 2 sda_blkreads_k_per_sec"
    fi
    if [ -f $MONDAT ] ; then
        args="$args $MONDAT 2 db_cache_hits_n_per_sec $MONDAT 3 db_cache_tries_n_per_sec $MONDAT 4 db_ro_evict_n_per_secs $MONDAT 5 db_page_read_n_per_secs $MONDAT 6 entrycache_mbytes"
    fi
    if [ -f $FDAT ] ; then
        args="$args $FDAT 3 fs_cache_mbytes"
    fi
    if [ -f $IOTDAT ] ; then
#        args="$args $IOTDAT 2 sysrd_kbytes_per_sec $IOTDAT 3 syswr_kbytes_per_sec $IOTDAT 4 dsrd_kbytes_per_sec $IOTDAT 5 dswr_kbytes_per_sec"
        args="$args $IOTDAT 5 dswr_kbytes_per_sec"
    fi
    doplot2 $args
}

run2()
{
    OUTD=`mktemp -d --tmpdir=$DIR`
    EXTRA=$OUTD/extra.dat
    SOUT=$OUTD/srch.out
    SDAT=$OUTD/srch.dat
    IOOUT=$OUTD/iostat.out
    IODAT=$OUTD/iostat.dat
    MONOUT=$OUTD/mon.out
    MONDAT=$OUTD/mon.dat

    startts=`date --rfc-3339=seconds`
    ver=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "" "objectclass=*" vendorVersion | grep vendorVersion`
    nthr=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=config" "objectclass=*" nsslapd-threadnumber | grep threadnumber`

    ldapdbmon2 > $MONOUT 2>&1 & monpid=$!

    ii=1
    echo starting $ii search procs 
    # each proc needs a non-overlapping range of values
    range=`expr $NENTRIES / $S2NPROCS`
    if [ $range -le $INCR ] ; then
        echo Error: range $range for $NENTRIES / $SNPROCS is less than the increment $INCR
        exit 1
    fi
    start=1
    end=$range
    while [ $ii -gt 0 ] ; do
        NTHREADS=1 STARTNUM=$start ENDNUM=$end dosearch2 > $SOUT 2>&1 &
        ii=`expr $ii - 1`
        start=`expr $start + $range`
        end=`expr $end + $range`
    done

    endts=`date --rfc-3339=seconds`
    spaces="                             "
    cat <<EOF >> $EXTRA
Test Duration $DURATION seconds Start $startts End $endts
search2: procs=1 threads=1 $ver $nthr numentries: $NENTRIES
EOF
    echo converting search data
    sort -n $SOUT* | cnvtldcltoutput > $SDAT

    echo plotting data
    run2plots
}

for cmd in "$@" ; do
    case $cmd in
    doplot) shift ; doplot "$@" ; exit 0 ;;
    comptimedata) shift ; comptimedata "$@" ; exit 0 ;;
    run2plots) shift ; run2plots "$@" ; exit 0 ;;
    mod2plots) shift ; mod2plots "$@" ; exit 0 ;;
    cnvtiostatoutput) shift ; cnvtiostatoutput "$@" ; exit 0 ;;
    cnvtdbmonoutput) shift ; cnvtdbmonoutput "$@" ; exit 0 ;;
    cnvtfreeoutput) shift ; cnvtfreeoutput "$@" ; exit 0 ;;
    cnvtiotopoutput) shift ; cnvtiotopoutput "$@" ; exit 0 ;;
    esac
    $cmd || { echo Error: $cmd returned error $! ; exit 1 ; }
done
