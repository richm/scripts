import os
import sys
import time
import ldap
import pprint
from dsadmin import DSAdmin, Entry

host1 = "localhost"
cfgport = 1100
port1 = cfgport + 30

basedn = 'dc=example,dc=com'
newinst = 'ipa'
#os.environ['USE_GDB'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

accountdn = "cn=accounts," + basedn

# add schema
srv.addAttr("( NAME 'posixName' DESC 'posixName' SYNTAX 1.3.6.1.4.1.1466.115.121.1.26 SINGLE-VALUE )")
srv.addAttr("( NAME 'ipaUserDN' DESC 'ipaUserDN' SYNTAX 1.3.6.1.4.1.1466.115.121.1.12 SINGLE-VALUE )")
srv.addObjClass("( NAME 'ipaPosixName' SUP top AUXILIARY MUST posixName MAY ipaUserDN )")

# # enable attr uniqueness for posixName
# dn = "cn=attribute uniqueness,cn=plugins,cn=config"
# mod = [(ldap.MOD_REPLACE, 'pluginarg0', ['posixName']),
#        (ldap.MOD_REPLACE, 'nsslapd-pluginarg1', [accountdn])]
# srv.modify_s(dn, mod)

# # stop start for plugin changes to take effect
# srv.stop()
# srv.start()

# add containers
ent = Entry(accountdn)
ent.setValues('objectclass', 'nsContainer')
srv.add_s(ent)

userdn = "cn=users," + accountdn
ent = Entry(userdn)
ent.setValues('objectclass', 'nsContainer')
srv.add_s(ent)

groupdn = "cn=groups," + accountdn
ent = Entry(groupdn)
ent.setValues('objectclass', 'nsContainer')
srv.add_s(ent)

# add CoS
dn = "cn=generatePosixName," + groupdn
ent = Entry(dn)
ent.setValues('description', 'generate posixName for group entries')
ent.setValues('objectClass', ['top', 'ldapsubentry', 'cossuperdefinition', 'cosIndirectDefinition'])
ent.setValues('cosAttribute', 'posixName override')
ent.setValues('cosIndirectSpecifier', 'ipaUserDN')
srv.add_s(ent)

# add user entry
dn = "cn=foo," + userdn
ent = Entry(dn)
ent.setValues('objectclass', ['person', 'ipaPosixName'])
ent.setValues('sn', 'Foo')
ent.setValues('posixName', 'foo')
srv.add_s(ent)

# add group entry
dn = "cn=foo," + groupdn
ent = Entry(dn)
ent.setValues('objectclass', ['nsContainer', 'ipaPosixName'])
ent.setValues('posixName', 'foo')
ent.setValues('ipaUserDN', "cn=foo," + userdn)
ent.setValues('posixName', 'dummyforschemachecking')
srv.add_s(ent)

# search for group entry
ents = srv.search_s(dn, ldap.SCOPE_BASE, "(objectclass=*)")
pprint.pprint(ents)
