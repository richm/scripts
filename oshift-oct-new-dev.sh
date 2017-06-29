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
OS_O_A_DIR=${OS_O_A_DIR:-/data/src/github.com/openshift/openshift-ansible}
OS_A_C_J_DIR=${OS_A_C_J_DIR:-/data/src/github.com/openshift/aos-cd-jobs}
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

# based on
# https://github.com/openshift/aos-cd-jobs/blob/master/sjb/config/test_cases/test_branch_openshift_ansible_logging.yml
#  sync_repos:
#    - name: "origin-aggregated-logging"
#    - name: "openshift-ansible"
oct sync local origin-aggregated-logging --branch $GIT_BRANCH --merge-into master --src $HOME/origin-aggregated-logging
oct sync local openshift-ansible --branch $ANSIBLE_BRANCH --merge-into master --src $HOME/openshift-ansible
# also needs aos_cd_jobs
oct sync remote aos-cd-jobs --branch master

#      title: "build an origin-aggregated-logging release"
#      repository: "origin-aggregated-logging"
#      script: |-
#        hack/build-images.sh
ssh openshiftdevel "cd $OS_O_A_L_DIR; hack/build-images.sh"

#      title: "build an openshift-ansible release"
#      repository: "openshift-ansible"
runfile=`mktemp`
trap "rm -f $runfile" ERR EXIT INT TERM
cat > $runfile <<EOF
cd $OS_O_A_DIR
tito_tmp_dir="tito"
rm -rf "\${tito_tmp_dir}"
mkdir -p "\${tito_tmp_dir}"
tito tag --offline --accept-auto-changelog
tito build --output="\${tito_tmp_dir}" --rpm --test --offline --quiet
createrepo "\${tito_tmp_dir}/noarch"
cat << EOR > ./openshift-ansible-local-release.repo
[openshift-ansible-local-release]
baseurl = file://\$( pwd )/\${tito_tmp_dir}/noarch
gpgcheck = 0
name = OpenShift Ansible Release from Local Source
EOR
sudo cp ./openshift-ansible-local-release.repo /etc/yum.repos.d
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "install the openshift-ansible release"
#      repository: "openshift-ansible"
cat > $runfile <<EOF
cd $OS_O_A_DIR
jobs_repo=$OS_A_C_J_DIR
last_tag="\$( git describe --tags --abbrev=0 --exact-match HEAD )"
last_commit="\$( git log -n 1 --pretty=%h )"
sudo yum install -y "atomic-openshift-utils\${last_tag/openshift-ansible/}.git.0.\${last_commit}.el7"
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "install Ansible plugins"
#      repository: "origin"
cat > $runfile <<EOF
cd $OS_ROOT
sudo yum install -y python-pip
sudo pip install junit_xml
sudo chmod o+rw /etc/environment
echo "ANSIBLE_JUNIT_DIR=\$( pwd )/_output/scripts/ansible_junit" >> /etc/environment
sudo mkdir -p /usr/share/ansible/plugins/callback
for plugin in 'default_with_output_lists' 'generate_junit'; do
  wget "https://raw.githubusercontent.com/openshift/origin-ci-tool/master/oct/ansible/oct/callback_plugins/\${plugin}.py"
  sudo mv "\${plugin}.py" /usr/share/ansible/plugins/callback
done
sudo sed -r -i -e 's/^#?stdout_callback.*/stdout_callback = default_with_output_lists/' -e 's/^#?callback_whitelist.*/callback_whitelist = generate_junit/' /etc/ansible/ansible.cfg
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "determine the release commit for origin images and version for rpms"
#      repository: "origin"
cat > $runfile <<EOF
cd $OS_ROOT
jobs_repo=$OS_A_C_J_DIR
git log -1 --pretty=%h >> "\${jobs_repo}/ORIGIN_COMMIT"
( source hack/lib/init.sh; os::build::rpm::get_nvra_vars; echo "-\${OS_RPM_VERSION}-\${OS_RPM_RELEASE}" ) >> "\${jobs_repo}/ORIGIN_PKG_VERSION"
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "install origin"
#      repository: "aos-cd-jobs"
cat > $runfile <<EOF
cd $OS_A_C_J_DIR
ansible-playbook -vv --become               \
  --become-user root         \
  --connection local         \
  --inventory sjb/inventory/ \
  -e deployment_type=origin  \
  /usr/share/ansible/openshift-ansible/playbooks/byo/openshift-node/network_manager.yml
ansible-playbook -vv --become               \
  --become-user root         \
  --connection local         \
  --inventory sjb/inventory/ \
  -e deployment_type=origin  \
  -e etcd_data_dir="\${ETCD_DATA_DIR}" \
  -e openshift_pkg_version="\$( cat ./ORIGIN_PKG_VERSION )"               \
  -e oreg_url='openshift/origin-\${component}:'"\$( cat ./ORIGIN_COMMIT )" \
/usr/share/ansible/openshift-ansible/playbooks/byo/config.yml
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#  title: "expose the kubeconfig"
cat > $runfile <<EOF
sudo chmod a+x /etc/ /etc/origin/ /etc/origin/master/
sudo chmod a+rw /etc/origin/master/admin.kubeconfig
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "install origin-aggregated-logging"
#      repository: "aos-cd-jobs"
cat > $runfile <<EOF
cd $OS_A_C_J_DIR
ansible-playbook -vv --become               \
  --become-user root         \
  --connection local         \
  --inventory sjb/inventory/ \
  -e deployment_type=origin  \
  -e openshift_logging_image_prefix="openshift/origin-" \
  -e openshift_logging_kibana_hostname="$kibana_host"           \
  -e openshift_logging_kibana_ops_hostname="$kibana_ops_host"           \
  -e openshift_logging_master_public_url="https://$fqdn:8443"          \
  -e openshift_master_logging_public_url="https://$kibana_host" \
  /usr/share/ansible/openshift-ansible/playbooks/byo/openshift-cluster/openshift-logging.yml \
  --skip-tags=update_master_config
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "run logging tests"
#      repository: "origin-aggregated-logging"
cat > $runfile <<EOF
cd $OS_O_A_L_DIR
KUBECONFIG=/etc/origin/master/admin.kubeconfig TEST_ONLY=true SKIP_TEARDOWN=true make test
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

echo use \"oct deprovision\" when you are done
