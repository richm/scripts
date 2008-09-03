
use NDSAdminNL qw(my_ldap_url_parse createInstance check_mesg createAndSetupReplica);
use Net::LDAP;

my $sroot = $ENV{SERVER_ROOT};

my $host1 = "localhost.localdomain";

my $host2 = $host1;
my $cfgport = 7100;

my ($m1, $m2, $h1, $h2, $c1, $c2);

#$ENV{USE_DBX} = 1;
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

my $dn = "\xa4\x89\x84\x7e\x81\x84\x94\x89\x95\x6b\x96\xa4\x7e\x81\x84\x94\x89\x95\x89\xa2\xa3\x99\x81\xa3\x96\x99\xa2\x6b\x96\xa4\x7e\xa3\x96\x97\x96\x93\x96\x87\xa8\x94\x81\x95\x81\x87\x85\x94\x85\x95\xa3\x6b\x96\x7e\x95\x85\xa3\xa2\x83\x81\x97\x85\x99\x96\x96\xa3";
my $pw = "\x83\x81\xa3\x84\x96\x87\xf0\xf1";

my $conn = new Net::LDAP($host1, port => $cfgport+10);

print "Attempting to bind . . .\n";
my $mesg = $conn->bind($dn, password => $pw);
check_mesg($mesg, "Error binding to directory",
           {LDAP_NO_SUCH_OBJECT => LDAP_NO_SUCH_OBJECT}); # ignore error for test

print "Attempting to search . . .\n";
#         0x0030:  0964 c86b 3072 0201 0263 6d04 2784 837e  .d.k0r...cm.'..~
# 30=ldapmsg 0x72=len 020102=msgid 63=srch 0x6d=len 04=type 0x27=len
# 84 837e 9389 95a4 a76b 8483 7e83 9699 976b 8483 7e99 816b 8483 7e99 89a3 8581 8984 6b84 837e a4a2
#         0x0040:  9389 95a4 a76b 8483 7e83 9699 976b 8483  .....k..~....k..
#         0x0050:  7e99 816b 8483 7e99 89a3 8581 8984 6b84  ~..k..~.......k.
#         0x0060:  837e a4a2 0a01 020a 0102 0201 0002 0100  .~..............
# 0a=enum 01=len 02=sub 0a=enum 01=len 02=derefFindingBaseObj 02=int 01=len 00=sizelimit 02=int 01=len 00=timelimit
#         0x0070:  0101 00a0 2ca3 1b04 0b96 8291 8583 a383  ....,...........
# 01=bool 01=len 00=attrsonly a0=andfilter 2c=len a3=eqfilter 1b=len 04=os 0b=len value=96 8291 8583 a383 9381 a2a2
#         0x0080:  9381 a2a2 040c 9796 a289 a7c1 8383 96a4  ................
# 04=os 0c=len value=9796 a289 a7c1 8383 96a4 95a3
#         0x0090:  95a3 a30d 0403 a489 8404 06a2 a8a2 9193  ................
# a3=eqfilter 0d=len 04=os 03=len value=a489 84 04=os 06=len value=a2 a8a2 9193 f1
#         0x00a0:  f130 0504 03f1 4bf1                      .0....K.
# attrlist - 30=seq 05=len 04=type 03=len value=f1 4b f1

my $basedn = "\x84\x83\x7e\x93\x89\x95\xa4\xa7\x6b\x84\x83\x7e\x83\x96\x99\x97\x6b\x84\x83\x7e\x99\x81\x6b\x84\x83\x7e\x99\x89\xa3\x85\x81\x89\x84\x6b\x84\x83\x7e\xa4\xa2";
my $scope = "sub";
#my $filter = "\x96\x82\x91\x85\x83\xa3\x83\x93\x81\xa2\xa2=\x97\x96\xa2\x89\xa7\xc1\x83\x83\x96\xa4\x95\xa3";
my $filter = "(&(\x96\x82\x91\x85\x83\xa3\x83\x93\x81\xa2\xa2=\x97\x96\xa2\x89\xa7\xc1\x83\x83\x96\xa4\x95\xa3)(\xa4\x89\x84=\xa2\xa8\xa2\x91\x93\xf1))";

$mesg = $conn->search(base   => $basedn,
                      scope  => $scope,
                      filter => $filter);
check_mesg($mesg, "Error searching");
