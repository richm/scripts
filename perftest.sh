#!/bin/sh

DIR=${DIR:-.}
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
ROOTPW=${ROOTPW:-secret}
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
    if [ -f $DIR/$1.ldif ] ; then
        cat $DIR/$1.ldif | $PREFIX/lib/dirsrv/slapd-$INST/ldif2db -n $1 -i -
    else
        bzip2 -dc $DIR/$1.ldif.bz2 | $PREFIX/lib/dirsrv/slapd-$INST/ldif2db -n $1 -i -
    fi
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

getextrastart() {
    startts=`date --rfc-3339=seconds`
    ver=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "" "objectclass=*" vendorVersion | grep vendorVersion`
    nthr=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=config" "objectclass=*" nsslapd-threadnumber | grep threadnumber`
    dbcache=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=config,cn=ldbm database,cn=plugins,cn=config" "objectclass=*" nsslapd-dbcachesize | grep dbcachesize`
    cache1=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=monitor,cn=$DB1,$dbdn" currententrycachesize maxentrycachesize currententrycachecount currentdncachesize maxdncachesize currentdncachecount | grep -v '^$'`
    cache2=`ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=monitor,cn=$DB2,$dbdn" currententrycachesize maxentrycachesize currententrycachecount currentdncachesize maxdncachesize currentdncachecount | grep -v '^$'`
}

getextraend() {
    echo EXTRASTART
    endts=`date --rfc-3339=seconds`
    cat <<EOF
Test Duration $DURATION seconds Start $startts End $endts
$ver $nthr
EOF
    echo $cache1 | fmt -100
    echo $cache2 | fmt -100
    echo EXTRAEND
}

#	    -e timestamp,esearch,random,srchnentries=1,sampinterval=$INTERVAL \
dosearch() {
    opts=esearch,random
    if [ "$USEINCR" = 1 ] ; then
        opts="incr=$INCR,commoncounter"
    fi
    getextrastart
    $GDB $LDCLT -h $HOST -p $PORT -D "$LDCLTDN" -w "$LDCLTPW" \
        $ASYNC \
	    -e timestamp,esearch,$opts,srchnentries=1,sampinterval=$INTERVAL \
        $EXTRALDCLTOPTS \
	    -r${STARTNUM:-1} -R${ENDNUM:-$NENTRIES} \
	    -n$NTHREADS \
	    -f $LDCLTFLT -b "$1" \
	    -v -q & pid=$!
    # give ldclt a chance to run
    sleep 5
    kill -s 0 $pid || { echo Error: $LDCLT exited unexpectedly ; return 1 ; }
    sleep `expr $DURATION - 5`
    kill -2 $pid
    wait $pid
    getextraend
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

XLABEL=${XLABEL:-"Time"}
gnuplotheader='
set terminal png font "'$GPFONT'" 12 size 1700,1800
set xlabel "'"$XLABEL"'"
set xdata time
set timefmt "%s"
set format x "%H:%M:%S"
set grid'

doplot() {
    graphout=$1 ; shift
    extradat=$1 ; shift
    DELIM=${DELIM:-" "}
    if [ -n "$AUTOTITLE" ] ; then
        AUTOTITLE="set key autotitle columnhead"
    fi
    TITLE=${TITLE:-"Ops/Second by Time"}
    YLABEL=${YLABEL:-"ops/sec"}
    gpstr="plot"
    gpnext=""
    ii=1
    while [ $1 ] ; do
        gpoutf=$1 ; shift
        col=$1 ; shift
        field="$1" ; shift
        fieldvar="field$ii"
        gpstr="${gpstr}$gpnext "'"'$gpoutf'" using 1:'$col' title "'"$field"'" with lines'
        gpnext=", "
        # get stats
        statstr="$statstr"'
plot "'$gpoutf'" u 1:'$col'
'$fieldvar'_min = GPVAL_DATA_Y_MIN
'$fieldvar'_max = GPVAL_DATA_Y_MAX
f(x) = '$fieldvar'_mean
fit f(x) "'$gpoutf'" u 1:'$col' via '$fieldvar'_mean
'$fieldvar'_dev = sqrt(FIT_WSSR / (FIT_NDF + 1 ))
labelstr = labelstr . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'"$field"'", '$fieldvar'_mean, '$fieldvar'_min, '$fieldvar'_max, '$fieldvar'_dev)'
        ii=`expr $ii + 1`
    done

    # output of fit command goes to stderr - no way to turn it off :P
    gnuplot <<EOF 2> /dev/null
extradat = system("cat $extradat")
set fit logfile "/dev/null"
set terminal unknown
labelstr = ""
$statstr
$gnuplotheader
$AUTOTITLE
set datafile separator "$DELIM"
set label 1 labelstr at screen 0.4,0.99
set label 2 extradat at screen 0.01,0.99
set key at screen 1.0,1.0
set output "$graphout"
set title "$TITLE"
set ylabel "$YLABEL (linear)"
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
set ylabel "$YLABEL (logarithmic)"
replot
unset multiplot
EOF
}

doplotvar()
{
    graphout=$1 ; shift
    extradat=$1 ; shift
    DELIM=${DELIM:-" "}
    AUTOTITLE="set key autotitle columnhead"
    TITLE=${TITLE:-"Ops/Second by Time"}
    YLABEL=${YLABEL:-"ops/sec"}
    gpstr=""
    ii=1
    while [ $1 ] ; do
        gpoutf=$1 ; shift # the data file
        ncol=$1 ; shift # the number of columns in the datafile
        col=2
        gpstr="plot"
        gpnext=""
        while [ $col -le $ncol ] ; do
            fieldvar="field${ii}_$col"
            gpstr="${gpstr}$gpnext "'"'$gpoutf'" using ($1-21600):'$col' with lines'
            gpnext=", "
            # get stats
            statstr="$statstr"'
plot "'$gpoutf'" u 1:'$col'
'$fieldvar'_min = GPVAL_DATA_Y_MIN
'$fieldvar'_max = GPVAL_DATA_Y_MAX
f(x) = '$fieldvar'_mean
fit f(x) "'$gpoutf'" u 1:'$col' via '$fieldvar'_mean
'$fieldvar'_dev = sqrt(FIT_WSSR / (FIT_NDF + 1 ))
labelstr = labelstr . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'"$fieldvar"'", '$fieldvar'_mean, '$fieldvar'_min, '$fieldvar'_max, '$fieldvar'_dev)'
            col=`expr $col + 1`
        done
        ii=`expr $ii + 1`
    done

    # output of fit command goes to stderr - no way to turn it off :P
    gnuplot <<EOF 2> /dev/null
extradat = system("cat $extradat")
set fit logfile "/dev/null"
set terminal unknown
set datafile separator "$DELIM"
labelstr = ""
$statstr
$gnuplotheader
$AUTOTITLE
set label 1 labelstr at screen 0.4,0.99
set label 2 extradat at screen 0.01,0.99
set key at screen 1.0,1.0
set output "$graphout"
set title "$TITLE"
set ylabel "$YLABEL (linear)"
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
set ylabel "$YLABEL (logarithmic)"
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
    gawk -F '[|]ldclt.*Average rate.*total: *' '
    BEGIN { sum = 0; lastone = 0; nn = 1; sumsq=0; min=9999999999; max=0; }
    NF > 1 {
        sums[$1] += $2
        if (!lastone) { lastone = $1 }
        if (lastone != $1) {
            lastsum = sums[lastone]
            sum += lastsum
            sumsq += lastsum * lastsum
            if (lastsum > max) { max=lastsum }
            if (lastsum < min) { min=lastsum }
            print lastone, lastsum, (sum/nn); delete sums[lastone]; lastone = $1 ; ++nn
        }
    }
    END { lastsum = sums[lastone] ; sum += lastsum ; avg = sum/nn ; sumsq += lastsum * lastsum ;
          dev = sqrt(sumsq/nn - (avg)**2) ;
          print lastone, lastsum, avg, min, max, dev }
'
}

cnvtoldldcltoutput() {
    # old format doesn't timestamp each line
    #Sampling interval  = 10 sec
    #ldclt[18791]: Starting at Thu May  2 18:06:35 2013
    #ldclt[18791]: Average rate:  613.50/thr  ( 490.80/sec), total:   4908
    # throw away ldclt header and footer data
    # sum counts during same time period
    awk -F '[ :]+' '
    BEGIN { sum = 0; nn = 1; sumsq=0; min=9999999999; max=0
        x="Jan 01 Feb 02 Mar 03 Apr 04 May 05 Jun 06 Jul 07 Aug 08 Sep 09 Oct 10 Nov 11 Dec 12"
        split(x,data)
        for(i = 1 ; i < 25 ; i += 2) {
            mon[data[i]]=data[i+1]
        }
        mints=9999999999999
        maxts=0
    }
    /^Sampling interval/ {intv=$4}
    /Starting at/ {
        m=mon[$5]
        origts=$4 " " $5 " " $6 " " $7 ":" $8 ":" $9 " " $10
        ts=mktime($10 " " m " " $6 " " $7 " " $8 " " $9)
        if (ts < mints) { mints=ts }
        if (ts > maxts) { maxts=ts }
    }
    /Average rate:.*\/thr.*, total:/ {
        sum += $NF
        sums[ts] += $NF
        if (ts > maxts) { maxts=ts }
        ts += intv
    }
    END {
        globalavg = sum / (maxts - mints)
        for (ii = mints; ii <= maxts; ++ii) {
            if (ii in sums) {
                if (ii == maxts) {
                    print ii, sums[ii], globalavg
                } else {
                    print ii, sums[ii]
                }
            }
        }
    }
'
}

# get the beginning and ending timestamp from a converted ldclt output, or any type of file where the
# timestamp is in the first column
getstartendts() {
    awk -v end=$1 'BEGIN {firsttime=1} ; { ts = $1; if ($1 && firsttime && !end) { print ts ; firsttime = 0 } } ; END {if (end) {print ts}}'
}

cnvtiostatoutput() {
#01/25/2013 10:46:26 PM
#    awk -v hroff=4 -F '[T /:-]' '
    awk -v hroff=-8 -v secoff=-9 -v startts=$1 -v endts=$2 -F '[T /:-]+' '
#    BEGIN { print "hroff=" hroff }
    BEGIN { sum[3] = 0 ; sum[4] = 0 ; nn = 1 }
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
    $1 == "sda" && (ts >= startts) && (ts <= endts) {
        sum[3] += $3 ; sum[4] += $4
        print ts, $3, $4, (sum[3]/nn), (sum[4]/nn), origts
        nn++
    }
'
}

cnvtdbmonoutput() {
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
        for (attr in attrlist) { n=attrlist[attr] ; attrs[n] = 0 ; lastattr = tolower(n) ; scalefactor[n] = 1 ; sum[n] = 0 }
        scalefactor["nsslapd-db-cache-try"] = 0.1
        scalefactor["nsslapd-db-cache-hit"] = 0.1
        scalefactor["currententrycachesize"] = 0.001
        nn = 1
    }
    /^[a-zA-Z][a-zA-Z][a-zA-Z] [a-zA-Z][a-zA-Z][a-zA-Z]  *[0-9][0-9]* [0-9][0-9][:][0-9][0-9][:][0-9][0-9] [a-zA-Z][a-zA-Z]* [0-9][0-9][0-9][0-9]/ {
        m=mon[$2]
        ts=mktime($8 " " m " " $3 " " $4 " " $5 " " $6)
        ts=ts + (hroff * 3600) + secoff
    }
    (ts >= startts) && (ts <= endts) && (tolower($1) in attrs) {
        key = tolower($1)
        attrs[key] = $2 * scalefactor[key]
        if (key == lastattr) {
            printf "%d", ts
            for (ii = 1; ii in attrlist; ++ii) {
#                print "ii=" ii
                n = tolower(attrlist[ii])
#                print "n=" n
                v = attrs[n] - lastattrs[n]
                # reduce churn
                if ((n == "currententrycachesize") && (v < 50)) {
                    v = 50
                }
                printf " %d", v
                lastattrs[n] = attrs[n]
                sum[n] += v
            }
            for (ii = 1; ii in attrlist; ++ii) {
#                print "ii=" ii
                n = tolower(attrlist[ii])
                printf " %f", (sum[n]/nn)
            }
            printf "\n"
            nn++
        }
    }
'
}

cnvtfreeoutput() {
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
            print prevts, buf, cache
        }
        prevts=ts
    }
    /^Mem:/ { buf=$6 ; cache=$7/5000 }
'
}

cnvtiotopoutput() {
# output of
# iotop -o -b -d 1 -k -t -q > iotop.out 2>&1
# Total DISK READ: 0.00 K/s | Total DISK WRITE: 0.00 K/s
#     TIME  TID  PRIO  USER     DISK READ  DISK WRITE  SWAPIN      IO    COMMAND
# 00:01:13 26634 be/4 nobody      0.00 K/s    0.00 K/s  0.00 %  0.00 % ns-slapd -D /etc/dirsrv/slapd-389 -i /var/run/dirsrv/slapd-389.pid -w /var/run/dirsrv/slapd-389.startpid
    awk -v hroff=-10 -v secoff=-635 -v startts=$1 -v endts=$2 -F '[ :]*' '
    BEGIN { yr = strftime("%Y", startts) ; mon = strftime("%m", startts) ; day = strftime("%d", startts) ; sum[1] = sum[2] = sum[3] = sum[4] = 0 ; nn = 1 }
    /^Total DISK READ:/ { totalr=$4 ; totalw=$10; doprint=1 }
    /ns-slapd/ {
        if (doprint) {
            origts=$1 ":" $2 ":" $3
            ts=mktime(yr " " mon " " day " " $1 " " $2 " " $3)+(hroff*3600)+secoff
            if ((ts >= startts) && (ts <= endts)) {
                sum[1] += totalr ; sum[2] += totalw ; sum[3] += $7 ; sum[4] += $9
                print ts, totalr, totalw, $7, $9, sum[1]/nn, sum[2]/nn, sum[3]/nn, sum[4]/nn, origts
                nn++
            } else {
                # diff=ts - startts
                # hrs=diff/3600
                # print "ts diff is " diff " hrs " hrs
            }
            doprint = 0
        }
    }
'
}

cnvttopoutput() {
# Id:a, Mode_altscr=0, Mode_irixps=1, Delay_time=3.000, Curwin=0
# Def     fieldscur=AehioqtWKNmbcdfgjPlrsUVYZX
#         winflags=128313, sortindx=10, maxtasks=0
#         summclr=1, msgsclr=1, headclr=3, taskclr=1
# Job     fieldscur=ABcefgjlrstuvyzMKNHIWOPQDX
#         winflags=62777, sortindx=0, maxtasks=0
#         summclr=6, msgsclr=6, headclr=7, taskclr=6
# Mem     fieldscur=ANOPQRSTUVbcdefgjlmyzWHIKX
#         winflags=62777, sortindx=13, maxtasks=0
#         summclr=5, msgsclr=5, headclr=4, taskclr=5
# Usr     fieldscur=ABDECGfhijlopqrstuvyzMKNWX
#         winflags=62777, sortindx=4, maxtasks=0
#         summclr=3, msgsclr=3, headclr=2, taskclr=3
# top -b -p 16778 -d 1 -n 300 > top.out 2>&1
    awk -v hroff=-10 -v secoff=-648 -v startts=$1 -v endts=$2 -v thresh=5.0 -F '[ :]*' '
    BEGIN { yr = strftime("%Y", startts) ; mon = strftime("%m", startts) ; day = strftime("%d", startts) ; nn = 1 }
    /^top/ {
        origts=$3 ":" $4 ":" $5
        ts=mktime(yr " " mon " " day " " $3 " " $4 " " $5)+(hroff*3600)+secoff
        # diff=ts - startts
        # hrs=diff/3600
        # print "ts diff is " diff " hrs " hrs
    }
    (($3 > thresh) && (ts >= startts) && (ts <= endts) && ($10 == "ns-slapd")) {
        if ($8 == "-") {
            val=2500
        } else if ($8 == "poll_sche") {
            val=2000
        } else if ($8 == "sync_page") {
            val=100
        } else {
            val=0
        }
        print ts, $3, val, origts
        nn++
    }
'
}

cnvtextradata() {
    awk '
    /^EXTRASTART/,/^EXTRAEND/ {
        if ($1 ~ /^EXTRASTART/) next
        if ($1 ~ /^EXTRAEND/) next
        if ($1 ~ /^Catch/) next
        if ($1 ~ /^ldclt/) next
        if (NF < 1) next
        print
    }
    '
}

cnvtlogconvcsv() {
#Time,time_t,Results,Search,Add,Mod,Modrdn,Moddn,Compare,Delete,Abandon,
#     Connections,SSL Conns,Bind,Anon Bind,Unbind,NotesA,Unindexed,ElapsedTime
# NotesA field only present in newer versions
#17/Apr/2013:22:09:20 -0400,1366157360,297,206,0,0,0,0,0,0,0,0,0,90,0,0,0
# convert to format more suitable for gnuplot
# the ts field is in gm time
    tail -n +2 | \
    awk -F'[,]+' -v hroff=2 -v start=$1 -v end=$2 '
    function showit() {
        outstr=""
        for (ii = 2; ii <= NF; ++ii) {
            if (ii == 2) {outstr=$2}
            else {outstr=outstr " " $ii}
        }
        outstr=outstr " " $1
        print outstr
    }
    function sumit() {
        $11 *= 50 # scale up abandon requests for emphasis
        for (ii = 3; ii <= NF; ++ii) {
            sum[$2,ii] += $ii
        }
        sum[$2,ii] = $1
        if ($2 < mints) { mints = $2 }
        if ($2 > maxts) { maxts = $2 }
        if (ii > maxnf) { maxnf = ii }
    }
    BEGIN {OFS=" "; secoff=hroff*3600; found=0; mints=9999999999; maxts=0; maxnf=0}
    {$2 += secoff; if (($2 >= start) && ($2 <= end)) {sumit(); found=1}}
    END {if (!found) {print "Error: no records found between", start, "and", end; exit 1;}
        for (ts = mints; ts <= maxts; ++ts) {
            if (!sum[ts,maxnf]) {
                # no record at this timestamp, skip it
                continue
            }
            outstr=""
            for (f = 3; f <= maxnf; ++f) {
                val=sum[ts,f]
                if (!val) { val="0" }
                if (outstr) {
                    outstr=outstr " " val
                } else {
                    outstr=val
                }
            }
            print ts, outstr
        }
    }
    '
}

cnvtlogconvextra() {
    awk '
    /Total Connections:/ {print}
    /StartTLS Connections:/ {print}
    /LDAPS Connections:/ {print}
    /LDAPI Conections:/ {print}
    /Peak Concurrent Connections:/ {print}
    /Total Operations:/ {print}
    /Total Results:/ {print}
    /Highest FD Taken:/ {print}
    '
}

cnvtsockstats() {
# 1367593658
# sockets: used 119
# TCP: inuse 9 orphan 0 tw 0 alloc 13 mem 0
# ...
#
    awk -v hroff=2 '
    BEGIN {mints=99999999999999; maxts=0;tsoff=hroff*3600}
    /^[0-9]/ {
        ts=$1+tsoff
        if (ts < mints) { mints = ts }
        if (ts > maxts) { maxts = ts }
    }
    /^sockets:/ {sock[ts]+=$3}
    /^TCP:/ {tw[ts]+=$7}
    END {
        for (ii = mints; ii <= maxts; ++ii) {
            if (ii in sock) {
                print ii, sock[ii], tw[ii]
            }
        }
    }
    '
}

cnvtpingstats() {
#1368560951
#PING ibm-x3950x5-01.rhts.eng.bos.redhat.com (10.16.65.79) 56(84) bytes of data.
#64 bytes from ibm-x3950x5-01.rhts.eng.bos.redhat.com (10.16.65.79): icmp_seq=1 ttl=64 time=1.48 ms
    awk -F '[ =]+' -v hroff=2 '
    BEGIN {sum=0;min=9999999999;max=0;tsoff=hroff*3600;inv=1;n=0}
    NR == 1 {ts=$1+tsoff}
    /^PING/ {next}
    / bytes from / {
        sum += $11
        if ($11 < min) { min = $11 }
        if ($11 > max) { max = $11 }
        print ts, $11
        n+=1
        ts+=1
    }
    END { print ts, $11, (sum/n), min, max }
    '
}

# input file is already in awk space separated format
# as given to doplot
getstats() {
    awk -v fieldspec=$1 -v doavg=$2 -v domax=$3 -v domin=$4 '
    BEGIN {
        split(fieldspec,fields,",")
        for (ii in fields) {
            min[ii] = 99999999999999999
        }
    }
    {
        for (ii in fields) {
            f = fields[ii]
            sum[ii] += $f
            if ($f < min[ii]) {min[ii] = $f}
            if ($f > max[ii]) {max[ii] = $f}
        }
        ++nn
    }
    END {
        str=""
        sep=""
        for (ii in fields) {
            if (doavg) {str=str sep (sum[ii]/nn); if (sep == "") {sep=","}}
            if (domax) {str=str sep max[ii]; if (sep == "") {sep=","}}
            if (domin) {str=str sep min[ii]; if (sep == "") {sep=","}}
        }
        print str
    }
    '
}

comptimedata() {
    graphout=$1 ; shift
    extra1=$1 ; shift
    extra2=$1 ; shift
    # first, get the start/end time for each data set
    gpstr="plot"
    gpnext=""
    statstr=""
    while [ $1 ] ; do
        fn=$1 ; shift
        col=$1 ; shift
        field=$1 ; shift
        startts=`getstartendts < $fn`
        gpstr="$gpstr$gpnext "'"'$fn'" using (timecolumn(1)-'$startts'):'$col' title "'$field'" with lines'
        gpnext=", "
        # get stats
        statstr="$statstr"'
plot "'$fn'" u 1:2
'$field'_min = GPVAL_DATA_Y_MIN
'$field'_max = GPVAL_DATA_Y_MAX
f(x) = '$field'_mean
fit f(x) "'$fn'" u 1:'$col' via '$field'_mean
'$field'_dev = sqrt(FIT_WSSR / (FIT_NDF + 1 ))
if (uselabel1) labelstr1 = labelstr1 . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'$field'", '$field'_mean, '$field'_min, '$field'_max, '$field'_dev) ; label1lines = label1lines + 1
if (uselabel2) labelstr2 = labelstr2 . sprintf("%s: mean=%g min=%g max=%g stddev=%g\n", "'$field'", '$field'_mean, '$field'_min, '$field'_max, '$field'_dev) ; label2lines = label2lines + 1
if (label1lines > linesperlabel) uselabel1 = 0; uselabel2 = 1
'
    done
    gnuplot <<EOF 2> /dev/null
extra1 = system("cat $extra1")
extra2 = system("cat $extra2")
set fit logfile "/dev/null"
set terminal unknown
linesperlabel = 6
graphheight = 0.40
labelposx = 0.49
uselabel1 = 1
uselabel2 = 0
label1lines = 0
label2lines = 0
labelstr1 = ""
labelstr2 = ""
$statstr
$gnuplotheader
set label 1 extra1 at screen 0.01,0.99
set label 2 extra2 at screen labelposx,0.99
set label 3 labelstr1 at screen 0.01,0.89
set label 4 labelstr2 at screen labelposx,0.89
print "extra1=", extra1
print "extra2=", extra2
print "label1=", labelstr1
print "label2=", labelstr2
set key at screen 1.0,1.0
set output "$graphout"
set title "Ops/Second by Time"
set ylabel "ops/sec (linear)"
set multiplot
set size 1.0,graphheight
set origin 0.0,graphheight
set mytics 2
$gpstr
unset label 1
unset label 2
unset label 3
unset label 4
unset title
set mytics default
set size 1.0,graphheight
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

    getextrastart $EXTRA

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
        NTHREADS=$S1THREADS STARTNUM=$start ENDNUM=$end dosearch1 > $S1OUT.$ii 2>&1 &
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
        NTHREADS=$S2THREADS STARTNUM=$start ENDNUM=$end dosearch2 > $S2OUT.$ii 2>&1 &
        ii=`expr $ii - 1`
        start=`expr $start + $range`
        end=`expr $end + $range`
    done

    echo starting mods
    NTHREADS=$MTHREADS domod1 > $MOUT 2>&1 &
    wait

    getextraend $EXTRA

    echo converting search1 data
    sort -n $S1OUT.* | cnvtldcltoutput > $S1DAT
    echo converting search2 data
    sort -n $S2OUT.* | cnvtldcltoutput > $S2DAT
    echo converting mods data
    cnvtldcltoutput < $MOUT > $MDAT

    echo plotting data
    doplot $OUTD/graph.png $EXTRA $S1DAT 3 search1 $S2DAT 3 search2 $MDAT 3 mod
}

ldapdbmon() {
    while [ 1 ] ; do
        date +"%s"
        ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=database,cn=monitor,cn=ldbm database,cn=plugins,cn=config"
        ldapsearch -xLLL -h $HOST -p $PORT -D "$ROOTDN" -w "$ROOTPW" -s base -b "cn=monitor,cn=$1,cn=ldbm database,cn=plugins,cn=config"
        sleep $INTERVAL
    done
}

ldapdbmon1() { ldapdbmon "$DB1"; }
ldapdbmon2() { ldapdbmon "$DB2"; }

run2plots() {
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
    doplot $args
}

mod2plots() {
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
    if [ "$USEAVG" -eq 1 ] ; then
        col=3
    else
        col=2
    fi
    args="$OUTD/graph.png $EXTRA $MDAT $col mods_per_sec"
    if [ "$USEAVG" -eq 1 ] ; then
        col1=4 ; col2=5
    else
        col1=2 ; col2=3
    fi
    if [ -f $IODAT ] ; then
        args="$args $IODAT $col1 sda_blkrd_k_per_sec $IODAT $col2 sda_blkwr_k_per_sec"
    fi
    if [ "$USEAVG" -eq 1 ] ; then
        col1=7 ; col2=8 ; col3=9 ; col4=10 ; col5=11
    else
        col1=2 ; col2=3 ; col3=4 ; col4=5 ; col5=6
    fi
    if [ -f $MONDAT ] ; then
        args="$args $MONDAT $col1 db_cache_hits_n_per_sec $MONDAT $col2 db_cache_tries_n_per_sec $MONDAT $col3 db_ro_evict_n_per_sec $MONDAT $col4 db_page_read_n_per_sec $MONDAT $col5 entrycache_mbytes"
    fi
    if [ -f $FDAT ] ; then
        args="$args $FDAT 3 fs_cache_mbytes"
    fi
    if [ "$USEAVG" -eq 1 ] ; then
        col=9
    else
        col=5
    fi
    if [ -f $IOTDAT ] ; then
#        args="$args $IOTDAT 2 sysrd_kbytes_per_sec $IOTDAT 3 syswr_kbytes_per_sec $IOTDAT 4 dsrd_kbytes_per_sec $IOTDAT 5 dswr_kbytes_per_sec"
        args="$args $IOTDAT $col dswr_kbytes_per_sec"
    fi
    doplot $args
}

srchmodplots() {
    OUTD=$1 ; shift
    EXTRA=$OUTD/extra.dat
    SOUT=$OUTD/srch.out
    SDAT=$OUTD/srch.dat
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

    if [ ! -f $SDAT ] ; then
        echo converting search data
        sort -n $SOUT* | cnvtldcltoutput > $SDAT
    fi
    if [ ! -f $MDAT ] ; then
        echo converting mod data
        sort -n $MOUT* | cnvtldcltoutput > $MDAT
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
    if [ "$USEAVG" -eq 1 ] ; then
        col=3
    else
        col=2
    fi
    args="$OUTD/graph.png $EXTRA $SDAT $col avg_search_per_sec $MDAT $col avg_mods_per_sec"
    if [ "$USEAVG" -eq 1 ] ; then
        col1=4 ; col2=5
    else
        col1=2 ; col2=3
    fi
    if [ -f $IODAT ] ; then
        args="$args $IODAT $col1 sda_blkrd_k_per_sec $IODAT $col2 sda_blkwr_k_per_sec"
    fi
    if [ "$USEAVG" -eq 1 ] ; then
        col1=7 ; col2=8 ; col3=9 ; col4=10 ; col5=11
    else
        col1=2 ; col2=3 ; col3=4 ; col4=5 ; col5=6
    fi
    if [ -f $MONDAT ] ; then
        args="$args $MONDAT $col1 db_cache_hits_n_per_sec $MONDAT $col2 db_cache_tries_n_per_sec $MONDAT $col3 db_ro_evict_n_per_sec $MONDAT $col4 db_page_read_n_per_sec $MONDAT $col5 entrycache_mbytes"
    fi
    if [ -f $FDAT ] ; then
        args="$args $FDAT 3 fs_cache_mbytes"
    fi
    if [ "$USEAVG" -eq 1 ] ; then
        col=9
    else
        col=5
    fi
    if [ -f $IOTDAT ] ; then
#        args="$args $IOTDAT 2 sysrd_kbytes_per_sec $IOTDAT 3 syswr_kbytes_per_sec $IOTDAT 4 dsrd_kbytes_per_sec $IOTDAT 5 dswr_kbytes_per_sec"
        args="$args $IOTDAT $col dswr_kbytes_per_sec"
    fi
    doplot $args
}

run2() {
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
    cat <<EOF >> $EXTRA
Test Duration $DURATION seconds Start $startts End $endts
search2: procs=1 threads=1 $ver $nthr numentries: $NENTRIES
EOF
    echo converting search data
    sort -n $SOUT* | cnvtldcltoutput > $SDAT

    echo plotting data
    run2plots
}

dosearches1() {
    OUTD=`mktemp -d --tmpdir=$DIR`
    SOUT=$OUTD/srch.out
    SDAT=$OUTD/srch.dat
    ii=$S1NPROCS
    echo starting $ii search procs 
    while [ $ii -gt 0 ] ; do
        NTHREADS=$S1THREADS dosearch1 > $SOUT.$ii 2>&1 &
        ii=`expr $ii - 1`
    done
    wait
}

srch1plots() {
    str1=
    str2=
    lastcount=0
    for dir in "$@" ; do
        if [ ! -d $dir -a ! -f $dir ] ; then
            lbl="$dir" # is a label
            continue
        fi
        if [ -n "$lbl" ] ; then
            curlbl="_"${lbl}"_"
        else
            curlbl="_"
        fi
        if [ ! -d $dir ] ; then continue ; fi
        if [ ! -f $dir/srch.dat ] ; then
            sort -n $dir/srch.out.* | cnvtldcltoutput > $dir/srch.dat
        fi
        count=0
        thr=`awk '/^Number of threads/ { print $NF }' $dir/srch.out.1`
        async=`awk '/^Async max pending/ { print $NF }' $dir/srch.out.1`
        for file in $dir/srch.out.? $dir/srch.out.?? ; do
            if [ ! -f "$file" ] ; then continue ; fi
            tmpstr=`cnvtextradata < $file | tee extra.dat | grep ^vendorVersion | cut -f2 -d' '`
            case $tmpstr in Sun*) vendor=sun ;; 389*) vendor=rhds ;; Red*) vendor=rhds ;;
            *) echo Error: unknown vendor $tmpstr in $file - skipping
            esac
            if [ -s extra.dat -a -n "$vendor" ] ; then
                mv extra.dat extra-$vendor-$lbl.dat
            else
                echo skipping empty extra.dat file from $file
            fi
            count=`expr $count + 1`
        done
        curlbl="${curlbl}$count"
        if [ $thr -gt 1 ] ; then
            curlbl="${curlbl}_t${thr}"
        fi
        if [ $async -gt 1 ] ; then
            curlbl="${curlbl}_a${async}"
        fi
        if [ $count -gt $lastcount ] ; then
            str1="$str1 $dir/srch.dat 2 ${vendor}${curlbl}"
            str2="$str2 $dir/srch.dat 3 ${vendor}${curlbl}"
        else
            str1="$dir/srch.dat 2 ${vendor}${curlbl} $str1"
            str2="$dir/srch.dat 3 ${vendor}${curlbl} $str2"
        fi
        lastcount=$count
    done
    extras=`ls -1 extra*.dat|head -2`
    nextras=`ls -1 extra*.dat|head -2|wc -l`
    if [ $nextras -lt 1 ] ; then
        extras="/dev/null /dev/null"
    elif [ $nextras -lt 2 ] ; then
        extras="$extras /dev/null"
    fi
    comptimedata graph.png $extras $str1
    comptimedata graph-avg.png $extras $str2
}

srch1csv() {
    csvfile=srch.csv
    echo vendor,label,clients,threads,async,avg,min,max,stddev > $csvfile
    for dir in "$@" ; do
        if [ ! -d $dir -a ! -f $dir ] ; then
            lbl="$dir" # is a label
            continue
        fi
        if [ ! -d $dir ] ; then continue ; fi
        if [ ! -f $dir/srch.dat ] ; then
            sort -n $dir/srch.out.* | cnvtldcltoutput > $dir/srch.dat
        fi
        count=0
        thr=`awk '/^Number of threads/ { print $NF }' $dir/srch.out.1`
        async=`awk '/^Async max pending/ { print $NF }' $dir/srch.out.1`
        for file in $dir/srch.out.? $dir/srch.out.?? ; do
            if [ ! -f "$file" ] ; then continue ; fi
            tmpstr=`cnvtextradata < $file | tee extra.dat | grep ^vendorVersion | cut -f2 -d' '`
            case $tmpstr in Sun*) vendor=sun ;; 389*) vendor=rhds ;; Red*) vendor=rhds ;;
            *) echo Error: unknown vendor $tmpstr in $file - skipping
            esac
            if [ -s extra.dat -a -n "$vendor" ] ; then
                mv extra.dat extra-$vendor-$lbl.dat
            else
                echo skipping empty extra.dat file from $file
            fi
            count=`expr $count + 1`
        done
        awk -v vendor=$vendor -v label="${lbl:-none}" -v count=$count -v thr=$thr -v async=${async:-0} '
        BEGIN { OFS="," }
        END { print vendor, label, count, thr, async, $3, $4, $5, $6 }
        ' $dir/srch.dat >> $csvfile
    done
    extras=`ls -1 extra*.dat|head -2`
    nextras=`ls -1 extra*.dat|head -2|wc -l`
    if [ $nextras -lt 1 ] ; then
        extras="/dev/null /dev/null"
    elif [ $nextras -lt 2 ] ; then
        extras="$extras /dev/null"
    fi
    cat $extras >> $csvfile
}

for cmd in "$@" ; do
    case $cmd in
    doplot) shift ; doplot "$@" ; exit 0 ;;
    doplotvar) shift ; doplotvar "$@" ; exit 0 ;;
    comptimedata) shift ; comptimedata "$@" ; exit 0 ;;
    run2plots) shift ; run2plots "$@" ; exit 0 ;;
    mod2plots) shift ; mod2plots "$@" ; exit 0 ;;
    cnvttopoutput) shift ; cnvttopoutput "$@" ; exit 0 ;;
    cnvtiostatoutput) shift ; cnvtiostatoutput "$@" ; exit 0 ;;
    cnvtdbmonoutput) shift ; cnvtdbmonoutput "$@" ; exit 0 ;;
    cnvtfreeoutput) shift ; cnvtfreeoutput "$@" ; exit 0 ;;
    cnvtiotopoutput) shift ; cnvtiotopoutput "$@" ; exit 0 ;;
    cnvtlogconvcsv) shift ; cnvtlogconvcsv "$@" ; exit 0 ;;
    srchmodplots) shift ; srchmodplots "$@" ; exit 0 ;;
    srch1plots) shift ; srch1plots "$@" ; exit 0 ;;
    srch1csv) shift ; srch1csv "$@" ; exit 0 ;;
    cnvtoldldcltoutput) shift ; cnvtoldldcltoutput "$@" ; exit 0 ;;
    cnvtsockstats) shift ; cnvtsockstats "$@" ; exit 0 ;;
    cnvtpingstats) shift ; cnvtpingstats "$@" ; exit 0 ;;
    getstats) shift ; getstats "$@" ; exit 0 ;;
    esac
    $cmd || { echo Error: $cmd returned error $! ; exit 1 ; }
done
