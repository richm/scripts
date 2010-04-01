
import os
import sys
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
cfgport = 1100
port1 = cfgport + 10

basedn = 'dc=example,dc=com'
newinst = 'srv'

os.environ['USE_GDB'] = '1'
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

# add schema
srv.addAttr("( NAME 'testUserAccountControl' DESC 'Attribute Bitwise filteri-Multi-Valued' SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 )")
srv.addAttr("( NAME 'testUserStatus' DESC 'State of User account active/disabled' SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )")
srv.addObjClass("( NAME 'testperson' SUP top AUXILIARY MUST ( testUserAccountControl $ testUserStatus ) X-ORIGIN 'BitWise' )")

vals = (0, (511,), (512,), (513,), (514,), (1023,))
for ii in xrange(1, len(vals)):
    dn = "cn=btestuser%d, %s" % (ii, basedn)
    ent = Entry(dn)
    ent.setValue('objectclass', 'top', 'person', 'testperson')
    ent.setValue('sn', 'User')
    ent.setValue('testUserAccountControl', [str(xx) for xx in vals[ii]])
    ent.setValue('testUserStatus', 'bogus')
    srv.add_s(ent)

print 'search for "(testUserAccountControl:1.2.840.113556.1.4.803:=514)"'
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, "(testUserAccountControl:1.2.840.113556.1.4.803:=514)")
for ent in ents:
    print "found entry %s val %s" % (ent.dn, ent.testUserAccountControl)
print 'search for "(testUserAccountControl:1.2.840.113556.1.4.804:=2)"'
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, "(testUserAccountControl:1.2.840.113556.1.4.804:=2)")
for ent in ents:
    print "found entry %s val %s" % (ent.dn, ent.testUserAccountControl)
