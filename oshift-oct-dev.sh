#!/bin/sh

set -euxo pipefail

getremoteip() {
    #ssh openshiftdevel curl -s http://169.254.169.254/latest/meta-data/public-ipv4
    ssh openshiftdevel -G|awk '/^hostname/ {print $2}'
}

getremotefqdn() {
    #ssh openshiftdevel curl -s http://169.254.169.254/latest/meta-data/public-hostname
    getent hosts $1 | awk '{print $2}'
}

update_etc_hosts() {
    for item in "$@" ; do
        sudo sed -i -e "/$item/d" /etc/hosts
    done
    echo "$@" | sudo tee -a /etc/hosts > /dev/null
}

scriptname=`basename $0`
if [ -f $HOME/.config/$scriptname ] ; then
    . $HOME/.config/$scriptname
fi

OS=${OS:-rhel}
TESTNAME=${TESTNAME:-logging}
INSTANCE_TYPE=${INSTANCE_TYPE:-m4.xlarge}
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
export AWS_SECURITY_GROUPS=${AWS_SECURITY_GROUPS:-sg-e1760186}

INSTNAME=${INSTNAME:-origin_$USER-$TESTNAME-$OS-1}

pushd $HOME/origin-aggregated-logging

# https://github.com/openshift/origin-ci-tool#installation
if [ ! -d .venv ] ; then
    virtualenv .venv --system-site-packages
fi
PS1=unused
source .venv/bin/activate
NO_SKIP=1
if [ -n "${NO_SKIP:-}" ] ; then
    if pip show origin-ci-tool > /dev/null ; then
        pip install --upgrade git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
    else
        pip install git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
    fi
    for pkg in boto boto3 ; do
        if pip show $pkg > /dev/null ; then
            pip install --upgrade $pkg
        else
            pip install $pkg
        fi
    done
    oct bootstrap self
fi
oct configure aws-defaults master_security_group_ids $AWS_SECURITY_GROUPS
oct configure aws-defaults master_instance_type $INSTANCE_TYPE
oct provision remote all-in-one --os $OS --provider aws --stage build --name $INSTNAME

ip=`getremoteip`
fqdn=`getremotefqdn $ip`

kibana_host=kibana.$fqdn
kibana_ops_host=kibana-ops.$fqdn
update_etc_hosts $ip $fqdn $kibana_host $kibana_ops_host

oct sync local origin-aggregated-logging --branch $GIT_BRANCH --merge-into master --src $HOME/origin-aggregated-logging
#oct sync remote openshift-ansible --branch master
#oct sync remote origin-aggregated-logging --refspec pull/471/head --branch pull-471 --merge-into master
#cd /data/src/github.com/openshift/origin-aggregated-logging
#hack/build-images.sh

# make etcd use a ramdisk
script="$( mktemp )"
cat <<SCRIPT >"${script}"
#!/bin/bash
set -o errexit -o nounset -o pipefail -o xtrace
cd "\${HOME}"
sudo su root <<SUDO
mkdir -p /tmp
mount -t tmpfs -o size=4096m tmpfs /tmp
mkdir -p /tmp/etcd
chmod a+rwx /tmp/etcd
restorecon -R /tmp
echo "ETCD_DATA_DIR=/tmp/etcd" >> /etc/environment
SUDO
SCRIPT
chmod +x "${script}"
scp "${script}" openshiftdevel:"${script}"
ssh -n openshiftdevel "bash ${script}"

LOG_DIR=/tmp/origin-aggregated-logging/logs
runfile=`mktemp`
trap "rm -f $runfile" ERR EXIT INT TERM

cat > $runfile <<EOF
echo PATH=$PATH
PATH=$PATH:/usr/sbin:$OS_ROOT/_output/local/bin/linux/amd64
export PATH
# this is a hack used on occasion but hopefully not any more
#export API_BIND_HOST=0.0.0.0
#export API_HOST=\$(openshift start --print-ip)
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
export PUBLIC_MASTER_HOST=$fqdn
export KIBANA_HOST=$kibana_host
export KIBANA_OPS_HOST=$kibana_ops_host
export OS_ANSIBLE_REPO=$ANSIBLE_URL
export OS_ANSIBLE_BRANCH=$ANSIBLE_BRANCH
export OS_DEBUG=true
export LOG_DIR=$LOG_DIR
mkdir -p $LOG_DIR
${EXTRA_ENV:-}
pushd $OS_O_A_L_DIR/hack/testing
sudo wget -O /usr/local/bin/stern https://github.com/wercker/stern/releases/download/1.5.1/stern_linux_amd64 && sudo chmod +x /usr/local/bin/stern
./logging.sh
mkdir /home/origin/.kube
cp /tmp/openshift/origin-aggregated-logging/openshift.local.config/master/admin.kubeconfig /home/origin/.kube/config
chmod o+w /home/origin/.kube/config
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

echo use \"oct deprovision\" when you are done
