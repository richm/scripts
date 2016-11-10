#!/bin/sh

set -ex

scriptname=`basename $0`
if [ -f $HOME/.config/$scriptname ] ; then
    . $HOME/.config/$scriptname
fi

OS=${OS:-centos7}
TESTNAME=${TESTNAME:-logging}
INSTANCE_TYPE=${INSTANCE_TYPE:-c4.large}
# on the remote machine
OS_ROOT=${OS_ROOT:-/data/src/github.com/openshift/origin}
RELDIR=${RELDIR:-$OS_ROOT/_output/local/releases}
# for cloning origin-aggregated-logging from a specific repo and branch
# you can override just the GITHUB_REPO=myusername or the entire GIT_URL
# if it is hosted somewhere other than github
GITHUB_REPO=${GITHUB_REPO:-openshift}
GIT_BRANCH=${GIT_BRANCH:-master}
GIT_URL=${GIT_URL:-https://github.com/${GITHUB_REPO}/origin-aggregated-logging}
OAL_LOCAL_PATH=`echo $GIT_URL | sed 's,https://,,'`
OS_O_A_L_DIR=${OS_O_A_L_DIR:-/data/src/github.com/openshift/origin-aggregated-logging}

export OPENSHIFT_VM_NAME_PREFIX=${USER:-$TESTNAME}-

INSTNAME=${INSTNAME:-origin_${OPENSHIFT_VM_NAME_PREFIX}$TESTNAME-$OS-1}

pushd $HOME/origin-aggregated-logging
# use vagrant from origin
if [ ! -f Vagrantfile ] ; then
    ln -s ../origin/Vagrantfile
fi
if [ ! -d contrib ] ; then
    ln -s ../origin/contrib
fi
vagrant origin-init --stage inst --os $OS --instance-type $INSTANCE_TYPE "$INSTNAME"
vagrant up --provider aws
vagrant sync-origin-aggregated-logging -s -c
# HACK
vagrant ssh -c "if [ ! -d /tmp/openshift ] ; then mkdir /tmp/openshift ; fi ; sudo chmod 777 /tmp/openshift" -- -n
# doesn't work in enforcing - see https://github.com/openshift/origin-aggregated-logging/issues/89
#vagrant ssh -c "sudo setenforce Enforcing"
vagrant ssh -c "cd $OS_ROOT ; GOPATH=/data OS_ROOT=$OS_ROOT hack/vendor-console.sh" -- -n

# pre-load images to make builds faster
for image in openshift/origin:v1.3.0 openshift/base-centos7 centos:centos7 openshift/origin-logging-elasticsearch openshift/origin-logging-fluentd openshift/origin-logging-curator openshift/origin-logging-kibana node:0.10.36 centos/ruby-22-centos7 ; do
    echo pulling image $image ...
    vagrant ssh -c "docker pull $image" -- -n
    echo done
done

# get hostname for kibana
fqdn=`vagrant ssh-config | awk '/HostName/ {print $2}'`
kibana_host=kibana.$fqdn
kibana_ops_host=kibana-ops.$fqdn
vagrant test-origin-aggregated-logging -d --env GIT_URL=$GIT_URL \
        --env GIT_BRANCH=$GIT_BRANCH \
        --env O_A_L_DIR=$OS_O_A_L_DIR \
        --env USE_LOCAL_SOURCE=true \
        --env OS_ROOT=$OS_ROOT \
        --env ENABLE_OPS_CLUSTER=true \
        --env DO_CLEANUP=false \
        --env SETUP_ONLY=true \
        --env VERBOSE=1 \
        --env PUBLIC_MASTER_HOST=$fqdn \
        --env KIBANA_HOST=$kibana_host \
        --env KIBANA_OPS_HOST=$kibana_ops_host

echo Use \'OPENSHIFT_VM_NAME_PREFIX=${OPENSHIFT_VM_NAME_PREFIX} vagrant ssh\' if you want to poke around in the machine
echo Use \'OPENSHIFT_VM_NAME_PREFIX=${OPENSHIFT_VM_NAME_PREFIX} vagrant modify-instance -r "$INSTNAME"-terminate -s
echo when you are finished
