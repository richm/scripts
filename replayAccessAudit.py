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
            self.ts = int(time.mktime(time.strptime(ts, ts_fmt_access)))
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

def parseAudit(f, start=0, finish=sys.maxint):
    ap = AuditParser(f, min_entry=start, max_entries=finish)
    ap.parse()
    auditops.update(ap.auditops)

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

def parseAccess(f, startoff, endoff):
    lineno = 0
    for line in f:
        lineno = lineno + 1
        if lineno >= startoff and lineno <= endoff:
            parseAccessLine(line)

if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('-c', '--access', nargs='+', type=file, help='access log files - will be parsed in the order given', dest='c', default=[])
    parser.add_argument('-u', '--audit', nargs='+', type=file, help='audit log files - will be parsed in the order given', dest='u', default=[])
    parser.add_argument('-b', '--accessbegin', type=int, help='beginning access log line', default=0, dest='b')
    parser.add_argument('-e', '--accessend', type=int, help='ending access log line', default=sys.maxint, dest='e')
    parser.add_argument('-s', '--auditstart', type=int, help='starting audit log record number', default=0, dest='s')
    parser.add_argument('-f', '--auditfinish', type=int, help='ending audit log record number', default=sys.maxint, dest='f')
    parser.add_argument('-v', action='count', help='repeat for more verbosity', default=0, dest='v')
    args = parser.parse_args()

    if len(args.c) == 0 and len(args.u) == 0:
        print "Error: no audit or access logs given"
        sys.exit(1)

    for ii in xrange(0, len(args.u)):
        start, finish = (0, sys.maxint)
        if ii == 0: start = args.s
        if ii == len(args.u)-1: finish = args.f
        parseAudit(args.u[ii], start, finish)

    naccess = len(args.c)
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
        begin, end = (0, sys.maxint)
        if ii == 0: begin = args.b
        if ii == naccess-1: end = args.e
        parseAccess(args.c[ii], begin, end)
