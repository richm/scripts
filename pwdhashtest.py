
import os
import sys
import ldap
from dsadmin import DSAdmin, Entry
import hashlib
import base64

host1 = "localhost.localdomain"
cfgport = 1100
port1 = cfgport + 30

basedn = 'dc=example,dc=com'
newinst = 'srv'

# os.environ['USE_VALGRIND'] = '1'
# srv = DSAdmin.createInstance({
# 	'newrootpw': 'password',
# 	'newhost': host1,
# 	'newport': port1,
# 	'newinst': newinst,
# 	'newsuffix': basedn,
#     'no_admin': True
# })

srv = DSAdmin(host1, port1, "cn=directory manager", 'password')

ent = Entry(basedn)
ent.setValues('objectclass', 'domain')
try: srv.add_s(ent)
except ldap.ALREADY_EXISTS: pass

ent = Entry("ou=people," + basedn)
ent.setValues('objectclass', 'organizationalUnit')
try: srv.add_s(ent)
except ldap.ALREADY_EXISTS: pass

def genpwd(pwd, salt):
    sha = hashlib.sha1(pwd)
    sha.update(salt)
    return '{SSHA}' + base64.b64encode(sha.digest() + salt)

pwd = 'averylongpassword'
for ii in xrange(0, 100):
    dn = 'cn=user%d,ou=people,%s' % (ii, basedn)
    try: srv.delete_s(dn)
    except ldap.NO_SUCH_OBJECT: pass
    ent = Entry(dn)
    ent.setValues('objectclass', 'person')
    ent.setValues('sn', 'User' + str(ii))
    if ii > 0:
        salt = 'a' * ii
        pwdstr = genpwd(pwd, salt)
    else:
        pwdstr = pwd
    ent.setValues('userPassword', pwdstr)
    srv.add_s(ent)

for ii in xrange(0, 100):
    dn = 'cn=user%d,ou=people,%s' % (ii, basedn)
    srv.simple_bind_s(dn, pwd)
    ents = srv.search_s("", ldap.SCOPE_BASE, '(objectclass=*)', [ 'vendorVersion' ])
    print dn, 'successfully read', ents[0].vendorVersion
