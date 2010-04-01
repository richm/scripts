
import os
import sys
import time
import ldap
import math
from ldap.controls import LDAPControl
from ldap.ldapobject import LDAPObject
import struct
import pprint

# should use pyasn1 instead of this hand coded
# ber codec stuff
seqtag = 0x30
settag = 0x31
booltag = 0x01
inttag = 0x02
octetstringtag = 0x04
# return the length of the tlv - len
# is the first byte of len
def lenlen(ll):
    """how many bytes do we need to encode ll"""
    return int(math.log(ll,256))+1

def encodelen(ll):
    if ll < 0x80:
        return struct.pack('b', ll)

    lenll = lenlen(ll)
    fmtstr = 'B%ds' % lenll
    return struct.pack(fmtstr, lenll|0x80, struct.pack("!l", ll)[-lenll:])

def encodeseq(data,tag=seqtag):
    return struct.pack('B', tag) + encodelen(len(data)) + data

def encodestring(ss):
    return encodeseq(ss,octetstringtag)

class BerIter(object):
    def __init__(self,data,dlen=-1):
        self.data = data
        if dlen == -1:
            dlen = len(data)
        self.len = dlen
        self.idx = 0
        self.lenstack = []
        self.seqdlen = -1

    def __iter__(self):
        if self.seqdlen > -1:
            self.lenstack.append(self.len)
            self.len = self.seqdlen + self.idx
            self.seqdlen = -1
        return self

    def next(self):
        if (self.idx >= self.len):
            # hit end - restore old length
            self.len = self.lenstack.pop()
            raise StopIteration
        else:
            ret = self.data[self.idx]
            self.idx = self.idx + 1
            return ret

    def readlen(self):
        """beriter should be positioned just after reading the tag, at
        the first byte of the len"""
        dlen = ord(self.next())
        if dlen & 0x80:
            # get number of len bytes
            nb = dlen & 0x7f
            # figure out number of padding bytes
            pad = 4 - nb
            # add pad bytes
            mystr = ''.join([chr(0) for xx in xrange(pad)])
            # add real vals
            mystr = mystr + ''.join([self.next() for xx in xrange(nb)])
            # read the next nb bytes of network ordered unsigned int bytes
            # unpack always returns a tuple, even for one value
            dlen = struct.unpack("!I", mystr)[0]
        return dlen

    def readint(self,dlen):
        val = 0
        if dlen > 0:
            val = ord(self.next())
            if val & 0x80: sign = -1
            else: sign = 0
            val = (sign << 8) | val
            dlen = dlen - 1
        for xx in self:
            val = (val << 8) | ord(xx)
        return val

    def nexttlv(self,tag=None):
        """beriter is an iterator over a sequence of ber encoded values.
        The beriter should be positioned so that beriter.next will return
        the tag. readtlv will return the tag, length, value tuple - the beriter
        will be positioned so that iter.next() will return the next tag"""
        # read the tag
        nexttag = ord(self.next())
        # read the len
        dlen = self.readlen()

        # read the value
        if nexttag == octetstringtag:
            # the old len is restored when the new len is reached
            # in next() during iteration
            self.lenstack.append(self.len)
            self.len = dlen + self.idx
            val = ''.join([xx for xx in self])
        elif nexttag == inttag or nexttag == booltag:
            # the old len is restored when the new len is reached
            # in next() during iteration
            self.lenstack.append(self.len)
            self.len = dlen + self.idx
            val = self.readint(len)
        else:
            val = None # caller will have to handle this

        return (nexttag, dlen, val)

    def peek(self): return ord(self.data[self.idx])

    def seqlen(self,dlen): self.seqdlen = dlen

class TLVIter(object):
    def __init__(self,data): self.beriter = BerIter(data)
    def __iter__(self):
        self.beriter.__iter__()
        return self
    def next(self): return self.beriter.nexttlv()
    def peek(self): return self.beriter.peek()
    def seqlen(self,dlen): self.beriter.seqlen(dlen)

class DerefCtrl(LDAPControl):
    """
    The draft Dereference Control
    """
    controlType = "1.3.6.1.4.1.4203.666.5.16"

    def __init__(self,derefspeclist,criticality=True):
        LDAPControl.__init__(self,DerefCtrl.controlType,criticality,derefspeclist)

    def encodeControlValue(self,value):
        val = ''
        for (derefattr,attrs) in value:
            derefspec = ''
            for attr in attrs:
                derefspec = derefspec + encodestring(attr)
            derefspec = encodestring(derefattr) + encodeseq(derefspec)
            derefspec = encodeseq(derefspec)
            val = val + derefspec
        val = encodeseq(val)
        return val

    def decodeControlValue(self,encodedValue):
        self.controlValue = encodedValue
        if encodedValue == None:
            self.controlValue = None
            return

        valiter = TLVIter(encodedValue)
        (tag, dlen, val) = valiter.next()
        valiter.seqlen(dlen)
        for (tag, dlen, derefres) in valiter:
            (tag, dlen, derefattr) = valiter.next()
            (tag, dlen, derefdn) = valiter.next()
            attrvals = {} # key is attrname, val is array of vals
            if valiter.peek() == (0x20|0x80): # do we have attrs and vals
                (tag, dlen, val) = valiter.next()
                valiter.seqlen(dlen)
                for (tag, dlen, attrvalseq) in valiter:
                    (tag, dlen, attrname) = valiter.next()
                    attrvals[attrname] = []
                    (tag, dlen, val) = valiter.next()
                    valiter.seqlen(dlen)
                    for (tag, dlen, val) in valiter:
                        attrvals[attrname].append(val)
            print "derefattr = ", derefattr, "derefdn = ", derefdn
            pprint.pprint(attrvals)

    def update(self,ctrls):
        for ctrl in ctrls:
            if ctrl.controlType == DerefCtrl.controlType:
                self.decodeControlValue(ctrl.controlValue)
                return

def encoderesultvalue(derefreslist):
    val = ''
    for derefres in derefreslist:
        derefval = ''
        derefattr = derefres[0]
        derefdn = derefres[1]
        attrvals = ''
        if len(derefres) > 2:
            for (name,vals) in derefres[2]:
                innerattrvals = ''
                for aval in vals:
                    innerattrvals = innerattrvals + encodestring(aval)
                innerattrvals = encodeseq(innerattrvals,settag)
                innerattrvals = encodestring(name) + innerattrvals
                attrvals = attrvals + encodeseq(innerattrvals)
            attrvals = encodeseq(attrvals,0x80|0x20)
        derefval = encodestring(derefattr) + encodestring(derefdn) + attrvals
        val = val + encodeseq(derefval)
    val = encodeseq(val)
    return val

def main():
    testreq = (
        ('derefattr1', ('val1', 'val2')),
        ('derefattr2', ('val3', 'val4'))
        )

    testreq2 = (
        ('member', ('uid', 'roomNumber', 'nsRoleDN', 'nsRole'))
        ,)

    testres = (
        ('derefattr1', 'derefdn1'),
        ('derefattr2', 'derefdn2',
         (('attr1', ('val1', 'val2', 'val3')),
          ('attr2', ('val4', 'val5', 'val6'))
          )
         ),
        ('derefattr3', 'derefdn3'),
        ('derefattr4', 'derefdn4',
         (('attr3', ('val7', 'val8', 'val9')),
          ('attr4', ('val10', 'val11', 'val12'))
          )
         )
        )

    dc = DerefCtrl(testreq)
    dc = DerefCtrl(testreq2)
    enc = encoderesultvalue(testres)
    pprint.pprint(enc)
    dc.decodeControlValue(enc)

if __name__ == '__main__':
    main()
