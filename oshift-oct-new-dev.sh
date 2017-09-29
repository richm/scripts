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
oct sync local origin-aggregated-logging --branch $GIT_BRANCH --merge-into ${GIT_BASE_BRANCH:-master} --src $HOME/origin-aggregated-logging
#oct sync remote openshift-ansible --branch master
oct sync local openshift-ansible --branch $ANSIBLE_BRANCH --merge-into ${ANSIBLE_BASE_BRANCH:-master} --src $HOME/openshift-ansible
# also needs aos_cd_jobs
oct sync remote aos-cd-jobs --branch master

# HACK HACK HACK
# there is a problem with the enterprise-3.3 repo:
#https://use-mirror2.ops.rhcloud.com/enterprise/enterprise-3.3/latest/RH7-RHAOS-3.3/x86_64/os/repodata/repomd.xml: [Errno 14] HTTPS Error 404 - Not Found
#so just disable this repo for now
# fixed 2017-08-10
#ssh -n openshiftdevel "echo enabled=0 | sudo tee -a /etc/yum.repos.d/rhel-7-server-ose-3.3-rpms.repo"

#      title: "build an origin-aggregated-logging release"
#      repository: "origin-aggregated-logging"
#      script: |-
#        hack/build-images.sh
ssh -n openshiftdevel "cd $OS_O_A_L_DIR; hack/build-images.sh"

#      title: "build an openshift-ansible release"
#      repository: "openshift-ansible"
runfile=`mktemp`
trap "rm -f $runfile" ERR EXIT INT TERM
cat > $runfile <<EOF
cd $OS_O_A_DIR
tito_tmp_dir="tito"
rm -rf "\${tito_tmp_dir}"
mkdir -p "\${tito_tmp_dir}"
tito tag --debug --offline --accept-auto-changelog
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
set -x
cd $OS_O_A_DIR
jobs_repo=$OS_A_C_J_DIR
last_tag="\$( git describe --tags --abbrev=0 --exact-match HEAD )"
if [ -z "\${last_tag}" ] ; then
   # fatal: no tag exactly matches '89c405109d8ca5906d9beb03e7e2794267f5f357'
   last_tag="\$( git describe --tags --abbrev=0 )"
fi
last_commit="\$( git log -n 1 --pretty=%h )"
if sudo yum install -y "atomic-openshift-utils\${last_tag/openshift-ansible/}.git.0.\${last_commit}.el7" ; then
   rpm -V "atomic-openshift-utils\${last_tag/openshift-ansible/}.git.0.\${last_commit}.el7"
else
   # for master, it looks like there is some sort of strange problem with git tags
   # tito will give the packages a N-V-R like this:
   # atomic-openshift-utils-3.7.0-0.134.0.git.20.186ded5.el7
   # git describe --tags --abbrev=0 looks like this
   # openshift-ansible-3.7.0-0.134.0
   # git describe --tags looks like this
   # openshift-ansible-3.7.0-0.134.0-20-g186ded5
   # there doesn't appear to be a git describe command which will give
   # the same result, so munge it
   verrel=\$( git describe --tags | \
              sed -e 's/^openshift-ansible-//' -e 's/-\([0-9][0-9]*\)-g\(..*\)\$/.git.\1.\2/' )
   sudo yum install -y "atomic-openshift-utils-\${verrel}.el7"
   rpm -V "atomic-openshift-utils-\${verrel}.el7"
fi
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
# is logging using master or a release branch?
pushd $OS_O_A_L_DIR
curbranch=\$( git rev-parse --abbrev-ref HEAD )
popd
cd $OS_ROOT
jobs_repo=$OS_A_C_J_DIR
if [[ "\${curbranch}" == master ]] ; then
   git log -1 --pretty=%h >> "\${jobs_repo}/ORIGIN_COMMIT"
   ( source hack/lib/init.sh; os::build::rpm::get_nvra_vars; echo "-\${OS_RPM_VERSION}-\${OS_RPM_RELEASE}" ) >> "\${jobs_repo}/ORIGIN_PKG_VERSION"
elif [[ "\${curbranch}" =~ ^release-* ]] ; then
    pushd $OS_O_A_L_DIR
    # get repo ver from branch name
    repover=\$( echo "\${curbranch}" | sed -e 's/release-//' -e 's/[.]//' )
    # get version from tag
    closest_tag=\$( git describe --tags --abbrev=0 )
    # pkg ver is commitver with leading "-" instead of "v"
    pkgver=\$( echo "\${closest_tag}" | sed 's/^v/-/' )
    # disable all of the centos repos except for the one for the
    # version being tested - this assumes a devenv environment where
    # all of the repos are installed
    for repo in \$( sudo yum repolist | awk '/^centos-paas-sig-openshift-origin/ {print \$1}' ) ; do
        case \$repo in
        centos-paas-sig-openshift-origin\${repover}-rpms) sudo yum-config-manager --enable \$repo > /dev/null ;;
        *) sudo yum-config-manager --disable \$repo > /dev/null ;;
        esac
    done
    echo "\${closest_tag}" > $OS_A_C_J_DIR/ORIGIN_COMMIT
    echo "\${pkgver}" > $OS_A_C_J_DIR/ORIGIN_PKG_VERSION
    # disable local origin repo
    sudo yum-config-manager --disable origin-local-release > /dev/null
fi
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

# make etcd use a ramdisk
cat <<SCRIPT > $runfile
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
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#      title: "install origin"
#      repository: "aos-cd-jobs"
cat > $runfile <<EOF
cd $OS_A_C_J_DIR
ansible-playbook -vvv --become               \
  --become-user root         \
  --connection local         \
  --inventory sjb/inventory/ \
  -e deployment_type=origin  \
  /usr/share/ansible/openshift-ansible/playbooks/byo/openshift-node/network_manager.yml

ansible-playbook -vvv --become               \
  --become-user root         \
  --connection local         \
  --inventory sjb/inventory/ \
  -e deployment_type=origin  \
  -e openshift_logging_install_logging=False \
  -e openshift_logging_install_metrics=False \
  -e openshift_docker_log_driver=${LOG_DRIVER:-journald} \
  -e openshift_docker_options="--log-driver=${LOG_DRIVER:-journald}" \
  -e etcd_data_dir="\${ETCD_DATA_DIR}" \
  -e openshift_pkg_version="\$( cat ./ORIGIN_PKG_VERSION )"               \
  -e oreg_url='openshift/origin-\${component}:'"\$( cat ./ORIGIN_COMMIT )" \
/usr/share/ansible/openshift-ansible/playbooks/byo/config.yml
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash -x $runfile"

#  title: "expose the kubeconfig"
cat > $runfile <<EOF
sudo chmod a+x /etc/ /etc/origin/ /etc/origin/master/
sudo chmod a+rw /etc/origin/master/admin.kubeconfig
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

# HACK - create mux pvc
if [ "${MUX_FILE_BUFFER_STORAGE_TYPE:-}" = pvc ] ; then
    cat > $runfile <<EOF
apiVersion: "v1"
kind: "PersistentVolume"
metadata:
  name: logging-muxpv-1
spec:
  capacity:
    storage: "6Gi"
  accessModes:
    - "ReadWriteOnce"
  hostPath:
    path: ${FILE_BUFFER_PATH:-/var/lib/fluentd}
EOF
    scp $runfile openshiftdevel:/tmp
    ssh -n openshiftdevel "oc create --config=/etc/origin/master/admin.kubeconfig -f $runfile"
fi

#      title: "install origin-aggregated-logging"
#      repository: "aos-cd-jobs"
cat > $runfile <<EOF
cd $OS_A_C_J_DIR
ansible-playbook -vv --become \
  --become-user root \
  --connection local \
  --inventory sjb/inventory/ \
  -e deployment_type=origin \
  -e openshift_logging_install_logging=True \
  -e openshift_logging_image_prefix="openshift/origin-" \
  -e openshift_logging_kibana_hostname="$kibana_host" \
  -e openshift_logging_kibana_ops_hostname="$kibana_ops_host" \
  -e openshift_logging_master_public_url="https://$fqdn:8443" \
  -e openshift_master_logging_public_url="https://$kibana_host" \
  -e openshift_logging_es_hostname=${ES_HOST:-es.$fqdn} \
  -e openshift_logging_es_ops_hostname=${ES_OPS_HOST:-es-ops.$fqdn} \
  -e openshift_logging_mux_hostname=${MUX_HOST:-mux.$fqdn} \
  -e openshift_logging_use_mux=${USE_MUX:-True} \
  -e openshift_logging_mux_allow_external=${MUX_ALLOW_EXTERNAL:-True} \
  -e openshift_logging_es_allow_external=${ES_ALLOW_EXTERNAL:-True} \
  -e openshift_logging_es_ops_allow_external=${ES_OPS_ALLOW_EXTERNAL:-True} \
  -e openshift_logging_install_eventrouter=True \
  ${EXTRA_ANSIBLE:-} \
  /usr/share/ansible/openshift-ansible/playbooks/byo/openshift-cluster/openshift-logging.yml \
  --skip-tags=update_master_config
EOF
cat $runfile
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

if [ -n "${PRESERVE:-}" ] ; then
    id=$( aws ec2 --profile rh-dev describe-instances --output text --filters "Name=tag:Name,Values=$INSTNAME" --query 'Reservations[].Instances[].[InstanceId]' )
    aws ec2 --profile rh-dev create-tags --resources $id \
        --tags Key=Name,Value=${INSTNAME}-preserve
fi

#      title: "run logging tests"
#      repository: "origin-aggregated-logging"
cat > $runfile <<EOF
sudo wget -O /usr/local/bin/stern https://github.com/wercker/stern/releases/download/1.5.1/stern_linux_amd64 && sudo chmod +x /usr/local/bin/stern
cd $OS_O_A_L_DIR
${EXTRA_ENV:-}
KUBECONFIG=/etc/origin/master/admin.kubeconfig TEST_ONLY=${TEST_ONLY:-true} \
  SKIP_TEARDOWN=true JUNIT_REPORT=true make test
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

echo use \"oct deprovision\" when you are done
