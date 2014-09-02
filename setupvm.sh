#!/bin/sh

set -o errexit

make_kickstart() {
    cat <<EOF
install
$VM_INSTALL_LOC
lang en_US.UTF-8
keyboard 'us'
timezone --utc $VM_TZ
authconfig --enableshadow --passalgo=sha512 --enablefingerprint
selinux --enforcing
rootpw $VM_ROOTPW
$VM_ZEROMBR
# The following is the partition information you requested
# Note that any partitions you deleted are not expressed
# here so unless you clear all partitions first, this is
# not guaranteed to work
clearpart --initlabel --linux --drives=vda
autopart
text
# Reboot after installation
reboot
firstboot --disable
firewall --disabled
bootloader --location=mbr --driveorder=vda --append="rhgb quiet"
ignoredisk --only-use=vda
network --bootproto=dhcp --ip=$VM_IP --netmask=255.255.255.0 --device=eth0 --hostname=$VM_FQDN
$VM_GROUP
$VM_USER
EOF

    # programatically add repos
    # these are the OS base repos
    # these are almost always mirrorlists
    set -- $VM_OS_BASE_REPO_LIST
    while [ -n "$1" ] ; do
        name="$1" ; shift # $1 is now url
        echo "repo --name=$name --mirrorlist=$1"
        shift
    done

    # these are any additional user-defined repos
    set -- $VM_REPO_LIST
    while [ -n "$1" ] ; do
        name="$1" ; shift # $1 is now url
        echo "repo --name=\"$name\" --baseurl=$1 --cost=100"
        shift
    done

    # programatically add packages
    echo ""
    echo '%packages --default --ignoremissing'
    if [ -n "$VM_PACKAGE_LIST" ] ; then
        # one package/group per line
        for pkg in $VM_PACKAGE_LIST ; do
            echo $pkg
        done
    fi
    echo '%end'

cat <<EOF2

%post --nochroot --log=/mnt/sysimage/root/post1.log

set -x

# Raise a network interface:
/sbin/ifconfig lo up

ls -al /boot
if [ -n "$VM_POST_SCRIPT_BASE" -o -n "$EXTRA_FILES_BASE" ] ; then
    initramfs=/boot/initramfs-\`uname -r\`.img
    for file in $VM_POST_SCRIPT_BASE $EXTRA_FILES_BASE ; do
        gunzip -c \$initramfs | cpio -i /\$file
        if [ -f "/\$file" ] ; then
            cp /\$file /mnt/sysimage/root
        fi
    done
fi
set +x

%end

%post --log=/root/post2.log

# kickstart does not automatically create yum repos for the extra
# repos specified by the repo keyword, so create them here
set -- $VM_REPO_LIST
while [ -n "\$1" ] ; do
    name="\$1" ; shift
    url="\$1" ; shift
    cat > /etc/yum.repos.d/\$name.repo <<EOF3
[\$name]
name=\$name
baseurl=\$url
enabled=1
gpgcheck=0
EOF3
done

# kickstart apparently does not always install packages specifed
# in the packages section - so install them here
yum -y install $VM_PACKAGE_LIST
set -x
if [ -n "$VM_USER_PW" ] ; then
    echo "$VM_USER_PW" | passwd --stdin "$VM_USER_ID"
fi
if [ -n "$VM_POST_SCRIPT_BASE" -a -x "/root/$VM_POST_SCRIPT_BASE" ] ; then
    sh -x /root/$VM_POST_SCRIPT_BASE
fi

touch $VM_WAIT_FILE

set +x

%end

EOF2
}

make_cloud_init_metadata() {
    cat <<EOF
instance-id: $VM_NAME
hostname: $VM_FQDN
local-hostname: $VM_FQDN
fqdn: $VM_FQDN
EOF
}

make_cloud_init_userdata() {
    cat <<EOF
#cloud-config
cloud_config_modules:
 - mounts
 - locale
 - set-passwords
 - timezone
 - puppet
 - chef
 - salt-minion
 - mcollective
 - disable-ec2-metadata
 - runcmd
 - yum_add_repo
 - package_update_upgrade_install
EOF
    # If a user and password were specified,
    # set them as the default user.
    if [ -n "$VM_USER_ID" -a -n "$VM_USER_PW" ] ; then
        cat <<EOF
system_info:
  default_user:
    name: $VM_USER_ID
    plain_text_passwd: $VM_USER_PW
    lock_passwd: False
    sudo: ALL=(ALL) NOPASSWD:ALL
EOF
    fi
    # If a user wasn't specified, just modify
    # the password for the normal default user.
    if [ ! -n "$VM_USER_ID" ]; then
        echo "password: $VM_ROOTPW"
    fi
    cat <<EOF
chpasswd: {expire: False}
ssh_pwauth: True
EOF
    # Add base OS yum repos
    if [ -n "$VM_OS_BASE_REPO_LIST" ] ; then
        echo "yum_repos:"
        set -- $VM_OS_BASE_REPO_LIST
        while [ -n "$1" ] ; do
            name="$1" ; shift # $1 is now url
            cat <<EOF
    $name:
        name: $name
        baseurl: $1
        enabled: true
        gpgcheck: 0
EOF
            shift
        done
    fi
    # Add additional user-defined repos
    if [ -n "$VM_REPO_LIST" ] ; then
        echo "yum_repos:"
        set -- $VM_REPO_LIST
        while [ -n "$1" ] ; do
            name="$1" ; shift # $1 is now url
            cat <<EOF
    $name:
        name: $name
        baseurl: $1
        enabled: true
        gpgcheck: 0
        cost: 100
EOF
            shift
        done
    fi
    cat <<EOF
package_upgrade: true
packages:
EOF
    for pkg in $VM_PACKAGE_LIST ; do
        echo " - $pkg"
    done
    # the hostname options in the metadata are just not working - they do not
    # set the fqdn correctly - so do it here in a runcmd
    cat <<EOF
runcmd:
 - [hostname, $VM_FQDN]
EOF
    for pkg in $VM_GROUP_PACKAGE ; do
        echo " - yum -y groupinstall \"$VM_GROUP_PACKAGE\""
    done
cat <<EOF
 - [mount, -o, ro, /dev/sr0, /mnt]
EOF
    if [ -n "$VM_POST_SCRIPT_BASE" ] ; then
        cat <<EOF
 - sh -x /mnt/$VM_POST_SCRIPT_BASE > /var/log/$VM_POST_SCRIPT_BASE.log 2>&1
EOF
    fi
cat <<EOF
 - [touch, $VM_WAIT_FILE]
EOF
}

make_cdrom() {
    # just put everything on the CD
    # first need a staging area
    staging=${VM_CD_STAGE_DIR:-`mktemp -d`}
    for file in $VM_POST_SCRIPT $VM_EXTRA_FILES "$@" ; do
        if [ ! -f "$file" ] ; then continue ; fi
        err=
        outfile=$staging/`basename $file .in`
        case $file in
            *.in) do_subst $file > $outfile || err=$? ;;
            *) $SUDOCMD cp -p $file $outfile || err=$? ;;
        esac
        if [ -n "$err" ] ; then
            echo error $err copying $file to $outfile  ; exit 1
        fi
    done
    make_cloud_init_metadata > $staging/meta-data
    make_cloud_init_userdata > $staging/user-data
    EXTRAS_CD_ISO=${EXTRAS_CD_ISO:-$VM_IMG_DIR/$VM_NAME-cidata.iso}
    $SUDOCMD rm -f $EXTRAS_CD_ISO
    $SUDOCMD genisoimage -joliet -rock -volid cidata -o $EXTRAS_CD_ISO $staging/* || { echo Error $? from genisoimage $EXTRAS_CD_ISO $staging/* ; exit 1 ; }
    if [ "$VM_DEBUG" = "2" ] ; then
        echo examine staging dir $staging
    else
        rm -rf $staging
    fi
    VI_EXTRAS_CD="--disk path=$EXTRAS_CD_ISO,device=cdrom"
}

wait_for_completion() {
    # $VM_NAME $VM_TIMEOUT $VM_WAIT_FILE
    # wait up to VM_TIMEOUT minutes for VM_NAME to be
    # done with installation - this method uses
    # virt-ls to look for a file in the vm - when
    # the file is present, installation/setup is
    # complete - keep polling every minute until
    # the file is found or we hit the timeout
    ii=$2
    while [ $ii -gt 0 ] ; do
        if $SUDOCMD virt-cat -d $1 $3 > /dev/null 2>&1 ; then
            return 0
        fi
        ii=`expr $ii - 1`
        sleep 60
    done
    echo Error: $1 $3 not found after $2 minutes
    return 1
}

gen_virt_mac() {
    echo 54:52:00`hexdump -n3 -e '/1 ":%02x"' /dev/random`
}

has_ipaddr() {
    # $1 is network name
    # $2 is ip addr to look for
    # $3 is dns or ip/dhcp
    ip=`$SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/$3/host[@ip=\"$2\"]/@ip)" -`
    test -n "$ip"
}

has_hostname() {
    # $1 is network name
    # $2 is hostname to look for
    # $3 is dns or ip/dhcp or etchosts
    if [ "$3" = "dns" ] ; then
        name=`$SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/dns/host[hostname=\"$2\"]/hostname)" -`
    elif [ "$3" = "ip/dhcp" ] ; then
        name=`$SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/ip/dhcp/host[@name=\"$2\"]/@name)" -`
    else
        name=`$SUDOCMD grep -e "[ 	]$2[ 	]" -e "[ 	]$2$" /etc/hosts`
    fi
    test -n "$name"
}

get_next_ip() {
    echo $1 | awk -F. '{$4 += 1;OFS=".";print}'
}

get_first_ip() {
    $SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/ip/@address)" - 2> /dev/null
}

get_available_ip() {
    nextip=`get_first_ip $1`
    while [ 1 ] ; do
        nextip=`get_next_ip $nextip`
        if has_ipaddr $1 $nextip ip/dhcp ; then
            continue
        fi
        break
    done
    echo $nextip
}

get_mac_for_domname() {
    # this sees if a dhcp mac address has been configured already for the domain
    # in the network configuration i.e. if the network has been set up ahead of time
    # it does not look at the domain configuration because we don't have domain
    # configuration yet
    $SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/ip/dhcp/host[@name=\"$2\"]/@mac)" -
}

get_ip_for_domname() {
    # this sees if a ip address has been configured already for the domain
    # in the network configuration i.e. if the network has been set up ahead of time
    # it does not look at the domain configuration because we don't have domain
    # configuration yet
    $SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/ip/dhcp/host[@name=\"$2\"]/@ip)" -
}

get_domain_name() {
    $SUDOCMD virsh net-dumpxml $1 | xmllint --xpath "string(/network/domain/@name)" -
}

set_domain_name() {
#    domname=`get_domain_name`
#    if [ "$domname" != "$2" ] ; then
#        $SUDOCMD virsh net-update $1 add domain "<domain name='$2'/>" --live --config
#    fi
     echo $1
}

# add host to virt network dns, dhcp, and /etc/hosts on host machine
add_host() {
    # this is so we can auto-config network on vm using dhcp
    if ! has_hostname "$1" "$5" ip/dhcp ; then
        $SUDOCMD virsh net-update "$1" add ip-dhcp-host "<host mac='$2' name='$5' ip='$3'/>" --live --config
    fi
    # this is for dns lookups on vm
    if ! has_hostname "$1" "$5" dns ; then
        $SUDOCMD virsh net-update "$1" add dns-host "<host ip='$3'><hostname>$4</hostname><hostname>$5</hostname></host>" --live --config
    fi
    # this is for hostname resolution on host machine
    if ! has_hostname "$1" "$5" etchosts ; then
        echo "$3	$4 $5" | $SUDOCMD tee -a /etc/hosts
    fi
}

remove_vm() {
    while [ -n "$1" ] ; do
        $SUDOCMD virsh destroy $1 || echo "Error stopping vm $1"
        $SUDOCMD virsh undefine $1 --remove-all-storage || echo "Error removing vm $1"
        shift
    done
}

remove_virt_network() {
    while [ -n "$1" ] ; do
        $SUDOCMD virsh net-destroy $1 || echo "Error stopping virtnet $1"
        $SUDOCMD virsh net-undefine $1 || echo "Error removing virtnet $1"
        shift
    done
}

check_for_existence() {
    if $SUDOCMD virsh dominfo $1 ; then
        echo VM $1 already exists
        echo If you want to recreate it, do
        echo  $SUDOCMD virsh destroy $1
        echo  $SUDOCMD virsh undefine $1 --remove-all-storage
        echo and re-run this script
        exit 0
    fi
}

make_disk_image() {
    # use the given diskfile as our backing file
    # make a new one based on the vm name
    # NOTE: We cannot create an image which is _smaller_ than the backing image
    # we have to grab the current size of the backing file, and omit the disk size
    # argument if VM_DISKSIZE is less than or equal to the backing file size
    # strip the trailing M, G, etc.
    bfsize=`$SUDOCMD qemu-img info $2 | awk -F'[ .]+' '/virtual size/ {print gensub(/[a-zA-Z]/, "", "g", $3)}'`
    if [ $3 -gt $bfsize ] ; then
        sizearg=${3}G
    else
        echo disk size $3 for $1 is smaller than the size $bfsize of the backing file $2
        echo the given disk size cannot be smaller than the backing file size
        echo new vm will use size $bfsize
    fi
    $SUDOCMD qemu-img create -f qcow2 -b $2 $1 $sizearg
}

get_config() {
    for file in "$@" ; do
        . $file
    done
    VM_IMG_DIR=${VM_IMG_DIR:-/var/lib/libvirt/images}
    VM_RAM=${VM_RAM:-2048} # RAM in kbytes
    VM_CPUS=${VM_CPUS:-2}
    # size in GB
    VM_DISKSIZE=${VM_DISKSIZE:-16}
    VM_NAME=${VM_NAME:-ad}
    VM_DISKFILE=${VM_DISKFILE:-$VM_IMG_DIR/$VM_NAME.qcow2}
    VM_KS=${VM_KS:-$VM_NAME.ks}
    VM_KS_BASENAME=`basename $VM_KS 2> /dev/null`
    VM_ROOTPW=${VM_ROOTPW:-password}
    VM_RNG=${VM_RNG:-"--rng /dev/random"}
    if [ -z "$VM_TZ" ] ; then
        if [ -f /etc/sysconfig/clock ] ; then
            VM_TZ=`. /etc/sysconfig/clock  ; echo $ZONE`
        else
            VM_TZ=`timedatectl status | awk '/Timezone:/ {print $2}'`
        fi
    fi
    # fedora zerombr takes no arguments
    VM_ZEROMBR=${VM_ZEROMBR:-"zerombr yes"}
    VM_TIMEOUT=${VM_TIMEOUT:-60}
    VM_WAIT_FILE=${VM_WAIT_FILE:-/root/installcomplete}
    if [ -n "$VM_POST_SCRIPT" ] ; then
        VM_POST_SCRIPT_BASE=`basename $VM_POST_SCRIPT 2> /dev/null`
    fi

    VM_NETWORK_NAME=${VM_NETWORK_NAME:-default}
    VM_NETWORK=${VM_NETWORK:-"network=$VM_NETWORK_NAME"}
    VM_DOMAIN=${VM_DOMAIN:-`get_domain_name "$VM_NETWORK_NAME"`}
    VM_DOMAIN=${VM_DOMAIN:-"test"}
    VM_FQDN=${VM_FQDN:-$VM_NAME.$VM_DOMAIN}
    VM_IP=${VM_IP:-`get_ip_for_domname "$VM_NETWORK_NAME" "$VM_NAME"`}
    VM_IP=${VM_IP:-`get_available_ip $VM_NETWORK_NAME`}
}

create_vm() {
(
    get_config "$@"
    check_for_existence $VM_NAME
    # must specify a disk image, a cdrom, or a url to install from
    if [ -z "$VM_PXE" -a -z "$VM_URL" -a -z "$VM_CDROM" -a -z "$VM_DISKFILE" -a -z "$VM_DISKFILE_BACKING" ] ; then
        echo Error: no install source or disk specified in env or $@
        echo Must specify VM_URL \(network install\)
        echo              VM_CDROM \(local cd iso install\)
        echo              VM_DISKFILE/VM_DISKFILE_BACKING \(create vm from existing disk image\)
        echo              VM_PXE \(boot vm from PXE\)
        exit 1
    fi

    if [ -n "$VM_URL" ] ; then
        # for kickstart file you cannot use an nfs url, you have to split it
        # into --server and --dir
        case $VM_URL in
            nfs*) VM_INSTALL_LOC=`echo $VM_URL|sed -e 's,^nfs://\([^/]*\)/\(.*\)$,nfs --server=\1 --dir=/\2,'` ;;
            *) VM_INSTALL_LOC="url --url $VM_URL" ;;
        esac
        VI_LOC="-l $VM_URL"
    elif [ -n "$VM_CDROM" ] ; then
        VI_LOC="--cdrom $VM_CDROM"
    elif [ -n "$VM_DISKFILE" -o -n "$VM_DISKFILE_BACKING" ] ; then
        VI_LOC="--import"
    elif [ -n "$VM_PXE" ] ; then
        VI_LOC="--pxe"
    fi

    if [ -z "$VM_NAME" ] ; then
        echo Error: no VM_NAME specified in env or $@
        exit 1
    fi

    if [ -z "$VM_NO_MAC" -a -z "$VM_MAC" ] ; then
        # try to get the mac addr from virsh
        VM_MAC=`get_mac_for_domname "$VM_NETWORK_NAME" "$VM_NAME"`
        if [ -z "$VM_MAC" ] ; then
            VM_MAC=`gen_virt_mac`
        fi
    fi

    if [ -n "$VM_MAC" ] ; then
        case "$VM_NETWORK" in
            *mac=$VM_MAC*) echo mac=$VM_MAC already in $VM_NETWORK ;;
            *) VM_NETWORK="$VM_NETWORK,mac=$VM_MAC" ;;
        esac
    fi

    if [ -z "$VM_NO_MAC" ] ; then
        set_domain_name "$VM_DOMAIN"
        add_host "$VM_NETWORK_NAME" "$VM_MAC" "$VM_IP" "$VM_FQDN" "$VM_NAME"
    fi

    if $SUDOCMD test -n "$VM_DISKFILE_BACKING" -a -f "$VM_DISKFILE_BACKING" ; then
        make_disk_image "$VM_DISKFILE" "$VM_DISKFILE_BACKING" "$VM_DISKSIZE"
    fi

    if $SUDOCMD test -f "$VM_DISKFILE" ; then
        # already have a disk file, so this is not a kickstart
        # assume cloud-init
        make_cdrom
        VI_LOC="--import"
        DISKARG="--disk path=$VM_DISKFILE,size=$VM_DISKSIZE,bus=virtio"
    elif [ -n "$VM_PXE" ] ; then
        DISKARG="--disk size=$VM_DISKSIZE"
    else # make a kickstart
        tmpks=
        if [ ! -f "$VM_KS" ] ; then
            VM_KS=`mktemp`
            make_kickstart > $VM_KS
            VM_KS_BASENAME=`basename $VM_KS`
            tmpks=1
        else
            echo Using kickstart file $VM_KS
        fi
        INITRD_INJECT="--initrd-inject=$VM_KS"
        for file in $VM_POST_SCRIPT $VM_EXTRA_FILES ; do
            INITRD_INJECT="$INITRD_INJECT --initrd-inject=$file"
        done

        for file in $VM_EXTRA_FILES ; do
            EXTRA_FILES_BASE="$EXTRA_FILES_BASE "`basename $file 2> /dev/null`
        done
        VI_EXTRA_ARGS="-x ks=file:/$VM_KS_BASENAME"
        DISKARG="--disk path=$VM_DISKFILE,size=$VM_DISKSIZE,bus=virtio"
    fi

    $SUDOCMD virt-install --name $VM_NAME --ram $VM_RAM $INITRD_INJECT \
        $VM_OS_VARIANT --hvm --check-cpu --accelerate --vcpus $VM_CPUS \
        --connect=qemu:///system --noautoconsole $VM_RNG \
        $DISKARG \
        $VI_EXTRAS_CD --network $VM_NETWORK \
        $VI_LOC $VI_EXTRA_ARGS ${VM_DEBUG:+"-d"} --force

    wait_for_completion $VM_NAME $VM_TIMEOUT $VM_WAIT_FILE

    if [ -n "$tmpks" ] ; then
        rm -f $VM_KS
    fi
)
}

# MAIN

if [ -n "$VM_DEBUG" ] ; then
    set -x
fi

case "$0" in
    *setupvm.sh) create_vm "$@" ;;
    *) : ;; # sourced - do nothing
esac
