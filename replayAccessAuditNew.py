import sys
import re
import time
import ldif
import ldap
import ldap.sasl
import ldap.cidict
import os, os.path
import pprint
import StringIO
from operator import itemgetter

# regex that matches a BIND request line
regex_num = r'[-]?\d+' # matches numbers including negative
regex_new_conn = re.compile(r'^(\[.+\]) (conn=%s) (fd=%s) (slot=%s) (?:SSL )?connection from (\S+)' % (regex_num, regex_num, regex_num))
regex_sslinfo = re.compile(r'^\[.+\] (conn=%s) SSL (.+)$' % regex_num)
regex_bind_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) BIND dn="(.*)" method=(\S+) version=\d ?(?:mech=(\S+))?' % (regex_num, regex_num))
regex_bind_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=97 ' % (regex_num, regex_num, regex_num))
regex_autobind = re.compile(r'^(\[.+\]) (conn=%s) AUTOBIND dn="(.*)"' % regex_num)
regex_unbind = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) UNBIND' % (regex_num, regex_num))
regex_closed = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) fd=%s closed' % (regex_num, regex_num, regex_num))
regex_ssl_map_fail = re.compile(r'^\[.+\] (conn=%s) (SSL failed to map client certificate.*)$' % regex_num)
regex_mod_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) MOD dn="(.*)" (?:authzid=".*")?' % (regex_num, regex_num))
regex_mod_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=103 ' % (regex_num, regex_num, regex_num))
regex_add_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) ADD dn="(.*)" (?:authzid=".*")?' % (regex_num, regex_num))
regex_add_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=105 ' % (regex_num, regex_num, regex_num))
regex_mdn_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) MODRDN dn="(.*)" newrdn="(.+)" newsuperior="(.*)"' % (regex_num, regex_num))
regex_mdn_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=109 ' % (regex_num, regex_num, regex_num))
regex_del_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) DEL dn="(.*)" (?:authzid=".*")?' % (regex_num, regex_num))
regex_del_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=107 ' % (regex_num, regex_num, regex_num))
#[01/Jun/2012:17:53:14 -0600] conn=7 op=3 SRCH base="cn=ipaconfig,cn=etc,dc=testdomain,dc=com" scope=0 filter="(objectClass=*)" attrs=ALL
regex_srch_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) SRCH base="(.*)" scope=(%s) filter="(.*)" attrs=(?:(ALL)|"(.*)")' % (regex_num, regex_num, regex_num))
#[01/Jun/2012:17:53:14 -0600] conn=7 op=3 RESULT err=0 tag=101 nentries=1 etime=0
regex_srch_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=101 nentries=(%s) ' % (regex_num, regex_num, regex_num, regex_num))
#[03/Sep/2013:11:16:35 -0400] conn=2467156 op=2 ABANDON targetop=1 msgid=829128 nentries=16 etime=60
# targetop=NOTFOUND also, that's why it has to be a string, not an int
regex_abandon = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) ABANDON targetop=(\S+) msgid=(%s) nentries=(%s) etime=(%s)' % (regex_num, regex_num, regex_num, regex_num, regex_num))
# format for strptime
ts_fmt_access = '[%d/%b/%Y:%H:%M:%S -0700]'
ts_fmt_audit = '%Y%m%d%H%M%S'
ts_fmt_auditz = '%Y%m%d%H%M%SZ'

def accesstime2ts(accesstsstr):
    utctime = int(time.mktime(time.strptime(accesstsstr, ts_fmt_access)))
    return int(time.mktime(time.localtime(utctime)))

# extra time to sleep between ops
extra_sleep_time = 1.0

# if false, need to generate our own uuids
have_ipa_uuid_plugin = False
uuidcnt = 1
def adduuid(ent):
    if have_ipa_uuid_plugin: return # ipa uuid plugin will assign uuid
    hasipaobj = False
    hasuuid = False
    for name,vals in ent:
        if name.lower() == 'objectclass':
            for val in vals:
                if val.lower() == "ipaobject":
                    hasipaobj = True
            if not hasipaobj:
                break
        if name.lower() == "ipauniqueid":
            hasuuid = True
            break
    if hasipaobj and not hasuuid:
        global uuidcnt
        ent.append(('ipauniqueid', [str(uuidcnt)]))
        uuidcnt = uuidcnt + 1

# bind errors we can ignore
ignore_errors = {'10': 'Referral',
                 '14': 'SASL Bind In Progress'
                 }

# table to map numeric error codes to exceptions
err2ex = {0x01:ldap.OPERATIONS_ERROR, 0x02:ldap.PROTOCOL_ERROR,
          0x03:ldap.TIMELIMIT_EXCEEDED, 0x04:ldap.SIZELIMIT_EXCEEDED,
          0x05:ldap.COMPARE_FALSE, 0x06:ldap.COMPARE_TRUE,
          0x07:ldap.STRONG_AUTH_NOT_SUPPORTED, 0x08:ldap.STRONG_AUTH_REQUIRED,
          0x09:ldap.PARTIAL_RESULTS, 0x0a:ldap.REFERRAL,
          0x0b:ldap.ADMINLIMIT_EXCEEDED, 0x0c:ldap.UNAVAILABLE_CRITICAL_EXTENSION,
          0x0d:ldap.CONFIDENTIALITY_REQUIRED, 0x0e:ldap.SASL_BIND_IN_PROGRESS,
          0x10:ldap.NO_SUCH_ATTRIBUTE, 0x11:ldap.UNDEFINED_TYPE,
          0x12:ldap.INAPPROPRIATE_MATCHING, 0x13:ldap.CONSTRAINT_VIOLATION,
          0x14:ldap.TYPE_OR_VALUE_EXISTS, 0x15:ldap.INVALID_SYNTAX,
          0x20:ldap.NO_SUCH_OBJECT, 0x21:ldap.ALIAS_PROBLEM,
          0x22:ldap.INVALID_DN_SYNTAX, 0x23:ldap.IS_LEAF,
          0x24:ldap.ALIAS_DEREF_PROBLEM,
          0x30:ldap.INAPPROPRIATE_AUTH, 0x31:ldap.INVALID_CREDENTIALS,
          0x32:ldap.INSUFFICIENT_ACCESS, 0x33:ldap.BUSY,
          0x34:ldap.UNAVAILABLE, 0x35:ldap.UNWILLING_TO_PERFORM,
          0x36:ldap.LOOP_DETECT, 0x40:ldap.NAMING_VIOLATION,
          0x41:ldap.OBJECT_CLASS_VIOLATION, 0x42:ldap.NOT_ALLOWED_ON_NONLEAF,
          0x43:ldap.NOT_ALLOWED_ON_RDN, 0x44:ldap.ALREADY_EXISTS,
          0x45:ldap.NO_OBJECT_CLASS_MODS, 0x46:ldap.RESULTS_TOO_LARGE,
          0x47:ldap.AFFECTS_MULTIPLE_DSAS, 0x50:ldap.OTHER}

ex2err = {}
for num,ex in err2ex.iteritems():
    ex2err[ex] = num

# special error handling hacks
LDAP_SIZELIMIT_EXCEEDED = 4
def get_sizelimit(op):
    sizelimit = -1
    if isinstance(op.req, SrchReq) and (int(op.res.errnum) == LDAP_SIZELIMIT_EXCEEDED):
        sizelimit = int(op.res.nentries)
    return sizelimit

prevtime = time.time()
prevopts = 0

class Req(object):
    def __init__(self, tsstr=None, conn=None, op=None, auditts=None):
        if tsstr:
            self.ts = accesstime2ts(tsstr)
        else:
            self.ts = 0
        self.conn = conn
        self.op = op
        if auditts:
            try:
                self.auditts = int(time.mktime(time.strptime(auditts, ts_fmt_audit)))
            except ValueError:
                self.auditts = int(time.mktime(time.strptime(auditts, ts_fmt_auditz)))-time.timezone
        else:
            self.auditts = 0
    def __cmp__(self, oth): return oth.ts - self.ts
    def __eq__(self, oth): return cmp(self, oth) == 0
    def __str__(self):
        return 'ts=%s auditts=%s %s %s' % (time.strftime(ts_fmt_access, time.localtime(self.ts)),
                                           time.strftime(ts_fmt_audit, time.localtime(self.auditts)),
                                           self.conn, self.op)
    def __repr__(self): return str(self)
    def same(self, oth, skipts=False):
        if skipts: ret = True
        else: ret = self.ts == oth.ts
        if ret: ret = self.__class__ == oth.__class__
        if ret: ret = self.conn == oth.conn
        if ret: ret = self.op == oth.op
        return ret

class UnbindReq(Req):
    def __init__(self, match=None):
        (tsstr, connid, opnum) = match.groups()
        Req.__init__(self, tsstr, connid, opnum)
    def __str__(self):
        return Req.__str__(self) + ' UNBIND'
    def __repr__(self): return str(self)

class DNReq(Req):
    def __init__(self, dn, tsstr=None, conn=None, op=None, auditts=None):
        Req.__init__(self, tsstr, conn, op, auditts)
        self.dn = dn
    def __str__(self):
        return Req.__str__(self) + ' dn="' + self.dn + '"'
    def __repr__(self): return str(self)
    def same(self, oth, skipts=False):
        ret = Req.same(self, oth, skipts)
        if ret: ret = self.dn == oth.dn
        return ret

class BindReq(DNReq):
    def __init__(self, match=None):
        (tsstr, connid, opnum, dn, method, mech) = match.groups()
        DNReq.__init__(self, dn, tsstr, connid, opnum)
        self.method = method
        self.mech = mech
    def __str__(self):
        return DNReq.__str__(self) + ' BIND method=%s mech=%s' % (self.method, self.mech)
    def __repr__(self): return str(self)

class SrchReq(DNReq):
    def __init__(self, match=None):
        (tsstr, connid, opnum, dn, scope, filt, allkw, attrs) = match.groups()
        DNReq.__init__(self, dn, tsstr, connid, opnum)
        self.scope = int(scope)
        self.filt = filt
        if allkw or not attrs:
            self.attrs = None
        else:
            self.attrs = attrs.split()
    def __str__(self):
        return Req.__str__(self) + ' SRCH base="%s" scope=%d filter="%s" attrs=%s' % (self.dn, self.scope, self.filt, self.attrs)
    def __repr__(self): return str(self)

class AddReq(DNReq):
    def __init__(self, dn=None, tsstr=None, conn=None, op=None, auditts=None, ent=None, match=None):
        if match:
            (tsstr, conn, op, dn) = match.groups()
        DNReq.__init__(self, dn, tsstr, conn, op, auditts)
        self.ent = ent
    def __str__(self):
        return DNReq.__str__(self) + ' ADD'
    def __repr__(self): return str(self)
    def same(self, oth, skipts=False):
        ret = DNReq.same(self, oth, skipts)
        if ret: ret = self.ent == oth.ent
        return ret

class ModReq(DNReq):
    def __init__(self, dn=None, tsstr=None, conn=None, op=None, auditts=None, mods=None, match=None):
        if match:
            (tsstr, conn, op, dn) = match.groups()
        DNReq.__init__(self, dn, tsstr, conn, op, auditts)
        self.mods = mods
    def __str__(self):
        return DNReq.__str__(self) + ' MOD'
    def __repr__(self): return str(self)
    def same(self, oth, skipts=False):
        ret = DNReq.same(self, oth, skipts)
        if ret: ret = self.mods == oth.mods
        return ret

class DelReq(DNReq):
    def __init__(self, dn=None, tsstr=None, conn=None, op=None, auditts=None, match=None):
        if match:
            (tsstr, conn, op, dn) = match.groups()
        DNReq.__init__(self, dn, tsstr, conn, op, auditts)
    def __str__(self):
        return DNReq.__str__(self) + ' DEL'
    def __repr__(self): return str(self)

class MdnReq(DNReq):
    def __init__(self, dn=None, tsstr=None, conn=None, op=None, newrdn=None, newsuperior=None, deleteoldrdn=0, auditts=None, match=None):
        if match:
            (tsstr, conn, op, dn, newrdn, newsuperior) = match.groups()
        DNReq.__init__(self, dn, tsstr, conn, op, auditts)
        self.newrdn = newrdn
        if newsuperior and ((newsuperior == "(null)") or (newsuperior == "null")):
            self.newsuperior = None
        else:
            self.newsuperior = newsuperior
        self.deleteoldrdn = deleteoldrdn
    def __str__(self):
        return DNReq.__str__(self) + ' MODRDN newrdn="%s" deleteoldrdn=%d newsuperior="%s"' % (self.newrdn, self.deleteoldrdn, self.newsuperior)
    def __repr__(self): return str(self)
    def same(self, oth, skipts=False):
        ret = DNReq.same(self, oth, skipts)
        if ret:
            ret = (self.newrdn, self.newsuperior, self.deleteolrdn) == (oth.newrdn, oth.newsuperior, oth.deleteolrdn)
        return ret

class Res(object):
    def __init__(self, match=None, fields=None):
        if match:
            if match.lastindex == 4:
                ts, conn, op, errnum = match.groups()
            else:
                ts, conn, op = match.groups()
                errnum = '0'
            self.ts = accesstime2ts(ts)
            self.conn = conn
            self.op = op
            self.errnum = errnum
        elif fields:
            self.ts, self.conn, self.op, self.errnum = fields
    def __str__(self):
        return 'RESULT ts=%s %s %s err=%s' % (time.strftime(ts_fmt_access, time.localtime(self.ts)),
                                              self.conn, self.op, self.errnum)
    def __repr__(self): return str(self)

class SrchRes(Res):
    def __init__(self, match=None):
        ts, conn, op, errnum, nentries = match.groups()
        self.ts = accesstime2ts(ts)
        self.conn = conn
        self.op = op
        self.errnum = errnum
        self.nentries = nentries
    def __str__(self):
        return Res.__str__(self) + ' nentries=' + self.nentries
    def __repr__(self): return str(self)

class AbandonRes(Res):
    def __init__(self, match=None):
        (ts, connid, opnum, targetop, msgid, nentries, etime) = match.groups()
        self.ts = accesstime2ts(ts)
        self.conn = connid
        self.op = opnum
        self.errnum = 0
        try:
            self.targetop = int(targetop) # could be NOTFOUND
        except:
            self.targetop = -1
        self.msgid = int(msgid)
        self.nentries = int(nentries)
        self.etime = int(etime)
    def __str__(self):
        return Res.__str__(self) + ' ABANDON targetop=%d msgid=%d nentries=%d etime=%d' % (self.targetop, self.msgid, self.nentries, self.etime)
    def __repr__(self): return str(self)
    def targetopid(self): return 'op=%d' % self.targetop

class Op(object):
    def __init__(self, req=None, res=None, auditreq=None):
        self.req = req
        self.res = res
        self.auditreq = auditreq
    def __str__(self):
        return str(self.req) + ' ' + str(self.res) + ' AUDIT ' + str(self.auditreq)
    def __repr__(self): return str(self)
    # a complete op has both a request and a result
    def iscomplete(self): return self.req and self.res
    def opid(self):
        if self.req: return self.req.op
        if self.res: return self.res.op
        assert(False)

class Conn(object):
    def __init__(self, timestamp, conn, fd, slot, ip):
        self.conn = conn
        self.fd = fd
        self.slot = slot
        self.ip = ip
        self.timestamp = timestamp
        if timestamp:
            self.ts = accesstime2ts(timestamp)
        self.binddn = None
        self.ops = []
        self.sslinfo = ''
        url = os.environ.get('LDAPURL', None)
        if url:
            self.ld = ldap.initialize(url)
        else:
            self.ld = None
        self.autobind = False

    def addssl(self, sslinfo):
        if self.sslinfo and sslinfo:
            self.sslinfo += ' '
        self.sslinfo += sslinfo

    def findop(self, opid):
        for op in self.ops:
            if op.opid() == opid: return op
        return None

    def replayops(self):
        if not self.ld: return False
        isclosed = False
        while self.ops:
            op = self.ops[0]
            if op.iscomplete():
                op = self.ops.pop(0)
                if op.res.errnum in ignore_errors: # don't care about this op
                    pass
                else:
                    # find the corresponding audit op, if any
                    if not op.auditreq:
                        op.auditreq = findAuditReq(op)
                    myisclosed = self.replay(op)
                    if myisclosed and not isclosed: isclosed = True
            else: break # found an incomplete op - cannot continue
        return isclosed

    def addreq(self, req):
        isclosed = False
        op = self.findop(req.op)
        if op:
            assert(op.req == None)
            op.req = req
            isclosed = self.replayops()
        else: # store request until we get the result
            op = Op(req=req)
            self.ops.append(op)
        if isinstance(req,BindReq):
            self.binddn = req.dn
            val = binddns.get(self.binddn, 0) + 1
            binddns[self.binddn] = val
        return isclosed

    def addres(self, res):
        isclosed = False
        if isinstance(res,AbandonRes) and res.targetop >= 0:
            # if an op is abandoned, the abandon is the "result"
            op = self.findop(res.targetopid())
        else:
            op = self.findop(res.op)
        if op:
            assert(op.res == None)
            op.res = res
            isclosed = self.replayops()
            if isinstance(res,AbandonRes) and res.targetop >= 0:
                print str(op)
        else: # store request until we get the result
            op = Op(res=res)
            self.ops.append(op)
        return isclosed

    def replay(self, op):
        isclosed = False
        global prevopts
        global prevtime
        nerr = int(op.res.errnum)
        # do we need to sleep before sending the op?
        if os.environ.get('NOTIMING', None):
            pass
        elif prevopts:
            lag = extra_sleep_time + op.req.ts - prevopts
            tdiff = time.time() - prevtime
            if tdiff < lag:
                time.sleep(extra_sleep_time + lag - tdiff)
        prevopts = op.req.ts
        prevtime = time.time()
        print "replaying op", str(op)
        try:
            if isinstance(op.req, SrchReq):
                sizelimit = get_sizelimit(op)
                ents = self.ld.search_ext_s(op.req.dn, op.req.scope, op.req.filt, op.req.attrs, sizelimit=sizelimit)
            elif isinstance(op.req, BindReq):
                if self.autobind:
                    self.ld.sasl_interactive_bind_s("", ldap.sasl.external())
                elif op.req.method.lower() == 'sasl' and op.req.mech.lower() == 'gssapi':
                    self.ld.sasl_interactive_bind_s("", ldap.sasl.gssapi())
                else:
                    self.ld.simple_bind_s(os.environ['BINDDN'], os.environ['BINDPW'])
            elif isinstance(op.req, AddReq):
                if not op.auditreq or not op.auditreq.ent:
                    if nerr: # not logged due to error - make up something
                        ent = makeAddEnt(nerr)
                    else:
                        raise Exception("add op was successful but no error - " + str(op))
                else:
                    ent = op.auditreq.ent
                adduuid(ent)
                self.ld.add_s(op.req.dn, ent)
            elif isinstance(op.req, ModReq):
                if not op.auditreq or not op.auditreq.mods:
                    if op.res.errnum: # not logged due to error - make up something
                        mods = makeModMods(nerr)
                    else:
                        raise Exception("add op was successful but no error - " + str(op))
                else:
                    mods = op.auditreq.mods
                self.ld.modify_s(op.req.dn, mods)
            elif isinstance(op.req, MdnReq):
                self.ld.rename_s(op.req.dn, op.req.newrdn, op.req.newsuperior, op.req.deleteoldrdn)
            elif isinstance(op.req, DelReq):
                self.ld.delete_s(op.req.dn)
            elif isinstance(op.req, UnbindReq):
                self.ld.unbind_s()
                self.ld = None
                isclosed = True
            # if we got here, op succeeded - check if it was supposed to return an error
            if nerr:
                raise Exception("Error: op %s was supposed to error %d but did not" % (op, nerr))
            if isinstance(op.res, SrchRes):
                nentries = str(len(ents))
                if not nentries == op.res.nentries:
                    raise Exception("Error: op %s was supposed to return %s entries but returned %s instead" % (op, op.res.nentries, nentries))
        except ldap.LDAPError, e:
            if nerr: # see if we caught the right error
                ex = err2ex[nerr]
                if not isinstance(e, ex):
                    raise Exception("Error: op %s was supposed to return error %d but returned %s instead" % (op, nerr, e))
            else:
                raise Exception("Error: op %s threw error %s" % (op, e))
        return isclosed

# key is conn=X
# val is list of conns with that conn id
#   - due to restarts, an access log may contain several of the same conn id
# each conn has a dict of ops
#  key is op=Y
#  value is list
#    list[0] is BIND request
#    list[1] is RESULT
conns = {}
# key is binddn
# val is number of times a connection was made which was followed by a bind with that dn
binddns = {}
mints = 99999999999
maxts = 0
def updateminmaxts(ts):
    global mints
    global maxts
    if ts < mints: mints = ts
    if ts > maxts: maxts = ts

NOT_A_MOD = -1

ignoreattrs = ldap.cidict.cidict({'creatorsName':'creatorsName', 'modifiersName':'modifiersName',
                                  'createTimestamp':'createTimestamp', 'modifyTimestamp':'modifyTimestamp',
                                  'ipaUniqueID':'ipaUniqueID', 'time':'time', 'entryusn':'entryusn'})

def getChangeType(rec):
    if 'add' in rec: return (ldap.MOD_ADD, rec['add'][0])
    if 'replace' in rec: return (ldap.MOD_REPLACE, rec['replace'][0])
    if 'delete' in rec: return (ldap.MOD_DELETE, rec['delete'][0])
    return (NOT_A_MOD, '')

# take an ldif style mod record and turn it into a modify_s modlist
def ldif2mod(rec):
    ct,name = getChangeType(rec)
    if ct != NOT_A_MOD: # a valid mod
        if not name in ignoreattrs:
            return (ct, name, rec.get(name, []))
    return (ct, None, []) # removed or not a mod

def ldif2add(rec):
    # must be in mods list format
    mods = []
    for key,val in rec.iteritems():
        if key in ignoreattrs:
            continue
        else:
            mods.append((key, val))
    return mods

def ldif2mdn(rec):
    newrec = {}
    if 'newrdn' in rec:
        newrec['newrdn'] = rec['newrdn'][0]
    if 'newsuperior' in rec:
        newrec['newsuperior'] = rec['newsuperior'][0]
    if 'deleteoldrdn' in rec:
        newrec['deleteoldrdn'] = int(rec['deleteoldrdn'][0])
    return newrec

def is_mod(rec):
    return rec and (getChangeType(rec)[0] != NOT_A_MOD)

def is_del(rec):
    return rec and (len(rec) <= 2) and ('time' in rec) and ((len(rec) == 1) or ((len(rec) == 2) and ('modifiersname' in rec)))

def is_mdn(rec):
    return rec and (('newrdn' in rec) or ('deleteoldrdn' in rec) or ('newsuperior' in rec))

def is_add(rec):
    return rec and ('objectclass' in rec)

# -
# time: 20121126230007: dn: some=dn,some=suffix
# look for a value of a timestamp followed by a ": dn:"
# just skip it
bogusre = re.compile(r'^%s: dn: .*$' % regex_num)
def is_bogus(rec):
    tsstr = rec.get('time', [None])[0]
    return tsstr and bogusre.match(tsstr)

def get_ts_from_rec(rec):
    if 'time' in rec:
        return rec['time'][0]
    if 'modifytimestamp' in rec:
        return rec['modifytimestamp'][0]
    return None

def parseRec(rec):
    tsstr = get_ts_from_rec(rec)
    if is_mod(rec):
        return (tsstr, ldap.REQ_MODIFY, ldif2mod(rec))
    if is_del(rec):
        return (tsstr, ldap.REQ_DELETE, None)
    if is_add(rec):
        return (tsstr, ldap.REQ_ADD, ldif2add(rec))
    if is_mdn(rec):
        return (tsstr, ldap.REQ_MODRDN, ldif2mdn(rec))
    return (tsstr, -1, None)

def isIncomplete(dn, ent):
    return dn == None and not 'time' in ent

def appendEnt(req, ent):
    req.ent.extend(ent.iteritems())

# ops from the audit log, indexed by timestamp
# key is timestamp, val is a list of ops
auditops = {}

class AuditParser(ldif.LDIFParser):
    def __init__(self, input_file, min_entry=0, ignored_attr_types=None, max_entries=0, process_url_schemes=None, line_sep='\n'):
        ldif.LDIFParser.__init__(self, input_file, ignored_attr_types, max_entries, process_url_schemes, line_sep)
        self.min_entry = min_entry
        self.auditops = {}
        self.modlist = []
        self.savets = None
        self.savedn = None
        self.lastreq = None
    def handle(self, dn, ent):
        if self.records_read < self.min_entry: return
        # some ldap servers which will remain nameless generate bogus audit logs with empty lines
        # in the middle of a record - we detect this situation and just append the records to the
        # last request's records
        if not dn and is_bogus(ent): return
        ts, optype, data = parseRec(ldap.cidict.cidict(ent))
        if optype == -1 and isIncomplete(dn, ent):
            if not self.lastreq:
                raise Exception("Error: found incomplete record but no previous record to append to")
            if isinstance(self.lastreq, AddReq):
                appendEnt(self.lastreq, ent)
            else:
                raise Exception("Error: incomplete record was not an Add Request: " + str(self.lastreq) + ":" + str(ent))
        elif optype == -1:
            raise Exception("Error: unknown operation: " + str(dn) + ":" + str(ent))
        elif optype == ldap.REQ_MODIFY:
            if data[1]: # do not add stripped mods
                if dn:
                    if self.modlist:
                        self.lastreq = ModReq(self.savedn, auditts=self.savets, mods=self.modlist)
                        self.handleAuditReq(self.lastreq)
                    self.modlist, self.savets, self.savedn = ([data], ts, dn)
                else: # continuation
                    self.modlist.append(data)
            elif dn and not self.savedn: # but save ts and dn in case the first mod is stripped
                self.modlist, self.savets, self.savedn = ([], ts, dn)
        else:
            if self.modlist:
                # "flush" pending modify request
                self.handleAuditReq(ModReq(self.savedn, auditts=self.savets, mods=self.modlist))
                self.modlist, self.savets, self.savedn = ([], None, None)
            if optype == ldap.REQ_ADD:
                self.lastreq = AddReq(dn, auditts=ts, ent=data)
            elif optype == ldap.REQ_MODRDN:
                self.lastreq = MdnReq(dn, auditts=ts, newrdn=data.get('newrdn', None),
                             deleteoldrdn=data.get('deleteoldrdn', None),
                             newsuperior=data.get('newsuperior', None))
            elif optype == ldap.REQ_DELETE:
                self.lastreq = DelReq(dn, auditts=ts)
            self.handleAuditReq(self.lastreq)
    def parse(self):
        ldif.LDIFParser.parse(self)
        if self.modlist and self.savedn and self.savets:
            self.handleAuditReq(ModReq(self.savedn, auditts=self.savets, mods=self.modlist))
            self.modlist, self.savets, self.savedn = ([], None, None)
    def handleAuditReq(self, req): # subclass should override this
        self.auditops.setdefault(req.auditts, []).append(req)

# output from cl-ldif does not have record/entry starting with dn:
# line, so need to do some initial parsing first to put in correct
# format
# cl-ldif also does not have 'time' attribute - use modifyTimestamp
# or createTimestamp
def parseAudit(f, start=0, finish=sys.maxint, clldif=False):
    if clldif:
        outbuf = ''
        rec = []
        seenstart = False
        rec_has_time = False
        time_line = ''
        for line in f:
            if not seenstart:
                if line.startswith("changetype:"):
                    seenstart = True
                else:
                    continue
            if line == '\n':
                if not rec_has_time and time_line:
                    rec.insert(1, time_line)
                outbuf = outbuf + ''.join([xx for xx in rec]) + '\n'
                rec = []
                rec_has_time = False
                time_line = ''
            elif line.startswith('dn:'):
                rec.insert(0, line)
            else:
                rec.append(line)
                if not time_line:
                    if line.startswith('time:'):
                       rec_has_time = True
                       time_line = line
                    elif line.startswith('modifytimestamp:'):
                        time_line = line.replace('modifytimestamp:', 'time:', 1)
                    elif line.startswith('createtimestamp:'):
                        time_line = line.replace('createtimestamp:', 'time:', 1)
        if rec:
            if not rec_has_time and time_line:
                rec.insert(1, time_line)
            outbuf = outbuf + ''.join([xx for xx in rec]) + '\n'
        ldiff = StringIO.StringIO(outbuf)
    else:
        ldiff = f
    ap = AuditParser(ldiff, min_entry=start, max_entries=finish)
    ap.parse()
    auditops.update(ap.auditops)

# there isn't a way in general to uniquely tie
# an operation in the access log with its corresponding
# operation in the audit log, nor vice versa
# for replicated ops, CSN would definitely work
def couldBeSameReq(accessReq, auditReq):
    return type(accessReq) == type(auditReq) and accessReq.dn == auditReq.dn

def findAuditReq(op):
    req = None
    ts = op.res.ts
    # audit log ts for op might be before RESULT ts for op
    for ts in xrange(op.res.ts-1, op.res.ts+2):
        reqlist = auditops.get(ts, [])
        for ii in xrange(0, len(reqlist)):
            if couldBeSameReq(op.req, reqlist[ii]):
                req = reqlist.pop(ii)
                if len(reqlist) == 0:
                    del auditops[ts]
                break
        if req:
            break
    if not req:
        print "here"
    return req

regexmap = ((regex_bind_req, BindReq), (regex_bind_res, Res),
            (regex_add_req, AddReq), (regex_add_res, Res),
            (regex_mod_req, ModReq), (regex_mod_res, Res),
            (regex_mdn_req, MdnReq), (regex_mdn_res, Res),
            (regex_del_req, DelReq), (regex_del_res, Res),
            (regex_srch_req, SrchReq), (regex_srch_res, SrchRes),
            (regex_unbind, UnbindReq), (regex_closed, Res),
            (regex_abandon, AbandonRes))

# key is ts (time_t)
# val is list of Conn objects
connsbyts = {}

def tsinrange(ts, begin, end):
    return ts >= begin and ts <= end

def parseAccessLine(line, begints, endts):
    # is this a new conn line?
    match = regex_new_conn.match(line)
    if match:
        (timestamp, connid, fdid, slotid, ip) = match.groups()
        conn = Conn(timestamp, connid, fdid, slotid, ip)
        if not tsinrange(conn.ts, begints, endts): return False
        updateminmaxts(conn.ts)
        connsbyts.setdefault(conn.ts, []).append(conn)
        conns.setdefault(connid, []).append(conn)
        return True

    # is this an SSL info line?
    match = regex_sslinfo.match(line)
    if match:
        (connid, sslinfo) = match.groups()
        if connid in conns:
            conns[connid][-1].addssl(sslinfo)
        else:
            raise Exception("ERROR: sslinfo " + sslinfo + " for " + connid + " but conn not found")
        return True

    # is this a line with extra SSL mapping info?
    match = regex_ssl_map_fail.match(line)
    if match:
        (connid, sslinfo) = match.groups()
        if connid in conns:
            conns[connid][-1].addssl(sslinfo)
        else:
            raise Exception("ERROR: sslinfo " + sslinfo + " for " + connid + " but conn not found")
        return True

    # autobind
    match = regex_autobind.match(line)
    if match:
        (timestamp, connid, sslinfo) = match.groups()
        if connid in conns:
            conns[connid][-1].autobind = True
        else:
            raise Exception("ERROR: autobind for " + connid + " but conn not found")
        return True

    for rx,clz in regexmap:
        match = rx.match(line)
        if match:
            obj = clz(match=match)
            if not tsinrange(obj.ts, begints, endts): return False
            updateminmaxts(obj.ts)
            # should have seen new conn line - if not, have to create a dummy one
            connlist = conns.get(obj.conn, None)
            if obj.conn in conns:
                conn = conns[obj.conn][-1]
            else:
                conn = Conn(None, obj.conn, '', '', 'unknown')
                conns[obj.conn] = [conn]
                connsbyts.setdefault(0, []).append(conn)
            if isinstance(obj, Req):
                isclosed = conn.addreq(obj)
            else:
                isclosed = conn.addres(obj)
            if isclosed: # unbind or closure
                if conn.ld:
                    conn = conns.pop(obj.conn) # remove it
                if conn.ld:
                    conn.ld.unbind_s()
                    conn.ld = None
            return True

    return True # no match

def parseAccess(f, startoff, endoff, begints, endts):
    lineno = 0
    for line in f:
        lineno = lineno + 1
        if lineno >= startoff and lineno <= endoff:
            if (lineno % 10000) == 0: print "Line", lineno
            parseAccessLine(line, begints, endts)

def getBindStats():
    # now let's find all of the binddns that exceeded the threshold
    thresh = int(os.environ.get('THRESH', 1000))
    delim = os.environ.get('DELIM', '|')
    # sort in descending order of the number of connections from this binddn
    usebinddns = [dn for dn,val in sorted(binddns.iteritems(), key=itemgetter(1), reverse=True) if val > thresh]

    # print column header
    print "timestamp" + delim + delim.join(usebinddns) + delim + "ALL"
        
    for ts in xrange(mints, maxts+1):
        if not ts in connsbyts: continue # no data for this time
        binddn2cnt = {}
        allconn = 0
        for conn in connsbyts[ts]:
            if not conn.binddn: continue # conn terminated before bind
            val = binddn2cnt.get(conn.binddn, 0) + 1
            binddn2cnt[conn.binddn] = val
            allconn += 1
        # now have conn/sec by binddn
        outstr = str(ts)
        for dn in usebinddns:
            val = binddn2cnt.get(dn, 0)
            outstr = outstr + delim + str(val)
        print outstr + delim + str(allconn)

if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-c', '--access', nargs='+', type=file, help='access log files - will be parsed in the order given')
    parser.add_argument('-u', '--audit', nargs='+', type=file, help='audit log files - will be parsed in the order given')
    parser.add_argument('-b', '--accessbegin', type=int, help='beginning access log line', default=0)
    parser.add_argument('-e', '--accessend', type=int, help='ending access log line', default=sys.maxint)
    parser.add_argument('-s', '--auditstart', type=int, help='starting audit log record number', default=0)
    parser.add_argument('-f', '--auditfinish', type=int, help='ending audit log record number', default=sys.maxint)
    parser.add_argument('--accesstimebegin', type=str, help='beginning access log time', default='')
    parser.add_argument('--accesstimeend', type=str, help='ending access log time', default='')
    parser.add_argument('-v', action='count', help='repeat for more verbosity', default=0)
    parser.add_argument('--clldif', action='store_true', help='is audit output from cl-ldif?')
    args = parser.parse_args()

    if (not args.access or len(args.access) == 0) and (not args.audit or len(args.audit) == 0):
        print "Error: no audit or access logs given"
        sys.exit(1)

    if args.accesstimebegin:
        begints = accesstime2ts(args.accesstimebegin)
    else:
        begints = 0
    if args.accesstimeend:
        endts = accesstime2ts(args.accesstimeend)
    else:
        endts = sys.maxint

    if args.audit:
        for ii in xrange(0, len(args.audit)):
            start, finish = (0, sys.maxint)
            if ii == 0: start = args.auditstart
            if ii == len(args.audit)-1: finish = args.auditfinish
            parseAudit(args.audit[ii], start, finish, args.clldif)

    naccess = len(args.access)
    opid = 0
    if naccess == 0: # need dummy conn for audit log only
        conn = Conn('unknown', None, '', '', 'unknown')
        # sort audit log ops by timestamp
        for k in sorted(auditops.iterkeys()):
            opary = auditops[k]
            # these are actually Req's not Op's
            for op in opary:
                conn.addreq(op)
                conn.addres(Res(op.ts, '0', str(opid), '0'))
                opid += 1

    for ii in xrange(0, naccess):
        print "Analyzing file", args.access[ii].name
        begin, end = (0, sys.maxint)
        if ii == 0: begin = args.accessbegin
        if ii == naccess-1: end = args.accessend
        parseAccess(args.access[ii], begin, end, begints, endts)

    bindstats = False
    if bindstats:
        getBindStats()

    opsinprogress = False
    if opsinprogress:
        for ts in xrange(mints, maxts+1):
            if not ts in connsbyts: continue # no data for this time
            for conn in connsbyts[ts]:
                if not conn.ops:
                    print "Connection opened at", conn.timestamp, "from IP", conn.ip
                    continue
                for op in conn.ops:
                    if op.req and op.res: continue # op completed
                    if op.res:
                        print "Connection with result but no request", str(op.res)
                        continue
                    if op.req:
                        print "Request in progress", str(op.req)
                        continue
