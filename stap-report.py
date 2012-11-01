import sys
import re
import copy
from operator import  attrgetter

np = '[0-9]+' # number pattern
hp = '0x[a-zA-Z0-9]+' # hex pattern
aggbeginre = re.compile(r'^<<<<<<< aggregate stats$')
aggendre = re.compile(r'^>>>>>>>> aggregate stats$')
beginre = re.compile(r'^=======================================$')
stackre = re.compile(r'^stack contended (%s) times, (%s) avg usec, (%s) max usec, (%s) total usec, at$ ' % (np, np, np, np))
mutexre = re.compile(r'^mutex (%s) \((.+)\) contended (%s) times, (%s) avg usec, (%s) max usec, (%s) total usec, (?:init|popup) at$ ' % (hp, np, np, np, np))
lastcontre = re.compile(r'^mutex was last contended at$')

initre = re.compile(r'^init (%s) at$' % hp)
contre = re.compile(r'^contention (%s) elapsed (%s) at$' % (hp, np))
endre = re.compile(r'^======== END$')

# key is the mutex address e.g. 0xdeadbeef
# value is a stack trace of mutex init
addr2stack = {}
# key is a stack trace
# value is the mutexstack object for this stack
stack2msobj = {}
unique_stacks = {}

# this uniquely identifies a location where a mutex is created/initialized
# it contains statistics and a list of contentions
class MutexStack:
    def __init__(self, stack=None):
        self.mutexes = {} # set of mutex addresses
        self.conts = {} # set of contention stacks
        self.count = 0
        self.total = 0
        self.max = 0
        self.stack = stack
        self.conts_ary = None
    def addmutex(self, mutex):
        if not mutex.addr in self.mutexes:
            self.mutexes[mutex.addr] = mutex
    def addcont(self, cont):
        self.count += 1
        self.total += cont.elapsed
        if cont.elapsed > self.max: self.max = cont.elapsed
        oldcont = self.conts.get(cont.stack, None)
        if oldcont:
            oldcont.count += 1
            oldcont.total += cont.elapsed
            if cont.elapsed > oldcont.max: oldcont.max = cont.elapsed
        else:
            self.conts[cont.stack] = cont
        # if we have not see an init for this mutex, create a "dummy" mutex as a
        # placeholder
        mutex = self.mutexes.setdefault(cont.addr, Mutex(cont.addr, cont.stack))
        mutex.addcont(copy.deepcopy(cont))
    def addobj(self, curobj):
        if isinstance(curobj, Contention):
            self.addcont(curobj)
        elif isinstance(curobj, Mutex):
            self.addmutex(curobj)
        else:
            raise Exception("unknown object type " + str(curobj))
    def calcstats(self):
        if self.conts_ary: return
        self.conts_ary = self.conts.values()
        self.conts_by_count = sorted(self.conts_ary, key=attrgetter('count'), reverse=True)
        self.conts_by_max = sorted(self.conts_ary, key=attrgetter('max'), reverse=True)
        self.conts_by_total = sorted(self.conts_ary, key=attrgetter('total'), reverse=True)
    def __str__(self):
        return 'MutexStack %d contentions %d usec total time %d usec max - %d unique mutexes - %d unique contentions - stack\n%s' % \
            (self.count, self.total, self.max, len(self.mutexes), len(self.conts), self.stack)
    def get_conts_by_count(self):
        self.calcstats()
        return self.conts_by_count
    def get_conts_by_max(self):
        self.calcstats()
        return self.conts_by_max
    def get_conts_by_total(self):
        self.calcstats()
        return self.conts_by_total
    def mergewith(self, msobj): # combine msobj with self
        for mutex in msobj.mutexes.values(): self.addmutex(mutex)
        self.count += msobj.count
        self.total += msobj.total
        if msobj.max > self.max: self.max = msobj.max
        for stack, cont in msobj.conts.iteritems():
            mycont = self.conts.setdefault(stack, cont)
            if not mycont is cont: # stack already existed
                mycont.count += cont.count
                mycont.total += cont.total
                if cont.max > mycont.max: mycont.max = cont.max

class Mutex:
    def __init__(self, addr, stack=''):
        self.addr = addr
        self.stack = stack
        self.conts = {} # list of contentions
        self.count = 0
        self.total = 0
        self.max = 0
    def addstack(self, line): self.stack = self.stack + line
    def addcont(self, cont):
        self.count += 1
        self.total += cont.elapsed
        if cont.elapsed > self.max: self.max = cont.elapsed
        oldcont = self.conts.get(cont.stack, None)
        if oldcont:
            oldcont.count += 1
            oldcont.total += cont.elapsed
            if cont.elapsed > oldcont.max: oldcont.max = cont.elapsed
        else:
            self.conts[cont.stack] = cont
    def __str__(self):
        return 'Mutex %s %d contentions %d usec total time %d usec max - %d unique contentions - first seen at\n%s' % \
            (self.addr, self.count, self.total, self.max, len(self.conts), self.stack)

class Contention:
    def __init__(self, addr, elapsed):
        self.addr = addr
        self.elapsed = elapsed
        self.stack = ''
        self.count = 1
        self.total = elapsed
        self.max = elapsed
    def addstack(self, line): self.stack = self.stack + line

def finalize_obj(curobj):
    # finalize curobj
    if curobj:
        # first, find the unique init stack corresponding to this mutex addr, or
        # add the current object's stack if we have not seen this addr before
        initstack = addr2stack.setdefault(curobj.addr, curobj.stack)
        # next, lookup the mutexstack object corresponding to this initstack, or
        # add it if it does not exist
        mutexstack = stack2msobj.setdefault(initstack, MutexStack(initstack))
        # add the current object to the mutexstack
        mutexstack.addobj(curobj)

# pass 1 - read the file and parse all of the mutex init and contentions
print "Begin - parsing file", sys.argv[1]
f = file(sys.argv[1])
curobj = None
instack = False
for line in f:
    match = endre.match(line)
    if match:
        finalize_obj(curobj)
        curobj = None
        break
    match = initre.match(line)
    if match:
        finalize_obj(curobj)
        addr = match.group(1)
        curobj = Mutex(addr)
        instack = True
        continue
    match = contre.match(line)
    if match:
        finalize_obj(curobj)
        addr, elapsed = match.groups()
        curobj = Contention(addr, int(elapsed))
        instack = True
        continue
    elif not instack:
        finalize_obj(curobj)
        curobj = None
    else: # part of stack trace
        curobj.addstack(line)
f.close()
finalize_obj(curobj)

print "Done parsing file - finding all contended stacks"
# pass 2 - condense related stacks together e.g.
# all db contentions usually are in
# __db_tas_mutex_lock+0x11d [libdb-4.7.so]
# malloc/free
# _L_lock_5189+0x10 [libc-2.12.so]
# _int_free+0x40b [libc-2.12.so]
# _L_lock_9495+0x10 [libc-2.12.so]
# malloc+0x66 [libc-2.12.so]
# _L_lock_5189+0x10 [libc-2.12.so]
# _int_free+0x40b [libc-2.12.so]
dbre = re.compile(r'__db_tas_mutex_lock\+0x11d')
mallocre = re.compile(r'malloc\+0x66 \[libc')
freere = re.compile(r'_int_free\+0x40b')
free2re = re.compile(r'_int_free\+0x412')
reallocre = re.compile(r'__libc_realloc\+0xd4')
callocre = re.compile(r'__libc_calloc\+0x8b')
dbidx = -1
allocfreeidx = -1
stack_list = []
for stack, msobj in stack2msobj.iteritems():
    if msobj.count < 1: continue
    if dbre.search(stack):
        if dbidx < 0:
            dbidx = len(stack_list) # index of appended msobj
            stack_list.append(msobj)
        else:
            stack_list[dbidx].mergewith(msobj)
    elif mallocre.search(stack) or freere.search(stack) or reallocre.search(stack) or \
         callocre.search(stack) or free2re.search(stack):
        if allocfreeidx < 0:
            allocfreeidx = len(stack_list) # index of appended msobj
            stack_list.append(msobj)
        else:
            stack_list[allocfreeidx].mergewith(msobj)
    else:
        stack_list.append(msobj)

print "Found", len(stack_list), "contended stacks - sorting"
# pass 3 - sort by stats
msobj_by_count = sorted(stack_list, key=attrgetter('count'), reverse=True)
#msobj_by_max = sorted(stack_list, key=attrgetter('max'), reverse=True)
#msobj_by_total = sorted(stack_list, key=attrgetter('total'), reverse=True)

#print "Top Ten mutex stacks by number of contentions"
#for ii in xrange(0,10): print msobj_by_count[ii]
#print "Top Ten mutex stacks by total contention time"
#for ii in xrange(0,10): print msobj_by_total[ii]

outdir = '/var/tmp/stacks'
sumf = open('%s/Summary.csv' % outdir, 'w')
mistacksf = open('%s/MutexInitStacks.csv' % outdir, 'w')
print "Writing report CSV files to", outdir

sumf.write('Note: all libdb contentions on __db_tas_mutex_lock+0x11d have been merged\n')
sumf.write('Note: all malloc/realloc/calloc/free libc contentions have been merged\n')
sumf.write('The mutex init list contains all of the individual stacktraces at the end\n')
sumf.write('Init Stack,Cont. Stacks,Count,Total time (usec),Max time (usec),Notes\n')
for ii in xrange(0, len(msobj_by_count)):
    msobj = msobj_by_count[ii]
    initstack = 'initstack-%d' % ii
    contstack = 'contstacks-%d' % ii
    sumf.write('%s,%s,%d,%d,%d,\n' % (initstack, contstack, msobj.count, msobj.total, msobj.max))
    mistacksf.write('%s\n%s\n' % (initstack, msobj.stack))
    f = open('%s/%s.csv' % (outdir, initstack), 'w')
    f.write('%s\nContention stacks and stats for initstack %s\n' % (contstack, initstack))
    f.write('Location,Count,Total time (usec),Max time (usec)\n')
    cont_by_count = msobj.get_conts_by_count()
    for jj in xrange(0, len(cont_by_count)):
        cont = cont_by_count[jj]
        f.write('contstack-%d,%d,%d,%d\n' % (jj, cont.count, cont.total, cont.max))
    f.write('\nstacks in order of descending number of contentions\n\n')
    for jj in xrange(0, len(cont_by_count)):
        cont = cont_by_count[jj]
        f.write('contstack-%d\n%s\n' % (jj, cont.stack))
    f.close()

sumf.close()
mistacksf.write('All database init/first seen stacks:\n')
for stack, msobj in stack2msobj.iteritems():
    if dbre.search(stack):
        mistacksf.write('%s\n' % msobj.stack)

mistacksf.write('All alloc/free init/first seen stacks:\n')
for stack, msobj in stack2msobj.iteritems():
    if mallocre.search(stack) or freere.search(stack) or reallocre.search(stack) or callocre.search(stack):
        mistacksf.write('%s\n' % msobj.stack)
mistacksf.close()
