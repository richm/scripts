import ldap
import ldap.ldapobject
import ldap.schema.subentry
import ldap.schema.models

host = "localhost"
port = 1110
binddn = "cn=directory manager"
bindpw = "password"

conn = ldap.ldapobject.SimpleLDAPObject("ldap://" + host + ":" + str(port))
conn.simple_bind_s(binddn, bindpw)

ents = conn.search_s("cn=schema", ldap.SCOPE_BASE, "objectclass=*", ['attributeTypes'])

schema = ldap.schema.subentry.SubSchema(ents[0][1])

cis_syntaxes = {
    "1.3.6.1.4.1.1466.115.121.1.15": "1.3.6.1.4.1.1466.115.121.1.15",
    "1.3.6.1.4.1.1466.115.121.1.7": "1.3.6.1.4.1.1466.115.121.1.7",
    "1.3.6.1.4.1.1466.115.121.1.24": "1.3.6.1.4.1.1466.115.121.1.24",
    "1.3.6.1.4.1.1466.115.121.1.11": "1.3.6.1.4.1.1466.115.121.1.11",
    "1.3.6.1.4.1.1466.115.121.1.41": "1.3.6.1.4.1.1466.115.121.1.41",
    "1.3.6.1.4.1.1466.115.121.1.38": "1.3.6.1.4.1.1466.115.121.1.38",
    "1.3.6.1.4.1.1466.115.121.1.44": "1.3.6.1.4.1.1466.115.121.1.44"
}

ces_syntaxes = {
    "1.3.6.1.4.1.4401.1.1.1": "1.3.6.1.4.1.4401.1.1.1",
    "1.3.6.1.4.1.1466.115.121.1.26": "1.3.6.1.4.1.1466.115.121.1.26"
}

clz = ldap.schema.models.AttributeType
cis_but_exact = []
ces_but_ignore = []
for oid in schema.listall(clz):
    at = schema.get_obj(clz, oid)
    if ces_syntaxes.has_key(at.syntax):
        found = False
        if at.equality and at.equality.lower().find("ignore") > -1:
            found = True
            ces_but_ignore.append(at)
        if not found and at.substr and at.substr.lower().find("ignore") > -1:
            found = True
            ces_but_ignore.append(at)
        if not found and at.ordering and at.ordering.lower().find("ignore") > -1:
            found = True
            ces_but_ignore.append(at)
    if cis_syntaxes.has_key(at.syntax):
        found = False
        if at.equality and at.equality.lower().find("exact") > -1:
            found = True
            cis_but_exact.append(at)
        if not found and at.substr and at.substr.lower().find("exact") > -1:
            found = True
            cis_but_exact.append(at)
        if not found and at.ordering and at.ordering.lower().find("exact") > -1:
            found = True
            cis_but_exact.append(at)

print "The following are the list of attributes which have syntax CES but have a case ignore matching rule:"
for at in ces_but_ignore: print at
print ""
print "The following are the list of attributes which have syntax CIS but have a case exact matching rule:"
for at in cis_but_exact: print at
