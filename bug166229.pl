
use NDSAdminNL qw(my_ldap_url_parse createInstance check_mesg createAndSetupReplica);

my $sroot = $ENV{SERVER_ROOT};

my $host1 = "localhost.localdomain";

my $host2 = $host1;
my $cfgport = 10000;

my ($m1, $m2, $h1, $h2, $c1, $c2);

$ENV{USE_DBX} = 1;
$m1 = createInstance({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host1,
	newport => $cfgport+10,
	newinst => 'm1',
	newsuffix => 'dc=example,dc=com',
	verbose => 1
});
delete $ENV{USE_DBX};

# change the default password storage to clear
#my $mesg = $m1->modify("cn=config", replace => {passwordStorageScheme => 'CLEAR'});
#check_mesg($mesg, "Error changing password storage scheme to clear");

my $initfile = "$m1->{sroot}/slapd-$m1->{inst}/ldif/Example.ldif";
$m1->importLDIF($initfile, 0, "userRoot", 1);

#$m1->setLogLevel(1);

my $dn = "uid=tmorris,ou=people,dc=example,dc=com";
my $pw = "irrefutable";

#my $mesg = $m1->modify($dn, delete => {"userPassword" => []});
#check_mesg($mesg, "Error deleting userPassword");

system 'ldapsearch', '-v', '-h', $host1, '-p', $m1->{port}, '-Y', 'digest-md5', '-U', "dn:$dn", '-w', "$pw", '-s', 'sub', '-b', "dc=example,dc=com", '(objectclass=*)';

$m1->setLogLevel(0);
