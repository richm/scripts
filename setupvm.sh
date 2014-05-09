#!/bin/sh

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

# systemd needs these
mount -o bind /dev /mnt/sysimage/dev
mount -o bind /sys /mnt/sysimage/sys
mount -o bind /proc /mnt/sysimage/proc

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
set +x

%end

EOF2
}

CONF=${CONF:-$1}
CONF=${CONF:-vm.conf}

if [ -f $CONF ] ; then
    . $CONF
fi

VM_IMG_DIR=${VM_IMG_DIR:-/var/lib/libvirt/images}
VM_RAM=${VM_RAM:-2048} # RAM in kbytes
VM_CPUS=${VM_CPUS:-2}
# size in GB
VM_DISKSIZE=${VM_DISKSIZE:-16}
VM_NAME=${VM_NAME:-ad}
VM_DISKFILE=${VM_DISKFILE:-$VM_IMG_DIR/$VM_NAME.img}
VM_KS=${VM_KS:-$VM_NAME.ks}
VM_KS_BASENAME=`basename $VM_KS 2> /dev/null`
VM_ROOTPW=${VM_ROOTPW:-password}
if [ -z "$VM_TZ" ] ; then
    VM_TZ=`. /etc/sysconfig/clock  ; echo $ZONE`
fi
# fedora zerombr takes no arguments
VM_ZEROMBR=${VM_ZEROMBR:-"zerombr yes"}
VM_TIMEOUT=${VM_TIMEOUT:-60}

EXTRA_FILES=""

# check for required arguments
if [ -z "$VM_URL" ] ; then
    echo Error: no VM_URL specified in env or $CONF
    exit 1
fi

# for kickstart file you cannot use an nfs url, you have to split it
# into --server and --dir
case $VM_URL in
nfs*) VM_INSTALL_LOC=`echo $VM_URL|sed -e 's,^nfs://\([^/]*\)/\(.*\)$,nfs --server=\1 --dir=/\2,'` ;;
*) VM_INSTALL_LOC="url --url $VM_URL" ;;
esac

if [ -z "$VM_NAME" ] ; then
    echo Error: no VM_NAME specified in env or $CONF
    exit 1
fi

for file in $VM_POST_SCRIPT $VM_EXTRA_FILES ; do
    EXTRA_FILES="$EXTRA_FILES --initrd-inject=$file"
done

for file in $VM_EXTRA_FILES ; do
    EXTRA_FILES_BASE="$EXTRA_FILES_BASE "`basename $VM_EXTRA_FILES 2> /dev/null`
done

VM_POST_SCRIPT_BASE=`basename $VM_POST_SCRIPT 2> /dev/null`

if [ -z "$VM_MAC" ] ; then
    # try to get the mac addr from virsh
    VM_MAC=`$SUDOCMD virsh net-dumpxml default | grep "'"$VM_NAME"'"|sed "s/^.*mac='\([^']*\)'.*$/\1/"`
    if [ -z "$VM_MAC" ] ; then
        echo Error: your machine $VM_MAC has no mac address in virsh net-dumpxml default
        echo Please use virsh net-edit default to specify the mac address for $VM_MAC
        echo or set VM_MAC=mac:addr in the environment
        exit 1
    fi
fi

if [ -z "$VM_FQDN" ] ; then
    # try to get the ip addr from virsh
    VM_IP=`$SUDOCMD virsh net-dumpxml default | grep "'"$VM_NAME"'"|sed "s/^.*ip='\([^']*\)'.*$/\1/"`
    if [ -z "$VM_IP" ] ; then
        echo Error: your machine $VM_NAME has no IP address in virsh net-dumpxml default
        echo Please use virsh net-edit default to specify the IP address for $VM_NAME
        echo or set VM_FQDN=full.host.domain in the environment
        exit 1
    fi
    VM_FQDN=`getent hosts $VM_IP|awk '{print $2}'`
    echo using hostname $VM_FQDN for $VM_NAME with IP address $VM_IP
fi

tmpks=
if [ ! -f "$VM_KS" ] ; then
    VM_KS=`mktemp`
    make_kickstart > $VM_KS
    VM_KS_BASENAME=`basename $VM_KS`
    tmpks=1
else
    echo Using kickstart file $VM_KS
fi

virt-install --name $VM_NAME --ram $VM_RAM $EXTRA_FILES \
    $VM_OS_VARIANT --hvm --check-cpu --accelerate --noautoconsole \
    --connect=qemu:///system --wait=$VM_TIMEOUT --initrd-inject=$VM_KS \
    --disk path=$VM_DISKFILE,size=$VM_DISKSIZE,bus=virtio \
    --network network=default,mac="$VM_MAC" \
    -l $VM_URL -x "ks=file:/$VM_KS_BASENAME" -d

if [ -n "$tmpks" ] ; then
    rm -f $VM_KS
fi
