#!/bin/sh
inst=${INST:-localhost}
if [ -f $HOME/.dirsrv/dirsrv ] ; then
. $HOME/.dirsrv/dirsrv
else
. $PREFIX/etc/sysconfig/dirsrv
fi

if [ -f $HOME/.dirsrv/dirsrv-$inst ] ; then
. $HOME/.dirsrv/dirsrv-$inst
else
. $PREFIX/etc/sysconfig/dirsrv-$inst
fi

pidfile=$RUN_DIR/slapd-$inst.pid
startpidfile=$RUN_DIR/slapd-$inst.startpid
rm -f $pidfile $startpidfile
SLAPD=${PREFIX:-/usr}/sbin/ns-slapd
case `file $SLAPD` in
*"shell script"*) SLAPD=$SLAPD.orig ;;
*text*) SLAPD=$SLAPD.orig ;;
esac
if [ ! -f $SLAPD ] ; then
    echo Error: command $SLAPD not found
    exit 1
fi
SLAPD_COMMAND="$SLAPD -D $CONFIG_DIR -i $pidfile -w $startpidfile -d 0"

if [ -z "$PREFIX" ] ; then
    ARCH=`uname -p`
    case $ARCH in *64) AD=64 ;; esac
fi
DSLIBDIR=${PREFIX:-/usr}/lib$AD/dirsrv
PLUGINDIR=$DSLIBDIR/plugins

modules="-d $SLAPD"
for m in $DSLIBDIR=/libslapd.so.0.0.0 \
    $PLUGINDIR/libpwdstorage-plugin.so \
    $PLUGINDIR/libdes-plugin.so \
    /usr/lib64/sasl2/libgssapiv2.so.2.0.23 \
    $PLUGINDIR/libback-ldbm.so \
    $PLUGINDIR/libschemareload-plugin.so \
    /usr/lib64/libnssdbm3.so \
    /usr/lib64/libsoftokn3.so \
    /lib64/libdb-4.7.so \
    $PLUGINDIR/libsyntax-plugin.so \
    $PLUGINDIR/libautomember-plugin.so \
    $PLUGINDIR/libchainingdb-plugin.so \
    $PLUGINDIR/liblinkedattrs-plugin.so \
    $PLUGINDIR/libmanagedentries-plugin.so \
    $PLUGINDIR/libstatechange-plugin.so \
    $DSLIBDIR/libns-dshttpd.so.0.0.0 \
    $PLUGINDIR/libacl-plugin.so \
    $PLUGINDIR/libcos-plugin.so \
    $PLUGINDIR/libreplication-plugin.so \
    $PLUGINDIR/libroles-plugin.so \
    $PLUGINDIR/libhttp-client-plugin.so \
    $PLUGINDIR/libviews-plugin.so ;
do
    modules="$modules -d $m"
done

STAP_ARRAY_SIZE=${STAP_ARRAY_SIZE:-8192}
STAP_STRING_LEN=${STAP_STRING_LEN:-8192}
STAP_KRETACTIVE=${STAP_KRETACTIVE:-`expr 1024 \* 1024`}

STAP_OPTS="-s 1 -DMAXTRYLOCK=2000 -DMAXACTION=$STAP_ARRAY_SIZE -DMAXSTRINGLEN=$STAP_STRING_LEN -DKRETACTIVE=$STAP_KRETACTIVE -DSTP_NO_OVERLOAD -t --ldd -v"

KEEP_STATS=${KEEP_STATS:-0}
if [ $KEEP_STATS -eq 0 ] ; then
    KEEP_STATS=stap-dirsrv-nostats.stp
else
    KEEP_STATS=stap-dirsrv.stp
fi

if [ -n "$SLAPD_PID" ] ; then
    sudo stap $STAP_OPTS -x $SLAPD_PID $modules $KEEP_STATS $STAP_ARRAY_SIZE
else
    sudo stap $STAP_OPTS -c "$SLAPD_COMMAND" $modules $KEEP_STATS $STAP_ARRAY_SIZE
fi
