import sys
from argparse import ArgumentParser

# this must be the ldap.py module provided with pyasn1, not python-ldap
try:
    from pyasn1.type import tag, namedtype, univ, namedval
    from pyasn1.codec.der import decoder
    from pyasn1.error import SubstrateUnderrunError
    import pyasn1.codec.ber.eoo
    import ldap
except ImportError:
    print "you need the pyasn1 package"
    sys.exit(1)

try:
    dummy = ldap.LDAPMessage
except AttributeError:
    print "this not the right ldap.py module from pyasn1"
    print "e.g. set PYTHONPATH to include /usr/share/doc/python-pyasn1-0.0.12a"
    sys.exit(1)

usescapy = False # scapy does not handle TCP retransmissions
if usescapy:
    try:
        import scapy.all
        from scapy.layers.inet import TCP, IP
        from scapy.utils import PcapReader
    except ImportError:
        print "you need the scapy package"
        sys.exit(1)
else: # use pynids
    try:
        import nids
    except ImportError:
        print "you need the pynids package"
        print "or build pynids from source and"
        print "set PYTHONPATH to include /path/to/pynids-0.6.1/build/lib.linux-x86_64-2.6"
        sys.exit(1)

(QUIET, INFO, VERBOSE, DEBUG) = range(0, 4)
loglevel = INFO

parser = ArgumentParser()
parser.add_argument('files', nargs='+', help='files in pcap format')
parser.add_argument('-v', action='count', help='repeat for more verbosity', default=INFO)
parser.add_argument('-i', type=int, help='iterations of main loop - use tcpdump -r file|wc -l to get value')
parser.add_argument('-e', help='python boolean expression')
parser.add_argument('-f', help='pcap-filter expression')
args = parser.parse_args()
loglevel = args.v
niters = args.i
expr = args.e
filt = args.f
files = args.files
exprcode = None
if expr:
    exprcode = compile(args.e, '<string>', 'eval')

def berlen(s):
    octets = map(ord, s)
    l = octets[0]
    if not l & 0x80:
        return l
    l &= 0x7f
    if len(s) <= l:
        raise Exception("error: length of s", s, len(s), "less than length byte", l)
    ll = 0L
    for c in octets[1:l+1]:
        ll <<= 8L
        ll |= c
    return ll

def berint(s):
    octets = map(ord, s)
    if octets[0] & 0x80:
        value = -1L
    else:
        value = 0L
    for octet in octets:
        value = value << 8 | octet
    return value

class RUVElement(univ.OctetString): pass

class RUV(univ.SetOf):
    componentType = RUVElement()
    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ':\n'
        for idx in range(len(self._componentValues)):
            if idx: r = r + '\n'
            r = r + ' '*scope + self._componentValues[idx].prettyPrint(scope)
        return r

class TRSEnum(univ.Enumerated): pass

class TRSStartRespInfo(univ.SequenceOf):
    componentType = univ.OctetString()

#  Sequence().setComponentByPosition(0, Integer('1')).setComponentByPosition(1, Integer('2')).setComponentByPosition(2, OctetString('1.3.6.1.4.1.42.2.27.9.9.1')).setComponentByPosition(3, OctetString('dc=example,dc=com')).setComponentByPosition(4, Integer('1')).setComponentByPosition(5, OctetString('+from:el5i386:389:1:1:to:opensol.testdomain.com:389:dc=example,dc=com+')).setComponentByPosition(6, Set().setComponentByPosition(0, OctetString('{replicageneration} 50913350000000010000')).setComponentByPosition(1, OctetString('{replica 1 ldap://el5i386:389}')).setComponentByPosition(2, OctetString('{replica 4 ldap://opensol.testdomain.com:389}'))).setComponentByPosition(7, OctetString('50913362000000010000')).setComponentByPosition(8, Integer('10')).setComponentByPosition(9, Integer('1')).setComponentByPosition(10, Integer('0')).setComponentByPosition(11, Integer('0')) 
class TRSStartReq(univ.Sequence):
    suboids = {"1.3.6.1.4.1.42.2.27.9.9.1":"REPL_TRS_TOTAL_UPDATE_OID",
               "1.3.6.1.4.1.42.2.27.9.9.2":"REPL_TRS_INCREMENTAL_UPDATE_OID"}
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()), namedtype.NamedType('unknownInt1', TRSEnum()),
        namedtype.NamedType('subOid', ldap.LDAPOID()), namedtype.NamedType('replDN', ldap.LDAPDN()),
        namedtype.NamedType('replicaID', TRSEnum()), namedtype.NamedType('replDesc', ldap.LDAPString()),
        namedtype.NamedType('ruv', RUV()),
        namedtype.NamedType('maxcsn', ldap.LDAPString()),
        namedtype.NamedType('unknownInt8', TRSEnum()), namedtype.NamedType('unknownInt9', TRSEnum()),
        namedtype.NamedType('unknownInt10', TRSEnum()), namedtype.NamedType('unknownInt11', TRSEnum())
        )
    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ': ' + self.getComponentByName('subOid')._value + '\n'
        return r + univ.Sequence.prettyPrint(self)
    def check(self):
        assert(self.getComponentByName('unknownInt0')._value == 1)
        assert(self.getComponentByName('unknownInt1')._value == 2)
        assert(self.getComponentByName('subOid')._value in self.suboids)
        assert(self.getComponentByName('replicaID')._value <= 4)
        assert(self.getComponentByName('unknownInt8')._value == 10)
        assert(self.getComponentByName('unknownInt9')._value == 1)
        assert(self.getComponentByName('unknownInt10')._value == 0)
        assert(self.getComponentByName('unknownInt11')._value == 0)

class TRSStartResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()), namedtype.NamedType('unknownInt1', TRSEnum()),
        namedtype.NamedType('unknownInt2', TRSEnum()), namedtype.NamedType('unknownInt3', TRSEnum()),
        namedtype.NamedType('unknownInt4', TRSEnum()), namedtype.NamedType('replDesc', ldap.LDAPString()),
        namedtype.NamedType('unknownInt6', TRSEnum()), namedtype.NamedType('unknownInt7', TRSEnum()),
        namedtype.NamedType('unknownInt8', TRSEnum()), namedtype.NamedType('unknownInt9', TRSEnum()),
        namedtype.OptionalNamedType('replinfo', TRSStartRespInfo())
        )
    def check(self):
        assert(self.getComponentByName('unknownInt0')._value == 0)
        assert(self.getComponentByName('unknownInt1')._value == 1)
        assert(self.getComponentByName('unknownInt2')._value == 2)
        val = self.getComponentByName('unknownInt3')._value
        if val == 4: pass # default
        elif val == 1: print "non-default value", val
        else: assert(1)
        assert(self.getComponentByName('unknownInt4')._value == 3)
        assert(self.getComponentByName('unknownInt6')._value == 10)
        assert(self.getComponentByName('unknownInt7')._value == 1)
        assert(self.getComponentByName('unknownInt8')._value == 2097152)
        assert(self.getComponentByName('unknownInt9')._value == 0)

#Sequence().setComponentByPosition(0, Integer('0')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, Integer('1')).setComponentByPosition(1, Sequence().setComponentByPosition(0, OctetString('df538d2a-236511e2-80edd31d-f9926e3e')).setComponentByPosition(1, OctetString('dc=example,dc=com')))).searchresultentry)
#Sequence().setComponentByPosition(0, Integer('0')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, Integer('1')).setComponentByPosition(1, Sequence().setComponentByPosition(0, OctetString('df538d2a-236511e2-80edd31d-f9926e3e')).setComponentByPosition(1, OctetString('dc=example,dc=com')).setComponentByPosition(2, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('dc')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('example')).setComponentByPosition(1, Sequence())))).setComponentByPosition(1, Sequence().setComponentByPosition(0, OctetString('objectClass')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('top')).setComponentByPosition(1, Sequence())).setComponentByPosition(1, Sequence().setComponentByPosition(0, OctetString('domain')).setComponentByPosition(1, Sequence())))).setComponentByPosition(2, Sequence().setComponentByPosition(0, OctetString('creatorsName')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('cn=directory manager')).setComponentByPosition(1, Sequence())))).setComponentByPosition(3, Sequence().setComponentByPosition(0, OctetString('modifiersName')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('cn=directory manager')).setComponentByPosition(1, Sequence())))).setComponentByPosition(4, Sequence().setComponentByPosition(0, OctetString('createTimestamp')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('20121031141853Z')).setComponentByPosition(1, Sequence())))).setComponentByPosition(5, Sequence().setComponentByPosition(0, OctetString('modifyTimestamp')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('20121031141853Z')).setComponentByPosition(1, Sequence())))).setComponentByPosition(6, Sequence().setComponentByPosition(0, OctetString('entryid')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('1')).setComponentByPosition(1, Sequence())))).setComponentByPosition(7, Sequence().setComponentByPosition(0, OctetString('entrydn')).setComponentByPosition(1, Set().setComponentByPosition(0, Sequence().setComponentByPosition(0, OctetString('dc=example,dc=com')).setComponentByPosition(1, Sequence()))))))))

# hex bytes look like this: 30 0b 04 07 65 78 61 6d 70 6c 65 30 00
# so a sequence (30) of length 11 (0b) consisting of:
#   an octetstring (04) of length 7 with value example
#   a sequence (30) of length 0 - not sure what this sequence is supposed to contain, assuming some sort
#     of replication meta-data in an octetstring
class TRSAttributeValue(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('val', univ.OctetString()),
        namedtype.NamedType('extra', univ.Sequence(componentType=namedtype.NamedTypes(
                    namedtype.OptionalNamedType('extraval', univ.OctetString()))))
        )

class TRSAttribute(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('type', ldap.AttributeDescription()),
        namedtype.NamedType('vals', univ.SetOf(componentType=TRSAttributeValue()))
        )

class TRSEntry(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('uuid', ldap.LDAPString()), namedtype.NamedType('dn', ldap.LDAPDN()),
        namedtype.NamedType('entry', univ.SetOf(componentType=TRSAttribute()))
        )
    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ':\n'
        scopestr = ' '*scope
        r = r + '%sdn: %s\n%suuid: %s\n' % (scopestr, self._componentValues[1], scopestr, self._componentValues[0])
        for ii in range(0, len(self._componentValues[2])):
            trsattr = self._componentValues[2][ii]
            name = trsattr[0]
            vals = trsattr[1]
            for jj in range(0, len(vals)):
                val = vals[jj][0]
                r = r + '%s%s: %s\n' % (scopestr, name, val)
                if len(vals[jj][1]):
                    r = r + '\n%sextra-%s: %s' % (scopestr, name, str(vals[jj][1]))
        return r
    def check(self):
        for ii in range(0, len(self._componentValues[2])):
            trsattr = self._componentValues[2][ii]
            vals = trsattr[1]
            for jj in range(0, len(vals)):
                # want to know if the extra field ever has any data in it
                assert(len(vals[jj][1]) == 0)

class TRSEntrySeq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('trsentryid', TRSEnum()),
        namedtype.NamedType('trsentry', TRSEntry())
        )
    def check(self): self[1].check()

class TRSEntryReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()),
        namedtype.NamedType('trsentryset', univ.SetOf(componentType=TRSEntrySeq()))
        )
    def check(self):
        assert(self.getComponentByName('unknownInt0')._value == 0)
        assert(len(self[1]) == 1)
        self[1][0].check()

# looks like this: 0a 01 00 0a 01 07
# looks like the trsentryid field corresponds to the trsentryid field in the TRSEntrySeq in the TRSEntryReq
# perhaps the unknownInt0 field here corresponds to the unknownInt0 field in the TRSEntryReq or Resp
class TRSEuidResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('probResultCode', TRSEnum()), namedtype.NamedType('trsentryid', TRSEnum())
        )
    def check(self):
        assert(self[0]._value == 0)

class TRSEntryResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('probResultCode', TRSEnum())
        )
    def check(self):
        assert(self[0]._value == 0)

# add op
# 0\x82\x01\xfa - ldap tl preamble
#   \n\x01\x00 - trsenum
#   1\x82\x01\xf3 - set of trsupdateseq
#     0\x82\x01\xef - sequence of trsenum, trsmeta, trsupdate
#       \n\x01\x01 - trsenum
#       0` - sequence of
#         \x10#b55e4101-2ab011e2-808bafb5-37d3ceb6 - \x10 add tag followed by entry uuid
#         \x04\x14509d6f5f000000010000 - csn
#         \x04#8e077400-2ab011e2-80000000-00000000
#       0\x82\x01\x86 - sequence of trsupdateadd
#         \x04\x1ecn=testuser1,dc=example,dc=com - entry dn
#         0\x82\x01b - sequence of type/vals sequences
#          0\x1c - sequence of type/vals
#            \x04\x0bobjectClass - attribute type
#            1\r - set of values
#              \x04\x06person \x04\x03top
#          0\r - sequence of type/vals
#            \x04\x02sn - attribute type
#            1\x07 - set of values
#              \x04\x05User1
#          0\x11
#            \x04\x02cn
#            1\x0b
#              \x04\ttestuser1
#          0&
#            \x04\x0ccreatorsName
#            1\x16
#              \x04\x14cn=directory manager
#          0'
#            \x04\rmodifiersName
#            1\x16
#              \x04\x14cn=directory manager
#          0$
#            \x04\x0fcreateTimestamp
#            1\x11
#              \x04\x0f20121109210223Z
#          0$
#            \x04\x0fmodifyTimestamp
#            1\x11
#              \x04\x0f20121109210223Z
#          03
#            \x04\nnsUniqueId
#            1%
#              \x04#b55e4101-2ab011e2-808bafb5-37d3ceb6
#          0\x0f
#            \x04\x08parentid
#            1\x03
#              \x04\x011
#          0\x10
#            \x04\x07entryid
#            1\x05
#              \x04\x03162
#          0+
#            \x04\x07entrydn
#            1 - "1 " - space character
#              \x04\x1ecn=testuser1,dc=example,dc=com
# mod op
# 0\x82\x01\x05 - ldap tl preamble
#   \n\x01\x00
#   1\x81\xff
#     0\x81\xfc
#       \n\x01\x01
#       0;
#         \x08#b55e4101-2ab011e2-808bafb5-37d3ceb6 - 08 means mod
#         \x04\x14509d6f74000000010000
#       0\x81\xb9 sequence of trsupdatemod
#         \x04\x1ecn=testuser1,dc=example,dc=com
#         0\x81\x96
#           0;
#             \n\x01\x02
#             06
#               \x04\x0bdescription
#               1'
#                 \x04%changed on el5i386.testdomain.com:389
#           0,
#             \n\x01\x02
#             0'
#               \x04\rmodifiersname
#               1\x16
#                 \x04\x14cn=directory manager
#           0)
#             \n\x01\x02
#             0$
#               \x04\x0fmodifytimestamp
#               1\x11
#                 \x04\x0f20121109210244Z
#
# delete
# 0\x81\x90 - ldap preamble
#   \n\x01\x00 - trs enum
#   1\x81\x8a - set of
#     0\x81\x87 - sequence of
#       \n\x01\x01 - trsenum
#       0` - sequence of
#         \x20#b55e4101-2ab011e2-808bafb5-37d3ceb6 - 0x20 - delete
#         \x04\x14509d6f89000100010000
#         \x04#8e077400-2ab011e2-80000000-00000000
#       0\x20 - sequence of
#         \x04\x1ecn=testuser1,dc=example,dc=com

class TRSUpdateAdd(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('dn', ldap.LDAPDN()),
        namedtype.NamedType('entry', ldap.PartialAttributeList())
        )
    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ':\n'
        scopestr = ' '*scope
        r = r + '%sdn: %s\n' % (scopestr, self._componentValues[0])
        for ii in range(0, len(self._componentValues[1])):
            trsattr = self._componentValues[1][ii]
            name = trsattr[0]
            vals = trsattr[1]
            for jj in range(0, len(vals)):
                val = vals[jj]
                r = r + '%s%s: %s\n' % (scopestr, name, val)
        return r
    def check(self): pass

class TRSUpdateMod(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('dn', ldap.LDAPDN()),
        namedtype.NamedType('mods', univ.SequenceOf(componentType=univ.Sequence(componentType=namedtype.NamedTypes(namedtype.NamedType('op', univ.Enumerated(namedValues=namedval.NamedValues(('add', 0), ('delete', 1), ('replace', 2)))), namedtype.NamedType('vals', ldap.AttributeTypeAndValues())))))
        )
    def prettyPrint(self, scope=0):
        scope = scope + 1
        r = self.__class__.__name__ + ':\n'
        scopestr = ' '*scope
        r = r + '%sdn: %s\n' % (scopestr, self._componentValues[0])
        for ii in range(0, len(self._componentValues[1])):
            trsattr = self._componentValues[1][ii]
            name = trsattr[0]
            vals = trsattr[1]
            for jj in range(0, len(vals)):
                val = vals[jj]
                r = r + '%s%s: %s\n' % (scopestr, name, val)
        return r
    def check(self): pass

# the update del uses 0x20 (32) as the choice tag - pyasn1 really doesn't like this
# this is translated to (tag.tagClassUniversal, tag.tagFormatConstructed, 0x00) which
# is a Sequence, which pyasn1 doesn't want to decode as an OctetString, or it is
# translated to (0, 0, 0) which is the EndOfOctets code, which pyasn1 doesn't want
# to decode as an OctetString
# so we tell the decoder to decode EndOfOctets as an octet string
# unfortunately, the TRSUpdateUUID Choice class and the TRSUpdateDelChoice OctetString
# class share the same tag, so the ChoiceDecoder has to differentiate them based
# on the realasn1Spec type
class MyChoiceDecoder(pyasn1.codec.ber.decoder.AbstractDecoder):
    protoComponent = univ.Choice()
    def valueDecoder(self, substrate, asn1Spec, tagSet,
                     length, state, decodeFun):
        # the regular decoder passes asn1Spec as a hash instead of a
        # concrete class - so we do what it does and extract the
        # concrete class
        realasn1Spec = asn1Spec[tagSet]
        r = self._createComponent(tagSet, realasn1Spec) # XXX use default tagset
        if realasn1Spec.__class__ == TRSUpdateDelChoice:
            return r.clone(str(substrate)), ''
        if not decodeFun:
            return r, substrate
        if r.getTagSet() == tagSet: # explicitly tagged Choice
            component, substrate = decodeFun(
                substrate, r.getComponentTypeMap()
                )
        else:
            component, substrate = decodeFun(
                substrate, r.getComponentTypeMap(), tagSet, length, state
                )
        effectiveTagSet = getattr(
            component, 'getEffectiveTagSet', component.getTagSet
            )()
        r.setComponentByType(effectiveTagSet, component)
        return r, substrate

    indefLenValueDecoder = valueDecoder

usemydecode = True
if usemydecode:
    mycodecmap = decoder.decoder.codecMap.copy()
    mycodecmap.update({
            pyasn1.codec.ber.eoo.EndOfOctets.tagSet: MyChoiceDecoder(),
            })
    mydecode = decoder.decoder.Decoder(mycodecmap)
else:
    mydecode = decoder.decode

# not sure why this is a sequence unless there can be some optional component
class TRSUpdateDel(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('dn', ldap.LDAPDN()),
        namedtype.OptionalNamedType('unknown', ldap.LDAPString())
        )

class TRSUpdateDelChoice(univ.OctetString):
    tagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatConstructed, 0)
        )

class TRSUpdateUUID(univ.Choice):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('mod',
                            univ.OctetString().subtype(implicitTag=tag.Tag(tag.tagClassUniversal,
                                                                           tag.tagFormatSimple, 0x08))),
        namedtype.NamedType('add',
                            univ.OctetString().subtype(implicitTag=tag.Tag(tag.tagClassUniversal,
                                                                           tag.tagFormatSimple, 0x10))),
        namedtype.NamedType('del', TRSUpdateDelChoice())
        )

class TRSUpdateMeta(univ.Sequence):
    # looks like unknownuuid is present on add ops - could be the parent uuid
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('entryuuid', TRSUpdateUUID()),
        namedtype.NamedType('csn', ldap.LDAPString()),
        namedtype.OptionalNamedType('unknownuuid', ldap.LDAPString())
        )

class TRSUpdateSeq(univ.Sequence):
    # assume TRSUpdateAdd initially, change to other type as needed
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()), namedtype.NamedType('trsupdatemeta', TRSUpdateMeta()),
        namedtype.NamedType('trsupdate', TRSUpdateAdd())
        )
    # map of modop to mod type
    modmap = {'add':TRSUpdateAdd, 'mod':TRSUpdateMod, 'del':TRSUpdateDel}

    # def getComponentByPosition(self, idx):
    #     print "in getComponentByPosition"
    #     return univ.Sequence.getComponentByPosition(self, idx)
    # def setComponentByPosition(self, idx, value=None):
    #     print "in setComponentByPosition"
    #     return univ.Sequence.setComponentByPosition(self, idx, value)
    # def getComponentTypeMap(self):
    #     print "in getComponentTypeMap"
    #     return univ.Sequence.getComponentTypeMap(self)
    # def getComponentByName(self, name):
    #     print "in getComponentByName"
    #     return univ.Sequence.getComponentByName(self, name)
    # def setComponentByName(self, name, value=None):
    #     print "in setComponentByName"
    #     return univ.Sequence.setComponentByName(self, name, value)
    # def getComponentByPosition(self, idx):
    #     print "in getComponentByPosition"
    #     return univ.Sequence.getComponentByPosition(self, idx)
    # def setComponentByPosition(self, idx, value=None):
    #     print "in setComponentByPosition"
    #     return univ.Sequence.setComponentByPosition(self, idx, value)
    def getComponentTypeMapNearPosition(self, idx):
        print "in getComponentTypeMapNearPosition"
        if idx == 2: # the actual mod object type
            clz = self.modmap[self[1][0].getName()]
            compmap = {self.tagSet:clz()}
        else:
            compmap = univ.Sequence.getComponentTypeMapNearPosition(self, idx)
        return compmap
    # def getComponentPositionNearType(self, tagSet, idx):
    #     print "in getComponentPositionNearType"
    #     comp = univ.Sequence.getComponentPositionNearType(self, tagSet, idx)
    #     return comp

    def check(self): self[1].check()

class TRSUpdateReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()),
        namedtype.NamedType('trsupdateset', univ.SetOf(componentType=TRSUpdateSeq()))
        )

class TRSModsOpResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()), namedtype.NamedType('unknownInt1', TRSEnum()),
        namedtype.NamedType('csn', ldap.LDAPString())
        )

class TRSUpdateResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('probResultCode', TRSEnum())
        )

class TRSReleaseReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum())
        )

class TRSReleaseResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum())
        )

class TRSAcquireReq(univ.Sequence):
    # ruv looks like an RUV, but has a weird tag 0x8d instead of the normal set 0x31
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum())
        )

class TRSAcquireResp(univ.Sequence):
    # ruv looks like an RUV, but has a weird tag 0x8d instead of the normal set 0x31
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSEnum()),
        namedtype.NamedType('unknownInt1', TRSEnum()),
        namedtype.OptionalNamedType('ruv',
                                    RUV().subtype(implicitTag=tag.Tag(tag.tagClassContext,
                                                                      tag.tagFormatSimple, 0x0d)))
        )

class TRSEndReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('replDN', ldap.LDAPDN()), namedtype.NamedType('ruv', RUV())
        )
    def check(self): pass

class TRSEndResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('probResultCode', TRSEnum())
        )
    def check(self):
        assert(self[0]._value == 0)

class MyUnbindRequest(ldap.UnbindRequest):
    def verifySizeSpec(self): pass # valueDecoder expects this method

class MyDelRequest(ldap.LDAPDN):
    tagSet = univ.OctetString.tagSet.tagImplicitly(
        tag.Tag(tag.tagClassApplication, tag.tagFormatSimple, 10)
        )

class MyLDAPMessage(ldap.LDAPMessage):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('messageID', ldap.MessageID()),
        namedtype.NamedType('protocolOp', univ.Choice(componentType=namedtype.NamedTypes(namedtype.NamedType('bindRequest', ldap.BindRequest()), namedtype.NamedType('bindResponse', ldap.BindResponse()), namedtype.NamedType('unbindRequest', MyUnbindRequest()), namedtype.NamedType('searchRequest', ldap.SearchRequest()), namedtype.NamedType('searchResEntry', ldap.SearchResultEntry()), namedtype.NamedType('searchResDone', ldap.SearchResultDone()), namedtype.NamedType('searchResRef', ldap.SearchResultReference()), namedtype.NamedType('modifyRequest', ldap.ModifyRequest()), namedtype.NamedType('modifyResponse', ldap.ModifyResponse()), namedtype.NamedType('addRequest', ldap.AddRequest()), namedtype.NamedType('addResponse', ldap.AddResponse()), namedtype.NamedType('delRequest', MyDelRequest()), namedtype.NamedType('delResponse', ldap.DelResponse()), namedtype.NamedType('modDNRequest', ldap.ModifyDNRequest()), namedtype.NamedType('modDNResponse', ldap.ModifyDNResponse()), namedtype.NamedType('compareRequest', ldap.CompareRequest()), namedtype.NamedType('compareResponse', ldap.CompareResponse()), namedtype.NamedType('abandonRequest', ldap.AbandonRequest()), namedtype.NamedType('extendedReq', ldap.ExtendedRequest()), namedtype.NamedType('extendedResp', ldap.ExtendedResponse())))),
        namedtype.OptionalNamedType('controls', ldap.Controls().subtype(implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatConstructed, 0)))
        )

oid2asn = {
"1.3.6.1.4.1.42.2.27.9.6.1":{"name":"REPL_TRS_START_REQ_OID", "asn":TRSStartReq(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.2":{"name":"REPL_TRS_RESUME_REQ_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.3":{"name":"REPL_TRS_SUSPEND_REQ_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.4":{"name":"REPL_TRS_ACQUIRE_REQ_OID", "asn":TRSAcquireReq(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.5":{"name":"REPL_TRS_RELEASE_REQ_OID", "asn":TRSReleaseReq(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.6":{"name":"REPL_TRS_END_REQ_OID", "asn":TRSEndReq(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.7":{"name":"REPL_TRS_ENTRY_REQ_OID", "asn":TRSEntryReq(), 'loglevel':DEBUG},
"1.3.6.1.4.1.42.2.27.9.6.8":{"name":"REPL_TRS_UPDATE_REQ_OID", "asn":TRSUpdateReq(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.9":{"name":"REPL_TRS_CTRL_REQ_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.11":{"name":"REPL_TRS_START_RESP_OID", "asn":TRSStartResp(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.12":{"name":"REPL_TRS_RESUME_RESP_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.13":{"name":"REPL_TRS_SUSPEND_RESP_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.14":{"name":"REPL_TRS_ACQUIRE_RESP_OID", "asn":TRSAcquireResp(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.15":{"name":"REPL_TRS_RELEASE_RESP_OID", "asn":TRSReleaseResp(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.16":{"name":"REPL_TRS_END_RESP_OID", "asn":TRSEndResp(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.17":{"name":"REPL_TRS_ENTRY_RESP_OID", "asn":TRSEntryResp(), 'loglevel':DEBUG},
"1.3.6.1.4.1.42.2.27.9.6.18":{"name":"REPL_TRS_UPDATE_RESP_OID", "asn":TRSUpdateResp(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.19":{"name":"REPL_TRS_CTRL_RESP_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.21":{"name":"REPL_TRS_MODS_OP_RESP_OID", "asn":TRSModsOpResp(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.6.22":{"name":"REPL_TRS_EUID_OP_RESP_OID", "asn":TRSEuidResp(), 'loglevel':DEBUG},
"1.3.6.1.4.1.42.2.27.9.9.1":{"name":"REPL_TRS_TOTAL_UPDATE_OID", "asn":univ.Sequence(), 'loglevel':INFO},
"1.3.6.1.4.1.42.2.27.9.9.2":{"name":"REPL_TRS_INCREMENTAL_UPDATE_OID", "asn":univ.Sequence(), 'loglevel':INFO}
}

# list of incomplete buffers for which we need to complete the PDU
# indexed by srcip,destip,sport,dport
pending = {}
euids = {} # pending euid response entryids

# key is OID - value is number of these seen
opcount = {}

def printcounts():
    ret = ''
    for key, val in opcount.iteritems():
        name = oid2asn[key]['name']
        ret += "%s (%s): %d times\n" % (name, key, val)
    return ret
        
# pktary = [] # scapy

ldapmsgcount = 0

def processldap(ldapMessage, tcp):
    extreq = ldapMessage.getComponentByName('protocolOp').getComponentByName('extendedReq')
    extresp = ldapMessage.getComponentByName('protocolOp').getComponentByName('extendedResp')
    extname = ''
    if extreq or extresp:
        if extreq:
            extoid = extreq.getComponentByName('requestName')._value
            extval = extreq.getComponentByName('requestValue')._value
            extname = 'ExtendedRequest'
        else:
            extoid = extresp.getComponentByName('responseName')._value
            extval = extresp.getComponentByName('response')._value
            extname = 'ExtendedResponse'
        opcount[extoid] = opcount.setdefault(extoid, 0) + 1
        name = oid2asn.get(extoid, {}).get('name', '')
        asn = oid2asn.get(extoid, {}).get('asn', '')
        lvl = oid2asn.get(extoid, {}).get('loglevel', '')
        msgid = ldapMessage.getComponentByName('messageID')._value
        if lvl <= loglevel:
            print "MyLDAPMessage", tcp.addr, "messageID=%s" % str(msgid)
            print " %s=%s (%s)" % (extname, extoid, name)
        obj, buf2 = mydecode(extval, asn1Spec=asn)
        if lvl <= loglevel:
            print " ", obj.prettyPrint(2), "\n"
            if obj.__class__ == univ.Sequence:
                print " ", repr(obj), "\n"
        # checks
        # any errors in suspected error fields?
        try: obj.check()
        except AttributeError: pass # no check
        if extoid == "1.3.6.1.4.1.42.2.27.9.6.7":
            # save the entryid for later
            euids[obj[1][0][0]._value] = True
        elif extoid == "1.3.6.1.4.1.42.2.27.9.6.22":
            # have we seen this entryid before?
            assert(obj.getComponentByName('trsentryid')._value in euids)
            del euids[obj.getComponentByName('trsentryid')._value]
        elif extoid == "1.3.6.1.4.1.42.2.27.9.6.16" and loglevel > QUIET:
            print "End of update session"
            print printcounts()
        elif extoid == "1.3.6.1.4.1.42.2.27.9.6.1" and loglevel > QUIET:
            print "Start of update session"
            print printcounts()
    elif loglevel > QUIET:
        print ldapMessage.prettyPrint()

def dumptcp(tcp):
    print "addr %s server %d:%d:%d client %d:%d:%d" % (str(tcp.addr), tcp.server.count, tcp.server.count_new, tcp.server.offset, tcp.client.count, tcp.client.count_new, tcp.client.offset)

count = 0
skipcount = 0
def handleTcp(tcp):
    global count
    global ldapmsgcount
    if expr and not eval(exprcode):
        if loglevel >= DEBUG:
            print "found tcp packet that did not match expression", expr
            dumptcp(tcp)
        skipcount += 1
        return
    end_states = (nids.NIDS_CLOSE, nids.NIDS_TIMEOUT, nids.NIDS_RESET)
    if tcp.nids_state == nids.NIDS_JUST_EST:
        tcp.client.collect = 1
        tcp.server.collect = 1
    elif tcp.nids_state == nids.NIDS_DATA:
        count += 1
        if tcp.server.count_new:
            halfstr = tcp.server
            key = (tcp.addr, 'server')
        elif tcp.client.count_new:
            halfstr = tcp.client
            key = (tcp.addr, 'client')
        else:
            sys.stderr.write("Error: state is nids.NIDS_DATA but no new data available")
            return
        buf = pending.get(key, '')
        if buf: del pending[key]
        buf += halfstr.data[0:halfstr.count_new]
        while buf:
            try:
                ldapMessage, buf = mydecode(buf, asn1Spec=MyLDAPMessage())
                ldapmsgcount += 1
            except SubstrateUnderrunError, e:
                # we need more data from another packet to complete this PDU
                pending[key] = buf
                break
            if ldapMessage:
                processldap(ldapMessage, tcp)
    elif tcp.nids_state in end_states:
        print "connection closed"

for fn in files:
    print "reading", fn
    nids.param("filename", fn)
    nids.param("scan_num_hosts", 0)  # disable portscan detection
    nids.param("tcp_workarounds", 1)
    if filt:
        nids.param("pcap_filter", filt)
    try: nids.init()
    except nids.error, e:
        print "initialization error", e
        sys.exit(1)

    nids.register_tcp(handleTcp)

    for ii in xrange(0, niters):
        try:
            rc = nids.next()
            if rc == 0:
                print "nids next returned 0"
        except KeyboardInterrupt: break

print "ldapmsgcount =", ldapmsgcount
print "skipped =", skipcount
print "count =", count
print "pending =", pending
print "euids =", euids
print "opcount =", printcounts()

# scapy stuff
#     pkts = PcapReader(fn)
#     for pkt in pkts:
# #        print "reading packet", repr(pkt)
#         pktary.append(pkt)
#         if not pkt[TCP].payload: continue
#         buf = pending.get((pkt[IP].src, pkt[IP].dst, pkt[TCP].sport, pkt[TCP].dport), ('', None))[0]
#         if buf: del pending[(pkt[IP].src, pkt[IP].dst, pkt[TCP].sport, pkt[TCP].dport)]
#         buf += str(pkt[TCP].payload)
