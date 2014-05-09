#!/bin/sh

if [ ! "$NETSITE_ROOT" ] ; then
	NETSITE_ROOT=`pwd | sed -e s@/bin/slapd/server@@g`
fi

#export MALLOC_PERTURB_=$(($RANDOM % 255 + 1))
#export MALLOC_CHECK_=3

# assumes you have renamed the original ns-slapd binary
# to ns-slapd.orig
SLAPD=$0.orig
# assumes you have put the valgrind suppressions file in /tmp
VGSUPPRESS="--suppressions=/tmp/valgrind.supp"
# by default valgrind will demangle C++ symbols for you
# but valgrind must have mangled symbols in suppression files
#DEMANGLE="--demangle=no"
# use quiet mode if you only want the errors and nothing but the errors
QUIETMODE="-q"

VG_LOGDIR=${VG_LOGDIR:-/var/tmp}
if [ ! -d $VG_LOGDIR ] ; then
    mkdir -p $VG_LOGDIR || { echo error: could not mkdir -p $VG_LOGDIR ; exit 1; }
fi

MUTRACE_HOME=${MUTRACE_HOME:-/usr/local}

if [ $USE_PURIFY ]; then
	LD_LIBRARY_PATH=$NETSITE_ROOT/lib:$NETSITE_ROOT/bin/slapd/lib:$LD_LIBRARY_PATH
	export LD_LIBRARY_PATH
	PURIFYOPTIONS="-windows=no -log-file=purify.$$.log -append-logfile=yes -follow-child-processes=no -chain-length=50"
	export PURIFYOPTIONS
	SLAPD=./ns-slapd.pure
	# otherwise, run the same way we run valgrind
	USE_VALGRIND=1
fi

if [ "$USE_VALGRIND" -o "$USE_CALLGRIND" -o "$USE_DRD" -o "$USE_HELGRIND" ]; then
	if [ $TET_PNAME ]; then
		mybase=`basename $TET_PNAME .ksh`
		mybase=`basename $mybase .sh`
        if [ -z "$mybase" ] ; then
            mybase=unknown
        fi
        # valgrind --log-file %p is not supported on all platforms
		outputfile=${VG_LOGDIR}/$mybase.vg.$$
	else
		outputfile=${VG_LOGDIR}/slapd.vg.$$
	fi
    if [ $USE_VALGRIND ] ; then
	    CHECKCMD="valgrind $QUIETMODE --trace-children=yes --tool=memcheck --track-origins=yes --read-var-info=yes --leak-check=yes --leak-resolution=high $VGSUPPRESS $DEMANGLE --num-callers=50 --log-file=$outputfile"
    elif [ $USE_CALLGRIND ] ; then
        # collect bus is only for valgrind 3.6 and later - it collects lock/mutex events
        CHECKCMD="valgrind $QUIETMODE --tool=callgrind --collect-systime=yes --collect-bus=yes --separate-threads=yes --callgrind-out-file=${VG_LOGDIR}/callgrind.out.$$"
        USE_VALGRIND=1
    elif [ $USE_DRD ] ; then
        # time in ms
        DRD_LOCK_THRESHOLD=${DRD_LOCK_THRESHOLD:-1000}
        CHECKCMD="valgrind $QUIETMODE --tool=drd --show-confl-seg=no --shared-threshold=$DRD_LOCK_THRESHOLD --exclusive-threshold=$DRD_LOCK_THRESHOLD --num-callers=50 --log-file=${VG_LOGDIR}/drd.out.$$"
        USE_VALGRIND=1
    elif [ $USE_HELGRIND ] ; then
        CHECKCMD="valgrind $QUIETMODE --tool=helgrind --num-callers=50 --log-file=${VG_LOGDIR}/helgrind.out.$$"
        USE_VALGRIND=1
    fi
fi

if [ $USE_GDB ]; then
#	DISPLAY=:1 ; export DISPLAY
	case "$1" in
	db2index|suffix2instance|db2archive|archive2db|db2ldif|ldif2db)
	xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb --args $SLAPD "$@"
	;;
	*)
	(xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb --args $SLAPD -d 0 "$@") &
	;;
	esac
elif [ $USE_VALGRIND ]; then
    $CHECKCMD $SLAPD "$@"
elif [ $USE_MUTRACE ]; then
    case "$1" in
    db2index|suffix2instance|db2archive|archive2db|db2ldif|ldif2db)
    $SLAPD "$@"
    ;;
    *)
    LD_LIBRARY_PATH=$MUTRACE_HOME/lib $MUTRACE_HOME/bin/mutrace --frames=50 --all -d $SLAPD -d 0 "$@" > $VG_LOGDIR/mutrace.out.$$ 2>&1 &
    ;;
    esac
else
	$SLAPD "$@"
fi
