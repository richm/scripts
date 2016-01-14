#!/bin/sh

SUDOCMD=${SUDOCMD:-sudo}

if [ -z "$1" ] ; then
    echo Error: $0 VM-NAME
    echo Here is a list of available VMs:
    $SUDOCMD virsh list --all
    exit 1
fi

for vm in `$SUDOCMD virsh list --all --name` ; do
    if [ "$vm" = "$1" ] ; then
        found=1
        state=`$SUDOCMD virsh domstats $vm --state | awk -F'[ =]' '/state.state=/ {print $4}'`
        if [ ! "$state" = 1 ] ; then
            $SUDOCMD virsh start $vm
        fi
        break
    fi
done

if [ -z "$found" ] ; then
    echo Error: vm $1 not found
    echo Here is a list of available VMs:
    $SUDOCMD virsh list --all
    exit 1
fi

remote-viewer `sudo virsh domdisplay "$1"`
