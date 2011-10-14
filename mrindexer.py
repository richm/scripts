import os
import sys
import time
import tempfile
import ldap
import ldif
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
port1 = 1200
basedn = 'dc=example,dc=com'

ntf2 = tempfile.NamedTemporaryFile(delete=False,prefix='70',suffix='.ldif')
ntf2.write("""dn: cn=schema
attributetypes: ( 2.16.840.1.113730.3.1.99999999 NAME 'myattr' DESC 'my new attribute' EQUALITY caseIgnoreMatch ORDERING caseIgnoreOrderingMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 SINGLE-VALUE )
objectclasses: ( 2.16.840.1.113730.3.2.99999999 NAME 'myobjclass' DESC 'my objectclass' SUP top AUXILIARY MAY myattr )

""")
ntf2.close()
os.chmod(ntf2.name, 0644)

print "add index for myattr attribute"
#nsmatchingrule: 2.16.840.1.113730.3.3.2.15.1,2.16.840.1.113730.3.3.2.15.3
ntf = tempfile.NamedTemporaryFile(delete=False)
ntf.write("""dn: cn=myattr,cn=default indexes,cn=config,cn=ldbm database,cn=plugins,cn=config
objectClass: top
objectClass: nsIndex
cn: myattr
nsSystemIndex: false
nsIndexType: eq
nsmatchingrule: 2.16.840.1.113730.3.3.2.15.1

""")
ntf.close()
os.chmod(ntf.name, 0644)

initfile = os.environ.get('PREFIX', '/usr') + "/share/dirsrv/data/Example.ldif"
inf = open(initfile, 'r')
ntf3 = tempfile.NamedTemporaryFile(delete=False)
for line in inf:
    ntf3.write(line)
inf.close()
ntf3.write("""
dn: cn=myobj,%s
objectclass: person
objectclass: myobjclass
sn: me
myattr: somelongvalue

""" % basedn)
ntf3.close()
os.chmod(ntf3.name, 0644)

srv = DSAdmin.createInstance({
    'newrootpw': 'password',
    'newhost': host1,
    'newport': port1,
    'newinst': 'srv',
    'newsuffix': basedn,
    'verbose': False,
    'no_admin': True,
    'ConfigFile':[ntf.name],
    'SchemaFile':[ntf2.name],
    'InstallLdifFile':ntf3.name
})

os.unlink(ntf.name)
os.unlink(ntf2.name)
srv.importLDIF(ntf3.name,basedn,'userRoot',True)
#os.unlink(ntf3.name)
