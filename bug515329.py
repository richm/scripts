from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry, LEAF_TYPE


import os
import sys
import time
import ldap

host1 = "localhost.localdomain"
host2 = host1
host3 = host2
port1 = 1200
port2 = port1+10
port3 = port2+10
basedn = "dc=example,dc=com"

m1replargs = {
	'suffix': basedn,
	'bename': "userRoot",
	'binddn': "cn=replrepl,cn=config",
	'bindcn': "replrepl",
	'bindpw': "replrepl",
        'pd': 5,
    'log'   : False
}
m2replargs = m1replargs

m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': basedn,
	'verbose': True,
    'no_admin': True
})

#os.environ['USE_GDB'] = "1"
m2 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host2,
	'newport': port2,
	'newinst': 'm2',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
#del os.environ['USE_GDB']

c1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host3,
	'newport': port3,
	'newinst': 'c1',
	'newsuffix': basedn,
    'no_admin': True
})

m1.replicaSetupAll(m1replargs)
m2.replicaSetupAll(m2replargs)
c1replargs = m1replargs
c1replargs['type'] = LEAF_TYPE
c1.replicaSetupAll(c1replargs)

print "create agreements and init consumers"
agmtm1tom2 = m1.setupAgreement(m2, m1replargs)
time.sleep(2)
m1.startReplication(agmtm1tom2)
print "repl status after starting"
print m1.getReplStatus(agmtm1tom2)

agmtm2tom1 = m2.setupAgreement(m1, m2replargs)
agmtm1toc1 = m1.setupAgreement(c1, m1replargs)
time.sleep(2)
m1.startReplication(agmtm1toc1)
print "repl status after starting"
print m1.getReplStatus(agmtm1toc1)
agmtm2toc1 = m2.setupAgreement(c1, m2replargs)

print "add entry on m1 . . ."
dn = 'uid=testuser,dc=example,dc=com'
ent = Entry(dn)
ent.setValues('objectclass', 'inetOrgPerson')
ent.setValues('cn', "1")
ent.setValues('sn', 'testuser')
m1.add_s(ent)
time.sleep(2)
print "search for entry on m2 . . ."
ents = m2.search_s(dn, ldap.SCOPE_BASE)
if not ents:
   time.sleep(2)
   ents = m2.search_s(dn, ldap.SCOPE_BASE)
if not ents:
    print "entry not found on m2"
    sys.exit(1)
else:
    print "entry found on m2"
print "search for entry on c1 . . ."
ents = c1.search_s(dn, ldap.SCOPE_BASE)
if not ents:
   time.sleep(2)
   ents = c1.search_s(dn, ldap.SCOPE_BASE)
if not ents:
    print "entry not found on c1"
    sys.exit(1)
else:
    print "entry found on c1"

print "modify entry on m1 . . ."
mod = [(ldap.MOD_ADD, 'cn', '2'),
       (ldap.MOD_REPLACE, 'cn', '3'),
       (ldap.MOD_ADD, 'cn', '4'),
       (ldap.MOD_DELETE, 'cn', '3'),
       (ldap.MOD_ADD, 'cn',  '5'),
       (ldap.MOD_DELETE, 'cn', '4'),
       (ldap.MOD_REPLACE, 'description', '1'),
       (ldap.MOD_REPLACE, 'description', None),
       (ldap.MOD_ADD, 'sn', '2'),
       (ldap.MOD_REPLACE, 'sn', '3'),
       (ldap.MOD_ADD, 'sn', '4'),
       (ldap.MOD_DELETE, 'sn', '3'),
       (ldap.MOD_ADD, 'sn',  '5'),
       (ldap.MOD_REPLACE, 'sn', ['6', '7', '8'])]

expectval = '5'
expectvalsn = ['6', '7', '8']
m1.modify_s(dn, mod)
time.sleep(5)
print "search for entry on m2 . . ."
attrlist = ['cn', 'sn', 'nscpentrywsi']
ents = m2.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m2 entry is correct"
else:
   print "value of m2 entry is not correct:", ent.cn
   print "value of m2 entry is not correct:", ent.sn
   print "entrywsi:", str(ent)

print "search for entry on m1 . . ."
ents = m1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m1 entry is correct"
else:
   print "value of m1 entry is not correct:", ent.cn
   print "value of m1 entry is not correct:", ent.sn
   print "entrywsi:", str(ent)

print "search for entry on c1 . . ."
ents = c1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of c1 entry is correct"
else:
   print "value of c1 entry is not correct:", ent.cn
   print "value of c1 entry is not correct:", ent.sn
   print "entrywsi:", str(ent)

mod = [(ldap.MOD_ADD, 'cn', '6'),
       (ldap.MOD_REPLACE, 'cn', '7'),
       (ldap.MOD_ADD, 'cn', '8'),
       (ldap.MOD_DELETE, 'cn', '7'),
       (ldap.MOD_ADD, 'cn',  '9'),
       (ldap.MOD_DELETE, 'cn', '8'),
       (ldap.MOD_REPLACE, 'description', '2'),
       (ldap.MOD_REPLACE, 'description', None),
       (ldap.MOD_DELETE, 'sn', ['6', '7', '8']),
       (ldap.MOD_REPLACE, 'sn', ['9', '10', '11'])]

expectval = '9'
expectvalsn = ['9', '10', '11']
m1.modify_s(dn, mod)
time.sleep(5)
print "search for entry on m2 . . ."
ents = m2.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m2 entry is correct"
else:
   print "value of m2 entry is not correct:", ent.cn
   print "value of m2 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

print "search for entry on m1 . . ."
ents = m1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m1 entry is correct"
else:
   print "value of m1 entry is not correct:", ent.cn
   print "value of m1 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

print "search for entry on c1 . . ."
ents = c1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of c1 entry is correct"
else:
   print "value of c1 entry is not correct:", ent.cn
   print "value of c1 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

mod = [(ldap.MOD_ADD, 'cn', '10'),
       (ldap.MOD_REPLACE, 'cn', '11'),
       (ldap.MOD_ADD, 'cn', '12'),
       (ldap.MOD_DELETE, 'cn', '11'),
       (ldap.MOD_ADD, 'cn',  '13'),
       (ldap.MOD_DELETE, 'cn', '12'),
       (ldap.MOD_REPLACE, 'description', '3'),
       (ldap.MOD_REPLACE, 'description', None),
       (ldap.MOD_DELETE, 'sn', ['9', '10', '11']),
       (ldap.MOD_REPLACE, 'sn', ['12', '13', '14'])]

expectval = '13'
expectvalsn = ['12', '13', '14']
#c1.setLogLevel(8192)
m1.modify_s(dn, mod)
time.sleep(5)
print "search for entry on m2 . . ."
ents = m2.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m2 entry is correct"
else:
   print "value of m2 entry is not correct:", ent.cn
   print "value of m2 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

print "search for entry on m1 . . ."
ents = m1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m1 entry is correct"
else:
   print "value of m1 entry is not correct:", ent.cn
   print "value of m1 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

print "search for entry on c1 . . ."
ents = c1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of c1 entry is correct"
else:
   print "value of c1 entry is not correct:", ent.cn
   print "value of c1 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

mod = [(ldap.MOD_ADD, 'cn', '14'),
       (ldap.MOD_REPLACE, 'cn', '15'),
       (ldap.MOD_ADD, 'cn', '16'),
       (ldap.MOD_DELETE, 'cn', '15'),
       (ldap.MOD_ADD, 'cn',  '17'),
       (ldap.MOD_DELETE, 'cn', '16'),
       (ldap.MOD_REPLACE, 'description', '4'),
       (ldap.MOD_REPLACE, 'description', None),
       (ldap.MOD_DELETE, 'sn', ['12', '13', '14']),
       (ldap.MOD_REPLACE, 'sn', ['15', '16', '17'])]

expectval = '17'
expectvalsn = ['15', '16', '17']
c1.setLogLevel(8192)
m1.modify_s(dn, mod)
time.sleep(5)
print "search for entry on m2 . . ."
ents = m2.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m2 entry is correct"
else:
   print "value of m2 entry is not correct:", ent.cn
   print "value of m2 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

print "search for entry on m1 . . ."
ents = m1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of m1 entry is correct"
else:
   print "value of m1 entry is not correct:", ent.cn
   print "value of m1 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)

print "search for entry on c1 . . ."
ents = c1.search_s(dn, ldap.SCOPE_BASE, 'objectclass=*', attrlist)
ent = ents[0]
if ent.cn == expectval and ent.hasValue('sn', expectvalsn):
   print "value of c1 entry is correct"
else:
   print "value of c1 entry is not correct:", ent.cn
   print "value of c1 entry is not correct:", ent.sn
print "See if the old state information has been removed"
print "entrywsi:", str(ent)
