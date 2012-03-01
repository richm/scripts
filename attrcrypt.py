
import os
import sys
import ldap
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
port1 = 3890

basedn = 'o=attrcrypt.com'
newinst = 'srv'
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

os.environ["USE_GDB"] = "1"
srv.setupSSL(port1+1)

print "stopping and starting server again to force encryption keys to be saved to dse.ldif for use by export/import"
srv.stop()
srv.start()

def enableAttrEncryption(srv,attrname,alg,dbname="userRoot"):
    # Add an entry for this attribute
    dn = "cn=%s,cn=encrypted attributes,cn=%s,cn=ldbm database,cn=plugins,cn=config" % (attrname, dbname)
    ent = Entry(dn)
    ent.setValue('objectclass', 'nsAttributeEncryption')
    ent.setValue('nsEncryptionAlgorithm', alg)
    srv.add_s(ent)

def disableAttrEncryption(srv,attrname,dbname="userRoot"):
    dn = "dn: cn=%s,cn=encrypted attributes,cn=%s,cn=ldbm database,cn=plugins,cn=config" % (attrname, dbname)
    srv.delete_s(dn)

print "Enable attribute encryption for telephoneNumber"
enableAttrEncryption(srv,'telephoneNumber','3DES')

print "add user"
userdn = "uid=attrcryptuser,ou=people," + basedn
ent = Entry(userdn)
ent.setValue('objectclass', 'inetOrgPerson')
ent.setValue('cn', 'Attrcrypt User');
ent.setValue('sn', 'User')
ent.setValue('givenname', 'Attrcrypt')
ent.setValue('telephoneNumber', '1234567890')
srv.add_s(ent)

print "export encrypted data"
cmd = '%s/lib/dirsrv/slapd-%s/db2ldif -n userRoot -a /tmp/encrypted.ldif' % (os.environ['PREFIX'], newinst)
os.system(cmd)
print "export unencrypted data"
cmd = '%s/lib/dirsrv/slapd-%s/db2ldif -n userRoot -E -a /tmp/unencrypted.ldif' % (os.environ['PREFIX'], newinst)
os.system(cmd)
