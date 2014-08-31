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
password: $VM_ROOTPW
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
 - [mount, -o, ro, /dev/sr0, /mnt]
 - sh -x /mnt/$VM_POST_SCRIPT_BASE > /var/log/$VM_POST_SCRIPT_BASE.log 2>&1
 - [touch, $VM_WAIT_FILE]
EOF
}

make_cdrom() {
    # just put everything on the CD
    # first need a staging area
    staging=${VM_CD_STAGE_DIR:-`mktemp -d`}
    for file in for file in $VM_POST_SCRIPT $VM_EXTRA_FILES "$@" ; do
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
    ii=$VM_TIMEOUT
    while [ $ii -gt 0 ] ; do
        if $SUDOCMD virt-cat -d $VM_NAME $VM_WAIT_FILE > /dev/null 2>&1 ; then
            return 0
        fi
        ii=`expr $ii - 1`
        sleep 60
    done
    echo Error: $VM_NAME $VM_WAIT_FILE not found after $VM_TIMEOUT minutes
    return 1
}

for file in "$@" ; do
    . $file
done

if [ -n "$VM_DEBUG" ] ; then
    set -x
fi

if $SUDOCMD virsh dominfo $VM_NAME ; then
    echo VM $VM_NAME already exists
    echo If you want to recreate it, do
    echo  $SUDOCMD virsh destroy $VM_NAME
    echo  $SUDOCMD virsh undefine $VM_NAME --remove-all-storage
    echo and re-run this script
    exit 0
fi

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

EXTRA_FILES=""

# must specify a disk image, a cdrom, or a url to install from
if [ -z "$VM_URL" -a -z "$VM_CDROM" -a -z "$VM_DISKFILE" -a -z "$VM_DISKFILE_BACKING" ] ; then
    echo Error: no install source or disk specified in env or $@
    echo Must specify VM_URL \(network install\)
    echo              VM_CDROM \(local cd iso install\)
    echo              VM_DISKFILE/VM_DISKFILE_BACKING \(create vm from existing disk image\)
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
fi

if [ -z "$VM_NAME" ] ; then
    echo Error: no VM_NAME specified in env or $@
    exit 1
fi

if [ -n "$VM_POST_SCRIPT" ] ; then
    VM_POST_SCRIPT_BASE=`basename $VM_POST_SCRIPT 2> /dev/null`
fi

VM_NETWORK_NAME=${VM_NETWORK_NAME:-default}
VM_NETWORK=${VM_NETWORK:-"network=$VM_NETWORK_NAME"}
if [ -z "$VM_NO_MAC" -a -z "$VM_MAC" ] ; then
    # try to get the mac addr from virsh
    VM_MAC=`$SUDOCMD virsh net-dumpxml $VM_NETWORK_NAME | grep "'"$VM_NAME"'"|sed "s/^.*mac='\([^']*\)'.*$/\1/"`
    if [ -z "$VM_MAC" ] ; then
        echo Error: your machine $VM_MAC has no mac address in virsh net-dumpxml $VM_NETWORK_NAME
        echo Please use virsh net-edit $VM_NETWORK_NAME to specify the mac address for $VM_MAC
        echo or set VM_MAC=mac:addr in the environment
        exit 1
    fi
fi

if [ -n "$VM_MAC" ] ; then
    VM_NETWORK="$VM_NETWORK,mac=$VM_MAC"
fi

if [ -z "$VM_FQDN" ] ; then
    # try to get the ip addr from virsh
    VM_IP=`$SUDOCMD virsh net-dumpxml $VM_NETWORK_NAME | grep "'"$VM_NAME"'"|sed "s/^.*ip='\([^']*\)'.*$/\1/"`
    if [ -z "$VM_IP" ] ; then
        echo Error: your machine $VM_NAME has no IP address in virsh net-dumpxml $VM_NETWORK_NAME
        echo Please use virsh net-edit $VM_NETWORK_NAME to specify the IP address for $VM_NAME
        echo or set VM_FQDN=full.host.domain in the environment
        exit 1
    fi
    VM_FQDN=`getent hosts $VM_IP|awk '{print $2}'`
    echo using hostname $VM_FQDN for $VM_NAME with IP address $VM_IP
fi

if $SUDOCMD test -n "$VM_DISKFILE_BACKING" -a -f "$VM_DISKFILE_BACKING" ; then
    # use the given diskfile as our backing file
    # make a new one based on the vm name
    # NOTE: We cannot create an image which is _smaller_ than the backing image
    # we have to grab the current size of the backing file, and omit the disk size
    # argument if VM_DISKSIZE is less than or equal to the backing file size
    # strip the trailing M, G, etc.
    bfsize=`$SUDOCMD qemu-img info $VM_DISKFILE_BACKING | awk '/virtual size/ {print gensub(/\.[0-9][a-zA-Z]/, "", "g", $3)}'`
    if [ $VM_DISKSIZE -gt $bfsize ] ; then
        sizearg=${VM_DISKSIZE}G
    else
        echo disk size $VM_DISKSIZE for $VM_DISKFILE is smaller than the size $bfsize of the backing file $VM_DISKFILE_BACKING
        echo the given disk size cannot be smaller than the backing file size
        echo new vm will use size $bfsize
    fi
    $SUDOCMD qemu-img create -f qcow2 -b $VM_DISKFILE_BACKING $VM_DISKFILE $sizearg
fi

if $SUDOCMD test -f "$VM_DISKFILE" ; then
    # already have a disk file, so this is not a kickstart
    # assume cloud-init
    make_cdrom
    VI_LOC="--import"
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
fi

$SUDOCMD virt-install --name $VM_NAME --ram $VM_RAM $INITRD_INJECT \
    $VM_OS_VARIANT --hvm --check-cpu --accelerate --vcpus $VM_CPUS \
    --connect=qemu:///system --noautoconsole $VM_RNG \
    --disk path=$VM_DISKFILE,size=$VM_DISKSIZE,bus=virtio \
    $VI_EXTRAS_CD --network "$VM_NETWORK" \
    $VI_LOC $VI_EXTRA_ARGS ${VM_DEBUG:+"-d"} --force

wait_for_completion $VM_NAME $VM_TIMEOUT $VM_WAIT_FILE

if [ -n "$tmpks" ] ; then
    rm -f $VM_KS
fi
