use Net::LDAP;
use Net::LDAP::Util qw(canonical_dn ldap_explode_dn ldap_error_name);
use Net::LDAP::Constant qw(:all);

use Net::LDAP::Extension::SetPassword;

my $host = 'localhost';
my $port = 1100;

my $ldap = Net::LDAP->new($host, port => $port, version => 3 );
my $mesg = $ldap->start_tls(
                         verify => 'require',
                         cafile => $ENV{HOME} . "/save/cacert.asc",
                         );
die "error: ", $mesg->code(), ": ", $mesg->error()  if ($mesg->code());

my $binddn = "cn=Sam Carter, ou=people,dc=example,dc=com";
my $bindpw = "sprain";
my $newpw = "niarps";
#my $bindpw = "niarps";
#my $newpw = "sprain";

$mesg = $ldap->bind($binddn, password => $bindpw);
die "error: ", $mesg->code(), ": ", $mesg->error()  if ($mesg->code());

$mesg = $ldap->set_password( oldpasswd => $bindpw, newpasswd => $newpw );
die "error: ", $mesg->code(), ": ", $mesg->error()  if ($mesg->code());
 
print "changed your password to", $newpw , "\n";
