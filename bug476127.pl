use Mozilla::LDAP::Conn;
use Mozilla::LDAP::API qw(:api :ssl :apiv3 :constant); # Direct access to C API
use Mozilla::LDAP::Utils qw(normalizeDN printEntry);

my $host = 'localhost';
my $port = 1200;
my $binddn = "cn=directory manager";
my $bindpw = 'password';

my $conn = new Mozilla::LDAP::Conn($host, $port);
$conn->simpleBind($binddn, $bindpw);
my $dn = "uid=tedst3user3,ou=people,dc=testdomain,dc=com";
my $attr = 'userPassword';
my %mod = (
  $attr => { 'r' => [ 'password' ] }
);
  ldap_modify_s($self->{ld}, $dn, \%mod);
  my $rc = $self->getErrorCode();
  if ($rc) {
	print "Couldn't add schema $attr $val: $rc: " . $self->getErrorString(), "\n";
  }
