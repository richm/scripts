
dirStringSyntaxes = [ '1.3.6.1.4.1.1466.115.121.1.15' ] # Directory String
dirStringCompatSyntaxes = [ '1.3.6.1.4.1.1466.115.121.1.11', # Country String
                            '1.3.6.1.4.1.1466.115.121.1.44' ] # Printable String

dirStringSyntaxes.append(dirStringCompatSyntaxes)
dirStringSyntaxes.sort()
dirStringCompatSyntaxes.sort()

mylist = [
{ "desc": """The bitStringMatch rule compares an assertion value of the Bit String
syntax to an attribute value of a syntax (e.g., the Bit String
syntax) whose corresponding ASN.1 type is BIT STRING.
If the corresponding ASN.1 type of the attribute syntax does not have
a named bit list [ASN.1] (which is the case for the Bit String
syntax), then the rule evaluates to TRUE if and only if the attribute
value has the same number of bits as the assertion value and the bits
match on a bitwise basis.
If the corresponding ASN.1 type does have a named bit list, then
bitStringMatch operates as above, except that trailing zero bits in
the attribute and assertion values are treated as absent.""",
 "oid": "2.5.13.16",
 "name": "bitStringMatch",
 "syntax": "1.3.6.1.4.1.1466.115.121.1.6" },
{ "desc": """The booleanMatch rule compares an assertion value of the Boolean
syntax to an attribute value of a syntax (e.g., the Boolean syntax)
whose corresponding ASN.1 type is BOOLEAN.
The rule evaluates to TRUE if and only if the attribute value and the
assertion value are both TRUE or both FALSE.""",
  "oid": "2.5.13.13",
  "name": "booleanMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.7" },
{ "desc": """The caseExactIA5Match rule compares an assertion value of the IA5
String syntax to an attribute value of a syntax (e.g., the IA5 String
syntax) whose corresponding ASN.1 type is IA5String.
The rule evaluates to TRUE if and only if the prepared attribute
value character string and the prepared assertion value character
string have the same number of characters and corresponding
characters have the same code point.
In preparing the attribute value and assertion value for comparison,
characters are not case folded in the Map preparation step, and only
Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
 "oid": "1.3.6.1.4.1.1466.109.114.1",
 "name": "caseExactIA5Match",
 "syntax": "1.3.6.1.4.1.1466.115.121.1.26" },
{ "desc": """The caseExactMatch rule compares an assertion value of the Directory
String syntax to an attribute value of a syntax (e.g., the Directory
String, Printable String, Country String, or Telephone Number syntax)
whose corresponding ASN.1 type is DirectoryString or one of the
alternative string types of DirectoryString, such as PrintableString
(the other alternatives do not correspond to any syntax defined in
this document).
The rule evaluates to TRUE if and only if the prepared attribute
value character string and the prepared assertion value character
string have the same number of characters and corresponding
characters have the same code point.
In preparing the attribute value and assertion value for comparison,
characters are not case folded in the Map preparation step, and only
Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "2.5.13.5",
  "name": "caseExactMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" },
{ "desc": """The caseExactOrderingMatch rule compares an assertion value of the
Directory String syntax to an attribute value of a syntax (e.g., the
Directory String, Printable String, Country String, or Telephone
Number syntax) whose corresponding ASN.1 type is DirectoryString or
one of its alternative string types.
The rule evaluates to TRUE if and only if, in the code point
collation order, the prepared attribute value character string
appears earlier than the prepared assertion value character string;
i.e., the attribute value is \"less than\" the assertion value.
In preparing the attribute value and assertion value for comparison,
characters are not case folded in the Map preparation step, and only
Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "2.5.13.6",
  "name": "caseExactOrderingMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" },
{ "desc": """The caseExactSubstringsMatch rule compares an assertion value of the
Substring Assertion syntax to an attribute value of a syntax (e.g.,
the Directory String, Printable String, Country String, or Telephone
Number syntax) whose corresponding ASN.1 type is DirectoryString or
one of its alternative string types.
The rule evaluates to TRUE if and only if (1) the prepared substrings
of the assertion value match disjoint portions of the prepared
attribute value character string in the order of the substrings in
the assertion value, (2) an <initial> substring, if present, matches
the beginning of the prepared attribute value character string, and
(3) a <final> substring, if present, matches the end of the prepared
attribute value character string.  A prepared substring matches a
portion of the prepared attribute value character string if
corresponding characters have the same code point.
In preparing the attribute value and assertion value substrings for
comparison, characters are not case folded in the Map preparation
step, and only Insignificant Space Handling is applied in the
Insignificant Character Handling step.""",
  "oid": "2.5.13.7",
  "name": "caseExactSubstringsMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.58" },
{ "desc": """The caseIgnoreIA5Match rule compares an assertion value of the IA5
String syntax to an attribute value of a syntax (e.g., the IA5 String
syntax) whose corresponding ASN.1 type is IA5String.
The rule evaluates to TRUE if and only if the prepared attribute
value character string and the prepared assertion value character
string have the same number of characters and corresponding
characters have the same code point.
In preparing the attribute value and assertion value for comparison,
characters are case folded in the Map preparation step, and only
Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "1.3.6.1.4.1.1466.109.114.2",
  "name": "caseIgnoreIA5Match",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.26" },
{ "desc": """The caseIgnoreIA5SubstringsMatch rule compares an assertion value of
the Substring Assertion syntax to an attribute value of a syntax
(e.g., the IA5 String syntax) whose corresponding ASN.1 type is
IA5String.
The rule evaluates to TRUE if and only if (1) the prepared substrings
of the assertion value match disjoint portions of the prepared
attribute value character string in the order of the substrings in
the assertion value, (2) an <initial> substring, if present, matches
the beginning of the prepared attribute value character string, and
(3) a <final> substring, if present, matches the end of the prepared
attribute value character string.  A prepared substring matches a
portion of the prepared attribute value character string if
corresponding characters have the same code point.
In preparing the attribute value and assertion value substrings for
comparison, characters are case folded in the Map preparation step,
and only Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "1.3.6.1.4.1.1466.109.114.3",
  "name": "caseIgnoreIA5SubstringsMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.58" },
{ "desc": """The caseIgnoreListMatch rule compares an assertion value that is a
sequence of strings to an attribute value of a syntax (e.g., the
Postal Address syntax) whose corresponding ASN.1 type is a SEQUENCE
OF the DirectoryString ASN.1 type.
The rule evaluates to TRUE if and only if the attribute value and the
assertion value have the same number of strings and corresponding
strings (by position) match according to the caseIgnoreMatch matching
rule.
In [X.520], the assertion syntax for this matching rule is defined to
be:
      SEQUENCE OF DirectoryString {ub-match}
That is, it is different from the corresponding type for the Postal
Address syntax.  The choice of the Postal Address syntax for the
assertion syntax of the caseIgnoreListMatch in LDAP should not be
seen as limiting the matching rule to apply only to attributes with
the Postal Address syntax.""",
  "oid": "2.5.13.11",
  "name": "caseIgnoreListMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.41" },
{ "desc": """The caseIgnoreListSubstringsMatch rule compares an assertion value of
the Substring Assertion syntax to an attribute value of a syntax
(e.g., the Postal Address syntax) whose corresponding ASN.1 type is a
SEQUENCE OF the DirectoryString ASN.1 type.
The rule evaluates to TRUE if and only if the assertion value
matches, per the caseIgnoreSubstringsMatch rule, the character string
formed by concatenating the strings of the attribute value, except
that none of the <initial>, <any>, or <final> substrings of the
assertion value are considered to match a substring of the
concatenated string which spans more than one of the original strings
of the attribute value.
Note that, in terms of the LDAP-specific encoding of the Postal
Address syntax, the concatenated string omits the <DOLLAR> line
separator and the escaping of \"\\\" and \"$\" characters.""",
  "oid": "2.5.13.12",
  "name": "caseIgnoreListSubstringsMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.58" },
{ "desc": """The caseIgnoreMatch rule compares an assertion value of the Directory
String syntax to an attribute value of a syntax (e.g., the Directory
String, Printable String, Country String, or Telephone Number syntax)
whose corresponding ASN.1 type is DirectoryString or one of its
alternative string types.
The rule evaluates to TRUE if and only if the prepared attribute
value character string and the prepared assertion value character
string have the same number of characters and corresponding
characters have the same code point.
In preparing the attribute value and assertion value for comparison,
characters are case folded in the Map preparation step, and only
Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "2.5.13.2",
  "name": "caseIgnoreMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" },
{ "desc": """The caseIgnoreOrderingMatch rule compares an assertion value of the
Directory String syntax to an attribute value of a syntax (e.g., the
Directory String, Printable String, Country String, or Telephone
Number syntax) whose corresponding ASN.1 type is DirectoryString or
one of its alternative string types.
The rule evaluates to TRUE if and only if, in the code point
collation order, the prepared attribute value character string
appears earlier than the prepared assertion value character string;
i.e., the attribute value is \"less than\" the assertion value.
In preparing the attribute value and assertion value for comparison,
characters are case folded in the Map preparation step, and only
Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "2.5.13.3",
  "name": "caseIgnoreOrderingMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" },
{ "desc": """The caseIgnoreSubstringsMatch rule compares an assertion value of the
Substring Assertion syntax to an attribute value of a syntax (e.g.,
the Directory String, Printable String, Country String, or Telephone
Number syntax) whose corresponding ASN.1 type is DirectoryString or
one of its alternative string types.
The rule evaluates to TRUE if and only if (1) the prepared substrings
of the assertion value match disjoint portions of the prepared
attribute value character string in the order of the substrings in
the assertion value, (2) an <initial> substring, if present, matches
the beginning of the prepared attribute value character string, and
(3) a <final> substring, if present, matches the end of the prepared
attribute value character string.  A prepared substring matches a
portion of the prepared attribute value character string if
corresponding characters have the same code point.
In preparing the attribute value and assertion value substrings for
comparison, characters are case folded in the Map preparation step,
and only Insignificant Space Handling is applied in the Insignificant
Character Handling step.""",
  "oid": "2.5.13.4",
  "name": "caseIgnoreSubstringsMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.58" },
{ "desc": """The directoryStringFirstComponentMatch rule compares an assertion
value of the Directory String syntax to an attribute value of a
syntax whose corresponding ASN.1 type is a SEQUENCE with a mandatory
first component of the DirectoryString ASN.1 type.
Note that the assertion syntax of this matching rule differs from the
attribute syntax of attributes for which this is the equality
matching rule.
The rule evaluates to TRUE if and only if the assertion value matches
the first component of the attribute value using the rules of
caseIgnoreMatch.""",
  "oid": "2.5.13.31",
  "name": "directoryStringFirstComponentMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" },
{ "desc": """The distinguishedNameMatch rule compares an assertion value of the DN
syntax to an attribute value of a syntax (e.g., the DN syntax) whose
corresponding ASN.1 type is DistinguishedName.
The rule evaluates to TRUE if and only if the attribute value and the
assertion value have the same number of relative distinguished names
and corresponding relative distinguished names (by position) are the
same.  A relative distinguished name (RDN) of the assertion value is
the same as an RDN of the attribute value if and only if they have
the same number of attribute value assertions and each attribute
value assertion (AVA) of the first RDN is the same as the AVA of the
second RDN with the same attribute type.  The order of the AVAs is
not significant.  Also note that a particular attribute type may
appear in at most one AVA in an RDN.  Two AVAs with the same
attribute type are the same if their values are equal according to
the equality matching rule of the attribute type.  If one or more of
the AVA comparisons evaluate to Undefined and the remaining AVA
comparisons return TRUE then the distinguishedNameMatch rule
evaluates to Undefined.""",
  "oid": "2.5.13.1",
  "name": "distinguishedNameMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.12" },
{ "desc": """The integerFirstComponentMatch rule compares an assertion value of
the Integer syntax to an attribute value of a syntax (e.g., the DIT
Structure Rule Description syntax) whose corresponding ASN.1 type is
a SEQUENCE with a mandatory first component of the INTEGER ASN.1
type.
Note that the assertion syntax of this matching rule differs from the
attribute syntax of attributes for which this is the equality
matching rule.
The rule evaluates to TRUE if and only if the assertion value and the
first component of the attribute value are the same integer value.""",
  "oid": "2.5.13.29",
  "name": "integerFirstComponentMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.27" },
{ "desc": """The keywordMatch rule compares an assertion value of the Directory
String syntax to an attribute value of a syntax (e.g., the Directory
String syntax) whose corresponding ASN.1 type is DirectoryString.
The rule evaluates to TRUE if and only if the assertion value
character string matches any keyword in the attribute value.  The
identification of keywords in the attribute value and the exactness
of the match are both implementation specific.""",
  "oid": "2.5.13.33",
  "name": "keywordMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" },
{ "desc": """The numericStringSubstringsMatch rule compares an assertion value of
the Substring Assertion syntax to an attribute value of a syntax
(e.g., the Numeric String syntax) whose corresponding ASN.1 type is
NumericString.
The rule evaluates to TRUE if and only if (1) the prepared substrings
of the assertion value match disjoint portions of the prepared
attribute value character string in the order of the substrings in
the assertion value, (2) an <initial> substring, if present, matches
the beginning of the prepared attribute value character string, and
(3) a <final> substring, if present, matches the end of the prepared
attribute value character string.  A prepared substring matches a
portion of the prepared attribute value character string if
corresponding characters have the same code point.
In preparing the attribute value and assertion value for comparison,
characters are not case folded in the Map preparation step, and only
numericString Insignificant Character Handling is applied in the
Insignificant Character Handling step.""",
  "oid": "2.5.13.10",
  "name": "numericStringSubstringsMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.58" },
{ "desc": """The objectIdentifierFirstComponentMatch rule compares an assertion
value of the OID syntax to an attribute value of a syntax (e.g., the
Attribute Type Description, DIT Content Rule Description, LDAP Syntax
Description, Matching Rule Description, Matching Rule Use
Description, Name Form Description, or Object Class Description
syntax) whose corresponding ASN.1 type is a SEQUENCE with a mandatory
first component of the OBJECT IDENTIFIER ASN.1 type.
Note that the assertion syntax of this matching rule differs from the
attribute syntax of attributes for which this is the equality
matching rule.
The rule evaluates to TRUE if and only if the assertion value matches
the first component of the attribute value using the rules of
objectIdentifierMatch.""",
  "oid": "2.5.13.30",
  "name": "objectIdentifierFirstComponentMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.38" },
{ "desc": """The objectIdentifierMatch rule compares an assertion value of the OID
syntax to an attribute value of a syntax (e.g., the OID syntax) whose
corresponding ASN.1 type is OBJECT IDENTIFIER.
The rule evaluates to TRUE if and only if the assertion value and the
attribute value represent the same object identifier; that is, the
same sequence of integers, whether represented explicitly in the
<numericoid> form of <oid> or implicitly in the <descr> form (see
[RFC4512]).
If an LDAP client supplies an assertion value in the <descr> form and
the chosen descriptor is not recognized by the server, then the
objectIdentifierMatch rule evaluates to Undefined.""",
  "oid": "2.5.13.0",
  "name": "objectIdentifierMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.38" },
{ "desc": """The octetStringMatch rule compares an assertion value of the Octet
String syntax to an attribute value of a syntax (e.g., the Octet
String or JPEG syntax) whose corresponding ASN.1 type is the OCTET
STRING ASN.1 type.
The rule evaluates to TRUE if and only if the attribute value and the
assertion value are the same length and corresponding octets (by
position) are the same.""",
  "oid": "2.5.13.17",
  "name": "octetStringMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.40" },
{ "desc": """The octetStringOrderingMatch rule compares an assertion value of the
Octet String syntax to an attribute value of a syntax (e.g., the
Octet String or JPEG syntax) whose corresponding ASN.1 type is the
OCTET STRING ASN.1 type.
The rule evaluates to TRUE if and only if the attribute value appears
earlier in the collation order than the assertion value.  The rule
compares octet strings from the first octet to the last octet, and
from the most significant bit to the least significant bit within the
octet.  The first occurrence of a different bit determines the
ordering of the strings.  A zero bit precedes a one bit.  If the
strings contain different numbers of octets but the longer string is
identical to the shorter string up to the length of the shorter
string, then the shorter string precedes the longer string.""",
  "oid": "2.5.13.18",
  "name": "octetStringOrderingMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.40" },
{ "desc": """The telephoneNumberMatch rule compares an assertion value of the
Telephone Number syntax to an attribute value of a syntax (e.g., the
Telephone Number syntax) whose corresponding ASN.1 type is a
PrintableString representing a telephone number.
The rule evaluates to TRUE if and only if the prepared attribute
value character string and the prepared assertion value character
string have the same number of characters and corresponding
characters have the same code point.
In preparing the attribute value and assertion value for comparison,
characters are case folded in the Map preparation step, and only
telephoneNumber Insignificant Character Handling is applied in the
Insignificant Character Handling step.""",
  "oid": "2.5.13.20",
  "name": "telephoneNumberMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.50" },
{ "desc": """The telephoneNumberSubstringsMatch rule compares an assertion value
of the Substring Assertion syntax to an attribute value of a syntax
(e.g., the Telephone Number syntax) whose corresponding ASN.1 type is
a PrintableString representing a telephone number.
The rule evaluates to TRUE if and only if (1) the prepared substrings
of the assertion value match disjoint portions of the prepared
attribute value character string in the order of the substrings in
the assertion value, (2) an <initial> substring, if present, matches
the beginning of the prepared attribute value character string, and
(3) a <final> substring, if present, matches the end of the prepared
attribute value character string.  A prepared substring matches a
portion of the prepared attribute value character string if
corresponding characters have the same code point.
In preparing the attribute value and assertion value substrings for
comparison, characters are case folded in the Map preparation step,
and only telephoneNumber Insignificant Character Handling is applied
in the Insignificant Character Handling step.""",
  "oid": "2.5.13.21",
  "name": "telephoneNumberSubstringsMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.58" },
{ "desc": """The uniqueMemberMatch rule compares an assertion value of the Name
And Optional UID syntax to an attribute value of a syntax (e.g., the
Name And Optional UID syntax) whose corresponding ASN.1 type is
NameAndOptionalUID.
The rule evaluates to TRUE if and only if the <distinguishedName>
components of the assertion value and attribute value match according
to the distinguishedNameMatch rule and either, (1) the <BitString>
component is absent from both the attribute value and assertion
value, or (2) the <BitString> component is present in both the
attribute value and the assertion value and the <BitString> component
of the assertion value matches the <BitString> component of the
attribute value according to the bitStringMatch rule.
Note that this matching rule has been altered from its description in
X.520 [X.520] in order to make the matching rule commutative.  Server
implementors should consider using the original X.520 semantics
(where the matching was less exact) for approximate matching of
attributes with uniqueMemberMatch as the equality matching rule.""",
  "oid": "2.5.13.23",
  "name": "uniqueMemberMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.34" },
{ "desc": """The wordMatch rule compares an assertion value of the Directory
String syntax to an attribute value of a syntax (e.g., the Directory
String syntax) whose corresponding ASN.1 type is DirectoryString.
The rule evaluates to TRUE if and only if the assertion value word
matches, according to the semantics of caseIgnoreMatch, any word in
the attribute value.  The precise definition of a word is
implementation specific.""",
  "oid": "2.5.13.32",
  "name": "wordMatch",
  "syntax": "1.3.6.1.4.1.1466.115.121.1.15" }
]

print '/* list of names/oids/aliases for each matching rule */'
for item in mylist:
    print 'static const char *%(name)s_names[] = {"%(name)s", "%(oid)s", NULL};' % item
print '/* list of oids of syntaxes that the matching rule is compatible with */'
for item in mylist:
    item['synlist'] = '"%(syntax)s",' % item
    for synoid in item.get('compat_syntax', []):
        item['synlist'] += '"%s",' % synoid
    item['synlist'] += 'NULL'
    print 'static const char *%(name)s_syntaxes[] = {%(synlist)s};' % item

print '/* table of matching rule plugin defs for mr register and plugin register */'
print 'static struct mr_plugin_def mr_plugin_table[] = {'
for item in mylist:
    item['desc'] = item['desc'].replace('\n', '"\n"')
    print '''{{"%(oid)s", NULL, "%(desc)s", "%(syntax)s", 0}, /* matching rule desc */
 {"%(name)s-mr", VENDOR, DS_PACKAGE_VERSION, "%(name)s matching rule plugin"}, /* plugin desc */
   %(name)s_names, /* matching rule name/oid/aliases */
   NULL, NULL, mr_filter_ava, mr_filter_sub, mr_values2keys,
   mr_assertion2keys_ava, mr_assertion2keys_sub, mr_compare, %(name)s_syntaxes},''' % item
print '};'
