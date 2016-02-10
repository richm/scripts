#!/bin/bash
# based on https://github.com/openshift/origin#getting-started
# and https://github.com/openshift/origin/blob/master/examples/sample-app/container-setup.md
# and https://github.com/openshift/origin/blob/master/examples/sample-app/README.md
# and https://github.com/openshift/origin/blob/master/docs/debugging-openshift.md

set -o errexit

#ORIGIN_CONTAINER="sudo docker exec origin"

unset CURL_CA_BUNDLE

wait_for_builds_complete() {
    waittime=1200 # seconds - 20 minutes
    interval=30
    complete=0
    while [ $waittime -gt 0 -a $complete = 0 ] ; do
        # all lines must have $4 == "Complete"
        complete=`$ORIGIN_CONTAINER oc get builds | awk '$4 == "STATUS" || $4 == "Complete" {complete++}; END {print NR == complete}'`
        if [ $complete = 1 ] ; then
            echo Builds are complete
            break
        fi
        sleep $interval
        waittime=`expr $waittime - $interval`
    done
    if [ $complete = 0 ] ; then
        echo error builds are not complete
        $ORIGIN_CONTAINER oc get builds
    fi
}

#USE_LOGGING_DEPLOYER=${USE_LOGGING_DEPLOYER:-1}

#USE_LOGGING_DEPLOYER_SCRIPT=${USE_LOGGING_DEPLOYER_SCRIPT:-1}

DISABLE_LIBVIRT=${DISABLE_LIBVIRT:-1}

if [ -z "$GITHUB_REPO" -o -z "$GITHUB_BRANCH" ] ; then
    echo Error: you must set env. GITHUB_REPO and GITHUB_BRANCH e.g.
    echo   \$ GITHUB_REPO=my_github_username GITHUB_BRANCH=my_devel_branch bash -x $0 2\>\&1 \| tee output
    exit 1
fi
#GITHUB_REPO=${GITHUB_REPO:-openshift}
#GITHUB_BRANCH=${GITHUB_BRANCH:-master}

OS_O_A_L_DIR=${OS_O_A_L_DIR:-$HOME/origin-aggregated-logging}
if [ ! -d "$OS_O_A_L_DIR" ] ; then
    OS_O_A_L_DIR=/share/origin-aggregated-logging
fi

if [ ! -d "$OS_O_A_L_DIR" ] ; then
    OS_O_A_L_DIR=`mktemp -d`
    mkdir -p $OS_O_A_L_DIR/hack/templates
    mkdir -p $OS_O_A_L_DIR/deployment
    curl https://raw.githubusercontent.com/$GITHUB_REPO/origin-aggregated-logging/$GITHUB_BRANCH/hack/templates/dev-builds.yaml > $OS_O_A_L_DIR/hack/templates/dev-builds.yaml
    curl https://raw.githubusercontent.com/$GITHUB_REPO/origin-aggregated-logging/$GITHUB_BRANCH/deployment/deployer.yaml > $OS_O_A_L_DIR/deployment/deployer.yaml
fi

if [ -f /share/origin/examples/sample-app/pullimages.sh ] ; then
    bash -x /share/origin/examples/sample-app/pullimages.sh
else
    bash <(curl https://raw.githubusercontent.com/openshift/origin/master/examples/sample-app/pullimages.sh)
fi

if [ -n "$CHECK_HOSTNAME" ] ; then
    myhost=`hostname`
    myip=`getent ahostsv4 $myhost|awk "/ STREAM $myhost/ { print \\$1 }"`
    revhost=`getent hosts $myip|awk '{print $2}'`

    if [ "$myhost" != "$revhost" ] ; then
        echo Error: hostname is $myhost but $myip resolves to $revhost
        exit 1
    fi
fi

# openshift skydns component conflicts with libvirt dnsmasq
if [ -n "$DISABLE_LIBVIRT" ] ; then
    for virnet in `sudo virsh net-list |awk '/^$/ {next}; /^---/ {pp = 1; next}; pp == 1 {print $1}'` ; do
        if [ -n "$virnet" ] ; then
            sudo virsh net-destroy $virnet
            echo stopped virtual net $virnet - use sudo virsh net-start $virnet to restart
        fi
    done
else
    masterurlhack=",MASTER_URL=https://172.30.0.1:443"
fi

if sudo grep \^\#INSECURE_REGISTRY= /etc/sysconfig/docker ; then
    sudo sed -i -e "s,^#INSECURE_REGISTRY.*\$,INSECURE_REGISTRY='--insecure registry 172.30.0.0/16'," /etc/sysconfig/docker
    sudo systemctl restart docker
fi

if type firewall-cmd > /dev/null 2>&1 ; then
    if sudo firewall-cmd --list-interfaces > /dev/null 2>&1 || test $? = 252 ; then
        echo firewall not running
    else
        if sudo firewall-cmd --zone=trusted --list-interfaces | grep docker0 ; then
            echo docker0 is in firewall trusted zone
        else
            sudo firewall-cmd --zone=trusted --add-interface=docker0
            sudo firewall-cmd --permanent --zone=trusted --add-interface=docker0
        fi
    fi
fi

OS_VOL_DIR_BASE=${OS_VOL_DIR_BASE:-/var/lib/origin}
OS_VOL_DIR=${OS_VOL_DIR:-$OS_VOL_DIR_BASE/openshift.local.volumes}

if sudo test -d $OS_VOL_DIR ; then
    echo $OS_VOL_DIR exists
else
    sudo mkdir -p $OS_VOL_DIR
fi

if sudo secon --file $OS_VOL_DIR | grep '^type: svirt_sandbox_file_t' ; then
    echo selinux already set up for $OS_VOL_DIR
else
    sudo chcon -R -t svirt_sandbox_file_t $OS_VOL_DIR
fi

#PRE_BUILD_IMAGES=1
if [ -n "$PRE_BUILD_IMAGES" ] ; then
    pushd $OS_O_A_L_DIR/hack
    bash -x ./build-images.sh
    popd

    pushd $OS_O_A_L_DIR/hack/ssl
    bash -x ./generateExampleKeys.sh
    chmod +x createSecrets.sh
    popd
fi

if [ -n "$ORIGIN_CONTAINER" ] ; then
    myid=`id -u`
    pushd $HOME
    tar cf - --exclude .git origin-aggregated-logging | ( cd /run/user/$myid ; tar xf - )
    popd
    # copying .git fails
    #cp -r $HOME/origin-aggregated-logging /run/user/$myid

    sudo docker run -d --name "origin" --privileged --pid=host --net=host -v /:/rootfs:ro \
         -v /var/run:/var/run:rw -v /sys:/sys:ro -v /var/lib/docker:/var/lib/docker:rw \
         -v $OS_VOL_DIR:$OS_VOL_DIR -v /var/log:/var/log \
         openshift/origin start

    echo "Waiting for openshift origin to start . . ."
    sleep 30
    os_o_a_l_container_dir=/run/user/$myid/origin-aggregated-logging
    $ORIGIN_CONTAINER oc status
    $ORIGIN_CONTAINER oc get all
else
    os_o_a_l_container_dir=$OS_O_A_L_DIR
    export KUBECONFIG=$OS_VOL_DIR_BASE/openshift.local.config/master/admin.kubeconfig
    export CURL_CA_BUNDLE=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt
    sudo chmod +r $OS_VOL_DIR_BASE/openshift.local.config/master/admin.kubeconfig
    cat >> $HOME/.bash_profile <<EOF
export KUBECONFIG=$OS_VOL_DIR_BASE/openshift.local.config/master/admin.kubeconfig
export CURL_CA_BUNDLE=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt
EOF
    cat >> $HOME/.bashrc <<EOF
export KUBECONFIG=$OS_VOL_DIR_BASE/openshift.local.config/master/admin.kubeconfig
export CURL_CA_BUNDLE=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt
EOF
fi

# I don't think this is necessary since later it uses the full url to create the app
#$ORIGIN_CONTAINER mkdir -p $OS_VOL_DIR_BASE/examples/sample-app
#$ORIGIN_CONTAINER wget \
#     https://raw.githubusercontent.com/openshift/origin/master/examples/sample-app/application-template-stibuild.json \
#     -O $OS_VOL_DIR_BASE/examples/sample-app/application-template-stibuild.json

$ORIGIN_CONTAINER bash -c "echo export CURL_CA_BUNDLE=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt >> /root/.bashrc"
$ORIGIN_CONTAINER bash -c "echo export CURL_CA_BUNDLE=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt >> /root/.bash_profile"
if [ -z "$ORIGIN_CONTAINER" ] ; then
    export CURL_CA_BUNDLE=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt
fi
$ORIGIN_CONTAINER oadm registry --create --credentials=$OS_VOL_DIR_BASE/openshift.local.config/master/openshift-registry.kubeconfig

echo waiting for docker registry . . .
ii=300
while [ $ii -gt 0 ] ; do
    if $ORIGIN_CONTAINER oc describe service docker-registry --config=$OS_VOL_DIR_BASE/openshift.local.config/master/admin.kubeconfig | grep '^Endpoints:.*:5000' ; then
        echo docker registry is running
        break
    fi
    sleep 10
    ii=`expr $ii - 10`
done
if [ $ii = 0 ] ; then
    echo docker registry not running after 120 seconds
    exit 1
fi

if [ -z "$THE_OLD_WAY" ] ; then
    $ORIGIN_CONTAINER oc new-project logging
    $ORIGIN_CONTAINER oc secrets new logging-deployer nothing=/dev/null
    cat <<EOF | sudo tee $OS_VOL_DIR/logging-deployer.yml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: logging-deployer
secrets:
- name: logging-deployer
EOF
    $ORIGIN_CONTAINER oc create -f $OS_VOL_DIR/logging-deployer.yml
    $ORIGIN_CONTAINER oc policy add-role-to-user edit \
         system:serviceaccount:logging:logging-deployer
    if [ -n "$USE_LOGGING_DEPLOYER" ] ; then
        imageprefix="docker.io/openshift/origin-"
    elif [ -n "$USE_LOGGING_DEPLOYER_SCRIPT" ] ; then
        pushd $os_o_a_l_container_dir/deployment
        IMAGE_PREFIX="openshift/origin-" PROJECT=logging ./run.sh
        popd
    else
        $ORIGIN_CONTAINER oc process \
             -f $os_o_a_l_container_dir/hack/templates/dev-builds.yaml \
             -v LOGGING_FORK_URL=https://github.com/$GITHUB_REPO/origin-aggregated-logging,LOGGING_FORK_BRANCH=$GITHUB_BRANCH \
            | sudo tee $OS_VOL_DIR/dev-builds.json
        $ORIGIN_CONTAINER oc create -f $OS_VOL_DIR/dev-builds.json
        sleep 60
        $ORIGIN_CONTAINER oc get builds
        sleep 60
        wait_for_builds_complete
        $ORIGIN_CONTAINER oc get is
        imageprefix=`$ORIGIN_CONTAINER oc get is | awk '$1 == "logging-deployment" {print gensub(/^([^/]*\/logging\/).*$/, "\\\1", 1, $2)}'`
    fi
    #    $ORIGIN_CONTAINER oc edit scc/privileged
    # give fluentd permission to run privileged - it needs access to /var/log/messages and
    # /var/log/containers/* on the host
    $ORIGIN_CONTAINER oc get scc/privileged -o yaml | \
        sudo tee $OS_VOL_DIR/add-privileged-logging-user.yml
    echo "- system:serviceaccount:logging:aggregated-logging-fluentd" | \
        sudo tee -a $OS_VOL_DIR/add-privileged-logging-user.yml
    $ORIGIN_CONTAINER oc replace -f $OS_VOL_DIR/add-privileged-logging-user.yml
    $ORIGIN_CONTAINER oadm policy add-cluster-role-to-user cluster-reader \
                      system:serviceaccount:logging:aggregated-logging-fluentd
    if [ ! -n "$USE_LOGGING_DEPLOYER_SCRIPT" ] ; then
        $ORIGIN_CONTAINER oc process \
                          -f $os_o_a_l_container_dir/deployment/deployer.yaml \
                          -v IMAGE_PREFIX=$imageprefix,KIBANA_HOSTNAME=kibana.example.com,ES_CLUSTER_SIZE=1,PUBLIC_MASTER_URL=https://localhost:8443${masterurlhack} \
            | sudo tee $OS_VOL_DIR/logging-deployer.json
        logging_pod=`$ORIGIN_CONTAINER oc create -f $OS_VOL_DIR/logging-deployer.json -o name`
        echo logging pod is $logging_pod
        echo Waiting for logging to start
        sleep 30
        $ORIGIN_CONTAINER oc get pods --all-namespaces
        $ORIGIN_CONTAINER oc describe $logging_pod
        $ORIGIN_CONTAINER oc logs $logging_pod
    fi
    $ORIGIN_CONTAINER oc process logging-support-template | \
        sudo tee $OS_VOL_DIR/logging-support-template.json
    $ORIGIN_CONTAINER oc create -f $OS_VOL_DIR/logging-support-template.json || echo ignore already exists errors
    $ORIGIN_CONTAINER oc get dc
    echo wait for deploymentconfig logging-fluentd in order to scale it
    sleep 30
    $ORIGIN_CONTAINER oc scale dc logging-fluentd --replicas=1
    $ORIGIN_CONTAINER oc get pods
    sleep 30
    $ORIGIN_CONTAINER oc get pods
#    $ORIGIN_CONTAINER oc scale rc/logging-fluentd-1 --replicas=1
#    sleep 30
#    $ORIGIN_CONTAINER oc get pods
else
    $ORIGIN_CONTAINER bash -c "cd $os_o_a_l_container_dir/hack/ssl ; ./createSecrets.sh"

    $ORIGIN_CONTAINER oadm policy add-cluster-role-to-user cluster-reader system:serviceaccount:default:default

    $ORIGIN_CONTAINER oc create -f $os_o_a_l_container_dir/logging.yml

    echo Waiting for logging to start
    sleep 30
fi

$ORIGIN_CONTAINER oc status
$ORIGIN_CONTAINER oc get all

$ORIGIN_CONTAINER oc login --certificate-authority=$OS_VOL_DIR_BASE/openshift.local.config/master/ca.crt -u test -p test

$ORIGIN_CONTAINER oc whoami

$ORIGIN_CONTAINER oc new-project test --display-name="OpenShift 3 Sample" --description="This is an example project to demonstrate OpenShift v3"
$ORIGIN_CONTAINER oc new-app -f https://raw.githubusercontent.com/openshift/origin/master/examples/sample-app/application-template-stibuild.json

echo waiting for build to start . . .
sleep 10
$ORIGIN_CONTAINER oc logs build/ruby-sample-build-1 || echo logs returned error - ignored

echo waiting for service to deploy . . .
$ORIGIN_CONTAINER oc describe svc frontend
ii=1200
while [ $ii -gt 0 ] ; do
    endpoint=`$ORIGIN_CONTAINER oc describe svc frontend | tr -d '\r' | awk -F'[ ,]+' '/^Endpoints:/ {print $2}'`
    if [ -n "$endpoint" ] && wget -O - http://$endpoint ; then
        echo "Success"
        break
    fi
    sleep 30
    ii=`expr $ii - 30`
done

echo test elasticsearch
oc login -u 'system:admin'
oc project logging
# we are looking for the one that looks like this:
#23cab3e2002f        openshift/origin-pod:v1.1                                                                                                  "/pod"                   3 hours ago         Up 3 hours                                   k8s_POD.e0320077_logging-kibana-1-um5jz_logging_378d8b4b-b4ab-11e5-848d-54ee75107317_86c82ee7
# poduuid=`sudo docker ps | awk '/kibana/ && $2 ~ /^openshift\/origin-pod:/ {print gensub(/^.*_([a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})_.*$/, "\\\1", 1)}'`
# esip=`dig @localhost logging-es.logging.svc.cluster.local +noall +answer | awk '/^;/ || /^$/ {next}; {print $NF}'`
# cert=/var/lib/origin/openshift.local.volumes/pods/$poduuid/volumes/kubernetes.io~secret/kibana/cert
# key=/var/lib/origin/openshift.local.volumes/pods/$poduuid/volumes/kubernetes.io~secret/kibana/key
oc get secret logging-kibana --template='{{.data.ca}}' | base64 -d > ca
ca=./ca
oc get secret logging-kibana --template='{{.data.key}}' | base64 -d > key
key=./key
oc get secret logging-kibana --template='{{.data.cert}}' | base64 -d > cert
cert=./cert
esip=localhost
espod=`oc get pods | awk '/^logging-es-/ {print $1}'`
oc port-forward $espod 9200:9200 > port-forward.log 2>&1 &
sleep 5
sudo curl -s -k --cert $cert --key $key https://$esip:9200/_cluster/health | python -mjson.tool
sudo curl -s -k --cert $cert --key $key https://$esip:9200/logging*/_search | python -mjson.tool
sudo curl -s -k --cert $cert --key $key https://$esip:9200/.search*/_search | python -mjson.tool
sudo curl -s -k --cert $cert --key $key https://$esip:9200/test*/_search | python -mjson.tool
