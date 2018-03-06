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
NO_SKIP=${NO_SKIP:-0}
if [ ! -d .venv ] ; then
    virtualenv .venv --system-site-packages
    NO_SKIP=1
fi
PS1=unused
source .venv/bin/activate
if [ "${NO_SKIP:-0}" = 1 ] ; then
    if pip show origin-ci-tool > /dev/null ; then
#        pip install --upgrade git+file://$HOME/origin-ci-tool --process-dependency-links
        pip install --upgrade git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
    else
#        pip install git+file://$HOME/origin-ci-tool --process-dependency-links
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

# set instance values
oct configure aws-defaults master_security_group_ids $AWS_SECURITY_GROUPS
oct configure aws-defaults master_instance_type $INSTANCE_TYPE
oct configure aws-defaults master_root_volume_size ${ROOT_VOLUME_SIZE:-35}

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
# seems to be a bug currently - doesn't checkout branch other than master - so force it to make sure
ssh -n openshiftdevel "cd $OS_O_A_L_DIR; git checkout ${GIT_BASE_BRANCH:-master}"
#oct sync remote openshift-ansible --branch master
oct sync local openshift-ansible --branch $ANSIBLE_BRANCH --merge-into ${ANSIBLE_BASE_BRANCH:-master} --src $HOME/openshift-ansible
# seems to be a bug currently - doesn't checkout branch other than master - so force it to make sure
ssh -n openshiftdevel "cd $OS_O_A_DIR; git checkout ${ANSIBLE_BASE_BRANCH:-master}"
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
if [ "${USE_LOGGING:-true}" = true -a "${BUILD_IMAGES:-true}" = true ] ; then
    ssh -n openshiftdevel "cd $OS_O_A_L_DIR; hack/build-images.sh"
fi

#      title: "build an openshift-ansible release"
#      repository: "openshift-ansible"
runfile=`mktemp`
trap "rm -f $runfile" ERR EXIT INT TERM
cat > $runfile <<EOF
set -euxo pipefail
cd $OS_O_A_DIR
tito_tmp_dir="tito"
rm -rf "\${tito_tmp_dir}"
mkdir -p "\${tito_tmp_dir}"
titotagtmp=\$( mktemp )
if tito tag --debug --offline --accept-auto-changelog > \$titotagtmp 2>&1 ; then
    cat \$titotagtmp
elif grep -q "Tag openshift-ansible.* already exists" \$titotagtmp ; then
    cat \$titotagtmp
else
    cat \$titotagtmp
    rm -f \$titotagtmp
    exit 1
fi
rm -f \$titotagtmp
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
set -euxo pipefail
pushd $OS_O_A_L_DIR > /dev/null
curbranch=\$( git rev-parse --abbrev-ref HEAD )
popd > /dev/null
if [[ "\${curbranch}" == release-3.7 || "\${curbranch}" == release-3.6 ]] ; then
    sudo yum downgrade -y ansible-2.3\*
fi
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
set -euxo pipefail
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
set -euxo pipefail
# is logging using master or a release branch?
pushd $OS_O_A_L_DIR
curbranch=\$( git rev-parse --abbrev-ref HEAD )
popd
cd $OS_ROOT
jobs_repo=$OS_A_C_J_DIR
if [[ "\${curbranch}" == master ]] ; then
   git log -1 --pretty=%h >> "\${jobs_repo}/ORIGIN_COMMIT"
   ( source hack/lib/init.sh; os::build::rpm::get_nvra_vars; echo "-\${OS_RPM_VERSION}-\${OS_RPM_RELEASE}" ) >> "\${jobs_repo}/ORIGIN_PKG_VERSION"
   ( source hack/lib/init.sh; os::build::rpm::get_nvra_vars; echo "\${OS_GIT_MAJOR}.\${OS_GIT_MINOR}" | sed "s/+//" ) >> "\${jobs_repo}/ORIGIN_RELEASE"
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
    foundrepover=false
    for repo in \$( sudo yum repolist all | awk '/^[!]?centos-paas-sig-openshift-origin/ {print gensub(/^!/,"",1,\$1)}' ) ; do
        case \$repo in
        centos-paas-sig-openshift-origin\${repover}-rpms)
            foundrepover=true # found a repo for this version
            sudo yum-config-manager --enable \$repo > /dev/null ;;
        *)
            sudo yum-config-manager --disable \$repo > /dev/null ;;
        esac
    done
    if [[ "\${foundrepover:-false}" == false ]] ; then
        # see if there is a repo for this version that is available on the external
        # site but not yet configured as a local yum repo
        respcode=\$( curl -L -s -XHEAD -w '%{response_code}\n' http://cbs.centos.org/repos/paas7-openshift-origin\${repover}-candidate/x86_64/os/repodata )
        if [[ "\${respcode}" == "200" ]] ; then
            cat <<EOF2 | sudo tee /etc/yum.repos.d/centos-paas-sig-openshift-origin\${repover}-rpms.repo
[centos-paas-sig-openshift-origin\${repover}-rpms]
baseurl = https://buildlogs.centos.org/centos/7/paas/x86_64/openshift-origin\${repover}/
gpgcheck = 0
name = CentOS PaaS SIG Origin \${repover} Repository
sslclientcert = /var/lib/yum/client-cert.pem
sslclientkey = /var/lib/yum/client-key.pem
sslverify = 0
enabled = 1
EOF2
            foundrepover=true # found a repo for this version
        fi
    fi
    # disable local origin repo if foundrepover is true - else, we do not have
    # a release specific repo, use origin-local-release
    if [[ "\${foundrepover:-false}" == true ]] ; then
        echo "\${closest_tag}" > \${jobs_repo}/ORIGIN_COMMIT
        echo "\${pkgver}" > \${jobs_repo}/ORIGIN_PKG_VERSION
        sudo yum-config-manager --disable origin-local-release > /dev/null
        if ( sudo yum install --assumeno origin\${pkgver} 2>&1 || : ) | grep -q 'No package .* available' ; then
            # just ask yum what the heck the version is
            pkgver=\$( ( sudo yum install --assumeno origin 2>&1 || : ) | awk '\$1 == "x86_64" {print \$2}' )
            echo "-\${pkgver}" > \${jobs_repo}/ORIGIN_PKG_VERSION
        else
            echo package origin\${pkgver} is available
        fi
    else # use latest on machine
        pushd $OS_ROOT > /dev/null
        git log -1 --pretty=%h >> "\${jobs_repo}/ORIGIN_COMMIT"
        ( source hack/lib/init.sh; os::build::rpm::get_nvra_vars; echo "-\${OS_RPM_VERSION}-\${OS_RPM_RELEASE}" ) >> "\${jobs_repo}/ORIGIN_PKG_VERSION"
        ( source hack/lib/init.sh; os::build::rpm::get_nvra_vars; echo "\${OS_GIT_MAJOR}.\${OS_GIT_MINOR}" | sed "s/+//" ) >> "\${jobs_repo}/ORIGIN_RELEASE"
        popd > /dev/null
    fi
    # build our release deps package
    rpmbuild -ba $OS_O_A_L_DIR/hack/branch-deps.spec
    # downgrade/erase troublesome packages
    sudo yum -y downgrade docker-1.12\* docker-client-1.12\* docker-common-1.12\* docker-rhel-push-plugin-1.12\* skopeo-0.1.27\* skopeo-containers-0.1.27\*
    sudo yum -y install \$HOME/rpmbuild/RPMS/noarch/branch-deps-*.noarch.rpm
else
    echo Error: unknown base branch \$curbranch: please resubmit PR on master or a release-x.y branch
fi
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

# make etcd use a ramdisk
cat <<SCRIPT > $runfile
set -euxo pipefail
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
set -euxo pipefail
cd $OS_A_C_J_DIR
if [ -f /usr/share/ansible/openshift-ansible/playbooks/prerequisites.yml ] ; then
    ansible-playbook -vv --become               \
                        --become-user root         \
                        --connection local         \
                        --inventory sjb/inventory/ \
                        -e deployment_type=origin  \
                        -e openshift_docker_log_driver=${LOG_DRIVER:-journald} \
                        -e openshift_docker_options="--log-driver=${LOG_DRIVER:-journald}" \
                        /usr/share/ansible/openshift-ansible/playbooks/prerequisites.yml
fi

playbook_base='/usr/share/ansible/openshift-ansible/playbooks/'
if [[ -s "\${playbook_base}/openshift-node/network_manager.yml" ]]; then
    playbook="\${playbook_base}openshift-node/network_manager.yml"
else
    playbook="\${playbook_base}byo/openshift-node/network_manager.yml"
fi
ansible-playbook -vvv --become               \
  --become-user root         \
  --connection local         \
  --inventory sjb/inventory/ \
  -e deployment_type=origin  \
  -e openshift_docker_log_driver=${LOG_DRIVER:-journald} \
  -e openshift_docker_options="--log-driver=${LOG_DRIVER:-journald}" \
  \${playbook}

if [[ -s "\${playbook_base}deploy_cluster.yml" ]]; then
    playbook="\${playbook_base}deploy_cluster.yml"
else
    playbook="\${playbook_base}byo/config.yml"
fi
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
  -e oreg_url='openshift/origin-\${component}:'"${OPENSHIFT_IMAGE_TAG:-\$( cat ./ORIGIN_COMMIT )}" \
  \${playbook}
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash -x $runfile"

#  title: "expose the kubeconfig"
cat > $runfile <<EOF
set -euxo pipefail
sudo chmod a+x /etc/ /etc/origin/ /etc/origin/master/
sudo chmod a+rw /etc/origin/master/admin.kubeconfig
if [ ! -d ~/.kube ] ; then
    mkdir ~/.kube
fi
cp /etc/origin/master/admin.kubeconfig ~/.kube/config
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

if [ "${USE_LOGGING:-true}" = true ] ; then
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
fi

#      title: "install origin-aggregated-logging"
#      repository: "aos-cd-jobs"
if [ "${USE_LOGGING:-true}" = true ] ; then
    cat > $runfile <<EOF
set -euxo pipefail
cd $OS_A_C_J_DIR
playbook_base='/usr/share/ansible/openshift-ansible/playbooks/'
if [[ -s "\${playbook_base}openshift-logging/config.yml" ]]; then
    playbook="\${playbook_base}openshift-logging/config.yml"
else
    playbook="\${playbook_base}byo/openshift-cluster/openshift-logging.yml"
fi
pushd "$OS_O_A_L_DIR"
curbranch=\$( git rev-parse --abbrev-ref HEAD )
popd
logging_extras=""
if [[ "\$curbranch" == es5.x ]]; then
    logging_extras="\${logging_extras} -e openshift_logging_es5_techpreview=True \
                    -e openshift_logging_image_version=latest"
elif [[ "\${curbranch}" == master ]]; then
    # force image version/tag to be latest, otherwise it will use openshift_tag_version
    logging_extras="\${logging_extras} -e openshift_logging_image_version=latest"
fi
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
  ${EXTRA_ANSIBLE:-} \${logging_extras} \
  \${playbook} \
  --skip-tags=update_master_config
EOF
#  -e openshift_logging_install_eventrouter=True \
    cat $runfile
    scp $runfile openshiftdevel:/tmp
    ssh -n openshiftdevel "bash $runfile"
fi

if [ -n "${PRESERVE:-}" ] ; then
    id=$( aws ec2 --profile rh-dev describe-instances --output text --filters "Name=tag:Name,Values=$INSTNAME" --query 'Reservations[].Instances[].[InstanceId]' )
    aws ec2 --profile rh-dev create-tags --resources $id \
        --tags Key=Name,Value=${INSTNAME}-preserve
    sed -i -e "s/${INSTNAME}/${INSTNAME}-preserve/" $HOME/.config/origin-ci-tool/inventory/ec2.ini
fi

#      title: "run logging tests"
#      repository: "origin-aggregated-logging"
if [ "${USE_LOGGING:-true}" = true ] ; then
    cat > $runfile <<EOF
sudo wget -O /usr/local/bin/stern https://github.com/wercker/stern/releases/download/1.5.1/stern_linux_amd64 && sudo chmod +x /usr/local/bin/stern
cd $OS_O_A_L_DIR
${EXTRA_ENV:-}
KUBECONFIG=/etc/origin/master/admin.kubeconfig TEST_ONLY=${TEST_ONLY:-true} \
  SKIP_TEARDOWN=true JUNIT_REPORT=true make test
EOF
    scp $runfile openshiftdevel:/tmp
    ssh -n openshiftdevel "bash $runfile"
fi

echo use \"oct deprovision\" when you are done
