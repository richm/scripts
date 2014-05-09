#!/bin/sh

function getdomain() {
    dom=$(domainname)
    if [ -n "$dom" -a "$dom" != '(none)' ]; then
        echo $dom
        return 0
    fi
    awk '
        /^domain / {dom=$2 ; exit}
        /^search / {dom=$2 ; exit}
        END {if (!dom) {dom="local"}; print dom}
    ' /etc/resolv.conf
}

function getns() {
    awk '
        /^nameserver / {ns=$2 ; exit}
        END {if (!ns) {ns="127.0.0.1"}; print ns}
    ' /etc/resolv.conf
}

if [ -f /etc/ipa/default.conf ] ; then
    DOMAIN=$(awk -F'[= ]+' '/^domain/ {print $2}' /etc/ipa/default.conf)
    REALM=$(awk -F'[= ]+' '/^realm/ {print $2}' /etc/ipa/default.conf)
else
    DOMAIN=${DOMAIN:-ipa.$(getdomain)}
    REALM=${REALM:-$(echo $DOMAIN | tr 'a-z' 'A-Z')}
fi
INSTDIR=${INSTDIR:-$(echo $REALM | sed 's/\./-/g')}
PW=${PW:-Secret12}
HOST=${HOST:-$(hostname)}
FWDR=${FWDR:-$(getns)}
PRINC=${PRINC:-admin@$REALM}
DIR=${DIR:-/opt/stack}
LOCALUSER=${LOCALUSER:-rich}
KTFILE=${KTFILE:-/home/$LOCALUSER/ipaadmin.keytab}

# NFS stuff
if [ ! -d /share ] ; then
    mkdir /share
fi

# start NFS first
yum -y install nfs-utils
systemctl start nfs.target

cat >> /etc/fstab <<EOF
vmhost.testdomain.com:/export1/share	/share		nfs	nfsvers=3	0 0
EOF

mount /share

# SUDO stuff
if ! grep ^$LOCALUSER /etc/sudoers; then
    cat >> /etc/sudoers <<EOF
$LOCALUSER		ALL=(ALL) NOPASSWD: ALL
EOF
fi

# ipa
ipa-server-install -r $REALM -n $DOMAIN -p "$PW" -a "$PW" -N --hostname=$HOST --setup-dns --forwarder=$FWDR -U
if [ ! -f $KTFILE ] ; then
    ipa-getkeytab -s $HOST -p $PRINC -k /tmp/kt -D "cn=directory manager" -w "$PW"
    mv /tmp/kt $KTFILE
    chown $LOCALUSER:$LOCALUSER $KTFILE
else
    echo using keytab file $KTFILE
fi

if [ ! -d $DIR ] ; then
    mkdir -p $DIR
    chown -R $LOCALUSER:$LOCALUSER $DIR
fi

if [ ! -d $DIR/devstack ] ; then
    pushd $DIR
    sudo -u $LOCALUSER git clone https://github.com/openstack-dev/devstack
    popd
fi

if [ ! -d $DIR/designate ] ; then
    pushd $DIR
    if [ -d /share/designate ] ; then
        sudo -u $LOCALUSER git clone /share/designate
    else
        sudo -u $LOCALUSER git clone https://github.com/stackforge/devstack
    fi
    popd
fi

sudo -u $LOCALUSER sed -i -e 's/\<30\>/300/g' -e 's/\<15\>/300/g' $DIR/devstack/exerciserc
if [ ! -f $DIR/devstack/local.conf ] ; then
    sudo -u $LOCALUSER cat > $DIR/devstack/local.conf <<EOF
[[local|localrc]]
HOST_IP=127.0.0.1
ADMIN_PASSWORD=$PW
DATABASE_PASSWORD=\$ADMIN_PASSWORD
RABBIT_PASSWORD=\$ADMIN_PASSWORD
SERVICE_PASSWORD=\$ADMIN_PASSWORD
SERVICE_TOKEN=5786b0d4-2b08-4d1b-8c29-a5e71af82445
FIXED_RANGE=192.168.10.0/24
FLOATING_RANGE=192.168.20.0/25
ENABLED_SERVICES=glance,g-api,g-reg,nova,n-api,n-crt,n-obj,n-cpu,n-net,n-cond,n-sch,key,mysql,qpid,designate,designate-api,designate-central,designate-sink
DESIGNATE_BACKEND_DRIVER=ipa
IPA_PRINC=$PRINC
IPA_HOST=$HOST
IPA_CLIENT_KEYTAB=$KTFILE
# domain for fixedip tests
DESIGNATE_TEST_DOMAIN_FIX=fix.${DOMAIN}.
# domain for floatingip tests
DESIGNATE_TEST_DOMAIN_FLT=flt.${DOMAIN}.
DESIGNATE_TEST_NSREC=${HOST}.
LOGFILE=$DIR/status/stack/stack.log
SCREEN_LOGDIR=$DIR/status/stack
EOF
fi

pushd $DIR/devstack
sudo -u $LOCALUSER ./stack.sh 2>&1
