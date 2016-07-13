#!/bin/sh

set -ex

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
vagrant ssh -c "if [ ! -d /tmp/openshift ] ; then mkdir /tmp/openshift ; fi ; sudo chmod 777 /tmp/openshift"
# doesn't work in enforcing - see https://github.com/openshift/origin-aggregated-logging/issues/89
#vagrant ssh -c "sudo setenforce Enforcing"
vagrant test-origin-aggregated-logging -d --env GIT_URL=$GIT_URL \
        --env GIT_BRANCH=$GIT_BRANCH \
        --env O_A_L_DIR=$OS_O_A_L_DIR \
        --env USE_LOCAL_SOURCE=true \
        --env OS_ROOT=$OS_ROOT \
        --env ENABLE_OPS_CLUSTER=true \
        --env DEBUG_FAILURES=true \
        --env VERBOSE=1

echo Use \'OPENSHIFT_VM_NAME_PREFIX=${OPENSHIFT_VM_NAME_PREFIX} vagrant ssh\' if you want to poke around in the machine
echo Use \'OPENSHIFT_VM_NAME_PREFIX=${OPENSHIFT_VM_NAME_PREFIX} vagrant modify-instance -r "$INSTNAME"-terminate -s
echo when you are finished
echo Otherwise, pkill \'sleep 12345\'
sleep 12345 || echo sleep killed

vagrant modify-instance -r "$INSTNAME"_terminate -s
popd
