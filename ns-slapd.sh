#!/bin/sh

if [ ! "$NETSITE_ROOT" ] ; then
	NETSITE_ROOT=`pwd | sed -e s@/bin/slapd/server@@g`
fi

#assumes
SLAPD=$0.orig
VGSUPPRESS="--suppressions=/tmp/valgrind.supp"
# by default valgrind will demangle C++ symbols for you
# but valgrind must have mangled symbols in suppression files
#DEMANGLE="--demangle=no"
# use quiet mode if you only want the errors and nothing but the errors
QUIETMODE="-q"

if [ $USE_PURIFY ]; then
	LD_LIBRARY_PATH=$NETSITE_ROOT/lib:$NETSITE_ROOT/bin/slapd/lib:$LD_LIBRARY_PATH
	export LD_LIBRARY_PATH
	PURIFYOPTIONS="-windows=no -log-file=purify.$$.log -append-logfile=yes -follow-child-processes=no -chain-length=50"
	export PURIFYOPTIONS
	SLAPD=./ns-slapd.pure
fi

if [ $USE_VALGRIND ]; then
	CHECKCMD="valgrind $QUIETMODE --tool=memcheck --leak-check=yes --leak-resolution=high $VGSUPPRESS $DEMANGLE --num-callers=50 --log-file="
	# otherwise, run the same way we run purify
	USE_PURIFY=1
fi

if [ $USE_GDB ]; then
#	DISPLAY=:1 ; export DISPLAY
	argsfile=.gdbinit
	echo "break main" > $argsfile
	echo "run $* -d 0" >> $argsfile
	case "$1" in
	db2index|suffix2instance|db2archive|archive2db|db2ldif|ldif2db)
	xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb -x $argsfile $SLAPD
#	/usr/openwin/bin/xterm -bg white -fn 10x20 -sb -sl 2000 -title dbx -e /tools/ns/forte-6.2/bin/dbx -c "stop in main ; run $* -d 0" $SLAPD
	;;
	*)
	xterm -bg white -fn 10x20 -sb -sl 2000 -title gdb -e gdb -x $argsfile $SLAPD &
#	/usr/openwin/bin/xterm -bg white -fn 10x20 -sb -sl 2000 -title dbx -e /tools/ns/forte-6.2/bin/dbx -c "stop in main ; run $* -d 0" $SLAPD &
	;;
	esac
elif [ $USE_PURIFY ]; then
	if [ $TET_PNAME ]; then
		mybase=`basename $TET_PNAME .ksh`
		mybase=`basename $mybase .sh`
        if [ -z "$mybase" ] ; then
            mybase=unknown
        fi
        # for some reason, on fedora, --log-file does not append the pid
		outputfile=/var/tmp/$mybase.vg.$$
	else
		outputfile=/var/tmp/slapd.vg.$$
	fi
	CHECKCMD="${CHECKCMD}$outputfile"
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
