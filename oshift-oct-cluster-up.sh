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
#NO_SKIP=1
if [ -n "${NO_SKIP:-}" ] ; then
    if pip show origin-ci-tool > /dev/null ; then
        pip install --upgrade git+file://$HOME/origin-ci-tool --process-dependency-links
#        pip install --upgrade git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
    else
        pip install git+file://$HOME/origin-ci-tool --process-dependency-links
#        pip install git+https://github.com/openshift/origin-ci-tool.git --process-dependency-links
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
if [ -d $HOME/origin-aggregated-logging/fluentd/jemalloc ] ; then
    scp -r $HOME/origin-aggregated-logging/fluentd/jemalloc openshiftdevel:/data/src/github.com/openshift/origin-aggregated-logging/fluentd
fi

#oct sync remote openshift-ansible --branch master
oct sync local openshift-ansible --branch $ANSIBLE_BRANCH --merge-into ${ANSIBLE_BASE_BRANCH:-master} --src $HOME/openshift-ansible
# also needs aos_cd_jobs
oct sync remote aos-cd-jobs --branch master

runfile=$( mktemp )

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

#      title: "install Ansible and plugins"
#      repository: "origin"
cat > $runfile <<EOF
cd $OS_O_A_L_DIR
sudo yum install -y ansible python2 python-six tar java-1.8.0-openjdk-headless httpd-tools \
    libselinux-python python-passlib python-pip
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

#      title: "prep machine to be able to run oc cluster up and run it"
#      repository: "origin"
# https://github.com/openshift/origin/blob/master/docs/cluster_up_down.md#overview
cat > $runfile <<EOF
# 3.8 has a problem with fail-swap-on - not a valid flag
sudo yum install -y origin-clients-3.7.0 docker /usr/bin/firewall-cmd
sudo systemctl enable firewalld
sudo systemctl start firewalld
sudo sysctl -w net.ipv4.ip_forward=1

# set up docker for local registry
if ! sudo grep -q '^INSECURE_REGISTRY=' /etc/sysconfig/docker ; then
    # not present - easy - just add it
    echo "INSECURE_REGISTRY='--insecure-registry=172.30.0.0/16'" | sudo tee -a /etc/sysconfig/docker > /dev/null
elif ! sudo grep -q '^INSECURE_REGISTRY=.*--insecure-registry=172.30.0.0/16' /etc/sysconfig/docker ; then
    # already there - just add our registry - assumes 1 single line
    sudo sed -e "/^INSECURE_REGISTRY=/s,[']$, --insecure-registry 172.30.0.0/16'," -i /etc/sysconfig/docker
fi

# set docker log driver correctly
if ! sudo grep -q '^OPTIONS=' /etc/sysconfig/docker ; then
    # not present - easy - just add it
    echo "OPTIONS='--log-driver=${LOG_DRIVER:-journald}'" | sudo tee -a /etc/sysconfig/docker > /dev/null
elif ! sudo grep -q '^OPTIONS=.*--log-driver' /etc/sysconfig/docker ; then
    # already there - just add our value - assumes 1 single line
    sudo sed -e "/^OPTIONS=/s,[']$, --log-driver=${LOG_DRIVER:-journald}'," -i /etc/sysconfig/docker
else
    # already there with value - change the value
    sudo sed -e "/^OPTIONS=/s/--log-driver=[-_a-zA-Z0-9][-_a-zA-Z0-9]*/--log-driver=${LOG_DRIVER:-journald}/" -i /etc/sysconfig/docker
fi

sudo systemctl daemon-reload
sudo systemctl restart docker

subnet=\$( sudo docker network inspect -f "{{range .IPAM.Config }}{{ .Subnet }}{{end}}" bridge )
sudo firewall-cmd --permanent --new-zone dockerc
sudo firewall-cmd --permanent --zone dockerc --add-source \$subnet
sudo firewall-cmd --permanent --zone dockerc --add-port 8443/tcp
sudo firewall-cmd --permanent --zone dockerc --add-port 53/udp
sudo firewall-cmd --permanent --zone dockerc --add-port 8053/udp
sudo firewall-cmd --reload
metadata_endpoint="http://169.254.169.254/latest/meta-data"
public_hostname="\$( curl -s "\${metadata_endpoint}/public-hostname" )"
public_ip="\$( curl -s "\${metadata_endpoint}/public-ipv4" )"
sudo oc cluster up --public-hostname="\${public_hostname}" --routing-suffix="\${public_ip}.xip.io"
# change the config
# allow externalIPs, and kibana UI access
SERVER_CONFIG_DIR=/var/lib/origin/openshift.local.config
# add loggingPublicURL so the OpenShift UI Console will include a link for Kibana
# this part stolen from util.sh configure_os_server()
sudo cp \${SERVER_CONFIG_DIR}/master/master-config.yaml \${SERVER_CONFIG_DIR}/master/master-config.orig.yaml
if [ -n "${kibana_host:-}" ] ; then
    docker exec origin openshift ex config patch \${SERVER_CONFIG_DIR}/master/master-config.orig.yaml \
        --patch="{\"assetConfig\": {\"loggingPublicURL\": \"https://${kibana_host}\"}}" | \
        sudo tee \${SERVER_CONFIG_DIR}/master/master-config.yaml > /dev/null
fi
sudo cp \${SERVER_CONFIG_DIR}/master/master-config.yaml \${SERVER_CONFIG_DIR}/master/master-config.save.yaml
docker exec origin openshift ex config patch \${SERVER_CONFIG_DIR}/master/master-config.save.yaml \
    --patch="{\"networkConfig\": {\"externalIPNetworkCIDRs\": [\"0.0.0.0/0\"]}}" | \
    sudo tee \${SERVER_CONFIG_DIR}/master/master-config.yaml > /dev/null
# restart cluster so changes will take effect
sudo oc cluster down
sudo systemctl restart docker
sudo oc cluster up --use-existing-config --public-hostname="\${public_hostname}" --routing-suffix="\${public_ip}.xip.io"
EOF
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

#  title: "expose the kubeconfig"
cat > $runfile <<EOF
if [ ! -d ~/.kube ] ; then
    mkdir ~/.kube
fi
sudo cp /var/lib/origin/openshift.local.config/master/admin.kubeconfig ~/.kube/config
sudo chown \$USER ~/.kube/config
sudo mkdir -p /etc/origin/master
sudo cp /var/lib/origin/openshift.local.config/master/admin.kubeconfig /etc/origin/master/admin.kubeconfig
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
    ssh -n openshiftdevel "oc create -f $runfile"
fi

#      title: "install origin-aggregated-logging"
#      repository: "aos-cd-jobs"
cat > $runfile <<EOF
cd $OS_A_C_J_DIR
# cannot use the networking related parameters with cluster up deployment
if [ -f sjb/inventory/group_vars/OSEv3/general.yml ] ; then
    sed -e '/^osm_cluster_network_cidr/d' \
        -e '/^openshift_portal_net/d' \
        -e '/^osm_host_subnet_length/d' \
        -i sjb/inventory/group_vars/OSEv3/general.yml
else
    echo ERROR: no such file sjb/inventory/group_vars/OSEv3/general.yml
    exit 1
fi
cd $OS_O_A_DIR
playbook_base='playbooks/'
if [[ -s "\${playbook_base}openshift-logging/config.yml" ]]; then
    playbook="\${playbook_base}openshift-logging/config.yml"
else
    playbook="\${playbook_base}byo/openshift-cluster/openshift-logging.yml"
fi
ansible-playbook -vv --become \
  --become-user root \
  --connection local \
  --inventory $OS_A_C_J_DIR/sjb/inventory/ \
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
  ${EXTRA_ANSIBLE:-} \
  \${playbook} \
  --skip-tags=update_master_config
EOF
# richm 20171204 - problem with too much recursion with this role?
#  -e openshift_logging_install_eventrouter=True \
cat $runfile
scp $runfile openshiftdevel:/tmp
ssh -n openshiftdevel "bash $runfile"

if [ -n "${PRESERVE:-}" ] ; then
    id=$( aws ec2 --profile rh-dev describe-instances --output text --filters "Name=tag:Name,Values=$INSTNAME" --query 'Reservations[].Instances[].[InstanceId]' )
    aws ec2 --profile rh-dev create-tags --resources $id \
        --tags Key=Name,Value=${INSTNAME}-preserve
    sed -i -e "s/${INSTNAME}/${INSTNAME}-preserve/" $HOME/.config/origin-ci-tool/inventory/ec2.ini
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
