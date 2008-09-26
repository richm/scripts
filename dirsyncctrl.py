
import os
import sys
import time
import ldap
from ldap.controls import LDAPControl
from ldap.ldapobject import LDAPObject
import struct
import pprint

# should use pyasn1 instead of this hand coded
# ber codec stuff
seqtag = 0x30
octetstringtag = 0x04
# return the length of the tlv - len
# is the first byte of len
def readlen(beriter):
    """beriter should be positioned just after reading the tag, at
    the first byte of the len"""
    len = ord(beriter.next())
    if isinstance(len, str):
        len = ord(len)
    if len & 0x80:
        # get number of len bytes
        nb = len & 0x7f
        # figure out number of padding bytes
        pad = 4 - nb
        # add pad bytes
        mystr = ''.join([chr(0) for xx in xrange(pad)])
        # add real vals
        mystr = mystr + ''.join([beriter.next() for xx in xrange(nb)])
        # read the next nb bytes of network ordered unsigned int bytes
        len = struct.unpack("!I", mystr)
    return len

def readint(beriter, len):
    val = 0
    if len > 0:
        val = ord(beriter.next())
        if val & 0x80:
            sign = -1
        else:
            sign = 0
        val = (sign << 8) | val
        len = len - 1
    for xx in xrange(len):
        val = (val << 8) | ord(beriter.next())
    return val

def readtlv(beriter, tag):
    """beriter is an iterator over a sequence of ber encoded values.
    The beriter should be positioned so that beriter.next will return
    the tag. readtlv will return the tag, length, value tuple - the beriter
    will be positioned so that iter.next() will return the next tag"""
    # read the tag
    nexttag = ord(beriter.next())
    if not tag == nexttag:
        raise "Error: incorrect tag is %d should be %d" % (nexttag, tag)
    # read the len
    len = readlen(beriter)
    # sequence tag - no actual value
    if tag == seqtag:
        return (nexttag, len, None)

    # read the value
    if not nexttag == octetstringtag: # assume integer
        val = readint(beriter, len)
    else:
        val = ''.join([beriter.next() for xx in range(len)])

    return (nexttag, len, val)

class DirSyncCtrl(LDAPControl):
    """
    The MS AD DirSync control

    In this base class controlValue has to be passed as
    boolean type (True/False or 1/0).
    """
    controlType = "1.2.840.113556.1.4.841"
    beginTag = 0x30 # == 48 dec == '0' zero character == sequence tag
    flagTag = macTag = 0x02 # int tag
    cookieTag = 0x04 # octet string tag

    def __init__(self,criticality=True,flags=0,maxattributecount=-1,cookie=None):
        LDAPControl.__init__(self,DirSyncCtrl.controlType,criticality)
        self.flags = flags
        self.maxattributecount = maxattributecount
        self.cookie = cookie
        self.controlValue = None

    def encodeControlValue(self,value):
        """This assumes the integers are all <= 255, and the
        length of cookie is also <= 255"""
        if self.cookie:
            cookielen = len(self.cookie)
        else:
            cookielen = 0
        val = struct.pack('bbbbbbbb',
                          DirSyncCtrl.flagTag, 1, self.flags,
                          DirSyncCtrl.macTag, 1, self.maxattributecount,
                          DirSyncCtrl.cookieTag, cookielen)
        if self.cookie:
            val = val + self.cookie
#        print "control value is (%d, %d, %d)" % (self.flags, self.maxattributecount, cookielen)
        return struct.pack('bb', DirSyncCtrl.beginTag, len(val)) + val

    def decodeControlValue(self,encodedValue):
#        print "New dirsync value=", pprint.pformat(encodedValue)
        self.controlValue = encodedValue
        if encodedValue == None:
            self.controlValue = None
            return

        valiter = iter(encodedValue)
        # check begin tag
        (tag, len, val) = readtlv(valiter, DirSyncCtrl.beginTag)
        # read flags
        (tag, len, self.flags) = readtlv(valiter, DirSyncCtrl.flagTag)
#        print "flags value is", self.flags
        # have flags now, read mac
        (tag, len, self.maxattributecount) = readtlv(valiter, DirSyncCtrl.macTag)
#        print "maxattributecount value is", self.flags
        # reset to -1 to be like the DS code
        self.maxattributecount = -1
        # have mac now, read cookie
        (tag, len, self.cookie) = readtlv(valiter, DirSyncCtrl.cookieTag)
#        print "cookie len is", len

    def update(self,ctrls):
        for ctrl in ctrls:
            if ctrl.controlType == DirSyncCtrl.controlType:
                self.decodeControlValue(ctrl.controlValue)
                return

def main():
    adhost = 'ad.example.com'
    adport = 389
    aduri = "ldap://%s:%d/" % (adhost, adport)
    suffix = "DC=example,DC=com"
    adroot = "cn=administrator,cn=users," + suffix
    adrootpw = "adminpassword"

    ad = LDAPObject(aduri)
    ad.simple_bind_s(adroot, adrootpw)

    # do initial dirsync search to get entries and the initial dirsync
    # cookie
    scope = ldap.SCOPE_SUBTREE
    filter = '(objectclass=*)'
    attrlist = None
    dirsyncctrl = DirSyncCtrl()
    serverctrls = [dirsyncctrl]

    msgid = ad.search_ext(suffix, scope, filter, attrlist, 0, serverctrls)
    initiallist = {}
    # the dirsync control is returned with the LDAP_RES_SEARCH_RESULT
    #  def result3(self,msgid=_ldap.RES_ANY,all=1,timeout=None):
    while True:
        (rtype, rdata, rmsgid, decoded_serverctrls) = ad.result3(msgid)
        print "Search returned %d results" % len(rdata)
        for dn, ent in rdata:
            print "dn: ", dn
            pprint.pprint(ent)
        if rtype == ldap.RES_SEARCH_RESULT:
            dirsyncctrl.update(decoded_serverctrls)
            break

    # now search again with the updated dirsync control
    # we should get back no results since nothing in AD
    # has changed
    msgid = ad.search_ext(suffix, scope, filter, attrlist, 0, serverctrls)
    while True:
        (rtype, rdata, rmsgid, decoded_serverctrls) = ad.result3(msgid)
        print "Search returned %d results" % len(rdata)
        if len(rdata) > 0:
            print "Nothing changed but something was returned????"
            pprint.pprint(rdata)
        if rtype == ldap.RES_SEARCH_RESULT:
            dirsyncctrl.update(decoded_serverctrls)
            break

    print "Change something on the AD side, and press Enter"
    sys.stdin.readline()
    print "Searching for changes . . ."
    msgid = ad.search_ext(suffix, scope, filter, attrlist, 0, serverctrls)
    while True:
        (rtype, rdata, rmsgid, decoded_serverctrls) = ad.result3(msgid)
        print "Search returned %d results" % len(rdata)
        for dn, ent in rdata:
            print "dn: ", dn
            pprint.pprint(ent)
        if rtype == ldap.RES_SEARCH_RESULT:
            dirsyncctrl.update(decoded_serverctrls)
            break

if __name__ == '__main__':
    main()
