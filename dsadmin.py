"""The dsadmin module.


    IMPORTANT: Ternary operator syntax is unsupported on RHEL5
        x if cond else y #don't!
        

"""

import sys
import os
import os.path
HASPOPEN = True
try:
    from subprocess import Popen, PIPE, STDOUT
except ImportError:
    import popen2
    HASPOPEN = False
import base64
import urllib
import urllib2
import socket
import ldif
import re
import ldap
import cStringIO
import time
import operator
import shutil
import datetime
import select

from ldap.ldapobject import SimpleLDAPObject
from ldapurl import LDAPUrl

REPLBINDDN = ''
REPLBINDPW = ''
REPLICAID = 1  # the initial replica ID

# replicatype @see https://access.redhat.com/knowledge/docs/en-US/Red_Hat_Directory_Server/8.1/html/Administration_Guide/Managing_Replication-Configuring-Replication-cmd.html
# 2 for consumers and hubs (read-only replicas)
# 3 for both single and multi-master suppliers (read-write replicas)
# TODO: let's find a way to be consistent - eg. using bitwise operator
(MASTER_TYPE,
 HUB_TYPE,
 LEAF_TYPE) = range(3)

REPLICA_RDONLY_TYPE = 2  # CONSUMER and HUB
REPLICA_WRONLY_TYPE = 1  # SINGLE and MULTI MASTER
REPLICA_RDWR_TYPE = REPLICA_RDONLY_TYPE | REPLICA_WRONLY_TYPE

DBMONATTRRE = re.compile(r'^([a-zA-Z]+)-([1-9][0-9]*)$')
DBMONATTRRESUN = re.compile(r'^([a-zA-Z]+)-([a-zA-Z]+)$')


class Error(Exception):
    pass


class InvalidArgumentError(Error):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class NoSuchEntryError(Error):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return self.message


class Entry:
    """This class represents an LDAP Entry object.

        An LDAP entry consists of a DN and a list of attributes.
        Each attribute consists of a name and a list of values.
        In python-ldap, entries are returned as a list of 2-tuples.
        Instance variables:
          dn - string - the string DN of the entry
          data - cidict - case insensitive dict of the attributes and values
    """

    def __init__(self, entrydata):
        """entrydata is the raw data returned from the python-ldap
        result method, which is:
            * a search result entry     -> (dn, {dict...} )
            * or a reference            -> (None, reference)
            * or None.

        If creating a new empty entry, data is the string DN.
        """
        self.ref = None
        if entrydata:
            if isinstance(entrydata, tuple):
                if entrydata[0] is None:
                    self.ref = entrydata[1]  # continuation reference
                else:
                    self.dn = entrydata[0]
                    self.data = ldap.cidict.cidict(entrydata[1])
            elif isinstance(entrydata, basestring):
                self.dn = entrydata
                self.data = ldap.cidict.cidict()
        else:
            #
            self.dn = ''
            self.data = ldap.cidict.cidict()

    def __nonzero__(self):
        """This allows us to do tests like if entry: returns false if there is no data,
        true otherwise"""
        return self.data is not None and len(self.data) > 0

    def hasAttr(self, name):
        """Return True if this entry has an attribute named name, False otherwise"""
        return self.data and name in self.data

    def __getattr__(self, name):
        """If name is the name of an LDAP attribute, return the first value for that
        attribute - equivalent to getValue - this allows the use of
        entry.cn
        instead of
        entry.getValue('cn')
        This also allows us to return None if an attribute is not found rather than
        throwing an exception"""
        if name == 'dn' or name == 'data':
            return self.__dict__.get(name, None)
        return self.getValue(name)

    def getValues(self, name):
        """Get the list (array) of values for the attribute named name"""
        return self.data.get(name, [])

    def getValue(self, name):
        """Get the first value for the attribute named name"""
        return self.data.get(name, [None])[0]

    def hasValue(self, name, val=None):
        """True if the given attribute is present and has the given value"""
        if not self.hasAttr(name):
            return False
        if not val:
            return True
        if isinstance(val, list):
            return val == self.data.get(name)
        if isinstance(val, tuple):
            return list(val) == self.data.get(name)
        return val in self.data.get(name)

    def hasValueCase(self, name, val):
        """True if the given attribute is present and has the given value - case insensitive value match"""
        if not self.hasAttr(name):
            return False
        return val.lower() in [x.lower() for x in self.data.get(name)]

    def setValue(self, name, *value):
        """Value passed in may be a single value, several values, or a single sequence.
        For example:
           ent.setValue('name', 'value')
           ent.setValue('name', 'value1', 'value2', ..., 'valueN')
           ent.setValue('name', ['value1', 'value2', ..., 'valueN'])
           ent.setValue('name', ('value1', 'value2', ..., 'valueN'))
        Since *value is a tuple, we may have to extract a list or tuple from that
        tuple as in the last two examples above"""
        if isinstance(value[0], list) or isinstance(value[0], tuple):
            self.data[name] = value[0]
        else:
            self.data[name] = value

    def getAttrs(self):
        if not self.data:
            return []
        return self.data.keys()

    def iterAttrs(self, attrsOnly=False):
        if attrsOnly:
            return self.data.iterkeys()
        else:
            return self.data.iteritems()

    setValues = setValue

    def toTupleList(self):
        """Convert the attrs and values to a list of 2-tuples.  The first element
        of the tuple is the attribute name.  The second element is either a
        single value or a list of values."""
        return self.data.items()

    def getref(self):
        return self.ref

    def __str__(self):
        """Convert the Entry to its LDIF representation"""
        return self.__repr__()

    # the ldif class base64 encodes some attrs which I would rather see in raw form - to
    # encode specific attrs as base64, add them to the list below
    ldif.safe_string_re = re.compile('^$')
    base64_attrs = ['nsstate']

    def __repr__(self):
        """Convert the Entry to its LDIF representation"""
        sio = cStringIO.StringIO()
        # what's all this then?  the unparse method will currently only accept
        # a list or a dict, not a class derived from them.  self.data is a
        # cidict, so unparse barfs on it.  I've filed a bug against python-ldap,
        # but in the meantime, we have to convert to a plain old dict for printing
        # I also don't want to see wrapping, so set the line width really high (1000)
        newdata = {}
        newdata.update(self.data)
        ldif.LDIFWriter(
            sio, Entry.base64_attrs, 1000).unparse(self.dn, newdata)
        return sio.getvalue()


class CSN:
    """CSN is Change Sequence Number
        csn.ts is the timestamp (time_t - seconds)
        csn.seq is the sequence number (max 65535)
        csn.rid is the replica ID of the originating master
        csn.subseq is not currently used"""
    csnpat = r'(.{8})(.{4})(.{4})(.{4})'
    csnre = re.compile(csnpat)

    def __init__(self, csnstr):
        match = CSN.csnre.match(csnstr)
        self.ts = 0
        self.seq = 0
        self.rid = 0
        self.subseq = 0
        if match:
            self.ts = int(match.group(1), 16)
            self.seq = int(match.group(2), 16)
            self.rid = int(match.group(3), 16)
            self.subseq = int(match.group(4), 16)
        elif csnstr:
            self.ts = 0
            self.seq = 0
            self.rid = 0
            self.subseq = 0
            print csnstr, "is not a valid CSN"

    def csndiff(self, oth):
        return (oth.ts - self.ts, oth.seq - self.seq, oth.rid - self.rid, oth.subseq - self.subseq)

    def __cmp__(self, oth):
        if self is oth:
            return 0
        (tsdiff, seqdiff, riddiff, subseqdiff) = self.csndiff(oth)

        diff = tsdiff or seqdiff or riddiff or subseqdiff
        ret = 0
        if diff > 0:
            ret = 1
        elif diff < 0:
            ret = -1
        return ret

    def __eq__(self, oth):
        return cmp(self, oth) == 0

    def diff2str(self, oth):
        retstr = ''
        diff = oth.ts - self.ts
        if diff > 0:
            td = datetime.timedelta(seconds=diff)
            retstr = "is behind by %s" % td
        elif diff < 0:
            td = datetime.timedelta(seconds=-diff)
            retstr = "is ahead by %s" % td
        else:
            diff = oth.seq - self.seq
            if diff:
                retstr = "seq differs by %d" % diff
            elif self.rid != oth.rid:
                retstr = "rid %d not equal to rid %d" % (self.rid, oth.rid)
            else:
                retstr = "equal"
        return retstr

    def __repr__(self):
        return time.strftime("%x %X", time.localtime(self.ts)) + " seq: " + str(self.seq) + " rid: " + str(self.rid)

    def __str__(self):
        return self.__repr__()


class RUV:
    """RUV is Replica Update Vector
        ruv.gen is the generation CSN
        ruv.rid[1] through ruv.rid[N] are dicts - the number (1-N) is the replica ID
          ruv.rid[N][url] is the purl
          ruv.rid[N][min] is the min csn
          ruv.rid[N][max] is the max csn
          ruv.rid[N][lastmod] is the last modified timestamp
        example ruv attr:
        nsds50ruv: {replicageneration} 3b0ebc7f000000010000
        nsds50ruv: {replica 1 ldap://myhost:51010} 3b0ebc9f000000010000 3b0ebef7000000010000
        nsruvReplicaLastModified: {replica 1 ldap://myhost:51010} 292398402093
        if the tryrepl flag is true, if getting the ruv from the suffix fails, try getting
        the ruv from the cn=replica entry
    """
    genpat = r'\{replicageneration\}\s+(\w+)'
    genre = re.compile(genpat)
    ruvpat = r'\{replica\s+(\d+)\s+(.+?)\}\s*(\w*)\s*(\w*)'
    ruvre = re.compile(ruvpat)

    def __init__(self, ent):
        # rid is a dict
        # key is replica ID - val is dict of url, min csn, max csn
        self.rid = {}
        for item in ent.getValues('nsds50ruv'):
            matchgen = RUV.genre.match(item)
            matchruv = RUV.ruvre.match(item)
            if matchgen:
                self.gen = CSN(matchgen.group(1))
            elif matchruv:
                rid = int(matchruv.group(1))
                self.rid[rid] = {'url': matchruv.group(2),
                                 'min': CSN(matchruv.group(3)),
                                 'max': CSN(matchruv.group(4))}
            else:
                print "unknown RUV element", item
        for item in ent.getValues('nsruvReplicaLastModified'):
            matchruv = RUV.ruvre.match(item)
            if matchruv:
                rid = int(matchruv.group(1))
                self.rid[rid]['lastmod'] = int(matchruv.group(3), 16)
            else:
                print "unknown nsruvReplicaLastModified item", item

    def __cmp__(self, oth):
        if self is oth:
            return 0
        if not self:
            return -1  # None is less than something
        if not oth:
            return 1  # something is greater than None
        diff = cmp(self.gen, oth.gen)
        if diff:
            return diff
        for rid in self.rid.keys():
            for item in ('max', 'min'):
                csn = self.rid[rid][item]
                csnoth = oth.rid[rid][item]
                diff = cmp(csn, csnoth)
                if diff:
                    return diff
        return 0

    def __eq__(self, oth):
        return cmp(self, oth) == 0

    def getdiffs(self, oth):
        """Compare two ruvs and return the differences
        returns a tuple - the first element is the
        result of cmp() - the second element is a string"""
        if self is oth:
            return (0, "\tRUVs are the same")
        if not self:
            return (-1, "\tfirst RUV is empty")
        if not oth:
            return (1, "\tsecond RUV is empty")
        diff = cmp(self.gen, oth.gen)
        if diff:
            return (diff, "\tgeneration [" + str(self.gen) + "] not equal to [" + str(oth.gen) + "]: likely not yet initialized")
        retstr = ''
        for rid in self.rid.keys():
            for item in ('max', 'min'):
                csn = self.rid[rid][item]
                csnoth = oth.rid[rid][item]
                csndiff = cmp(csn, csnoth)
                if csndiff:
                    if len(retstr):
                        retstr += "\n"
                    retstr += "\trid %d %scsn %s\n\t[%s] vs [%s]" % (rid, item, csn.diff2str(csnoth),
                                                                     csn, csnoth)
                    if not diff:
                        diff = csndiff
        if not diff:
            retstr = "\tup-to-date - RUVs are equal"
        return (diff, retstr)


def wrapper(f, name):
    """This is the method that wraps all of the methods of the superclass.  This seems
    to need to be an unbound method, that's why it's outside of DSAdmin.  Perhaps there
    is some way to do this with the new classmethod or staticmethod of 2.4.
    Basically, we replace every call to a method in SimpleLDAPObject (the superclass
    of DSAdmin) with a call to inner.  The f argument to wrapper is the bound method
    of DSAdmin (which is inherited from the superclass).  Bound means that it will implicitly
    be called with the self argument, it is not in the args list.  name is the name of
    the method to call.  If name is a method that returns entry objects (e.g. result),
    we wrap the data returned by an Entry class.  If name is a method that takes an entry
    argument, we extract the raw data from the entry object to pass in."""
    def inner(*args, **kargs):
        if name == 'result':
            objtype, data = f(*args, **kargs)
            # data is either a 2-tuple or a list of 2-tuples
            # print data
            if data:
                if isinstance(data, tuple):
                    return objtype, Entry(data)
                elif isinstance(data, list):
                    # AD sends back these search references
#                     if objtype == ldap.RES_SEARCH_RESULT and \
#                        isinstance(data[-1],tuple) and \
#                        not data[-1][0]:
#                         print "Received search reference: "
#                         pprint.pprint(data[-1][1])
#                         data.pop() # remove the last non-entry element

                    return objtype, [Entry(x) for x in data]
                else:
                    raise TypeError("unknown data type %s returned by result" %
                                    type(data))
            else:
                return objtype, data
        elif name.startswith('add'):
            # the first arg is self
            # the second and third arg are the dn and the data to send
            # We need to convert the Entry into the format used by
            # python-ldap
            ent = args[0]
            if isinstance(ent, Entry):
                return f(ent.dn, ent.toTupleList(), *args[2:])
            else:
                return f(*args, **kargs)
        else:
            return f(*args, **kargs)
    return inner


class LDIFConn(ldif.LDIFParser):
    def __init__(
        self,
        input_file,
        ignored_attr_types=None, max_entries=0, process_url_schemes=None
    ):
        """
        See LDIFParser.__init__()

        Additional Parameters:
        all_records
        List instance for storing parsed records
        """
        self.dndict = {}  # maps dn to Entry
        self.dnlist = []  # contains entries in order read
        myfile = input_file
        if isinstance(input_file, basestring):
            myfile = open(input_file, "r")
        ldif.LDIFParser.__init__(self, myfile, ignored_attr_types,
                                 max_entries, process_url_schemes)
        self.parse()
        if isinstance(input_file, basestring):
            myfile.close()

    def handle(self, dn, entry):
        """
        Append single record to dictionary of all records.
        """
        if not dn:
            dn = ''
        newentry = Entry((dn, entry))
        self.dndict[DSAdmin.normalizeDN(dn)] = newentry
        self.dnlist.append(newentry)

    def get(self, dn):
        ndn = DSAdmin.normalizeDN(dn)
        return self.dndict.get(ndn, Entry(None))


class DSAdmin(SimpleLDAPObject):
    CFGSUFFIX = "o=NetscapeRoot"
    DEFAULT_USER_ID = "nobody"

    def getDseAttr(self, attrname):
        conffile = self.confdir + '/dse.ldif'
        try:
            dseldif = LDIFConn(conffile)
            cnconfig = dseldif.get("cn=config")
            if cnconfig:
                return cnconfig.getValue(attrname)
        except IOError, err:
            print "could not read dse config file", err
        return None

    def __initPart2(self):
        """Initialize the DSAdmin structure filling various fields, like:
            - dbdir
            - errlog
            - confdir

        """
        if self.binddn and len(self.binddn) and not hasattr(self, 'sroot'):
            try:
                ent = self.getEntry(
                    'cn=config', ldap.SCOPE_BASE, '(objectclass=*)',
                    ['nsslapd-instancedir', 'nsslapd-errorlog',
                     'nsslapd-certdir', 'nsslapd-schemadir'])
                self.errlog = ent.getValue('nsslapd-errorlog')
                self.confdir = ent.getValue('nsslapd-certdir')
                if self.isLocal:
                    if not self.confdir or not os.access(self.confdir + '/dse.ldif', os.R_OK):
                        self.confdir = ent.getValue('nsslapd-schemadir')
                        if self.confdir:
                            self.confdir = os.path.dirname(self.confdir)
                instdir = ent.getValue('nsslapd-instancedir')
                if not instdir and self.isLocal:
                    # get instance name from errorlog
                    self.inst = re.match(
                        r'(.*)[\/]slapd-([^/]+)/errors', self.errlog).group(2)
                    if self.isLocal and self.confdir:
                        instdir = self.getDseAttr('nsslapd-instancedir')
                    else:
                        instdir = re.match(r'(.*/slapd-.*)/logs/errors',
                                           self.errlog).group(1)
                if not instdir:
                    instdir = self.confdir
                if self.verbose:
                    print "instdir=", instdir
                    print ent
                match = re.match(r'(.*)[\/]slapd-([^/]+)$', instdir)
                if match:
                    self.sroot, self.inst = match.groups()
                else:
                    self.sroot = self.inst = ''
                ent = self.getEntry(
                    'cn=config,cn=ldbm database,cn=plugins,cn=config',
                    ldap.SCOPE_BASE, '(objectclass=*)',
                    ['nsslapd-directory'])
                self.dbdir = os.path.dirname(ent.getValue('nsslapd-directory'))
            except (ldap.INSUFFICIENT_ACCESS, ldap.CONNECT_ERROR, NoSuchEntryError):
                pass  # usually means
#                print "ignored exception"
            except ldap.OPERATIONS_ERROR, e:
                print "caught exception ", e
                print "Probably Active Directory, pass"
            except ldap.LDAPError, e:
                print "caught exception ", e
                raise

    def __localinit__(self):
        if self.sslport:
            proto = 'ldaps'
            self.port = self.sslport
        else:
            proto = 'ldap'

        SimpleLDAPObject.__init__(
            self, '%s://%s:%d' % (proto, self.host, self.port))

        # see if binddn is a dn or a uid that we need to lookup
        if self.binddn and not DSAdmin.is_a_dn(self.binddn):
            self.simple_bind_s("", "")  # anon
            ent = self.getEntry(DSAdmin.CFGSUFFIX, ldap.SCOPE_SUBTREE,
                                "(uid=%s)" % self.binddn,
                                ['uid'])
            if ent:
                self.binddn = ent.dn
            else:
                print "Error: could not find %s under %s" % (
                    self.binddn, DSAdmin.CFGSUFFIX)
        if not self.nobind:
            needtls = False
            while True:
                try:
                    if needtls:
                        self.start_tls_s()
                    self.simple_bind_s(self.binddn, self.bindpw)
                    break
                except ldap.CONFIDENTIALITY_REQUIRED:
                    needtls = True
            self.__initPart2()

    def __init__(self, host, port, binddn='', bindpw='', nobind=False, sslport=0):  # default to anon bind
        """We just set our instance variables and wrap the methods - the real work is
        done in __localinit__ and __initPart2 - these are separated out this way so
        that we can call them from places other than instance creation e.g. when
        using the start command, we just need to reconnect, not create a new instance"""
        self.__wrapmethods()
        self.verbose = False
        self.port = port or 389
        self.sslport = sslport
        self.host = host
        self.binddn = binddn
        self.bindpw = bindpw
        self.nobind = nobind
        self.isLocal = DSAdmin.isLocalHost(host)
        self.suffixes = {}
        self.agmt = {}
        self.__localinit__()

    def __str__(self):
        return self.host + ":" + str(self.port)

    def toLDAPURL(self):
        return "ldap://%s:%d/" % (self.host, self.port)

    def getEntry(self, *args):
        """This wraps the search function.  It is common to just get one entry"""
        res = self.search(*args)
        restype, obj = self.result(res)
        # TODO: why not test restype?
        if not obj:
            raise NoSuchEntryError("no such entry for " + str(args) + "\n")
        elif isinstance(obj, Entry):
            return obj
        else:  # assume list/tuple
            return obj[0]

    def __wrapmethods(self):
        """This wraps all methods of SimpleLDAPObject, so that we can intercept
        the methods that deal with entries.  Instead of using a raw list of tuples
        of lists of hashes of arrays as the entry object, we want to wrap entries
        in an Entry class that provides some useful methods"""
        for name in dir(self.__class__.__bases__[0]):
            attr = getattr(self, name)
            if callable(attr):
                setattr(self, name, wrapper(attr, name))

    def serverCmd(self, cmd, verbose, timeout):
        instanceDir = self.sroot + "/slapd-" + self.inst
        errLog = instanceDir + '/logs/errors'
        if hasattr(self, 'errlog'):
            errLog = self.errlog
        done = False
        started = True
        lastLine = ""
        cmd = cmd.lower()
        fullCmd = instanceDir + "/" + cmd + "-slapd"
        if cmd == 'start':
            cmdPat = 'slapd started.'
        else:
            cmdPat = 'slapd stopped.'

        timeout = timeout or 120  # default is 120 seconds
        if "USE_GDB" in os.environ or "USE_VALGRIND" in os.environ:
            timeout = timeout * 3
        timeout = int(time.time()) + timeout
        if cmd == 'stop':
            self.unbind()
        logfp = open(errLog, 'r')
        logfp.seek(0, 2)  # seek to end
        pos = logfp.tell()  # get current position
        logfp.seek(pos, 0)  # reset the EOF flag
        rc = os.system(fullCmd)
        while not done and int(time.time()) < timeout:
            line = logfp.readline()
            while not done and line:
                lastLine = line
                if verbose:
                    print line.strip()
                if line.find(cmdPat) >= 0:
                    started += 1
                    if started == 2:
                        done = True
                elif line.find("Initialization Failed") >= 0:
                    # sometimes the server fails to start - try again
                    rc = os.system(fullCmd)
                elif line.find("exiting.") >= 0:
                    # possible transient condition - try again
                    rc = os.system(fullCmd)
                pos = logfp.tell()
                line = logfp.readline()
            if line.find("PR_Bind") >= 0:
                # server port conflicts with another one, just report and punt
                print lastLine.strip()
                print "This server cannot be started until the other server on this"
                print "port is shutdown"
                done = True
            if not done:
                time.sleep(2)
                logfp.seek(pos, 0)
        logfp.close()
        if started < 2:
            now = int(time.time())
            if now > timeout:
                print "Probable timeout: timeout=%d now=%d" % (timeout, now)
            if verbose:
                print "Error: could not %s server %s %s: %d" % (
                    cmd, self.sroot, self.inst, rc)
            return 1
        else:
            if verbose:
                print "%s was successful for %s %s" % (
                    cmd, self.sroot, self.inst)
            if cmd == 'start':
                self.__localinit__()
        return 0

    def stop(self, verbose=False, timeout=0):
        if not self.isLocal and hasattr(self, 'asport'):
            if verbose:
                print "stopping remote server ", self
            self.unbind()
            if verbose:
                print "closed remote server ", self
            cgiargs = {}
            rc = DSAdmin.cgiPost(self.host, self.asport, self.cfgdsuser,
                                 self.cfgdspwd,
                                 "/slapd-%s/Tasks/Operation/stop" % self.inst,
                                 verbose, cgiargs)
            if verbose:
                print "stopped remote server %s rc = %d" % (self, rc)
            return rc
        else:
            return self.serverCmd('stop', verbose, timeout)

    def start(self, verbose=False, timeout=0):
        if not self.isLocal and hasattr(self, 'asport'):
            if verbose:
                print "starting remote server ", self
            cgiargs = {}
            rc = DSAdmin.cgiPost(self.host, self.asport, self.cfgdsuser,
                                 self.cfgdspwd,
                                 "/slapd-%s/Tasks/Operation/start" % self.inst,
                                 verbose, cgiargs)
            if verbose:
                print "connecting remote server", self
            if not rc:
                self.__localinit__()
            if verbose:
                print "started remote server %s rc = %d" % (self, rc)
            return rc
        else:
            return self.serverCmd('start', verbose, timeout)

    def startTask(self, entry, verbose=False):
        # start the task
        dn = entry.dn
        self.add_s(entry)
        entry = self.getEntry(dn, ldap.SCOPE_BASE)
        if not entry:
            if verbose:
                print "Entry %s was added successfully, but I cannot search it" % dn
                return False
        elif verbose:
            print entry
        return True

    def checkTask(self, entry, dowait=False, verbose=False):
        '''check task status - task is complete when the nsTaskExitCode attr is set
        return a 2 tuple (true/false,code) first is false if task is running, true if
        done - if true, second is the exit code - if dowait is True, this function
        will block until the task is complete'''
        attrlist = ['nsTaskLog', 'nsTaskStatus', 'nsTaskExitCode',
                    'nsTaskCurrentItem', 'nsTaskTotalItems']
        done = False
        exitCode = 0
        dn = entry.dn
        while not done:
            entry = self.getEntry(
                dn, ldap.SCOPE_BASE, "(objectclass=*)", attrlist)
            if verbose:
                print entry
            if entry.nsTaskExitCode:
                exitCode = int(entry.nsTaskExitCode)
                done = True
            if dowait:
                time.sleep(1)
            else:
                break
        return (done, exitCode)

    def startTaskAndWait(self, entry, verbose=False):
        self.startTask(entry, verbose)
        (done, exitCode) = self.checkTask(entry, True, verbose)
        return exitCode

    def importLDIF(self, ldiffile, suffix, be=None, verbose=False):
        cn = "import" + str(int(time.time()))
        dn = "cn=%s,cn=import,cn=tasks,cn=config" % cn
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'extensibleObject')
        entry.setValues('cn', cn)
        entry.setValues('nsFilename', ldiffile)
        if be:
            entry.setValues('nsInstance', be)
        else:
            entry.setValues('nsIncludeSuffix', suffix)

        rc = self.startTaskAndWait(entry, verbose)

        if rc:
            if verbose:
                print "Error: import task %s for file %s exited with %d" % (
                    cn, ldiffile, rc)
        else:
            if verbose:
                print "Import task %s for file %s completed successfully" % (
                    cn, ldiffile)
        return rc

    def exportLDIF(self, ldiffile, suffix, be=None, forrepl=False, verbose=False):
        cn = "export" + str(int(time.time()))
        dn = "cn=%s,cn=export,cn=tasks,cn=config" % cn
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'extensibleObject')
        entry.setValues('cn', cn)
        entry.setValues('nsFilename', ldiffile)
        if be:
            entry.setValues('nsInstance', be)
        else:
            entry.setValues('nsIncludeSuffix', suffix)
        if forrepl:
            entry.setValues('nsExportReplica', 'true')

        rc = self.startTaskAndWait(entry, verbose)

        if rc:
            if verbose:
                print "Error: export task %s for file %s exited with %d" % (
                    cn, ldiffile, rc)
        else:
            if verbose:
                print "Export task %s for file %s completed successfully" % (
                    cn, ldiffile)
        return rc

    def createIndex(self, suffix, attr, verbose=False):
        cn = "index" + str(int(time.time()))
        dn = "cn=%s,cn=index,cn=tasks,cn=config" % cn
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'extensibleObject')
        entry.setValues('cn', cn)
        entry.setValues('nsIndexAttribute', attr)
        beents = self.getBackendsForSuffix(suffix, ['cn'])
        # assume 1 local backend
        entry.setValues('nsInstance', beents[0].cn)
        rc = self.startTaskAndWait(entry, verbose)

        if rc:
            if verbose:
                print "Error: index task %s for file %s exited with %d" % (
                    cn, ldiffile, rc)
        else:
            if verbose:
                print "Index task %s for file %s completed successfully" % (
                    cn, ldiffile)
        return rc

    def fixupMemberOf(self, suffix, filt=None, verbose=False):
        cn = "fixupmemberof" + str(int(time.time()))
        dn = "cn=%s,cn=memberOf task,cn=tasks,cn=config" % cn
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'extensibleObject')
        entry.setValues('cn', cn)
        entry.setValues('basedn', suffix)
        if filt:
            entry.setValues('filter', filt)
        rc = self.startTaskAndWait(entry, verbose)

        if rc:
            if verbose:
                print "Error: fixupMemberOf task %s for basedn %s exited with %d" % (cn, suffix, rc)
        else:
            if verbose:
                print "fixupMemberOf task %s for basedn %s completed successfully" % (cn, suffix)
        return rc

    def addLDIF(self, input_file, cont=False):
        class LDIFAdder(ldif.LDIFParser):
            def __init__(self, input_file, conn, cont=False,
                         ignored_attr_types=None, max_entries=0, process_url_schemes=None
                         ):
                myfile = input_file
                if isinstance(input_file, basestring):
                    myfile = open(input_file, "r")
                self.conn = conn
                self.cont = cont
                ldif.LDIFParser.__init__(self, myfile, ignored_attr_types,
                                         max_entries, process_url_schemes)
                self.parse()
                if isinstance(input_file, basestring):
                    myfile.close()

            def handle(self, dn, entry):
                if not dn:
                    dn = ''
                newentry = Entry((dn, entry))
                try:
                    self.conn.add_s(newentry)
                except ldap.LDAPError, e:
                    if not self.cont:
                        raise e
                    print "Error: could not add entry %s: error %s" % (
                        dn, str(e))

        adder = LDIFAdder(input_file, self, cont)

    def getSuffixes(self):
        ents = self.search_s("cn=mapping tree,cn=config", ldap.SCOPE_ONELEVEL)
        sufs = []
        for ent in ents:
            unquoted = None
            quoted = None
            for val in ent.getValues('cn'):
                if val.find('"') < 0:  # prefer the one that is not quoted
                    unquoted = val
                else:
                    quoted = val
            if unquoted:  # preferred
                sufs.append(unquoted)
            elif quoted:  # strip
                sufs.append(quoted.strip('"'))
            else:
                raise Exception(
                    "Error: mapping tree entry " + ent.dn + " has no suffix")
        return sufs

    def setupBackend(self, suffix, binddn=None, bindpw=None, urls=None, attrvals={}, benamebase=None):
        ldbmdn = "cn=ldbm database,cn=plugins,cn=config"
        chaindn = "cn=chaining database,cn=plugins,cn=config"
        dnbase = ""
        # if benamebase is set, try creating without appending
        if benamebase:
            benum = 0
        else:
            benum = 1
        verbose = False

        # figure out what type of be based on args
        if binddn and bindpw and urls:  # its a chaining be
            benamebase = benamebase or "chaindb"
            dnbase = chaindn
        else:  # its a ldbm be
            benamebase = benamebase or "localdb"
            dnbase = ldbmdn

        print "benamebase: " + benamebase
        nsuffix = DSAdmin.normalizeDN(suffix)
        done = False
        while not done:
            try:
                # if benamebase is set, benum starts at 0
                # and the first attempt tries to create the
                # simple benamebase. On failure benum is
                # incremented and the suffix is appended
                # to the cn
                if benum:
                                cn = benamebase + str(benum)  # e.g. localdb1
                else:
                                cn = benamebase
                print "create backend with cn: %s" % cn
                dn = "cn=" + cn + "," + dnbase
                entry = Entry(dn)
                entry.setValues('objectclass', 'top',
                                'extensibleObject', 'nsBackendInstance')
                entry.setValues('cn', cn)
                entry.setValues('nsslapd-suffix', nsuffix)
                if binddn and bindpw and urls:  # its a chaining be
                    entry.setValues('nsfarmserverurl', urls)
                    entry.setValues('nsmultiplexorbinddn', binddn)
                    entry.setValues('nsmultiplexorcredentials', bindpw)
                else:  # set ldbm parameters, if any
                    pass
                    #     $entry->add('nsslapd-cachesize' => '-1');
                    #     $entry->add('nsslapd-cachememsize' => '2097152');

                # set attrvals (but not cn, because it's in dn)
                if attrvals:
                    for attr, val in attrvals.items():
                        if verbose:
                            print "adding %s = %s to entry %s" % (
                                attr, val, dn)
                        entry.setValues(attr, val)
                if verbose:
                    print entry
                self.add_s(entry)
                done = True
            except ldap.ALREADY_EXISTS:
                benum += 1
            except ldap.LDAPError, e:
                print "Could not add backend entry " + dn, e
                raise
        if verbose:
            entry = self.getEntry(dn, ldap.SCOPE_BASE)
            if not entry:
                print "Backend entry added, but could not be searched"
                return ""
            else:
                print entry
        return cn

    def setupSuffix(self, suffix, bename, parent=""):
        """Setup a suffix with the given backend-name.

            This method does not create the matching entry in the tree.
            Ex. setupSuffix(suffix='o=addressbook1', bename='addressbook1')
                creates:
                    - the addressbook1 backend-name and file
                    - the mapping in "cn=mapping tree,cn=config"
                you have to create:
                    - the ldap entry "o=addressbook1"
        """
        rc = 0
        verbose = False
        nsuffix = DSAdmin.normalizeDN(suffix)
        #escapedn = DSAdmin.escapeDNValue(nsuffix)
        nparent = ""
        if parent:
            nparent = DSAdmin.normalizeDN(parent)
        filt = DSAdmin.suffixfilt(suffix)
        try:
            entry = self.getEntry(
                "cn=mapping tree,cn=config", ldap.SCOPE_SUBTREE, filt)
        except NoSuchEntryError:
            entry = None
        if not entry:
            # fix me when we can actually used escaped DNs
            #dn = "cn=%s,cn=mapping tree,cn=config" % escapedn
            dn = 'cn="%s",cn=mapping tree,cn=config' % nsuffix
            entry = Entry(dn)
            entry.setValues(
                'objectclass', 'top', 'extensibleObject', 'nsMappingTree')
            #entry.setValues('cn', [escapedn, nsuffix]) # the value in the dn has to be DN escaped
            # the other value can be the unescaped value
            entry.setValues('cn', nsuffix)  # internal code will add the quoted value - unquoted value is useful for searching
            entry.setValues('nsslapd-state', 'backend')
            entry.setValues('nsslapd-backend', bename)
            if parent:
                entry.setValues('nsslapd-parent-suffix', nparent)
            try:
                self.add_s(entry)
                if verbose:
                    entry = self.getEntry(dn, ldap.SCOPE_BASE)
                    if not entry:
                        print "Entry %s was added successfully, but I cannot search it" % dn
                        rc = -1
                    else:
                        print entry
            except ldap.LDAPError, e:
                print "Error adding suffix entry " + dn, e
                raise
        else:
            if verbose:
                print "Suffix entry already exists:"
                print entry

        return rc

    def getMTEntry(self, suffix, attrs=[]):
        """Given a suffix, return the mapping tree entry for it.  If attrs is
        given, only fetch those attributes, otherwise, get all attributes.

        TODO: returned None if not found. Now raises
        """
        filt = DSAdmin.suffixfilt(suffix)
        entry = None
        try:
            entry = self.getEntry(
                "cn=mapping tree,cn=config", ldap.SCOPE_ONELEVEL, filt, attrs)
        except NoSuchEntryError:
            # TODO why not raise here?
            print ("Cannot find suffix in mapping tree: %r " % suffix)
            pass
        except ldap.FILTER_ERROR, e:
            print "Error searching for", filt
            raise e
        return entry

    def getBackendsForSuffix(self, suffix, attrs=[]):
        nsuffix = DSAdmin.normalizeDN(suffix)
        try:
            entries = self.search_s("cn=plugins,cn=config", ldap.SCOPE_SUBTREE,
                                    "(&(objectclass=nsBackendInstance)(|(nsslapd-suffix=%s)(nsslapd-suffix=%s)))" % (suffix, nsuffix),
                                    attrs)
        except NoSuchEntryError:
            pass
        return entries

    def getSuffixForBackend(self, bename, attrs=[]):
        """given a backend name, return the mapping tree entry for it"""
        try:
            entry = self.getEntry("cn=plugins,cn=config", ldap.SCOPE_SUBTREE,
                                  "(&(objectclass=nsBackendInstance)(cn=%s))" % bename,
                                  ['nsslapd-suffix'])
        except NoSuchEntryError:
            print "Could not find an entry for backend", bename
        if entry:
            suffix = entry.getValue('nsslapd-suffix')
            return self.getMTEntry(suffix, attrs)
        return None

    def findParentSuffix(self, suffix):
        """see if the given suffix has a parent suffix"""
        rdns = ldap.explode_dn(suffix)
        del rdns[0]

        while len(rdns) > 0:
            suffix = ','.join(rdns)
            mapent = self.getMTEntry(suffix)
            if mapent:
                return suffix
            else:
                del rdns[0]

        return ""

    def addSuffix(self, suffix, binddn=None, bindpw=None, urls=None, bename=None):
        """Create a suffix and its backend.

            Uses: setupBackend and SetupSuffix
            Requires: adding a matching entry in the tree

            TODO: raise exception instead returning codes!
            TODO: consider use logging instead of print
        """

        beents = self.getBackendsForSuffix(suffix, ['cn'])
        benames = []
        # no backends for this suffix yet - create one
        if not beents:
            bename = self.setupBackend(
                suffix, binddn, bindpw, urls, benamebase=bename)
            if not bename:
                print "Couldn't create backend for", suffix
                return -1  # ldap error code handled already
        else:  # use existing backend(s)
            benames = [entry.cn for entry in beents]
            bename = benames.pop(0)

        parent = self.findParentSuffix(suffix)
        if self.setupSuffix(suffix, bename, parent):
            print "Couldn't create suffix for %s %s" % (bename, suffix)
            return -1

        return 0

    def getDBStats(self, suffix, bename=''):
        if bename:
            dn = "cn=monitor,cn=%s,cn=ldbm database,cn=plugins,cn=config" % bename
        else:
            beents = self.getBackendsForSuffix(suffix)
            dn = "cn=monitor," + beents[0].dn
        dbmondn = "cn=monitor,cn=ldbm database,cn=plugins,cn=config"
        dbdbdn = "cn=database,cn=monitor,cn=ldbm database,cn=plugins,cn=config"
        try:
            # entrycache and dncache stats
            ent = self.getEntry(dn, ldap.SCOPE_BASE)
            monent = self.getEntry(dbmondn, ldap.SCOPE_BASE)
            dbdbent = self.getEntry(dbdbdn, ldap.SCOPE_BASE)
            ret = "cache   available ratio    count unitsize\n"
            mecs = ent.maxentrycachesize or "0"
            cecs = ent.currententrycachesize or "0"
            rem = int(mecs) - int(cecs)
            ratio = ent.entrycachehitratio or "0"
            ratio = int(ratio)
            count = ent.currententrycachecount or "0"
            count = int(count)
            if count:
                size = int(cecs) / count
            else:
                size = 0
            ret += "entry % 11d   % 3d % 8d % 5d" % (rem, ratio, count, size)
            if ent.maxdncachesize:
                mdcs = ent.maxdncachesize or "0"
                cdcs = ent.currentdncachesize or "0"
                rem = int(mdcs) - int(cdcs)
                dct = ent.dncachetries or "0"
                tries = int(dct)
                if tries:
                    ratio = (100 * int(ent.dncachehits)) / tries
                else:
                    ratio = 0
                count = ent.currentdncachecount or "0"
                count = int(count)
                if count:
                    size = int(cdcs) / count
                else:
                    size = 0
                ret += "\ndn    % 11d   % 3d % 8d % 5d" % (
                    rem, ratio, count, size)

            if ent.hasAttr('entrycache-hashtables'):
                ret += "\n\n" + ent.getValue('entrycache-hashtables')

            # global db stats
            ret += "\n\nglobal db stats"
            dbattrs = 'dbcachehits dbcachetries dbcachehitratio dbcachepagein dbcachepageout dbcacheroevict dbcacherwevict'.split(' ')
            cols = {'dbcachehits': [len('cachehits'), 'cachehits'], 'dbcachetries': [10, 'cachetries'],
                    'dbcachehitratio': [5, 'ratio'], 'dbcachepagein': [6, 'pagein'],
                    'dbcachepageout': [7, 'pageout'], 'dbcacheroevict': [7, 'roevict'],
                    'dbcacherwevict': [7, 'rwevict']}
            dbrec = {}
            for attr, vals in monent.iterAttrs():
                if attr.startswith('dbcache'):
                    val = vals[0]
                    dbrec[attr] = val
                    vallen = len(val)
                    if vallen > cols[attr][0]:
                        cols[attr][0] = vallen
            # construct the format string based on the field widths
            fmtstr = ''
            ret += "\n"
            for attr in dbattrs:
                fmtstr += ' %%(%s)%ds' % (attr, cols[attr][0])
                ret += ' %*s' % tuple(cols[attr])
            ret += "\n" + (fmtstr % dbrec)

            # other db stats
            skips = {'nsslapd-db-cache-hit': 'nsslapd-db-cache-hit', 'nsslapd-db-cache-try': 'nsslapd-db-cache-try',
                     'nsslapd-db-page-write-rate': 'nsslapd-db-page-write-rate',
                     'nsslapd-db-page-read-rate': 'nsslapd-db-page-read-rate',
                     'nsslapd-db-page-ro-evict-rate': 'nsslapd-db-page-ro-evict-rate',
                     'nsslapd-db-page-rw-evict-rate': 'nsslapd-db-page-rw-evict-rate'}

            hline = ''  # header line
            vline = ''  # val line
            for attr, vals in dbdbent.iterAttrs():
                if attr in skips:
                    continue
                if attr.startswith('nsslapd-db-'):
                    short = attr.replace('nsslapd-db-', '')
                    val = vals[0]
                    width = max(len(short), len(val))
                    if len(hline) + width > 70:
                        ret += "\n" + hline + "\n" + vline
                        hline = vline = ''
                    hline += ' %*s' % (width, short)
                    vline += ' %*s' % (width, val)

            # per file db stats
            ret += "\n\nper file stats"
            # key is number
            # data is dict - key is attr name without the number - val is the attr val
            dbrec = {}
            dbattrs = ['dbfilename', 'dbfilecachehit',
                       'dbfilecachemiss', 'dbfilepagein', 'dbfilepageout']
            # cols maps dbattr name to column header and width
            cols = {'dbfilename': [len('dbfilename'), 'dbfilename'], 'dbfilecachehit': [9, 'cachehits'],
                    'dbfilecachemiss': [11, 'cachemisses'], 'dbfilepagein': [6, 'pagein'],
                    'dbfilepageout': [7, 'pageout']}
            for attr, vals in ent.iterAttrs():
                match = DBMONATTRRE.match(attr)
                if match:
                    name = match.group(1)
                    num = match.group(2)
                    val = vals[0]
                    if name == 'dbfilename':
                        val = val.split('/')[-1]
                    dbrec.setdefault(num, {})[name] = val
                    vallen = len(val)
                    if vallen > cols[name][0]:
                        cols[name][0] = vallen
                match = DBMONATTRRESUN.match(attr)
                if match:
                    name = match.group(1)
                    if name == 'entrycache':
                        continue
                    num = match.group(2)
                    val = vals[0]
                    if name == 'dbfilename':
                        val = val.split('/')[-1]
                    dbrec.setdefault(num, {})[name] = val
                    vallen = len(val)
                    if vallen > cols[name][0]:
                        cols[name][0] = vallen
            # construct the format string based on the field widths
            fmtstr = ''
            ret += "\n"
            for attr in dbattrs:
                fmtstr += ' %%(%s)%ds' % (attr, cols[attr][0])
                ret += ' %*s' % tuple(cols[attr])
            for dbf in dbrec.itervalues():
                ret += "\n" + (fmtstr % dbf)
            return ret
        except Exception, e:
            print "caught exception", str(e)
        return ''

    def waitForEntry(self, dn, timeout=7200, attr='', quiet=True):
        scope = ldap.SCOPE_BASE
        filt = "(objectclass=*)"
        attrlist = []
        if attr:
            filt = "(%s=*)" % attr
            attrlist.append(attr)
        timeout += int(time.time())

        if isinstance(dn, Entry):
            dn = dn.dn

        # wait for entry and/or attr to show up
        if not quiet:
            sys.stdout.write("Waiting for %s %s:%s " % (self, dn, attr))
            sys.stdout.flush()
        entry = None
        while not entry and int(time.time()) < timeout:
            try:
                entry = self.getEntry(dn, scope, filt, attrlist)
            except NoSuchEntryError:
                pass  # found entry, but no attr
            except ldap.NO_SUCH_OBJECT:
                pass  # no entry yet
            except ldap.LDAPError, e:  # badness
                print "\nError reading entry", dn, e
                break
            if not entry:
                if not quiet:
                    sys.stdout.write(".")
                    sys.stdout.flush()
                time.sleep(1)

        if not entry and int(time.time()) > timeout:
            print "\nwaitForEntry timeout for %s for %s" % (self, dn)
        elif entry:
            if not quiet:
                print "\nThe waited for entry is:", entry
        else:
            print "\nError: could not read entry %s from %s" % (dn, self)

        return entry

    def addIndex(self, suffix, attr, indexTypes, *matchingRules):
        """Specify the suffix (should contain 1 local database backend),
            the name of the attribute to index, and the types of indexes
            to create e.g. "pres", "eq", "sub"
        """
        beents = self.getBackendsForSuffix(suffix, ['cn'])
        # assume 1 local backend
        dn = "cn=%s,cn=index,%s" % (attr, beents[0].dn)
        entry = Entry(dn)
        entry.setValues('objectclass', 'top', 'nsIndex')
        entry.setValues('cn', attr)
        entry.setValues('nsSystemIndex', "false")
        entry.setValues('nsIndexType', indexTypes)
        if matchingRules:
            entry.setValues('nsMatchingRule', matchingRules)
        try:
            self.add_s(entry)
        except ldap.ALREADY_EXISTS:
            print "Index for attr %s for backend %s already exists" % (
                attr, dn)

    def modIndex(self, suffix, attr, mod):
        """just a wrapper around a plain old ldap modify, but will
        find the correct index entry based on the suffix and attribute"""
        beents = self.getBackendsForSuffix(suffix, ['cn'])
        # assume 1 local backend
        dn = "cn=%s,cn=index,%s" % (attr, beents[0].dn)
        self.modify_s(dn, mod)

    def requireIndex(self, suffix):
        beents = self.getBackendsForSuffix(suffix, ['cn'])
        # assume 1 local backend
        dn = beents[0].dn
        replace = [(ldap.MOD_REPLACE, 'nsslapd-require-index', 'on')]
        self.modify_s(dn, replace)

    def addSchema(self, attr, val):
        dn = "cn=schema"
        self.modify_s(dn, [(ldap.MOD_ADD, attr, val)])

    def addAttr(self, *args):
        return self.addSchema('attributeTypes', args)

    def addObjClass(self, *args):
        return self.addSchema('objectClasses', args)

    def enableReplLogging(self):
        """Enable logging of replication stuff (1<<13)"""
        return self.setLogLevel(8192)

    def disableReplLogging(self):
        return self.setLogLevel(0)

    def setLogLevel(self, *vals):
        val = reduce(operator.add, vals)
        self.modify_s('cn=config', [(ldap.MOD_REPLACE,
                      'nsslapd-errorlog-level', str(val))])

    def setAccessLogLevel(self, *vals):
        val = reduce(operator.add, vals)
        self.modify_s('cn=config', [(
            ldap.MOD_REPLACE, 'nsslapd-accesslog-level', str(val))])

    def setupChainingIntermediate(self):
        confdn = "cn=config,cn=chaining database,cn=plugins,cn=config"
        try:
            self.modify_s(confdn, [(ldap.MOD_ADD, 'nsTransmittedControl',
                                   ['2.16.840.1.113730.3.4.12', '1.3.6.1.4.1.1466.29539.12'])])
        except ldap.TYPE_OR_VALUE_EXISTS:
            print "chaining backend config already has the required controls"

    def setupChainingMux(self, suffix, isIntermediate, binddn, bindpw, urls):
        self.addSuffix(suffix, binddn, bindpw, urls)
        if isIntermediate:
            self.setupChainingIntermediate()

    def setupChainingFarm(self, suffix, binddn, bindpw):
        # step 1 - create the bind dn to use as the proxy
        self.setupBindDN(binddn, bindpw)
        self.addSuffix(suffix)  # step 2 - create the suffix
        # step 3 - add the proxy ACI to the suffix
        try:
            acival = "(targetattr = \"*\")(version 3.0; acl \"Proxied authorization for database links\"" + \
                "; allow (proxy) userdn = \"ldap:///%s\";)" % binddn
            self.modify_s(suffix, [(ldap.MOD_ADD, 'aci', [acival])])
        except ldap.TYPE_OR_VALUE_EXISTS:
            print "proxy aci already exists in suffix %s for %s" % (
                suffix, binddn)

    # setup chaining from self to to - self is the mux, to is the farm
    # if isIntermediate is set, this server will chain requests from another server to to
    def setupChaining(self, to, suffix, isIntermediate):
        bindcn = "chaining user"
        binddn = "cn=%s,cn=config" % bindcn
        bindpw = "chaining"

        to.setupChainingFarm(suffix, binddn, bindpw)
        self.setupChainingMux(
            suffix, isIntermediate, binddn, bindpw, to.toLDAPURL())

    def setupChangelog(self, dirpath='', dbname='changelogdb'):
        """Setup the replication changelog.
            Return 0 on success

            TODO: why dirpath="" and not None?
            TODO: why not return changelog entry and raise on fault
        """
        dn = "cn=changelog5,cn=config"
        dirpath = os.path.join(dirpath or self.dbdir, dbname)
        entry = Entry(dn)
        entry.setValues('objectclass', "top", "extensibleobject")
        entry.setValues('cn', "changelog5")
        entry.setValues('nsslapd-changelogdir', dirpath)
        try:
            self.add_s(entry)
        except ldap.ALREADY_EXISTS:
            print "entry %s already exists" % dn
            return 0

        entry = self.getEntry(dn, ldap.SCOPE_BASE)
        if not entry:
            print "Entry %s was added successfully, but I cannot search it" % dn
            return -1
        elif self.verbose:
            print entry
        return 0

    def enableChainOnUpdate(self, suffix, bename):
        # first, get the mapping tree entry to modify
        mtent = self.getMTEntry(suffix, ['cn'])
        dn = mtent.dn

        # next, get the path of the replication plugin
        plgent = self.getEntry(
            "cn=Multimaster Replication Plugin,cn=plugins,cn=config",
            ldap.SCOPE_BASE, "(objectclass=*)", ['nsslapd-pluginPath'])
        path = plgent.getValue('nsslapd-pluginPath')

        mod = [(ldap.MOD_REPLACE, 'nsslapd-state', 'backend'),
               (ldap.MOD_ADD, 'nsslapd-backend', bename),
               (ldap.MOD_ADD, 'nsslapd-distribution-plugin', path),
               (ldap.MOD_ADD, 'nsslapd-distribution-funct', 'repl_chain_on_update')]

        try:
            self.modify_s(dn, mod)
        except ldap.TYPE_OR_VALUE_EXISTS:
            print "chainOnUpdate already enabled for %s" % suffix

    def setupConsumerChainOnUpdate(self, suffix, isIntermediate, binddn, bindpw, urls, beargs={}):
        # suffix should already exist
        # we need to create a chaining backend
        if not 'nsCheckLocalACI' in beargs:
            beargs['nsCheckLocalACI'] = 'on'  # enable local db aci eval.
        chainbe = self.setupBackend(suffix, binddn, bindpw, urls, beargs)
        # do the stuff for intermediate chains
        if isIntermediate:
            self.setupChainingIntermediate()
        # enable the chain on update
        return self.enableChainOnUpdate(suffix, chainbe)

    def setupReplica(self, args):
        """Setup a replica agreement using the following dict

            args = {
                suffix - dn of suffix
                binddn - the replication bind dn for this replica
                type - master, hub, leaf (see above for values) - if type is omitted, default is master
                legacy - true or false - for legacy consumer
                id - replica id or - if not given - an internal sequence number will be assigned

                # further args
                tpd -
                pd -
                referrals -
             }

             Ex. conn.setupReplica({
                    'suffix': "dc=example,dc=com",
                    'type'  : dsadmin.MASTER_TYPE,
                    'binddn': "cn=replication manager,cn=config"
              })
             binddn can also be a list:
            'binddn': [ "cn=repl1,cn=config", "cn=repl2,cn=config" ]

            TODO: use the more descriptive naming stuff? suffix, rtype=MASTER_TYPE, legacy=False, id=None
            TODO: this method does not update replica type
            DONE: replaced id and type keywords with rid and rtype
        """
        global REPLICAID  # declared here because we may assign to it
        suffix = args['suffix']
        repltype = args.get('type', MASTER_TYPE)
        binddn = args['binddn']
        replid = args.get('id', None)

        # set default values
        if repltype == MASTER_TYPE:
            replicatype = REPLICA_RDWR_TYPE
        else:
            replicatype = REPLICA_RDONLY_TYPE
        if args.get('legacy', False):
            legacy = 'on'
        else:
            legacy = 'off'

        # create replica entry in mapping-tree
        nsuffix = DSAdmin.normalizeDN(suffix)
        mtent = self.getMTEntry(suffix)
        if not mtent:
            raise NoSuchEntryError(
                "Error: no such suffix in Mapping Tree: %s" % suffix)

        dn = "cn=replica," + mtent.dn
        try:
            entry = self.getEntry(dn, ldap.SCOPE_BASE)
        except ldap.NO_SUCH_OBJECT:
            entry = None
        if entry:
            print "Already setup replica for suffix", suffix
            rec = self.suffixes.setdefault(nsuffix, {})
            rec['dn'] = dn
            rec['type'] = repltype
            return 0

        # If a replica does not exist
        binddnlist = []
        if binddn:
            if isinstance(binddn, basestring):
                binddnlist.append(binddn)
            else:
                binddnlist = binddn
        else:
            binddnlist.append(REPLBINDDN)

        if not replid and repltype == MASTER_TYPE:
            replid = REPLICAID
            REPLICAID += 1
        elif not replid:
            replid = 0
        else:
            REPLICAID = replid  # use given id for internal counter

        entry = Entry(dn)
        entry.setValues(
            'objectclass', "top", "nsds5replica", "extensibleobject")
        entry.setValues('cn', "replica")
        entry.setValues('nsds5replicaroot', nsuffix)
        entry.setValues('nsds5replicaid', str(replid))
        entry.setValues('nsds5replicatype', str(replicatype))
        if repltype != LEAF_TYPE:
            entry.setValues('nsds5flags', "1")
        entry.setValues('nsds5replicabinddn', binddnlist)
        entry.setValues('nsds5replicalegacyconsumer', legacy)

        # other args
        if 'tpi' in args:
            entry.setValues(
                'nsds5replicatombstonepurgeinterval', str(args['tpi']))
        if 'pd' in args:
            entry.setValues('nsds5ReplicaPurgeDelay', str(args['pd']))
        if 'referrals' in args:
            entry.setValues('nsds5ReplicaReferral', args['referrals'])

        self.add_s(entry)

        # check if the entry exists TODO better to raise!
        entry = self.getEntry(dn, ldap.SCOPE_BASE)
        if not entry:
            print "Entry %s was added successfully, but I cannot search it" % dn
            return -1
        elif self.verbose:
            print entry
        self.suffixes[nsuffix] = {'dn': dn, 'type': repltype}
        return 0

    def setupBindDN(self, binddn=REPLBINDDN, bindpw=REPLBINDPW):
        """ Create a person entry with the given dn and pwd.
            Return 0 on success

            binddn can be an entry

            TODO: Could we return the newly created entry and raise
                exception on fault?

            DONE: supported uid attribute too
        """
        if binddn and isinstance(binddn, Entry):
            assert binddn.dn, "Error: entry dn should be set!" % binddn
            binddn = binddn.dn

        ent = Entry(binddn)
        ent.setValues('objectclass', "top", "person")
        ent.setValues('userpassword', bindpw)
        ent.setValues('sn', "bind dn pseudo user")
        ent.setValues('cn', "bind dn pseudo user")

        # support for uid
        attribute, value = binddn.split(",")[0].split("=", 1)
        if attribute == 'uid':
            ent.setValues('objectclass', "top", "person", 'inetOrgPerson')
            ent.setValues('uid', value)

        try:
            self.add_s(ent)
        except ldap.ALREADY_EXISTS:
            print "Entry %s already exists" % binddn
        ent = self.getEntry(binddn, ldap.SCOPE_BASE)
        if not ent:
            print "Entry %s was added successfully, but I cannot search it" % binddn
            return -1
        elif self.verbose:
            print ent
        return 0

    def setupReplBindDN(self, dn, pwd):
        """TODO why not remove this redundant method?"""
        return self.setupBindDN(dn, pwd)

    def setupWinSyncAgmt(self, args, entry):
        if 'winsync' not in args:
            return

        suffix = args['suffix']
        entry.setValues("objectclass", "nsDSWindowsReplicationAgreement")
        entry.setValues("nsds7WindowsReplicaSubtree",
                        args.get("win_subtree",
                                 "cn=users," + suffix))
        entry.setValues("nsds7DirectoryReplicaSubtree",
                        args.get("ds_subtree",
                                 "ou=People," + suffix))
        entry.setValues(
            "nsds7NewWinUserSyncEnabled", args.get('newwinusers', 'true'))
        entry.setValues(
            "nsds7NewWinGroupSyncEnabled", args.get('newwingroups', 'true'))
        windomain = ''
        if 'windomain' in args:
            windomain = args['windomain']
        else:
            windomain = '.'.join(ldap.explode_dn(suffix, 1))
        entry.setValues("nsds7WindowsDomain", windomain)
        if 'interval' in args:
            entry.setValues("winSyncInterval", args['interval'])
        if 'onewaysync' in args:
            if args['onewaysync'].lower() == 'fromwindows' or \
                    args['onewaysync'].lower() == 'towindows':
                entry.setValues("oneWaySync", args['onewaysync'])
            else:
                raise Exception("Error: invalid value %s for oneWaySync: must be fromWindows or toWindows" % args['onewaysync'])

    # args - DSAdmin consumer (repoth), suffix, binddn, bindpw, timeout
    # also need an auto_init argument
    def setupAgreement(self, repoth, args):
        """Create a replication agreement from self to repoth - that is, self is the
        supplier and repoth is the DSAdmin object for the consumer (the consumer
        can be a master)

        repoth:
            * a DSAdmin object if chaining
            * an object with attributes: host, port, sslport

        args =  {
        'suffix': "dc=example,dc=com",
        'bename': "userRoot",
        'binddn': "cn=replrepl,cn=config",
        'bindcn': "replrepl", # so I need it?
        'bindpw': "replrepl",
        'log'   : True
        }


        """
        suffix = args['suffix']
        nsuffix = DSAdmin.normalizeDN(suffix)
        othhost, othport, othsslport = (
            repoth.host, repoth.port, repoth.sslport)
        othport = othsslport or othport
        cn = "meTo%s:%d" % (othhost, othport)
        if not nsuffix in self.suffixes:  # adding agreement to previously created replica
            replents = self.getReplicaEnts(suffix)
            if not replents:
                raise Exception(
                    "Error: no replica set up for suffix " + suffix)
            replent = replents[0]
            self.suffixes[nsuffix] = {
                'dn': replent.dn,
                'type': int(replent.nsds5replicatype)
            }
        dn = "cn=%s,%s" % (cn, self.suffixes[nsuffix]['dn'])
        try:
            entry = self.getEntry(dn, ldap.SCOPE_BASE)
        except ldap.NO_SUCH_OBJECT:
            entry = None
        if entry:
            print "Agreement exists:", dn
            self.suffixes.setdefault(nsuffix, {})[str(repoth)] = dn
            return dn
        if (nsuffix in self.agmt) and (repoth in self.agmt[nsuffix]):
            print "Agreement exists:", dn
            return dn

        entry = Entry(dn)
        binddn = args.get('binddn', REPLBINDDN)
        bindpw = args.get('bindpw', REPLBINDPW)
        entry.setValues('objectclass', "top", "nsds5replicationagreement")
        entry.setValues('cn', cn)
        entry.setValues('nsds5replicahost', othhost)
        entry.setValues('nsds5replicatimeout', str(args.get('timeout', 120)))
        entry.setValues('nsds5replicabinddn', binddn)
        entry.setValues('nsds5replicacredentials', bindpw)
        entry.setValues(
            'nsds5replicabindmethod', args.get('bindmethod', 'simple'))
        entry.setValues('nsds5replicaroot', nsuffix)
        entry.setValues('nsds5replicaupdateschedule', '0000-2359 0123456')
        entry.setValues('description', "me to %s%d" % (othhost, othport))
        if 'starttls' in args:
            entry.setValues('nsds5replicatransportinfo', 'TLS')
            entry.setValues('nsds5replicaport', str(othport))
        elif othsslport:
            entry.setValues('nsds5replicatransportinfo', 'SSL')
            entry.setValues('nsds5replicaport', str(othsslport))
        else:
            entry.setValues('nsds5replicatransportinfo', 'LDAP')
            entry.setValues('nsds5replicaport', str(othport))
        if 'fractional' in args:
            entry.setValues('nsDS5ReplicatedAttributeList', args['fractional'])
        if 'auto_init' in args:
            entry.setValues('nsds5BeginReplicaRefresh', 'start')
        if 'fractional' in args:
            entry.setValues('nsDS5ReplicatedAttributeList', args['fractional'])
        if 'stripattrs' in args:
            entry.setValues('nsds5ReplicaStripAttrs', args['stripattrs'])

        self.setupWinSyncAgmt(args, entry)
        try:
            self.add_s(entry)
        except:
            raise
        entry = self.waitForEntry(dn)
        if entry:
            self.suffixes.setdefault(nsuffix, {})[str(repoth)] = dn
            chain = 'chain' in args
            if chain and self.suffixes[nsuffix]['type'] == MASTER_TYPE:
                self.setupChainingFarm(suffix, binddn, bindpw)
            if chain and repoth.suffixes[nsuffix]['type'] == LEAF_TYPE:
                repoth.setupConsumerChainOnUpdate(suffix, 0, binddn, bindpw, self.toLDAPURL(), args['chainargs'])
            elif chain and repoth.suffixes[nsuffix]['type'] == HUB_TYPE:
                repoth.setupConsumerChainOnUpdate(suffix, 1, binddn, bindpw, self.toLDAPURL(), args['chainargs'])
        self.agmt.setdefault(nsuffix, {})[repoth] = dn
        return dn

    def stopReplication(self, agmtdn):
        mod = [(
            ldap.MOD_REPLACE, 'nsds5replicaupdateschedule', ['2358-2359 0'])]
        self.modify_s(agmtdn, mod)

    def restartReplication(self, agmtdn):
        mod = [(ldap.MOD_REPLACE, 'nsds5replicaupdateschedule', [
                '0000-2359 0123456'])]
        self.modify_s(agmtdn, mod)

    def findAgreementDNs(self, filt='', attrs=[]):
        realfilt = "(objectclass=nsds5ReplicationAgreement)"
        if filt:
            realfilt = "(&%s%s)" % (realfilt, filt)
        if not attrs:
            attrs.append('cn')
        ents = self.search_s(
            "cn=mapping tree,cn=config", ldap.SCOPE_SUBTREE, realfilt, attrs)
        return [ent.dn for ent in ents]

    def getReplicaEnts(self, suffix=None):
        if suffix:
            filt = "(&(objectclass=nsds5Replica)(nsds5replicaroot=%s))" % suffix
        else:
            filt = "(objectclass=nsds5Replica)"
        ents = self.search_s(
            "cn=mapping tree,cn=config", ldap.SCOPE_SUBTREE, filt)
        return ents

    def getReplStatus(self, agmtdn):
        attrlist = ['cn', 'nsds5BeginReplicaRefresh', 'nsds5replicaUpdateInProgress',
                    'nsds5ReplicaLastInitStatus', 'nsds5ReplicaLastInitStart',
                    'nsds5ReplicaLastInitEnd', 'nsds5replicaReapActive',
                    'nsds5replicaLastUpdateStart', 'nsds5replicaLastUpdateEnd',
                    'nsds5replicaChangesSentSinceStartup', 'nsds5replicaLastUpdateStatus',
                    'nsds5replicaChangesSkippedSinceStartup', 'nsds5ReplicaHost',
                    'nsds5ReplicaPort']
        ent = self.getEntry(
            agmtdn, ldap.SCOPE_BASE, "(objectclass=*)", attrlist)
        if not ent:
            print "Error reading status from agreement", agmtdn
        else:
            rh = ent.nsds5ReplicaHost
            rp = ent.nsds5ReplicaPort
            retstr = "Status for %s agmt %s:%s:%s" % (self, ent.cn, rh, rp)
            retstr += "\tUpdate In Progress  : " + \
                ent.nsds5replicaUpdateInProgress + "\n"
            retstr += "\tLast Update Start   : " + \
                ent.nsds5replicaLastUpdateStart + "\n"
            retstr += "\tLast Update End     : " + \
                ent.nsds5replicaLastUpdateEnd + "\n"
            retstr += "\tNum. Changes Sent   : " + \
                ent.nsds5replicaChangesSentSinceStartup + "\n"
            retstr += "\tNum. Changes Skipped: " + str(
                ent.nsds5replicaChangesSkippedSinceStartup) + "\n"
            retstr += "\tLast Update Status  : " + \
                ent.nsds5replicaLastUpdateStatus + "\n"
            retstr += "\tInit in Progress    : " + str(
                ent.nsds5BeginReplicaRefresh) + "\n"
            retstr += "\tLast Init Start     : " + \
                ent.nsds5ReplicaLastInitStart + "\n"
            retstr += "\tLast Init End       : " + \
                ent.nsds5ReplicaLastInitEnd + "\n"
            retstr += "\tLast Init Status    : " + str(
                ent.nsds5ReplicaLastInitStatus) + "\n"
            retstr += "\tReap In Progress    : " + \
                ent.nsds5replicaReapActive + "\n"
            return retstr

        return ""

    def getChangesSent(self, agmtdn):
        ent = self.getEntry(agmtdn, ldap.SCOPE_BASE, "(objectclass=*)",
                            ['nsds5replicaChangesSentSinceStartup'])
        retval = 0
        if not ent:
            print "Error reading status from agreement", agmtdn
        elif ent.nsds5replicaChangesSentSinceStartup:
            val = ent.nsds5replicaChangesSentSinceStartup
            items = val.split(' ')
            if len(items) == 1:
                retval = int(items[0])
            else:
                for item in items:
                    ary = item.split(":")
                    if ary and len(ary) > 1:
                        retval = retval + int(ary[1].split("/")[0])
        return retval

    def startReplication_async(self, agmtdn):
        mod = [(ldap.MOD_ADD, 'nsds5BeginReplicaRefresh', 'start')]
        self.modify_s(agmtdn, mod)

    def checkReplInit(self, agmtdn):
        """returns tuple - first element is done/not done, 2nd is no error/has error"""
        done = False
        hasError = 0
        attrlist = ['cn', 'nsds5BeginReplicaRefresh', 'nsds5replicaUpdateInProgress',
                    'nsds5ReplicaLastInitStatus', 'nsds5ReplicaLastInitStart',
                    'nsds5ReplicaLastInitEnd']
        entry = self.getEntry(
            agmtdn, ldap.SCOPE_BASE, "(objectclass=*)", attrlist)
        if not entry:
            print "Error reading status from agreement", agmtdn
            hasError = 1
        else:
            refresh = entry.nsds5BeginReplicaRefresh
            inprogress = entry.nsds5replicaUpdateInProgress
            status = entry.nsds5ReplicaLastInitStatus
            if not refresh:  # done - check status
                if not status:
                    print "No status yet"
                elif status.find("replica busy") > -1:
                    print "Update failed - replica busy - status", status
                    done = True
                    hasError = 2
                elif status.find("Total update succeeded") > -1:
                    print "Update succeeded: status ", status
                    done = True
                elif inprogress.lower() == 'true':
                    print "Update in progress yet not in progress: status ", status
                else:
                    print "Update failed: status", status
                    hasError = 1
                    done = True
            elif self.verbose:
                print "Update in progress: status", status

        return done, hasError

    def waitForReplInit(self, agmtdn):
        done = False
        haserror = 0
        while not done and not haserror:
            time.sleep(1)  # give it a few seconds to get going
            done, haserror = self.checkReplInit(agmtdn)
        return haserror

    def startReplication(self, agmtdn):
        rc = self.startReplication_async(agmtdn)
        if not rc:
            rc = self.waitForReplInit(agmtdn)
            if rc == 2:  # replica busy - retry
                rc = self.startReplication(agmtdn)
        return rc

    def replicaSetupAll(self, repArgs):
        """setup everything needed to enable replication for a given suffix.
            1- eventually create the suffix
            2- enable replication logging
            3- create changelog
            4- create replica user
            repArgs is a dict with the following fields:
                {
                suffix - suffix to set up for replication (eventually create)
                            optional fields and their default values
                bename - name of backend corresponding to suffix, otherwise
                    it will use the *first* backend found (isn't that dangerous?)
                parent - parent suffix if suffix is a sub-suffix - default is undef
                ro - put database in read only mode - default is read write
                type - replica type (MASTER_TYPE, HUB_TYPE, LEAF_TYPE) - default is master
                legacy - make this replica a legacy consumer - default is no

                binddn - bind DN of the replication manager user - default is REPLBINDDN
                bindpw - bind password of the repl manager - default is REPLBINDPW

                log - if true, replication logging is turned on - default false
                id - the replica ID - default is an auto incremented number
                }

            TODO: passing the repArgs as an object or as a **repArgs could be
                a better documentation choiche
                eg. replicaSetupAll(self, suffix, type=MASTER_TYPE, log=False, ...)
        """

        repArgs.setdefault('type', MASTER_TYPE)
        user = repArgs.get('binddn'), repArgs.get('bindpw')

        # eventually create the suffix (Eg. o=userRoot)
        # TODO should I check the addSuffix output as it doesn't raise
        self.addSuffix(repArgs['suffix'])
        if 'bename' not in repArgs:
            beents = self.getBackendsForSuffix(repArgs['suffix'], ['cn'])
            # just use first one
            repArgs['bename'] = beents[0].cn
        if repArgs.get('log', False):
            self.enableReplLogging()

        # enable changelog for master and hub
        if repArgs['type'] != LEAF_TYPE:
            self.setupChangelog()
        # create replica user
        try:
            self.setupReplBindDN(*user)
        except ldap.ALREADY_EXISTS:
            # no problem ;)
            pass

        # setup replica
        self.setupReplica(repArgs)
        if 'legacy' in repArgs:
            self.setupLegacyConsumer(*user)

        return 0

    def subtreePwdPolicy(self, basedn, pwdpolicy, verbose=False, **pwdargs):
        args = {'basedn': basedn, 'escdn': DSAdmin.escapeDNValue(
            DSAdmin.normalizeDN(basedn))}
        condn = "cn=nsPwPolicyContainer,%(basedn)s" % args
        poldn = "cn=cn\\=nsPwPolicyEntry\\,%(escdn)s,cn=nsPwPolicyContainer,%(basedn)s" % args
        temdn = "cn=cn\\=nsPwTemplateEntry\\,%(escdn)s,cn=nsPwPolicyContainer,%(basedn)s" % args
        cosdn = "cn=nsPwPolicy_cos,%(basedn)s" % args
        conent = Entry(condn)
        conent.setValues('objectclass', 'nsContainer')
        polent = Entry(poldn)
        polent.setValues('objectclass', ['ldapsubentry', 'passwordpolicy'])
        tement = Entry(temdn)
        tement.setValues('objectclass', ['extensibleObject',
                         'costemplate', 'ldapsubentry'])
        tement.setValues('cosPriority', '1')
        tement.setValues('pwdpolicysubentry', poldn)
        cosent = Entry(cosdn)
        cosent.setValues('objectclass', ['ldapsubentry',
                         'cosSuperDefinition', 'cosPointerDefinition'])
        cosent.setValues('cosTemplateDn', temdn)
        cosent.setValues(
            'cosAttribute', 'pwdpolicysubentry default operational-default')
        for ent in (conent, polent, tement, cosent):
            try:
                self.add_s(ent)
                if verbose:
                    print "created subtree pwpolicy entry", ent.dn
            except ldap.ALREADY_EXISTS:
                print "subtree pwpolicy entry", ent.dn, "already exists - skipping"
        self.setPwdPolicy({'nsslapd-pwpolicy-local': 'on'})
        self.setDNPwdPolicy(poldn, pwdpolicy, **pwdargs)

    def userPwdPolicy(self, user, pwdpolicy, verbose=False, **pwdargs):
        ary = ldap.explode_dn(user)
        par = ','.join(ary[1:])
        escuser = DSAdmin.escapeDNValue(DSAdmin.normalizeDN(user))
        args = {'par': par, 'udn': user, 'escudn': escuser}
        condn = "cn=nsPwPolicyContainer,%(par)s" % args
        poldn = "cn=cn\\=nsPwPolicyEntry\\,%(escudn)s,cn=nsPwPolicyContainer,%(par)s" % args
        conent = Entry(condn)
        conent.setValues('objectclass', 'nsContainer')
        polent = Entry(poldn)
        polent.setValues('objectclass', ['ldapsubentry', 'passwordpolicy'])
        for ent in (conent, polent):
            try:
                self.add_s(ent)
                if verbose:
                    print "created user pwpolicy entry", ent.dn
            except ldap.ALREADY_EXISTS:
                print "user pwpolicy entry", ent.dn, "already exists - skipping"
        mod = [(ldap.MOD_REPLACE, 'pwdpolicysubentry', poldn)]
        self.modify_s(user, mod)
        self.setPwdPolicy({'nsslapd-pwpolicy-local': 'on'})
        self.setDNPwdPolicy(poldn, pwdpolicy, **pwdargs)

    def setPwdPolicy(self, pwdpolicy, **pwdargs):
        self.setDNPwdPolicy("cn=config", pwdpolicy, **pwdargs)

    def setDNPwdPolicy(self, dn, pwdpolicy, **pwdargs):
        """input is dict of attr/vals"""
        mods = []
        for (attr, val) in pwdpolicy.iteritems():
            mods.append((ldap.MOD_REPLACE, attr, str(val)))
        if pwdargs:
            for (attr, val) in pwdargs.iteritems():
                mods.append((ldap.MOD_REPLACE, attr, str(val)))
        self.modify_s(dn, mods)

    def setupSSL(self, secport=0, sourcedir=None, secargs={}, copy_nss_files=True):
        """

            secargs = {
                'nsSSLPersonalitySSL':
            }
        """
        dn = 'cn=encryption,cn=config'
        ciphers = '-rsa_null_md5,+rsa_rc4_128_md5,+rsa_rc4_40_md5,+rsa_rc2_40_md5,+rsa_des_sha,' + \
            '+rsa_fips_des_sha,+rsa_3des_sha,+rsa_fips_3des_sha,' + \
            '+tls_rsa_export1024_with_rc4_56_sha,+tls_rsa_export1024_with_des_cbc_sha'
        mod = [(ldap.MOD_REPLACE, 'nsSSL3', secargs.get('nsSSL3', 'on')),
               (ldap.MOD_REPLACE, 'nsSSLClientAuth',
                secargs.get('nsSSLClientAuth', 'allowed')),
               (ldap.MOD_REPLACE, 'nsSSL3Ciphers', secargs.get('nsSSL3Ciphers', ciphers))]
        self.modify_s(dn, mod)

        dn = 'cn=RSA,cn=encryption,cn=config'
        ent = Entry(dn)
        ent.setValues('objectclass', ['top', 'nsEncryptionModule'])
        ent.setValues('nsSSLPersonalitySSL', secargs.get(
            'nsSSLPersonalitySSL', 'Server-Cert'))
        ent.setValues(
            'nsSSLToken', secargs.get('nsSSLToken', 'internal (software)'))
        ent.setValues('nsSSLActivation', secargs.get('nsSSLActivation', 'on'))
        try:
            self.add_s(ent)
        except ldap.ALREADY_EXISTS:
            pass

        dn = 'cn=config'
        mod = [(
            ldap.MOD_REPLACE, 'nsslapd-security', secargs.get('nsslapd-security', 'on')),
            (ldap.MOD_REPLACE, 'nsslapd-ssl-check-hostname',
             secargs.get('nsslapd-ssl-check-hostname', 'off')),
            (ldap.MOD_REPLACE, 'nsslapd-secureport', str(secport))]
        self.modify_s(dn, mod)

        if not sourcedir:
            sourcedir = os.environ['SECDIR']
        # get our cert dir
        ent = self.getEntry(dn, ldap.SCOPE_BASE, '(objectclass=*)')
        certdir = ent.getValue('nsslapd-certdir')
        # have to stop the server before replacing any security files
        self.stop()
        # eventually copy security files from source dir to our cert dir
        if copy_nss_files:
            for ff in ['cert8.db', 'key3.db', 'secmod.db', 'pin.txt', 'certmap.conf']:
                srcf = sourcedir + '/' + ff
                destf = certdir + '/' + ff
                # make sure dest is writable so we can copy over it
                try:
                    mode = os.stat(destf)[0]
                    newmode = mode | 0600
                    os.chmod(destf, newmode)
                except Exception, e:
                    pass  # oh well
                # copy2 will copy the mode too
                shutil.copy2(srcf, destf)

        # allow secport for selinux
        if secport != 636:
            cmd = 'semanage port -a -t ldap_port_t -p tcp ' + str(secport)
            os.system(cmd)

        # now, restart the ds
        self.start(True)

    def getRUV(self, suffix, tryrepl=False, verbose=False):
        uuid = "ffffffff-ffffffff-ffffffff-ffffffff"
        filt = "(&(nsUniqueID=%s)(objectclass=nsTombstone))" % uuid
        attrs = ['nsds50ruv', 'nsruvReplicaLastModified']
        ents = self.search_s(suffix, ldap.SCOPE_SUBTREE, filt, attrs)
        ent = None
        if ents and (len(ents) > 0):
            ent = ents[0]
        elif tryrepl:
            print "Could not get RUV from", suffix, "entry - trying cn=replica"
            ensuffix = DSAdmin.escapeDNValue(DSAdmin.normalizeDN(suffix))
            dn = "cn=replica,cn=%s,cn=mapping tree,cn=config" % ensuffix
            ents = self.search_s(dn, ldap.SCOPE_BASE, "objectclass=*", attrs)
        if ents and (len(ents) > 0):
            ent = ents[0]
        else:
            print "Could not read RUV for", suffix
            return None
        if verbose:
            print "RUV entry is", str(ent)
        return RUV(ent)

    ###########################
    # Static methods start here
    ###########################
    @staticmethod
    def normalizeDN(dn, usespace=False):
        # not great, but will do until we use a newer version of python-ldap
        # that has DN utilities
        ary = ldap.explode_dn(dn.lower())
        joinstr = ","
        if usespace:
            joinstr = ", "
        return joinstr.join(ary)

    @staticmethod
    def escapeDNValue(dn):
        '''convert special characters in a DN into LDAPv3 escapes e.g.
        "dc=example,dc=com" -> \"dc\=example\,\ dc\=com\"'''
        for cc in (' ', '"', '+', ',', ';', '<', '>', '='):
            dn = dn.replace(cc, '\\' + cc)
        return dn

    @staticmethod
    def escapeDNFiltValue(dn):
        '''convert special characters in a DN into LDAPv3 escapes
        for use in search filters'''
        for cc in (' ', '"', '+', ',', ';', '<', '>', '='):
            dn = dn.replace(cc, '\\%x' % ord(cc))
        return dn

    @staticmethod
    def suffixfilt(suffix):
        nsuffix = DSAdmin.normalizeDN(suffix)
        escapesuffix = DSAdmin.escapeDNFiltValue(nsuffix)
        spacesuffix = DSAdmin.normalizeDN(nsuffix, True)
        filt = '(|(cn=%s)(cn=%s)(cn=%s)(cn="%s")(cn="%s")(cn=%s)(cn="%s"))' % (escapesuffix, nsuffix, spacesuffix, nsuffix, spacesuffix, suffix, suffix)
        return filt

    @staticmethod
    def isLocalHost(hname):
        # first see if this is a "well known" local hostname
        if hname == 'localhost' or hname == 'localhost.localdomain':
            return True

        # first lookup ip addr
        ipadr = None
        try:
            ipadr = socket.gethostbyname(hname)
        except Exception, e:
            pass
        if not ipadr:
            print "Error: no IP Address for", hname
            return False

        # next, see if this IP addr is one of our
        # local addresses
        thematch = re.compile('inet addr:' + ipadr)
        found = False
        if HASPOPEN:
            p = Popen(['/sbin/ifconfig', '-a'], stdout=PIPE)
            child_stdout = p.stdout
        else:
            child_stdout, child_stdin = popen2.popen2(['/sbin/ifconfig', '-a'])
        for line in child_stdout:
            if re.search(thematch, line):
                found = True
                break
        if HASPOPEN:
            p.wait()
        return found

    @staticmethod
    def getfqdn(name=''):
        return socket.getfqdn(name)

    @staticmethod
    def getdomainname(name=''):
        fqdn = DSAdmin.getfqdn(name)
        index = fqdn.find('.')
        if index >= 0:
            return fqdn[index + 1:]
        else:
            return fqdn

    @staticmethod
    def getdefaultsuffix(name=''):
        dm = DSAdmin.getdomainname(name)
        if dm:
            return "dc=" + dm.replace('.', ',dc=')
        else:
            return 'dc=localdomain'

    @staticmethod
    def getnewhost(args):
        """One of the arguments to createInstance is newhost.  If this is specified, we need
        to convert it to the fqdn.  If not given, we need to figure out what the fqdn of the
        local host is.  This method sets newhost in args to the appropriate value and
        returns True if newhost is the localhost, False otherwise"""
        isLocal = False
        if 'newhost' in args:
            args['newhost'] = DSAdmin.getfqdn(args['newhost'])
            isLocal = DSAdmin.isLocalHost(args['newhost'])
        else:
            isLocal = True
            args['newhost'] = DSAdmin.getfqdn()
        return isLocal

    @staticmethod
    def getoldcfgdsinfo(args):
        """Use the old style sroot/shared/config/dbswitch.conf to get the info"""
        dbswitch = open("%s/shared/config/dbswitch.conf" % args['sroot'], 'r')
        try:
            matcher = re.compile(r'^directory\s+default\s+')
            for line in dbswitch:
                m = matcher.match(line)
                if m:
                    url = LDAPUrl(line[m.end():])
                    ary = url.hostport.split(":")
                    if len(ary) < 2:
                        ary.append(389)
                    else:
                        ary[1] = int(ary[1])
                    ary.append(url.dn)
                    return ary
        finally:
            dbswitch.close()

    @staticmethod
    def getnewcfgdsinfo(args):
        """Use the new style prefix/etc/dirsrv/admin-serv/adm.conf"""
        url = LDAPUrl(args['admconf'].ldapurl)
        ary = url.hostport.split(":")
        if len(ary) < 2:
            ary.append(389)
        else:
            ary[1] = int(ary[1])
        ary.append(url.dn)
        return ary

    @staticmethod
    def getcfgdsinfo(args):
        """We need the host and port of the configuration directory server in order
        to create an instance.  If this was not given, read the dbswitch.conf file
        to get the information.  This method will raise an exception if the file
        was not found or could not be open.  This assumes args contains the sroot
        parameter for the server root path.  If successful, returns a 3-tuple
        consisting of the host, port, and cfg suffix."""
        if 'cfgdshost' not in args or 'cfgdsport' not in args:
            if args['new_style']:
                return DSAdmin.getnewcfgdsinfo(args)
            else:
                return DSAdmin.getoldcfgdsinfo(args)
        else:
            return args['cfgdshost'], int(args['cfgdsport']), DSAdmin.CFGSUFFIX

    @staticmethod
    def is_a_dn(dn):
        """Returns True if the given string is a DN, False otherwise."""
        return (dn.find("=") > 0)

    @staticmethod
    def getcfgdsuserdn(cfgdn, args):
        """If the config ds user ID was given, not the full DN, we need to figure
        out what the full DN is.  Try to search the directory anonymously first.  If
        that doesn't work, look in ldap.conf.  If that doesn't work, just try the
        default DN.  This may raise a file or LDAP exception.  Returns a DSAdmin
        object bound as either anonymous or the admin user."""
        # create a connection to the cfg ds
        conn = DSAdmin(args['cfgdshost'], args['cfgdsport'], "", "")
        # if the caller gave a password, but not the cfguser DN, look it up
        if 'cfgdspwd' in args and \
                ('cfgdsuser' not in args or not DSAdmin.is_a_dn(args['cfgdsuser'])):
            if 'cfgdsuser' in args:
                ent = conn.getEntry(cfgdn, ldap.SCOPE_SUBTREE,
                                    "(uid=%s)" % args['cfgdsuser'],
                                    ['dn'])
                args['cfgdsuser'] = ent.dn
            elif 'sroot' in args:
                ldapconf = open(
                    "%s/shared/config/ldap.conf" % args['sroot'], 'r')
                for line in ldapconf:
                    ary = line.split()  # default split is all whitespace
                    if len(ary) > 1 and ary[0] == 'admnm':
                        args['cfgdsuser'] = ary[-1]
                ldapconf.close()
            elif 'admconf' in args:
                args['cfgdsuser'] = args['admconf'].userdn
            elif 'cfgdsuser' in args:
                args['cfgdsuser'] = "uid=%s,ou=Administrators,ou=TopologyManagement,%s" % \
                    (args['cfgdsuser'], cfgdn)
            conn.unbind()
            conn = DSAdmin(
                args['cfgdshost'], args['cfgdsport'], args['cfgdsuser'],
                args['cfgdspwd'])
        return conn

    @staticmethod
    def getserverroot(cfgconn, isLocal, args):
        """Grab the serverroot from the instance dir of the config ds if the user
        did not specify a server root directory"""
        if cfgconn and 'sroot' not in args and isLocal:
            ent = cfgconn.getEntry(
                "cn=config", ldap.SCOPE_BASE, "(objectclass=*)",
                ['nsslapd-instancedir'])
            if ent:
                args['sroot'] = os.path.dirname(
                    ent.getValue('nsslapd-instancedir'))

    @staticmethod
    def getadmindomain(isLocal, args):
        """Get the admin domain to use."""
        if isLocal and 'admin_domain' not in args:
            if 'admconf' in args:
                args['admin_domain'] = args['admconf'].admindomain
            elif 'sroot' in args:
                dsconf = open('%s/shared/config/ds.conf' % args['sroot'], 'r')
                for line in dsconf:
                    ary = line.split(":")
                    if len(ary) > 1 and ary[0] == 'AdminDomain':
                        args['admin_domain'] = ary[1].strip()
                dsconf.close()

    @staticmethod
    def getadminport(cfgconn, cfgdn, args):
        """Get the admin server port so we can contact it via http.  We get this from
        the configuration entry using the CFGSUFFIX and cfgconn.  Also get any other
        information we may need from that entry.  The return value is a 2-tuple consisting
        of the asport and True if the admin server is using SSL, False otherwise."""
        asport = 0
        secure = False
        if cfgconn:
            dn = cfgdn
            if 'admin_domain' in args:
                dn = "cn=%s,ou=%s, %s" % (
                    args['newhost'], args['admin_domain'], cfgdn)
            filt = "(&(objectclass=nsAdminServer)(serverHostName=%s)" % args[
                'newhost']
            if 'sroot' in args:
                filt += "(serverRoot=%s)" % args['sroot']
            filt += ")"
            ent = cfgconn.getEntry(
                dn, ldap.SCOPE_SUBTREE, filt, ['serverRoot'])
            if ent:
                if 'sroot' not in args and ent.serverRoot:
                    args['sroot'] = ent.serverRoot
                if 'admin_domain' not in args:
                    ary = ldap.explode_dn(ent.dn, 1)
                    args['admin_domain'] = ary[-2]
                dn = "cn=configuration, " + ent.dn
                ent = cfgconn.getEntry(dn, ldap.SCOPE_BASE, '(objectclass=*)',
                                       ['nsServerPort', 'nsSuiteSpotUser', 'nsServerSecurity'])
                if ent:
                    asport = ent.nsServerPort
                    secure = (ent.nsServerSecurity and (
                        ent.nsServerSecurity == 'on'))
                    if 'newuserid' not in args:
                        args['newuserid'] = ent.nsSuiteSpotUser
            cfgconn.unbind()
        return asport, secure

    @staticmethod
    def getserveruid(args):
        if 'newuserid' not in args:
            if 'admconf' in args:
                args['newuserid'] = args['admconf'].SuiteSpotUserID
            elif 'sroot' in args:
                ssusers = open("%s/shared/config/ssusers.conf" % args['sroot'])
                for line in ssusers:
                    ary = line.split()
                    if len(ary) > 1 and ary[0] == 'SuiteSpotUser':
                        args['newuserid'] = ary[-1]
                ssusers.close()
        if 'newuserid' not in args:
            args['newuserid'] = os.environ['LOGNAME']
            if args['newuserid'] == 'root':
                args['newuserid'] = DSAdmin.DEFAULT_USER_ID

    @staticmethod
    def cgiFake(sroot, verbose, prog, args):
        """Run the local program prog as a CGI using the POST method."""
        content = urllib.urlencode(args)
        length = len(content)
        # setup CGI environment
        env = os.environ.copy()
        env['REQUEST_METHOD'] = "POST"
        env['NETSITE_ROOT'] = sroot
        env['CONTENT_LENGTH'] = str(length)
        progdir = os.path.dirname(prog)
        if HASPOPEN:
            pipe = Popen(prog, cwd=progdir, env=env,
                         stdin=PIPE, stdout=PIPE, stderr=STDOUT)
            child_stdin = pipe.stdin
            child_stdout = pipe.stdout
        else:
            saveenv = os.environ
            os.environ = env
            child_stdout, child_stdin = popen2.popen2(prog)
            os.environ = saveenv
        child_stdin.write(content)
        child_stdin.close()
        for line in child_stdout:
            if verbose:
                sys.stdout.write(line)
            ary = line.split(":")
            if len(ary) > 1 and ary[0] == 'NMC_Status':
                exitCode = ary[1].strip()
                break
        child_stdout.close()
        if HASPOPEN:
            osCode = pipe.wait()
            print "%s returned NMC code %s and OS code %s" % (
                prog, exitCode, osCode)
        return exitCode

    @staticmethod
    def formatInfData(args):
        """Format args data for input to setup or migrate taking inf style data"""
        content = """[General]
FullMachineName= %s
SuiteSpotUserID= %s
""" % (args['newhost'], args['newuserid'])

        if args['have_admin']:
            content = content + """
ConfigDirectoryLdapURL= ldap://%s:%d/%s
ConfigDirectoryAdminID= %s
ConfigDirectoryAdminPwd= %s
AdminDomain= %s
""" % (args['cfgdshost'], args['cfgdsport'],
       DSAdmin.CFGSUFFIX,
       args['cfgdsuser'], args['cfgdspwd'], args['admin_domain'])

        content = content + """

[slapd]
ServerPort= %s
RootDN= %s
RootDNPwd= %s
ServerIdentifier= %s
Suffix= %s
""" % (args['newport'], args['newrootdn'], args['newrootpw'],
       args['newinst'], args['newsuffix'])

        if 'InstallLdifFile' in args:
            content = content + """
InstallLdifFile= %s
""" % args['InstallLdifFile']
        if 'AddOrgEntries' in args:
            content = content + """
AddOrgEntries= %s
""" % args['AddOrgEntries']
        if 'ConfigFile' in args:
            for ff in args['ConfigFile']:
                content = content + """
ConfigFile= %s
""" % ff
        if 'SchemaFile' in args:
            for ff in args['SchemaFile']:
                content = content + """
SchemaFile= %s
""" % ff

        if 'ldapifilepath' in args:
            content = content + "ldapifilepath= " + args[
                'ldapifilepath'] + "\n"

        return content

    @staticmethod
    def runInfProg(prog, content, verbose):
        """run a program that takes an .inf style file on stdin"""
        cmd = [prog]
        if verbose:
            cmd.append('-ddd')
        else:
            cmd.extend(['-l', '/dev/null'])
        cmd.extend(['-s', '-f', '-'])
        if HASPOPEN:
            pipe = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
            child_stdin = pipe.stdin
            child_stdout = pipe.stdout
        else:
            pipe = popen2.Popen4(cmd)
            child_stdin = pipe.tochild
            child_stdout = pipe.fromchild
        child_stdin.write(content)
        child_stdin.close()
        while not pipe.poll():
            (rr, wr, xr) = select.select([child_stdout], [], [], 1.0)
            if rr and len(rr) > 0:
                line = rr[0].readline()
                if not line:
                    break
                if verbose:
                    sys.stdout.write(line)
            elif verbose:
                print "timed out waiting to read from", cmd
        child_stdout.close()
        exitCode = pipe.wait()
        if verbose:
            print "%s returned exit code %s" % (prog, exitCode)
        return exitCode

    @staticmethod
    def cgiPost(host, port, username, password, uri, verbose, secure, args):
        """Post the request to the admin server.  Admin server requires authentication,
        so we use the auth handler classes.  NOTE: the url classes in python use the
        deprecated base64.encodestring() function, which truncates lines, causing Apache
        to give us a 400 Bad Request error for the Authentication string.  So, we have
        to tell base64.encodestring() not to truncate."""
        prefix = 'http'
        if secure:
            prefix = 'https'
        hostport = host + ":" + port
        # construct our url
        url = '%s://%s:%s%s' % (prefix, host, port, uri)
        # tell base64 not to truncate lines
        savedbinsize = base64.MAXBINSIZE
        base64.MAXBINSIZE = 256
        # create the password manager - we don't care about the realm
        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        # add our password
        passman.add_password(None, hostport, username, password)
        # create the auth handler
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        # create our url opener that handles basic auth
        opener = urllib2.build_opener(authhandler)
        # make admin server think we are the console
        opener.addheaders = [('User-Agent', 'Fedora-Console/1.0')]
        if verbose:
            print "requesting url", url
            sys.stdout.flush()
        exitCode = 1
        try:
            req = opener.open(url, urllib.urlencode(args))
            for line in req:
                if verbose:
                    print line
                ary = line.split(":")
                if len(ary) > 1 and ary[0] == 'NMC_Status':
                    exitCode = ary[1].strip()
                    break
            req.close()
#         except IOError, e:
#             print e
#             print e.code
#             print e.headers
#             raise
        finally:
            # restore binsize
            base64.MAXBINSIZE = savedbinsize
        return exitCode

    @staticmethod
    def getsbindir(sroot, prefix):
        if sroot:
            return "%s/bin/slapd/admin/bin" % sroot
        elif prefix:
            return "%s/sbin" % prefix
        return "/usr/sbin"

    @staticmethod
    def createInstance(args):
        """Create a new instance of directory server.  First, determine the hostname to use.  By
        default, the server will be created on the localhost.  Also figure out if the given
        hostname is the local host or not."""
        verbose = args.get('verbose', 0)
        isLocal = DSAdmin.getnewhost(args)

        # old style or new style?
        sroot = args.get('sroot', os.environ.get('SERVER_ROOT', None))
        if sroot and 'sroot' not in args:
            args['sroot'] = sroot
        # new style - prefix or FHS?
        prefix = args.get('prefix', os.environ.get('PREFIX', None))
        if 'prefix' not in args:
            args['prefix'] = (prefix or '')
        args['new_style'] = not sroot

        # do we have ds only or ds+admin?
        if 'no_admin' not in args:
            sbindir = DSAdmin.getsbindir(sroot, prefix)
            if os.path.isfile(sbindir + '/setup-ds-admin.pl'):
                args['have_admin'] = True

        if 'have_admin' not in args:
            args['have_admin'] = False

        # get default values from adm.conf
        if args['new_style'] and args['have_admin']:
            admconf = LDIFConn(
                args['prefix'] + "/etc/dirsrv/admin-serv/adm.conf")
            args['admconf'] = admconf.get('')

        # next, get the configuration ds host and port
        if args['have_admin']:
            args['cfgdshost'], args[
                'cfgdsport'], cfgdn = DSAdmin.getcfgdsinfo(args)
        if args['have_admin']:
            cfgconn = DSAdmin.getcfgdsuserdn(cfgdn, args)
        # next, get the server root if not given
        if not args['new_style']:
            DSAdmin.getserverroot(cfgconn, isLocal, args)
        # next, get the admin domain
        if args['have_admin']:
            DSAdmin.getadmindomain(isLocal, args)
        # next, get the admin server port and any other information - close the cfgconn
        if args['have_admin']:
            asport, secure = DSAdmin.getadminport(cfgconn, cfgdn, args)
        # next, get the server user id
        DSAdmin.getserveruid(args)
        # fixup and verify other args
        if 'newport' not in args:
            args['newport'] = '389'
        if 'newrootdn' not in args:
            args['newrootdn'] = 'cn=directory manager'
        if 'newsuffix' not in args:
            args['newsuffix'] = DSAdmin.getdefaultsuffix(args['newhost'])
        if not isLocal or 'cfgdshost' in args:
            if 'admin_domain' not in args:
                args['admin_domain'] = DSAdmin.getdomainname(args['newhost'])
            if isLocal and 'cfgdspwd' not in args:
                args['cfgdspwd'] = "dummy"
            if isLocal and 'cfgdshost' not in args:
                args['cfgdshost'] = args['newhost']
            if isLocal and 'cfgdsport' not in args:
                args['cfgdsport'] = 55555
        missing = False
        for param in ('newhost', 'newport', 'newrootdn', 'newrootpw', 'newinst', 'newsuffix'):
            if param not in args:
                print "missing required argument", param
                missing = True
        if missing:
            raise InvalidArgumentError("missing required arguments")

        # try to connect with the given parameters
        try:
            newconn = DSAdmin(args['newhost'], args['newport'],
                              args['newrootdn'], args['newrootpw'])
            newconn.isLocal = isLocal
            if args['have_admin']:
                newconn.asport = asport
                newconn.cfgdsuser = args['cfgdsuser']
                newconn.cfgdspwd = args['cfgdspwd']
            print "Warning: server at %s:%s already exists, returning connection to it" % \
                  (args['newhost'], args['newport'])
            return newconn
        except ldap.SERVER_DOWN:
            pass  # not running - create new one

        if not isLocal or 'cfgdshost' in args:
            for param in ('cfgdshost', 'cfgdsport', 'cfgdsuser', 'cfgdspwd', 'admin_domain'):
                if param not in args:
                    print "missing required argument", param
                    missing = True
        if not isLocal and not asport:
            print "missing required argument admin server port"
            missing = True
        if missing:
            raise InvalidArgumentError("missing required arguments")

        # construct a hash table with our CGI arguments - used with cgiPost
        # and cgiFake
        cgiargs = {
            'servname': args['newhost'],
            'servport': args['newport'],
            'rootdn': args['newrootdn'],
            'rootpw': args['newrootpw'],
            'servid': args['newinst'],
            'suffix': args['newsuffix'],
            'servuser': args['newuserid'],
            'start_server': 1
        }
        if 'cfgdshost' in args:
            cgiargs['cfg_sspt_uid'] = args['cfgdsuser']
            cgiargs['cfg_sspt_uid_pw'] = args['cfgdspwd']
            cgiargs['ldap_url'] = "ldap://%s:%d/%s" % (
                args['cfgdshost'], args['cfgdsport'], cfgdn)
            cgiargs['admin_domain'] = args['admin_domain']

        if not isLocal:
            DSAdmin.cgiPost(args['newhost'], asport, args['cfgdsuser'],
                            args['cfgdspwd'], "/slapd/Tasks/Operation/Create", verbose,
                            secure, cgiargs)
        elif not args['new_style']:
            prog = args['sroot'] + "/bin/slapd/admin/bin/ds_create"
            if not os.access(prog, os.X_OK):
                prog = args['sroot'] + "/bin/slapd/admin/bin/ds_newinst"
            DSAdmin.cgiFake(args['sroot'], verbose, prog, cgiargs)
        else:
            prog = ''
            if args['have_admin']:
                prog = DSAdmin.getsbindir(sroot, prefix) + "/setup-ds-admin.pl"
            else:
                prog = DSAdmin.getsbindir(sroot, prefix) + "/setup-ds.pl"
            content = DSAdmin.formatInfData(args)
            DSAdmin.runInfProg(prog, content, verbose)

        newconn = DSAdmin(args['newhost'], args['newport'],
                          args['newrootdn'], args['newrootpw'])
        newconn.isLocal = isLocal
        if args['have_admin']:
            newconn.asport = asport
            newconn.cfgdsuser = args['cfgdsuser']
            newconn.cfgdspwd = args['cfgdspwd']
        return newconn

    @staticmethod
    def createAndSetupReplica(createArgs, repArgs):
        # pass this sub two dicts - the first one is a dict suitable to create
        # a new instance - see createInstance for more details
        # the second is a dict suitable for replicaSetupAll - see replicaSetupAll
        conn = DSAdmin.createInstance(createArgs)
        if not conn:
            print "Error: could not create server", createArgs
            return 0

        conn.replicaSetupAll(repArgs)
        return conn


def testit():
    host = 'localhost'
    port = 10200
    binddn = "cn=directory manager"
    bindpw = "secret12"

    basedn = "cn=config"
    scope = ldap.SCOPE_BASE
    filt = "(objectclass=*)"

    try:
        m1 = DSAdmin(host, port, binddn, bindpw)
#        filename = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot, m1.inst)
#        m1.importLDIF(filename, "dc=example,dc=com", None, True)
#        m1.exportLDIF('/tmp/ldif', "dc=example,dc=com", False, True)
        print m1.sroot, m1.inst, m1.errlog
        ent = m1.getEntry(basedn, scope, filt, None)
        if ent:
            print ent.passwordmaxage
        m1 = DSAdmin.createInstance({
                                    'cfgdshost': host,
                                    'cfgdsport': port,
                                    'cfgdsuser': 'admin',
                                    'cfgdspwd': 'admin',
                                    'newrootpw': 'password',
                                    'newhost': host,
                                    'newport': port + 10,
                                    'newinst': 'm1',
                                    'newsuffix': 'dc=example,dc=com',
                                    'verbose': 1
                                    })
#     m1.stop(True)
#     m1.start(True)
        cn = m1.setupBackend("dc=example2,dc=com")
        rc = m1.setupSuffix("dc=example2,dc=com", cn)
        entry = m1.getEntry("cn=config", ldap.SCOPE_SUBTREE, "(cn=" + cn + ")")
        print "new backend entry is:"
        print entry
        print entry.getValues('objectclass')
        print entry.OBJECTCLASS
        results = m1.search_s("cn=monitor", ldap.SCOPE_SUBTREE)
        print results
        results = m1.getBackendsForSuffix("dc=example,dc=com")
        print results

    except ldap.LDAPError, e:
        print e

    print "done"


if __name__ == "__main__":
    testit()
