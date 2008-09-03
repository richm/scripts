
use NDSAdminNL qw(my_ldap_url_parse createInstance check_mesg createAndSetupReplica);

my $sroot = $ENV{SERVER_ROOT};

my $host1 = "localhost.localdomain";

my $host2 = $host1;
my $cfgport = 7100;

my ($m1, $m2, $h1, $h2, $c1, $c2);

#$ENV{USE_DBX} = 1;
$m1 = createAndSetupReplica({
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
},
{
	suffix => "dc=example,dc=com",
	bename => "userRoot",
	binddn => "cn=replrepl,cn=config",
	bindcn => "replrepl",
	bindpw => "replrepl",
      log => 1
});
$m2 = createAndSetupReplica({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host1,
	newport => $cfgport+20,
	newinst => 'm2',
	newsuffix => 'dc=example,dc=com',
	verbose => 1
},
{
	suffix => "dc=example,dc=com",
	bename => "userRoot",
	binddn => "cn=replrepl,cn=config",
	bindcn => "replrepl",
	bindpw => "replrepl",
      log => 1
});
delete $ENV{USE_DBX};

#$ENV{USE_DBX} = 1;
$h1 = createAndSetupReplica({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host2,
	newport => $cfgport+30,
	newinst => 'h1',
	newsuffix => 'dc=example,dc=com',
	verbose => 1
},
{
	suffix => "dc=example,dc=com",
	bename => "userRoot",
	binddn => "cn=replrepl,cn=config",
	bindcn => "replrepl",
	bindpw => "replrepl",
	type => 2,
      log => 1
});
#	type => 2,
delete $ENV{USE_DBX};

my $initfile = "$m1->{sroot}/slapd-$m1->{inst}/ldif/Example.ldif";
$m1->importLDIF($initfile, 0, "userRoot", 1);

print "create agreements and init consumers\n";
#my $agmtm1toh1 = $m1->setupAgreement($h1, "dc=example,dc=com", "cn=replrepl,cn=config", "replrepl");
my $agmtm1tom2 = $m1->setupAgreement($m2, "dc=example,dc=com", "cn=replrepl,cn=config", "replrepl");
$m1->startReplication($agmtm1tom2);
my $agmtm1toh1 = $m1->setupAgreement($h1, "dc=example,dc=com", "cn=replrepl,cn=config", "replrepl",
	0, 120, '(objectclass=*) $ EXCLUDE userPassword gecos loginShell description');
my $agmtm2toh1 = $m2->setupAgreement($h1, "dc=example,dc=com", "cn=replrepl,cn=config", "replrepl",
	0, 120, '(objectclass=*) $ EXCLUDE userPassword gecos loginShell description');
#$m1->startReplication_async($agmtm1toh1);
#$m1->waitForReplInit($agmtm1toh1);
$m1->startReplication($agmtm1toh1);

print "Try a change\n";
my $mesg = $m2->modify("dc=example,dc=com", replace => {description => [ 'my description' ]});
check_mesg($mesg, "Could not modify dc=example,dc=com");
print "Wait\n";
$mesg = $h1->search(base   => "dc=example,dc=com",
	                scope  => 'base',
	                filter => '(objectclass=*)');
my $ent = $mesg->shift_entry;
$ent->dump;
