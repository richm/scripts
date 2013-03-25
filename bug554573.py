from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry


import os
import sys
import time
import ldap
#from ldap.ldapobject import SimpleLDAPObject
#import ldap.sasl
from subprocess import Popen, PIPE

host1 = "NEEDFQDNHERE"
port1 = 1200
secport1 = port1+1
basedn = "dc=example,dc=com"

#os.environ['USE_DBX'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'srv',
	'newsuffix': basedn,
	'verbose': False,
    'no_admin': True
})
#del os.environ['USE_DBX']

srv.setupSSL(secport1, os.environ['SECDIR'],
            {'nsslapd-security': 'on'})

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
srv.importLDIF(initfile, '', "userRoot", True)

print "create entry to map cert to"
certdn = "cn=%s,cn=config" % host1
ent = Entry(certdn)
ent.setValues("objectclass", "extensibleObject")
srv.add_s(ent)

print "find existing acis"
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, "(aci=*)")

print "remove default acis"
mod = [(ldap.MOD_DELETE, "aci", [])]
for ent in ents:
    srv.modify_s(ent.dn, mod)

print "add an aci for this user"
mod = [(ldap.MOD_ADD, "aci",
        '(targetattr=*)(version 3.0;acl "Test user read-search access"; '
        'allow (read, search, compare)(userdn = "ldap:///%s");)' % certdn)]
srv.modify_s(basedn, mod)

print "allow unauthenticated binds"
mod = [(ldap.MOD_REPLACE, "nsslapd-allow-unauthenticated-binds", ['on'])]
srv.modify_s("cn=config", mod)

cacert = os.environ['SECDIR'] + "/cacert.asc"
cert = os.environ['SECDIR'] + "/Server-Cert-cert.pem"
key = os.environ['SECDIR'] + "/Server-Cert-key.pem"

# conn = SimpleLDAPObject("ldap://%s:%d/" % (host1, port1))
# conn.set_option(ldap.OPT_X_TLS_CACERTFILE, cacert)
# conn.set_option(ldap.OPT_X_TLS_CERTFILE, cert)
# conn.set_option(ldap.OPT_X_TLS_KEYFILE, key)
# conn.start_tls_s()
# conn.sasl_interactive_bind_s("", ldap.sasl.external())

certdb = os.environ['SECDIR'] + "/cert8.db"
pintxt = os.environ['SECDIR'] + "/pin.txt"
certname = "Server-Cert"
filter = "(uid=scarter)"

print "bind as anonymous and search - should return nothing"
binddn = ""
bindpw = ""
cmdargs = ["/usr/lib64/mozldap/ldapsearch", "-h", host1, "-p", str(port1),
           "-ZZZ", "-P", certdb, "-N", certname, "-I", pintxt, "-D", binddn,
           "-w", bindpw, "-b", basedn, filter]
cmd = Popen(cmdargs, stdout=PIPE)
output = cmd.communicate()[0]
numdns = output.count("\ndn:")
assert numdns == 0

# /usr/lib64/mozldap/ldapsearch -h fqdn -p 1200 -ZZZ -P ~/save/cert8.db -N Server-Cert -I ~/save/pin.txt -s base -b "" "objectclass=*"

print "bind and search - specify the cert DN as the simple bind dn"
binddn = certdn
cmdargs = ["/usr/lib64/mozldap/ldapsearch", "-h", host1, "-p", str(port1),
           "-ZZZ", "-P", certdb, "-N", certname, "-I", pintxt, "-D", binddn,
           "-w", bindpw, "-b", basedn, filter]
cmd = Popen(cmdargs, stdout=PIPE)
output = cmd.communicate()[0]
numdns = output.count("\ndn:")
assert numdns == 0

print "turn on the force sasl external switch"
mod = [(ldap.MOD_REPLACE, "nsslapd-force-sasl-external", ['on'])]
srv.modify_s("cn=config", mod)

print "bind as anonymous and search - should return 1 entry"
binddn = ""
bindpw = ""
cmdargs = ["/usr/lib64/mozldap/ldapsearch", "-h", host1, "-p", str(port1),
           "-ZZZ", "-P", certdb, "-N", certname, "-I", pintxt, "-D", binddn,
           "-w", bindpw, "-b", basedn, filter]
cmd = Popen(cmdargs, stdout=PIPE)
output = cmd.communicate()[0]
numdns = output.count("\ndn:")
assert numdns == 1

print "bind and search - specify the cert DN as the simple bind dn"
binddn = certdn
cmdargs = ["/usr/lib64/mozldap/ldapsearch", "-h", host1, "-p", str(port1),
           "-ZZZ", "-P", certdb, "-N", certname, "-I", pintxt, "-D", binddn,
           "-w", bindpw, "-b", basedn, filter]
cmd = Popen(cmdargs, stdout=PIPE)
output = cmd.communicate()[0]
numdns = output.count("\ndn:")
assert numdns == 1
