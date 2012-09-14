import sys
import re
import time
import ldif
import ldap
import ldap.sasl
import ldap.cidict
import os, os.path
import pprint

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
regex_mod_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) MOD dn="(.*)"' % (regex_num, regex_num))
regex_mod_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=103 ' % (regex_num, regex_num, regex_num))
regex_add_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) ADD dn="(.*)"' % (regex_num, regex_num))
regex_add_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=105 ' % (regex_num, regex_num, regex_num))
regex_mdn_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) MODRDN dn="(.*)" newrdn="(.+)" newsuperior="(.*)"' % (regex_num, regex_num))
regex_mdn_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=109 ' % (regex_num, regex_num, regex_num))
regex_del_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) DEL dn="(.*)"' % (regex_num, regex_num))
regex_del_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=107 ' % (regex_num, regex_num, regex_num))
#[01/Jun/2012:17:53:14 -0600] conn=7 op=3 SRCH base="cn=ipaconfig,cn=etc,dc=testdomain,dc=com" scope=0 filter="(objectClass=*)" attrs=ALL
regex_srch_req = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) SRCH base="(.*)" scope=(%s) filter="(.*)" attrs=(?:(ALL)|"(.*)")' % (regex_num, regex_num, regex_num))
#[01/Jun/2012:17:53:14 -0600] conn=7 op=3 RESULT err=0 tag=101 nentries=1 etime=0
regex_srch_res = re.compile(r'^(\[.+\]) (conn=%s) (op=%s) RESULT err=(%s) tag=101 nentries=(%s) ' % (regex_num, regex_num, regex_num, regex_num))
# format for strptime
ts_fmt_access = '[%d/%b/%Y:%H:%M:%S -0600]'
ts_fmt_audit = '%Y%m%d%H%M%S'

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
            self.ts = int(time.mktime(time.strptime(tsstr, ts_fmt_access)))
        else:
            self.ts = 0
        self.conn = conn
        self.op = op
        if auditts:
            self.auditts = int(time.mktime(time.strptime(auditts, ts_fmt_audit)))
        else:
            self.auditts = 0
    def __cmp__(self, oth): return oth.ts - self.ts
    def __eq__(self, oth): return cmp(self, oth) == 0
    def __str__(self):
        return 'ts=%s auditts=%s %s %s' % (time.strftime(ts_fmt_access, time.localtime(self.ts)),
                                           time.strftime(ts_fmt_audit, time.localtime(self.auditts)),
                                           self.conn, self.op)
    def __repr__(self): return str(self)

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

class ModReq(DNReq):
    def __init__(self, dn=None, tsstr=None, conn=None, op=None, auditts=None, mods=None, match=None):
        if match:
            (tsstr, conn, op, dn) = match.groups()
        DNReq.__init__(self, dn, tsstr, conn, op, auditts)
        self.mods = mods
    def __str__(self):
        return DNReq.__str__(self) + ' MOD'
    def __repr__(self): return str(self)

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

class Res(object):
    def __init__(self, match=None):
        if match.lastindex == 4:
            ts, conn, op, errnum = match.groups()
        else:
            ts, conn, op = match.groups()
            errnum = '0'
        self.ts = int(time.mktime(time.strptime(ts, ts_fmt_access)))
        self.conn = conn
        self.op = op
        self.errnum = errnum
    def __str__(self):
        return 'RESULT ts=%s %s %s err=%s' % (time.strftime(ts_fmt_access, time.localtime(self.ts)),
                                              self.conn, self.op, self.errnum)
    def __repr__(self): return str(self)

class SrchRes(Res):
    def __init__(self, match=None):
        ts, conn, op, errnum, nentries = match.groups()
        self.ts = int(time.mktime(time.strptime(ts, ts_fmt_access)))
        self.conn = conn
        self.op = op
        self.errnum = errnum
        self.nentries = nentries
    def __str__(self):
        return Res.__str__(self) + ' nentries=' + self.nentries
    def __repr__(self): return str(self)

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
        self.ops = []
        self.sslinfo = ''
        self.ld = ldap.initialize(os.environ['LDAPURL'])
        self.autobind = False

    def addssl(self, sslinfo):
        if self.sslinfo and sslinfo:
            self.sslinfo += ' '
        self.sslinfo += sslinfo

    def findop(self, obj):
        for op in self.ops:
            if op.opid() == obj.op: return op
        return None

    def replayops(self):
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
        op = self.findop(req)
        if op:
            assert(op.req == None)
            op.req = req
            isclosed = self.replayops()
        else: # store request until we get the result
            op = Op(req=req)
            self.ops.append(op)
        return isclosed

    def addres(self, res):
        isclosed = False
        op = self.findop(res)
        if op:
            assert(op.res == None)
            op.res = res
            isclosed = self.replayops()
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
# val is ops hash
#  key is op=Y
#  value is list
#    list[0] is BIND request
#    list[1] is RESULT
conns = {}

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
    return rec and (len(rec) == 2) and ('time' in rec) and ('modifiersname' in rec)

def is_mdn(rec):
    return rec and (('newrdn' in rec) or ('deleteoldrdn' in rec) or ('newsuperior' in rec))

def is_add(rec):
    return rec and ('objectclass' in rec)

def parseRec(rec):
    tsstr = rec.get('time', [None])[0]
    if is_mod(rec):
        return (tsstr, ldap.REQ_MODIFY, ldif2mod(rec))
    if is_del(rec):
        return (tsstr, ldap.REQ_DELETE, None)
    if is_add(rec):
        return (tsstr, ldap.REQ_ADD, ldif2add(rec))
    if is_mdn(rec):
        return (tsstr, ldap.REQ_MODRDN, ldif2mdn(rec))
    raise Exception(str(rec) + " is an unknown type")

# ops from the audit log, indexed by timestamp
# key is timestamp, val is a list of ops
auditops = {}
def addAuditOp(req):
    auditops.setdefault(req.auditts, []).append(req)

def parseAudit(fname):
    f = open(fname)
    lrl = ldif.LDIFRecordList(f)
    lrl.parse()
    f.close()
    modlist = []
    savets = None
    savedn = None
    for dn,ent in lrl.all_records:
        ts, optype, data = parseRec(ldap.cidict.cidict(ent))
        if optype == ldap.REQ_MODIFY:
            if data[1]: # do not add stripped mods
                if dn:
                    if modlist:
                        addAuditOp(ModReq(savedn, auditts=savets, mods=modlist))
                    modlist, savets, savedn = ([data], ts, dn)
                else: # continuation
                    modlist.append(data)
            elif dn and not savedn: # but save ts and dn in case the first mod is stripped
                modlist, savets, savedn = ([], ts, dn)
        else:
            if modlist:
                addAuditOp(ModReq(dn, auditts=savets, mods=modlist))
            modlist, savets, savedn = ([], None, None)
            if optype == ldap.REQ_ADD:
                req = AddReq(dn, auditts=ts, ent=data)
            elif optype == ldap.REQ_MODRDN:
                req = MdnReq(dn, auditts=ts, newrdn=data.get('newrdn', None),
                             deleteoldrdn=data.get('deleteoldrdn', None),
                             newsuperior=data.get('newsuperior', None))
            elif optype == ldap.REQ_DELETE:
                req = DelReq(dn, auditts=ts)
            addAuditOp(req)
    if modlist and savedn and savets:
        addAuditOp(ModReq(savedn, auditts=savets, mods=modlist))

def findAuditReq(op):
    req = None
    reqlist = auditops.get(op.res.ts, [])
    for ii in xrange(0, len(reqlist)):
        req = reqlist[ii]
        if type(req) == type(op.req):
            req = reqlist.pop(ii)
            if len(reqlist) == 0:
                del auditops[op.res.ts]
            break
        else:
            req = None
    return req

regexmap = ((regex_bind_req, BindReq), (regex_bind_res, Res),
            (regex_add_req, AddReq), (regex_add_res, Res),
            (regex_mod_req, ModReq), (regex_mod_res, Res),
            (regex_mdn_req, MdnReq), (regex_mdn_res, Res),
            (regex_del_req, DelReq), (regex_del_res, Res),
            (regex_srch_req, SrchReq), (regex_srch_res, SrchRes),
            (regex_unbind, UnbindReq), (regex_closed, Res))

def parseAccessLine(line):
    # is this a new conn line?
    match = regex_new_conn.match(line)
    if match:
        (timestamp, connid, fdid, slotid, ip) = match.groups()
        if connid in conns: conns.pop(connid) # remove old one, if any
        conn = Conn(timestamp, connid, fdid, slotid, ip)
        conns[connid] = conn
        return True

    # is this an SSL info line?
    match = regex_sslinfo.match(line)
    if match:
        (connid, sslinfo) = match.groups()
        if connid in conns:
            conns[connid].addssl(sslinfo)
        else:
            raise Exception("ERROR: sslinfo " + sslinfo + " for " + connid + " but conn not found")
        return True

    # is this a line with extra SSL mapping info?
    match = regex_ssl_map_fail.match(line)
    if match:
        (connid, sslinfo) = match.groups()
        if connid in conns:
            conns[connid].addssl(sslinfo)
        else:
            raise Exception("ERROR: sslinfo " + sslinfo + " for " + connid + " but conn not found")
        return True

    # autobind
    match = regex_autobind.match(line)
    if match:
        (timestamp, connid, sslinfo) = match.groups()
        if connid in conns:
            conns[connid].autobind = True
        else:
            raise Exception("ERROR: autobind for " + connid + " but conn not found")
        return True

    for rx,clz in regexmap:
        match = rx.match(line)
        if match:
            obj = clz(match=match)
            # should have seen new conn line - if not, have to create a dummy one
            conn = conns.get(obj.conn, Conn('unknown', obj.conn, '', '', 'unknown'))
            if isinstance(obj, Req):
                isclosed = conn.addreq(obj)
            else:
                isclosed = conn.addres(obj)
            if isclosed: # unbind or closure
                conn = conns.pop(obj.conn) # remove it
                if conn.ld:
                    conn.ld.unbind_s()
                    conn.ld = None
            return True

    return True # no match

def parseAccess(fname, startoff, endoff):
    lineno = 0
    f = open(fname)
    for line in f:
        lineno = lineno + 1
        if lineno >= startoff and lineno <= endoff:
            parseAccessLine(line)
    f.close()

startoff = int(sys.argv[3])
endoff = int(sys.argv[4])

# if not audit log is provided, can only replay connect/bind/search requests
if sys.argv[2] and len(sys.argv[2]):
    parseAudit(sys.argv[2])
parseAccess(sys.argv[1], startoff, endoff)
