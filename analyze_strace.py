import sys
import re
import datetime
import pprint
from argparse import ArgumentParser, REMAINDER

year = 2013
month = 4
day = 1

parser = ArgumentParser()
parser.add_argument('-s', help='start time (strace format %H:%M:%S.%usec)')
parser.add_argument('-e', help='end time (strace format %H:%M:%S.%usec)')
parser.add_argument('files', nargs='+', help='strace output files - -o file -f -T -tt')
args = parser.parse_args()

start = None
end = None
if args.s:
    start = datetime.datetime.strptime(args.s, '%H:%M:%S.%f').replace(year=year).replace(month=month).replace(day=day)
if args.e:
    end = datetime.datetime.strptime(args.e, '%H:%M:%S.%f').replace(year=year).replace(month=month).replace(day=day)

usepid = True
usecapt = True

regex_num = r'[0-9]+'
regex_ts = r'(%s):(%s):(%s).(%s)' % (regex_num, regex_num, regex_num, regex_num)
regex_func = r'[a-zA-Z_][a-zA-Z0-9_]*'
regex_time = r'(%s).(%s)' % (regex_num, regex_num)
regex_syscall_comp = r'^'
regex_syscall_beg = r'^'
regex_syscall_end = r'^'
regex_op_comp = r'^'
regex_op_end = r'^'
fields_beg = ()
if usepid:
    regex_syscall_comp = regex_syscall_comp + r'(%s)\s+' % regex_num
    regex_syscall_beg = regex_syscall_beg + r'(%s)\s+' % regex_num
    regex_syscall_end = regex_syscall_end + r'(%s)\s+' % regex_num
    fields_beg = (('pid', str),)
    regex_op_comp = regex_syscall_comp
    regex_op_end = regex_syscall_end
fields_beg = fields_beg + (('hr', int), ('mn', int), ('tssec', int), ('tsmsec', int), ('func', str))
fields = fields_beg
regex_syscall_comp = regex_syscall_comp + r'%s\s(%s)\(.*' % (regex_ts, regex_func)
regex_syscall_beg = regex_syscall_beg + r'%s\s(%s)\(.*unfinished.*$' % (regex_ts, regex_func)
regex_syscall_end = regex_syscall_end + r'%s\s<... (%s) resumed>.*' % (regex_ts, regex_func)
regex_op_comp = regex_op_comp + r'%s\ssetsockopt\(%s, SOL_TCP, TCP_CORK, \[0\], 4\) = 0' % (regex_ts, regex_num)
regex_op_end = regex_op_end + r'%s\s<... setsockopt resumed>.*= 0' % regex_ts
if usecapt:
    regex_syscall_comp = regex_syscall_comp + r'<%s>' % regex_time
    regex_syscall_end = regex_syscall_end + r'<%s>' % regex_time
    regex_op_comp = regex_op_comp + r' <%s>' % regex_time
    regex_op_end = regex_op_end + r' <%s>' % regex_time
    fields = fields + (('sec', int), ('msec', int))
regex_syscall_comp = regex_syscall_comp + r'$'
regex_syscall_end = regex_syscall_end + r'$'
regex_op_comp = regex_op_comp + r'$'
regex_op_end = regex_op_end + r'$'
fields_end = fields

re_s_c = re.compile(regex_syscall_comp)
re_s_b = re.compile(regex_syscall_beg)
re_s_e = re.compile(regex_syscall_end)
re_op_c = re.compile(regex_op_comp)
re_op_e = re.compile(regex_op_end)

thresholds = [500000, 100000, 50000, 10000, 5000, 1000, 0]
threshcounts = {}

def update_thresh(tval):
    if tval.seconds > 0:
        threshcounts[500000] = threshcounts.get(500000, 0) + 1
        return
    for thr in thresholds:
        if tval.microseconds > thr:
            threshcounts[thr] = threshcounts.get(thr, 0) + 1
            return

funcs = {}

recs = []
ops = []
op = {}
stats = {'funcs': {}}
for fn in args.files:
    f = file(fn)
    prevsec = -1
    prevmsec = -1
    for line in f:
        rec = {}
        match = re_s_c.match(line) or re_s_e.match(line) or re_s_b.match(line)
        if not match:
            print "no match for line", line
            continue
        if match.re == re_s_c:
            usefields = fields
        elif match.re == re_s_e:
            usefields = fields_end
        else:
            continue # ignoring begin for now
        for (field, conv), val in zip(usefields, match.groups()):
            rec[field] = conv(val)
        ts = datetime.datetime(year, month, day, hour=rec['hr'], minute=rec['mn'], second=rec['tssec'], microsecond=rec['tsmsec'])
        if start and ts < start: continue
        if end and ts > end: break
        rec['ts'] = ts
        if usecapt:
            rec['ft'] = datetime.timedelta(seconds=rec['sec'], microseconds=rec['msec'])
        else:
            if prevsec == -1 and prevmsec == -1:
                prevsec = rec['tssec']
                prevmsec = rec['tsmsec']
                continue
            elapsec = rec['tssec'] - prevsec
            elapmsec = rec['tsmsec'] - prevmsec
            # calculate ft from the elapsed time since the last operation
            rec['ft'] = datetime.timedelta(seconds=elapsec, microseconds=elapmsec)
            prevsec = rec['tssec']
            prevmsec = rec['tsmsec']
        ft = rec['ft']
        func = rec['func']
        # add this particular syscall time
        funcstat = stats['funcs'].setdefault(func, {})
        funcstat['num'] = funcstat.get('num', 0) + 1
        num = funcstat['num']
        if ft < funcstat.get('min', datetime.timedelta.max):
            funcstat['min'] = ft
            funcstat['mints'] = rec['ts']
        if ft > funcstat.get('max', datetime.timedelta.min):
            funcstat['max'] = ft
            funcstat['maxts'] = rec['ts']
        fft = ((ft.seconds * 1000000) + ft.microseconds) / 1000000.0
        funcstat['ftavg'] = (float(num) * funcstat.get('ftavg', 0.0) + fft) / float(num+1.0)
        stats['funcs'][func] = funcstat
        recs.append(rec)
        if op and 'begin' in op and 'pid' in op and op['pid'] != rec['pid']:
            continue
        # add total operation syscall time
        op['ft'] = op.get('ft', datetime.timedelta(0)) + ft
        if re_op_c.match(line) or re_op_e.match(line):
            if 'begin' in op:
                op['end'] = rec['ts']
                # calculate total op time
                dur = op['end'] - op['begin']
                op['dur'] = dur
                if dur < stats.get('opmin', datetime.timedelta.max):
                    stats['opmin'] = dur
                    stats['opminop'] = op
                if dur > stats.get('opmax', datetime.timedelta.min):
                    stats['opmax'] = dur
                    stats['opmaxop'] = op
                if op['ft'] < stats.get('ftmin', datetime.timedelta.max):
                    stats['ftmin'] = op['ft']
                    stats['ftminop'] = op
                if op['ft'] > stats.get('ftmax', datetime.timedelta.min):
                    stats['ftmax'] = op['ft']
                    stats['ftmaxop'] = op
                update_thresh(dur)
                if dur.microseconds > 100000:
                    print "long op:", dur.microseconds, op['begin'].strftime("%X.%f"), op['end'].strftime("%X.%f")
                opnum = len(ops)
                fdur = ((dur.seconds * 1000000) + dur.microseconds) / 1000000.0
                stats['opavg'] = (float(opnum) * stats.get('opavg', 0.0) + fdur) / float(opnum+1.0)
                fft = ((op['ft'].seconds * 1000000) + op['ft'].microseconds) / 1000000.0
                stats['ftavg'] = (float(opnum) * stats.get('ftavg', 0.0) + fft) / float(opnum+1.0)
                ops.append(op)
            op = {'begin': rec['ts'], 'pid': rec['pid']}
    f.close()

def optime(op, field):
    return "%d.%6.6d start %s end %s" % (op[field].seconds, op[field].microseconds,
                                         op['begin'].strftime("%X.%f"), op['end'].strftime("%X.%f"))

print "Found", len(ops), "operations"
print "longest duration:     ", optime(stats['opmaxop'], 'dur')
print "shortest duration:    ", optime(stats['opminop'], 'dur')
print "longest syscall op:   ", optime(stats['ftmaxop'], 'ft')
print "shortest syscall op:  ", optime(stats['ftminop'], 'ft')
print "average duration:     ", "%6.6f" % stats['opavg']
print "average syscall time: ", "%6.6f" % stats['ftavg']
print "Number of operations with duration longer than"
for thr in thresholds:
    if thr in threshcounts:
        print thr, "usec:", threshcounts[thr]

avgsum = 0.0
ftmin = datetime.timedelta.max
ftmax = datetime.timedelta.min
sortedfuncs = sorted(stats['funcs'].iterkeys(), key=lambda x: stats['funcs'][x]['ftavg'], reverse=True)
for func in sortedfuncs:
    funcstats = stats['funcs'][func]
    print "Stats for syscall", func
    print "min time: %d.%6.6d at %s" % (funcstats['min'].seconds, funcstats['min'].microseconds, funcstats['mints'].strftime("%X.%f"))
    print "max time: %d.%6.6d at %s" % (funcstats['max'].seconds, funcstats['max'].microseconds, funcstats['maxts'].strftime("%X.%f"))
    print "avg time: %6.6f " % funcstats['ftavg']
    avgsum = avgsum + funcstats['ftavg']
    if funcstats['min'] < ftmin:
        ftmin = funcstats['min']
    if funcstats['max'] > ftmax:
        ftmax = funcstats['max']
print "Stats for other syscalls"
print "min time: %d.%6.6d" % (ftmin.seconds, ftmin.microseconds)
print "max time: %d.%6.6d" % (ftmax.seconds, ftmax.microseconds)
print "avg     : %6.6f" % (avgsum/float(len(stats['funcs'])))
