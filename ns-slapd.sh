#!/bin/sh

if [ ! "$NETSITE_ROOT" ] ; then
	NETSITE_ROOT=`pwd | sed -e s@/bin/slapd/server@@g`
fi

export MALLOC_PERTURB_=$(($RANDOM % 255 + 1))
export MALLOC_CHECK_=3

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

if [ $USE_PURIFY ]; then
	LD_LIBRARY_PATH=$NETSITE_ROOT/lib:$NETSITE_ROOT/bin/slapd/lib:$LD_LIBRARY_PATH
	export LD_LIBRARY_PATH
	PURIFYOPTIONS="-windows=no -log-file=purify.$$.log -append-logfile=yes -follow-child-processes=no -chain-length=50"
	export PURIFYOPTIONS
	SLAPD=./ns-slapd.pure
	# otherwise, run the same way we run valgrind
	USE_VALGRIND=1
fi

if [ "$USE_VALGRIND" -o "$USE_CALLGRIND" ]; then
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
	    CHECKCMD="valgrind $QUIETMODE --tool=memcheck --leak-check=yes --leak-resolution=high $VGSUPPRESS $DEMANGLE --num-callers=50 --log-file=$outputfile"
    elif [ $USE_CALLGRIND ] ; then
        CHECKCMD="valgrind $QUIETMODE --tool=callgrind --callgrind-out-file=${VG_LOGDIR}/callgrind.out.$$"
        USE_VALGRIND=1
    fi
fi

if [ $USE_GDB ]; then
#	DISPLAY=:1 ; export DISPLAY
	case "$1" in
	db2index|suffix2instance|db2archive|archive2db|db2ldif|ldif2db)
	xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb --args $SLAPD
	;;
	*)
	xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb --args $SLAPD &
	;;
	esac
elif [ $USE_VALGRIND ]; then
	case "$1" in
	db2index|suffix2instance|db2archive|archive2db|db2ldif|ldif2db)
		$CHECKCMD $SLAPD "$@"
		;;
	*)
#		$SLAPD "$@" -d 0 &
		$CHECKCMD $SLAPD "$@"
		;;
	esac
else
	$SLAPD "$@"
fi
