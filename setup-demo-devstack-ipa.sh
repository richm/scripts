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

function named_conf_set() {
    # $1 is section name
    # $2 is option name
    # $3 is value
    # this will replace any existing values of $2 with $3
}

DOMAIN=${DOMAIN:-ipa.$(getdomain)}
REALM=${REALM:-$(echo $DOMAIN | tr 'a-z' 'A-Z')}
INSTDIR=${INSTDIR:-$(echo $REALM | sed 's/\./-/g')}
PW=${PW:-Secret12}
HOST=${HOST:-$(hostname)}
FWDR=${FWDR:-$(getns)}
PRINC=${PRINC:-admin@$REALM}
KTFILE=${KTFILE:-$HOME/ipaadmin.keytab}
DIR=${DIR:-/opt/stack}

if [ ! -d ~/designate ] ; then
    echo need dev designate repo
    exit 1
fi

sudo yum -y install git python-pip freeipa-server bind-dyndb-ldap

if [ ! -d /etc/dirsrv/slapd-$INSTDIR ]; then
    sudo ipa-server-install -r $REALM -n $DOMAIN -p "$PW" -a "$PW" -N --hostname=$HOST --setup-dns --forwarder=$FWDR -U
    echo not sure how best to do this
    echo ipactl stop
    echo add this to /etc/named.conf in the global options section
    sudo cat <<EOF
	listen-on {127.0.0.1; 172.18.85.10;};
	listen-on-v6 {fe80::f048:7ff:feaf:7707/64; ::1/128;};
	allow-transfer { "none"; };
	allow-recursion { "none"; };
	recursion no;
	version "[Secured]";
	rate-limit {
		responses-per-second 15;
	};
EOF
    echo Press Enter when ready
    read dummy
    echo ipactl start
else
    echo ipa already setup, skipping
fi

if [ ! -f $KTFILE ] ; then
    ipa-getkeytab -s $HOST -p $PRINC -k $KTFILE -D "cn=directory manager" -w $PW
else
    echo using keytab file $KTFILE
fi

if [ ! -d $DIR ] ; then
    sudo mkdir -p $DIR
    sudo chown -R fedora:fedora $DIR
fi

if [ ! -d $DIR/devstack ] ; then
    pushd $DIR
    git clone https://github.com/openstack-dev/devstack
    popd
fi

sed -i -e 's/\<30\>/300/g' -e 's/\<15\>/300/g' $DIR/devstack/exerciserc

if [ ! -d $DIR/designate ] ; then
    pushd $DIR
    git clone $HOME/designate
    popd
fi
pushd $DIR/designate
git checkout demo
git pull
sudo pip install -r ipa-requirements.txt
if [ ! -f $DIR/devstack/lib/designate ] ; then
    cd contrib/devstack
    ./install.sh
fi
popd

if [ ! -f $DIR/devstack/local.conf ] ; then
    cat > $DIR/devstack/local.conf <<EOF
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
./stack.sh 2>&1 | tee output && RUN_EXERCISES=novahostip ./exercise.sh

cat <<EOF
POST /v2/d5b04e149dfb4c849c34c03c840b0d6c/servers/e10f7e21-a5a5-496d-940c-6ee745e7b048/action HTTP/1.1
x-auth-project-id: admin
accept: application/json
x-auth-token: 417e6286fa4b4f9b9ec8fcc32bf52a4a
content-type: application/json


> {"disk_over_commit": false, "block_migration": false, "host": "compute2"}}'
> reply: 'HTTP/1.1 400 Bad Request\r\n'
> header: Content-Length: 129
> header: Content-Type: application/json; charset=UTF-8
EOF