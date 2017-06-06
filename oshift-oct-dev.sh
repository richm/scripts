#!/bin/sh

set -euxo pipefail

scriptname=`basename $0`
if [ -f $HOME/.config/$scriptname ] ; then
    . $HOME/.config/$scriptname
fi

OS=${OS:-rhel}
TESTNAME=${TESTNAME:-logging}
INSTANCE_TYPE=${INSTANCE_TYPE:-c4.xlarge}
# on the remote machine
OS_ROOT=${OS_ROOT:-/data/src/github.com/openshift/origin}
RELDIR=${RELDIR:-$OS_ROOT/_output/local/releases}
# for cloning origin-aggregated-logging from a specific repo and branch
# you can override just the GITHUB_REPO=myusername or the entire GIT_URL
# if it is hosted somewhere other than github
GITHUB_REPO=${GITHUB_REPO:-openshift}
GIT_BRANCH=${GIT_BRANCH:-master}
GIT_URL=${GIT_URL:-https://github.com/${GITHUB_REPO}/origin-aggregated-logging}
ANSIBLE_REPO=${ANSIBLE_REPO:-openshift}
ANSIBLE_BRANCH=${ANSIBLE_BRANCH:-master}
ANSIBLE_URL=${ANSIBLE_URL:-https://github.com/${ANSIBLE_REPO}/openshift-ansible}
OAL_LOCAL_PATH=`echo $GIT_URL | sed 's,https://,,'`
OS_O_A_L_DIR=${OS_O_A_L_DIR:-/data/src/github.com/openshift/origin-aggregated-logging}
#USE_AMI=${USE_AMI:-fork_ami_openshift3_logging-1.4-backports}

INSTNAME=${INSTNAME:-origin_$USER-$TESTNAME-$OS-1}

pushd $HOME/origin-aggregated-logging

# https://github.com/openshift/origin-ci-tool#installation
if [ ! -d .venv ] ; then
    virtualenv .venv --system-site-packages
fi
PS1=unused
source .venv/bin/activate
pip install git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
pip install --upgrade git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
pip install boto boto3
oct bootstrap self
oct provision remote all-in-one --os $OS --provider aws --stage build --name $INSTNAME
oct sync local origin-aggregated-logging --branch $GIT_BRANCH --merge-into master --src $HOME/origin-aggregated-logging

fqdn=${fqdn:-openshiftdevel}
kibana_host=kibana.$fqdn
kibana_ops_host=kibana-ops.$fqdn
LOG_DIR=/tmp/origin-aggregated-logging/logs

runfile=`mktemp`
trap "rm -f $runfile" ERR EXIT INT TERM
cat > $runfile <<EOF
echo PATH=$PATH
PATH=$PATH:/usr/sbin:$OS_ROOT/_output/local/bin/linux/amd64
export PATH
#sudo sed -i -e 's/^#RateLimitBurst=.*\$/RateLimitBurst=1000000/' /etc/systemd/journald.conf
#sudo systemctl restart systemd-journald
export GIT_URL=$GIT_URL
export GIT_BRANCH=$GIT_BRANCH
export O_A_L_DIR=$OS_O_A_L_DIR
export USE_LOCAL_SOURCE=true
export OS_ROOT=$OS_ROOT
export ENABLE_OPS_CLUSTER=true
export DO_CLEANUP=false
export SETUP_ONLY=false
export VERBOSE=1
#export PUBLIC_MASTER_HOST=$fqdn
#export KIBANA_HOST=$kibana_host
#export KIBANA_OPS_HOST=$kibana_ops_host
export OS_ANSIBLE_REPO=$ANSIBLE_URL
export OS_ANSIBLE_BRANCH=$ANSIBLE_BRANCH
export OS_DEBUG=true
export LOG_DIR=$LOG_DIR
mkdir -p $LOG_DIR
${EXTRA_ENV:-}
pushd $OS_O_A_L_DIR/hack/testing
./logging.sh
EOF
scp $runfile $fqdn:/tmp
ssh -n $fqdn "bash $runfile"

echo use \"oct deprovision\" when you are done
