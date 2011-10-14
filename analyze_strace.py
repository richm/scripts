import sys
import re
import datetime
import pprint

regex_num = r'[0-9]+'
regex_ts = r'(%s):(%s):(%s).(%s)' % (regex_num, regex_num, regex_num, regex_num)
regex_func = r'[a-zA-Z][a-zA-Z0-9_]*'
regex_time = r'(%s).(%s)' % (regex_num, regex_num)
regex_syscall_comp = r'^(%s)\s+%s\s(%s)\(.*<%s>$' % (regex_num, regex_ts, regex_func, regex_time)
regex_syscall_beg = r'^(%s)\s+%s\s(%s)\(.*unfinished.*$' % (regex_num, regex_ts, regex_func)
regex_syscall_end = r'^(%s)\s+%s\s<... (%s) resumed>.*<%s>$' % (regex_num, regex_ts, regex_func, regex_time)

re_s_c = re.compile(regex_syscall_comp)
re_s_b = re.compile(regex_syscall_beg)
re_s_e = re.compile(regex_syscall_end)

funcs = {}

fields_beg = (('pid', str), ('hr', int), ('mn', int), ('tssec', int), ('tsmsec', int), ('func', str))
fields = fields_beg + (('sec', int), ('msec', int))
fields_end = fields

year = 2011
month = 7
day = 13

recs = []
ops = []
f = file(sys.argv[1])
op = {}
stats = {'funcs': {}}
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
    rec['ts'] = datetime.datetime(year, month, day, hour=rec['hr'], minute=rec['mn'], second=rec['tssec'], microsecond=rec['tsmsec'])
    rec['ft'] = datetime.timedelta(seconds=rec['sec'], microseconds=rec['msec'])
    ft = rec['ft']
    # add total operation syscall time
    op['ft'] = op.get('ft', datetime.timedelta(0)) + ft
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
    if func == 'sendto': # begin new operation
        if 'begin' in op:
            op['end'] = recs[-2]['ts']
            # calculate total op time
            op['dur'] = op['end'] - op['begin']
            if op['dur'] < stats.get('opmin', datetime.timedelta.max):
                stats['opmin'] = op['dur']
                stats['opminop'] = op
            if op['dur'] > stats.get('opmax', datetime.timedelta.min):
                stats['opmax'] = op['dur']
                stats['opmaxop'] = op
            if op['ft'] < stats.get('ftmin', datetime.timedelta.max):
                stats['ftmin'] = op['ft']
                stats['ftminop'] = op
            if op['ft'] > stats.get('ftmax', datetime.timedelta.min):
                stats['ftmax'] = op['ft']
                stats['ftmaxop'] = op
            opnum = len(ops)
            fdur = ((op['dur'].seconds * 1000000) + op['dur'].microseconds) / 1000000.0
            stats['opavg'] = (float(opnum) * stats.get('opavg', 0.0) + fdur) / float(opnum+1.0)
            fft = ((op['ft'].seconds * 1000000) + op['ft'].microseconds) / 1000000.0
            stats['ftavg'] = (float(opnum) * stats.get('ftavg', 0.0) + fft) / float(opnum+1.0)
            ops.append(op)
        op = {'begin': rec['ts']}
f.close()

def optime(op, field):
    return "%d.%6.6d at %s" % (op[field].seconds, op[field].microseconds, op['end'].strftime("%X.%f"))

print "Found", len(ops), "operations"
print "longest duration:     ", optime(stats['opmaxop'], 'dur')
print "shortest duration:    ", optime(stats['opminop'], 'dur')
print "longest syscall op:   ", optime(stats['ftmaxop'], 'ft')
print "shortest syscall op:  ", optime(stats['ftminop'], 'ft')
print "average duration:     ", "%6.6f" % stats['opavg']
print "average syscall time: ", "%6.6f" % stats['ftavg']

avgsum = 0.0
ftmin = datetime.timedelta.max
ftmax = datetime.timedelta.min
for func, funcstats in stats['funcs'].iteritems():
    if func == 'fdatasync':
        print "Stats for syscall", func
        print "min time: %d.%6.6d at %s" % (funcstats['min'].seconds, funcstats['min'].microseconds, funcstats['mints'].strftime("%X.%f"))
        print "max time: %d.%6.6d at %s" % (funcstats['max'].seconds, funcstats['max'].microseconds, funcstats['maxts'].strftime("%X.%f"))
        print "avg time: %6.6f " % funcstats['ftavg']
    else:
        avgsum = avgsum + funcstats['ftavg']
        if funcstats['min'] < ftmin:
            ftmin = funcstats['min']
        if funcstats['max'] < ftmax:
            ftmax = funcstats['max']
print "Stats for other syscalls"
print "min time: %d.%6.6d" % (ftmin.seconds, ftmin.microseconds)
print "max time: %d.%6.6d" % (ftmax.seconds, ftmax.microseconds)
print "avg sum:  %6.6f" % avgsum
