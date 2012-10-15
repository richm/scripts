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
SLAPD_COMMAND="$SLAPD -D $CONFIG_DIR -i $pidfile -w $startpidfile -d 0"

modules="-d $SLAPD"
for m in /usr/lib64/dirsrv/plugins/libpwdstorage-plugin.so \
    /usr/lib64/dirsrv/plugins/libdes-plugin.so \
    /usr/lib64/sasl2/libgssapiv2.so.2.0.23 \
    /usr/lib64/dirsrv/plugins/libback-ldbm.so \
    /usr/lib64/dirsrv/plugins/libschemareload-plugin.so \
    /usr/lib64/libnssdbm3.so \
    /usr/lib64/libsoftokn3.so \
    /lib64/libdb-4.7.so \
    /usr/lib64/dirsrv/plugins/libsyntax-plugin.so \
    /usr/lib64/dirsrv/plugins/libautomember-plugin.so \
    /usr/lib64/dirsrv/plugins/libchainingdb-plugin.so \
    /usr/lib64/dirsrv/plugins/liblinkedattrs-plugin.so \
    /usr/lib64/dirsrv/plugins/libmanagedentries-plugin.so \
    /usr/lib64/dirsrv/plugins/libstatechange-plugin.so \
    /usr/lib64/dirsrv/libns-dshttpd.so.0.0.0 \
    /usr/lib64/dirsrv/plugins/libacl-plugin.so \
    /usr/lib64/dirsrv/plugins/libcos-plugin.so \
    /usr/lib64/dirsrv/plugins/libreplication-plugin.so \
    /usr/lib64/dirsrv/plugins/libroles-plugin.so \
    /usr/lib64/dirsrv/plugins/libhttp-client-plugin.so \
    /usr/lib64/dirsrv/plugins/libviews-plugin.so ;
do
    modules="$modules -d $m"
done

STAP_ARRAY_SIZE=${STAP_ARRAY_SIZE:-20000}
MAXINIT=${MAXINIT:-`expr $MAXACTION / 2`}
STAP_STRING_LEN=${STAP_STRING_LEN:-4096}

STAP_OPTS="-DMAXACTION=$STAP_ARRAY_SIZE -DMAXSTRINGLEN=$STAP_STRING_LEN -DKRETACTIVE=1000 -DSTP_NO_OVERLOAD -t --ldd -v"

sudo stap $STAP_OPTS -c "$SLAPD_COMMAND" $modules -e stap-dirsrv.stp
