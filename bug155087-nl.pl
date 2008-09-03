
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
delete $ENV{USE_DBX};

#$ENV{USE_DBX} = 1;
$h1 = createAndSetupReplica({
	cfgdshost => $host1,
	cfgdsport => $cfgport,
	cfgdsuser => 'admin',
	cfgdspwd => 'admin',
	newrootpw => 'password',
	newhost => $host2,
	newport => $cfgport+20,
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
delete $ENV{USE_DBX};

my $initfile = "$m1->{sroot}/slapd-$m1->{inst}/ldif/Example.ldif";
$m1->importLDIF($initfile, 0, "userRoot", 1);

print "Show monitor entry on consumer\n";
my $mesg = $h1->search(base   => "cn=monitor,cn=userRoot,cn=ldbm database,cn=plugins,cn=config",
					   scope  => 'base',
					   filter => '(objectclass=*)');
check_mesg($mesg, "Could not search monitor entry");
my $entry = $mesg->shift_entry;
$entry->dump;

print "create agreements and init consumers\n";
my $agmtm1toh1 = $m1->setupAgreement($h1, "dc=example,dc=com", "cn=replrepl,cn=config", "replrepl");
$m1->startReplication_async($agmtm1toh1);
$m1->waitForReplInit($agmtm1toh1);
print "Show monitor entry on consumer again\n";
$mesg = $h1->search(base   => "cn=monitor,cn=userRoot,cn=ldbm database,cn=plugins,cn=config",
					   scope  => 'base',
					   filter => '(objectclass=*)');
check_mesg($mesg, "Could not search monitor entry");
$entry = $mesg->shift_entry;
$entry->dump;
