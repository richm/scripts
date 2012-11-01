import sys
import ldap
from pyasn1.type import tag, namedtype, univ, namedval
#from ldap_unbind_fix import LDAPMessage
from pyasn1.codec.der import decoder

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

# hex dump looks like this: 0a 01 02 or 0a 01 0a and usually the last sequence is 0a 01 00
class TRSUnknownInt(univ.Integer):
    tagSet = tag.initTagSet(
        tag.Tag(tag.tagClassUniversal, tag.tagFormatSimple, 0x0a)
        )

#  Sequence().setComponentByPosition(0, Integer('1')).setComponentByPosition(1, Integer('2')).setComponentByPosition(2, OctetString('1.3.6.1.4.1.42.2.27.9.9.1')).setComponentByPosition(3, OctetString('dc=example,dc=com')).setComponentByPosition(4, Integer('1')).setComponentByPosition(5, OctetString('+from:el5i386:389:1:1:to:opensol.testdomain.com:389:dc=example,dc=com+')).setComponentByPosition(6, Set().setComponentByPosition(0, OctetString('{replicageneration} 50913350000000010000')).setComponentByPosition(1, OctetString('{replica 1 ldap://el5i386:389}')).setComponentByPosition(2, OctetString('{replica 4 ldap://opensol.testdomain.com:389}'))).setComponentByPosition(7, OctetString('50913362000000010000')).setComponentByPosition(8, Integer('10')).setComponentByPosition(9, Integer('1')).setComponentByPosition(10, Integer('0')).setComponentByPosition(11, Integer('0')) 
class TRSStartReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSUnknownInt()), namedtype.NamedType('unknownInt1', TRSUnknownInt()),
        namedtype.NamedType('subOid', ldap.LDAPOID()), namedtype.NamedType('replDN', ldap.LDAPDN()),
        namedtype.NamedType('unknownInt4', TRSUnknownInt()), namedtype.NamedType('replDesc', ldap.LDAPString()),
        namedtype.NamedType('ruv', RUV()),
        namedtype.NamedType('maxcsn', ldap.LDAPString()),
        namedtype.NamedType('unknownInt8', TRSUnknownInt()), namedtype.NamedType('unknownInt9', TRSUnknownInt()),
        namedtype.NamedType('unknownInt10', TRSUnknownInt()), namedtype.NamedType('unknownInt11', TRSUnknownInt())
        )

class TRSStartResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSUnknownInt()), namedtype.NamedType('unknownInt1', TRSUnknownInt()),
        namedtype.NamedType('unknownInt2', TRSUnknownInt()), namedtype.NamedType('unknownInt3', TRSUnknownInt()),
        namedtype.NamedType('unknownInt4', TRSUnknownInt()), namedtype.NamedType('replDesc', ldap.LDAPString()),
        namedtype.NamedType('unknownInt6', TRSUnknownInt()), namedtype.NamedType('unknownInt7', TRSUnknownInt()),
        namedtype.NamedType('unknownInt8', TRSUnknownInt()), namedtype.NamedType('unknownInt9', TRSUnknownInt())
        )

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

class TRSEntrySeq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('trsentryid', TRSUnknownInt()),
        namedtype.NamedType('trsentry', TRSEntry())
        )

class TRSEntryReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSUnknownInt()),
        namedtype.NamedType('trsentryset', univ.SetOf(componentType=TRSEntrySeq()))
        )

class TRSEuidResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSUnknownInt()), namedtype.NamedType('unknownInt1', TRSUnknownInt())
        )

class TRSEntryResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSUnknownInt())
        )

class TRSEndReq(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('replDN', ldap.LDAPDN()), namedtype.NamedType('ruv', RUV())
        )

class TRSEndResp(univ.Sequence):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('unknownInt0', TRSUnknownInt())
        )

class MyUnbindRequest(ldap.UnbindRequest):
    def verifySizeSpec(self): pass # valueDecoder expects this method

class MyLDAPMessage(ldap.LDAPMessage):
    componentType = namedtype.NamedTypes(
        namedtype.NamedType('messageID', ldap.MessageID()),
        namedtype.NamedType('protocolOp', univ.Choice(componentType=namedtype.NamedTypes(namedtype.NamedType('bindRequest', ldap.BindRequest()), namedtype.NamedType('bindResponse', ldap.BindResponse()), namedtype.NamedType('unbindRequest', MyUnbindRequest()), namedtype.NamedType('searchRequest', ldap.SearchRequest()), namedtype.NamedType('searchResEntry', ldap.SearchResultEntry()), namedtype.NamedType('searchResDone', ldap.SearchResultDone()), namedtype.NamedType('searchResRef', ldap.SearchResultReference()), namedtype.NamedType('modifyRequest', ldap.ModifyRequest()), namedtype.NamedType('modifyResponse', ldap.ModifyResponse()), namedtype.NamedType('addRequest', ldap.AddRequest()), namedtype.NamedType('addResponse', ldap.AddResponse()), namedtype.NamedType('delRequest', ldap.DelRequest()), namedtype.NamedType('delResponse', ldap.DelResponse()), namedtype.NamedType('modDNRequest', ldap.ModifyDNRequest()), namedtype.NamedType('modDNResponse', ldap.ModifyDNResponse()), namedtype.NamedType('compareRequest', ldap.CompareRequest()), namedtype.NamedType('compareResponse', ldap.CompareResponse()), namedtype.NamedType('abandonRequest', ldap.AbandonRequest()), namedtype.NamedType('extendedReq', ldap.ExtendedRequest()), namedtype.NamedType('extendedResp', ldap.ExtendedResponse())))),
        namedtype.OptionalNamedType('controls', ldap.Controls().subtype(implicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatConstructed, 0)))
        )

oid2asn = {
"1.3.6.1.4.1.42.2.27.9.6.1":{"name":"REPL_TRS_START_REQ_OID", "asn":TRSStartReq()},
"1.3.6.1.4.1.42.2.27.9.6.2":{"name":"REPL_TRS_RESUME_REQ_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.3":{"name":"REPL_TRS_SUSPEND_REQ_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.4":{"name":"REPL_TRS_ACQUIRE_REQ_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.5":{"name":"REPL_TRS_RELEASE_REQ_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.6":{"name":"REPL_TRS_END_REQ_OID", "asn":TRSEndReq()},
"1.3.6.1.4.1.42.2.27.9.6.7":{"name":"REPL_TRS_ENTRY_REQ_OID", "asn":TRSEntryReq()},
"1.3.6.1.4.1.42.2.27.9.6.8":{"name":"REPL_TRS_UPDATE_REQ_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.9":{"name":"REPL_TRS_CTRL_REQ_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.11":{"name":"REPL_TRS_START_RESP_OID", "asn":TRSStartResp()},
"1.3.6.1.4.1.42.2.27.9.6.12":{"name":"REPL_TRS_RESUME_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.13":{"name":"REPL_TRS_SUSPEND_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.14":{"name":"REPL_TRS_ACQUIRE_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.15":{"name":"REPL_TRS_RELEASE_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.16":{"name":"REPL_TRS_END_RESP_OID", "asn":TRSEndResp()},
"1.3.6.1.4.1.42.2.27.9.6.17":{"name":"REPL_TRS_ENTRY_RESP_OID", "asn":TRSEntryResp()},
"1.3.6.1.4.1.42.2.27.9.6.18":{"name":"REPL_TRS_UPDATE_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.19":{"name":"REPL_TRS_CTRL_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.21":{"name":"REPL_TRS_MODS_OP_RESP_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.6.22":{"name":"REPL_TRS_EUID_OP_RESP_OID", "asn":TRSEuidResp()},
"1.3.6.1.4.1.42.2.27.9.9.1":{"name":"REPL_TRS_TOTAL_UPDATE_OID", "asn":univ.Sequence()},
"1.3.6.1.4.1.42.2.27.9.9.2":{"name":"REPL_TRS_INCREMENTAL_UPDATE_OID", "asn":univ.Sequence()}
}

for fn in sys.argv[1:]:
    f = open(fn)
    print "reading", fn
    buf = f.read()
    ii = 0
    while buf:
        print "reading message", ii
        ldapMessage, buf = decoder.decode(buf, asn1Spec=MyLDAPMessage())
        if ldapMessage:
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
                name = oid2asn.get(extoid, {}).get('name', '')
                asn = oid2asn.get(extoid, {}).get('asn', '')
                msgid = ldapMessage.getComponentByName('messageID')._value
                print "MyLDAPMessage"
                print " messageID=%s" % str(msgid)
                print " %s=%s (%s)" % (extname, extoid, name)
                obj, buf2 = decoder.decode(extval, asn1Spec=asn)
                print " ", obj.prettyPrint(2), "\n"
            else:
                print ldapMessage.prettyPrint()
        ii += 1
    f.close()
