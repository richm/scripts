#!/bin/sh

get_interesting_stacks() {
    awk -F'[ #@]+' '
    function isinteresting() {
        if ((stack[0] == "select") && (stack[1] == "DS_Sleep")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "pthread_cond_timedwait") && (stack[1] == "PR_WaitCondVar")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "pthread_cond_timedwait") && (stack[2] == "PR_WaitCondVar")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "pthread_cond_wait") && (stack[1] == "PR_WaitCondVar")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "pthread_cond_timedwait") && (stack[1] == "pt_TimedWait")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "pt_TimedWait") && (stack[1] == "PR_WaitCondVar")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "PR_WaitCondVar") && (stack[1] == "slapi_wait_condvar")) {
            # not interesting
            return 0
        }
        if ((stack[0] == "__poll") && (stack[1] == "_pr_poll_with_poll") && (stack[2] == "slapd_daemon")) {
            # not interesting
            return 0
        }
        return 1
    }
    function printstack() {
        print "Thread", threadnum
        str=stack[0]
        for (ii = 0; ii <= 200; ++ii) {
            if (ii in stack) {
                str=str " " stack[ii]
            }
        }
        print str
    }
    function procstack() {
        if (isinteresting()) {
            printstack()
            intthreads++
            print ""
        }
        delete stack
        inthread=0
    }
    BEGIN {inthread=0;intthreads=0}
    /^Thread / {inthread=1; threadnum=$2; next}
    /^#[0-9][0-9]*  *0x.* in / {
        stack[$2] = $5
        next
    }
    /^#[0-9][0-9]*  .* at / {
        stack[$2] = $3
        next
    }
    /^[\r\n]*$/ && inthread {procstack(); inthread=0; next}
    END {procstack(); print "Found", intthreads, "interesting threads"}
    '
}
#    /^$/ && inthread {procstack(); inthread=0; next}

get_interesting_stacks
