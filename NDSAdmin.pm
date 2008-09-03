package NDSAdmin;

use Socket;
use Sys::Hostname;
use IPC::Open2;
use Symbol;
use URI::Escape;
use MIME::Base64;
use Cwd;
use File::Basename;

use Mozilla::LDAP::Conn;
use Mozilla::LDAP::API qw(:api :ssl :apiv3 :constant); # Direct access to C API
use Mozilla::LDAP::Utils qw(normalizeDN printEntry);

require    Exporter;
@ISA       = qw(Exporter Mozilla::LDAP::Conn);
@EXPORT    = qw(getFQDN getdomainname createAndSetupReplica replicaSetupAll
			  createInstance defaultadmindomain defaultsuffix printRUV
			  parseCSNs compareCSNs compareRUVs $MASTER_TYPE $HUB_TYPE $LEAF_TYPE
			  parseCSN getTSDiff printTSDiff removeOtherInstance);

my $isNT = -d '\\';

my $REPLBINDDN;
my $REPLBINDCN;
my $REPLBINDPW;

sub getFQDN {
# return fully qualified host and domain name
# ex : hippo.mcom.com
# if the hostname from hostname() is not FQDN, find the first alias
# which matches the hostname which is also FQDN e.g.
# if given hippo, the $name might be realhost.mcom.com, but one of the aliases
# may be hippo.mcom.com - prefer the latter over the former since it matches
# the hostname
  my $hostname = shift;
  my $hrefalias = shift;

  return 'localhost' if (!$hostname && $ENV{LOCALHOSTFORHOSTNAME});
  return 'localhost' if ($hostname eq 'localhost' && $ENV{LOCALHOSTFORHOSTNAME});

  my $fqdn;
  if ($isNT) { # gethostbyname on NT messes up ldap_simple_bind_s
	$hostname = $hostname || `hostname`; # hostname on NT does not give FQDN
  } else {
	$hostname = $hostname || hostname();

# find the alias that most closely matches the hostname
	my ($name, $aliases, @rest) = gethostbyname($hostname);
	if ($aliases) {
	  my @alias = split(/\s+/, $aliases);
	  my $max = 1; # must have at least 1 domain component
	  for (@alias) {
		$hrefalias->{$_} = $_ if ($hrefalias);
		my $n = tr/\./\./; # count dots in name
		if (($n >= $max) && /^$hostname/) {
		  $max = $n;
		  $fqdn = $_;
		}
	  }
	}
  }

  if (!$fqdn) {
	if (open(NSLOOKUP, "nslookup $hostname|")) {
	  my $name;
	  sleep 1; # allow pipe to fill with data
	  while (<NSLOOKUP>) {
		chop;
		# use aliases if available, and the alias is an FQDN, and the
		# the alias is a close match to our hostname
		if (/^Aliases:\s*/) {
		  my $alias = $'; # ' fix font lock
		  $hrefalias->{$alias} = $alias if ($hrefalias);
		  if ($alias =~ /\./ && $alias =~ /^$hostname/) {
			$fqdn = $alias;
			last;
		  }
	    }
		# if no alias, just use the name
		if (/^Name:\s*/) {
		  $name = $';
		  $hrefalias->{$name} = $name if ($hrefalias);
		}
	  }
	  close NSLOOKUP;
	  if (!$fqdn && $name) {
		$fqdn = $name;
	  }
	}
  }

  # if we could not find a match, return the hostname if it contains
  # domain components or return the $name
  if (!$fqdn) {
	if ($hostname =~ /\./) { # perhaps the hostname is already fqdn
	  $fqdn = $hostname;
	} elsif ($name =~ /\./) { # try the canonical name
	  $fqdn = $name;
	} elsif (my $dmn = `domainname`) { # append the domain name
	  $fqdn = $hostname.$dmn;
	} else { # punt
	  $fqdn = $hostname;
	}
  }

  return $fqdn;
}

sub getdomainname {
  my $h = getFQDN(shift);
  # if $h begins with word. ...
  if ($h =~ /^.+?\./) {
	# ... return everything after word.
	return $'; # ' fix comment
  }
  return "";
}

sub defaultadmindomain {
  return (getdomainname(shift) || "mcom.com");
}

sub defaultsuffix {
  my $dm = getdomainname(shift);
  return "dc=mcom, dc=com" if (! $dm);
  my @dc = split(/\./, $dm);
  map { $_ = "dc=$_" } @dc;
  return join(',', @dc);
}

#########################################
# OVERRIDE methods go here ##############
#########################################
sub rebindProc {
  print "In rebind proc, args = @_\n" if ($verbose);
  return ($main::binddn, $main::bindpw, LDAP_AUTH_SIMPLE);
}

# returns the rebind proc subroutine
sub genRebindProc {
  my ($dn, $pwd, $auth, $verbose) = @_;
  $auth = LDAP_AUTH_SIMPLE if (!$auth);
  return sub {
	print "In rebind proc, args = @_\n" if ($verbose);
	return ($dn, $pwd, $auth);
  };
}

sub toString {
  my $self = shift;
  return $self->{host} . ":" . $self->{port};
}

sub toLDAPURL {
  my $self = shift;
  return "ldap://" . $self->{host} . ":" . $self->{port} . "/";
}

# override superclass init to do ldapv3 bind
sub init {
  my ($self) = shift;
  my ($ret, $ld);

  return 0 unless (defined($self->{"host"}));
  return 0 unless (defined($self->{"port"}));

  if (defined($self->{"certdb"}) && ($self->{"certdb"} ne ""))
    {
      $ret = ldapssl_client_init($self->{"certdb"}, 0);
      return 0 if ($ret < 0);

      $ld = ldapssl_init($self->{"host"}, $self->{"port"}, 1);
    }
  else
    {
      $ld = ldap_init($self->{"host"}, $self->{"port"});
    }
  return 0 unless $ld;

  $self->{"ld"} = $ld;
  if (defined($self->{"usenspr"})) {
    $ret = prldap_install_routines($self->{"ld"}, $self->{"usenspr"});
    return 0 unless ($ret == LDAP_SUCCESS);
  }

  # now defaults to 3
  $self->setVersion($self->{"version"});

  # see if binddn is a dn or a uid that we need to lookup
  if ($self->{binddn} && ($self->{"binddn"} !~ /\=/)) {
	$ret = ldap_simple_bind_s($ld, "", "");
	my $cfgent = $self->search("o=NetscapeRoot", "sub", "(uid=" . $self->{binddn} . ")",
							   0, qw(uid));
	my $rc = $self->getErrorCode();
	if ($cfgent) {
	  $self->{binddn} = $cfgent->getDN();
	} else {
	  print "Error: could not find ", $self->{"binddn"}, " under o=NetscapeRoot: $rc\n";
	}
  }
	
  $ret = ldap_simple_bind_s($ld, $self->{"binddn"}, $self->{"bindpasswd"});
  $self->setRebindProc(genRebindProc($self->{binddn}, $self->{bindpasswd}));

  $self->initPart2();

  return (($ret == LDAP_SUCCESS) ? 1 : 0);
}

#############################################################################
# Do a simple authentication, so that we can rebind as another user.
# override superclass to do ldapv3 bind
sub simpleAuth
{
  my ($self, $dn, $pswd) = @_;
  my ($ret);

  $self->setVersion($self->{"version"});
  $self->{binddn} = $dn;
  $self->{bindpasswd} = $pswd;
  # see if binddn is a dn or a uid that we need to lookup
  if ($self->{binddn} && ($self->{"binddn"} !~ /\=/)) {
	$ret = ldap_simple_bind_s($ld, "", "");
	my $cfgent = $self->search("o=NetscapeRoot", "sub", "(uid=" . $self->{binddn} . ")",
							   0, qw(uid));
	my $rc = $self->getErrorCode();
	if ($cfgent) {
	  $self->{binddn} = $cfgent->getDN();
	} else {
	  print "Error: could not find ", $self->{"binddn"}, " under o=NetscapeRoot: $rc\n";
	}
  }
  $ret = ldap_simple_bind_s($self->{"ld"}, $dn, $pswd);
  if ($ret == LDAP_CONSTRAINT_VIOLATION) { # password retry limit exceeded
	print "Error: password retry limit exceeded for $dn\n";
  } elsif ($ret != LDAP_SUCCESS) {
	print "Error: could not bind $dn: $ret\n";
  }
 
  if ($ret == LDAP_SUCCESS) {
	$self->setRebindProc(genRebindProc($dn, $pswd));

	$self->initPart2();
  }

  return (($ret == LDAP_SUCCESS) ? 1 : 0);
}

# we should do this any time we rebind - the user may have created the initial
# connection as anonymous, then did a rebind as an administrative user, so we
# need to read the information we could not read before
sub initPart2 {
  my $self = shift;
  # set the other things like the instance name and server root, but not if
  # the connection is anonymous
  if ($self->{binddn} && length($self->{binddn}) && !$self->{sroot}) {
	my $cfgent = $self->search("cn=config", "base", "(objectclass=*)",
							   0, qw(nsslapd-instancedir nsslapd-errorlog));
	my $rc = $self->getErrorCode();
	my %ignore = ( 50 => 50, 91 => 91 );
	if ($cfgent) {
	  my $instdir = $cfgent->getValues('nsslapd-instancedir');
	  if ($instdir =~ m|(.*)[\\/]slapd-(\w+)$|) {
		$self->{sroot} = $1;
		$self->{inst} = $2;
	  } else {
		print "Error: could not parse instance dir $instdir\n";
	  }
	  $self->{errlog} = $cfgent->getValues('nsslapd-errorlog');
	  if (!$self->{isLocal}) {
		if (-d $instdir) { # does instance dir exist on this machine?
		  $self->{isLocal} = 1;
		} else {
		  $self->{isLocal} = 0;
		}
	  }
	} elsif (!$ignore{$rc}) {
	  print "Error: could not read cn=config: err=$rc\n";
	}
  }
}

# this does not check to see if the suffix already has backends, because
# this function can also be used to create multiple backends for entry
# distribution
# call getBackendsForSuffix before calling this function if you need
# to make sure the suffix does not already have backends
# returns the name (the cn) of the backend just created or 0
sub setupBackend {
  my ($self, $suffix, $binddn, $bindpw, $urls, $attrvals) = @_;
  my $ldbmdn = "cn=ldbm database, cn=plugins, cn=config";
  my $chaindn = "cn=chaining database, cn=plugins, cn=config";
  my $dnbase;
  my $benamebase;
  # figure out what type of be based on args
  if ($binddn && $bindpw && $urls) { # its a chaining be
	$benamebase = "chaindb";
	$dnbase = $chaindn;
  } else { # its a ldbm be
	$benamebase = "localdb";
	$dnbase = $ldbmdn;
  }
  my $nsuffix = normalizeDN($suffix);
  my $rc = 68;
  my $benum = 1;
  while ($rc == 68) {
	$entry = new Mozilla::LDAP::Entry();
	my $cn = $benamebase . $benum; # e.g. localdb1
	my $dn = "cn=$cn, $dnbase";
	$entry->setDN($dn);
	$entry->setValues('objectclass', 'top', 'extensibleObject', 'nsBackendInstance');
	$entry->setValues('cn', $cn);
	$entry->setValues('nsslapd-suffix', $nsuffix);
	if ($binddn && $bindpw && $urls) { # its a chaining be
	  $entry->setValues('nsfarmserverurl', @{$urls});
	  $entry->setValues('nsmultiplexorbinddn', $binddn);
	  $entry->setValues('nsmultiplexorcredentials', $bindpw);
	} else { # set ldbm parameters
	  $entry->setValues('nsslapd-cachesize', '-1');
	  $entry->setValues('nsslapd-cachememsize', '2097152');
	}
	for (my ($attr, $val) = each %{$attrvals}) { # add more attrs and values
	  $entry->setValues($attr, $val);
	}
	$self->add($entry);
	$rc = $self->getErrorCode();
	if ($rc == 0) {
	  $entry = $self->search($dn, "base", "(objectclass=*)");
	  if (! $entry) {
		print "Entry $dn was added successfully, but I cannot search it: " .
		  $self->getErrorString(), "\n";
		$rc = -1;
	  } else {
		printEntry($entry);
		return $cn;
	  }
	} elsif ($rc == 68) { # that name exists
	  $benum++; # increment and try again
	} else {
	  print "Couldn't add entry $dn: ", $self->getErrorString(), "\n";
	}
  }

  return 0;
}

sub setupSuffix {
  my ($self, $suffix, $bename, $parent, $rc) = @_;
  my $nsuffix = normalizeDN($suffix);
  my $nparent = normalizeDN($parent) if ($parent);

  my $dn = "cn=\"$nsuffix\", cn=mapping tree, cn=config";
  my $entry = $self->search("cn=mapping tree, cn=config", "sub",
							"(|(cn=\"$suffix\")(cn=\"$nsuffix\"))");
  if (! $entry) {
	$entry = new Mozilla::LDAP::Entry();
	$dn = "cn=\"$nsuffix\", cn=mapping tree, cn=config";
	$entry->setDN($dn);
	$entry->setValues('objectclass', 'top', 'extensibleObject', 'nsMappingTree');
	$entry->setValues('cn', "\"$nsuffix\"");
	$entry->setValues('nsslapd-state', 'backend');
	$entry->setValues('nsslapd-backend', $bename);
	$entry->setValues('nsslapd-parent-suffix', "\"$nparent\"") if ($parent);
	$self->add($entry);
	if ($rc = $self->getErrorCode()) {
	  print "Couldn't add entry " . $entry->getDN() . ": " . $self->getErrorString(), "\n";
	  return $rc;
	} else {
	  $entry = $self->search($dn, "base", "(objectclass=*)");
	  if (! $entry) {
		print "Entry $dn was added successfully, but I cannot search it: " .
		  $self->getErrorString(), "\n";
		return -1;
	  } else {
		printEntry($entry);
	  }
	}
  }

  return $rc;
}

# given a suffix, return the mapping tree entry for it
sub getMTEntry {
  my ($self, $suffix, @attrs) = @_;
  my $nsuffix = normalizeDN($suffix);
  if (@attrs) {
	return $self->search("cn=mapping tree,cn=config", "one",
						 "(|(cn=\"$suffix\")(cn=\"$nsuffix\"))", 0, @attrs);
  } else {
	return $self->search("cn=mapping tree,cn=config", "one",
						 "(|(cn=\"$suffix\")(cn=\"$nsuffix\"))");
  }
}

# given a suffix, return a list of backend entries for that suffix
sub getBackendsForSuffix {
  my ($self, $suffix, @attrs) = @_;
  my $nsuffix = normalizeDN($suffix);
  my $beent;
  my @beents;
  if (@attrs) {
	$beent = $self->search("cn=plugins,cn=config", "sub",
						   "(&(objectclass=nsBackendInstance)(|(nsslapd-suffix=$suffix)(nsslapd-suffix=$nsuffix)))",
						   0, @attrs);
  } else {
	$beent = $self->search("cn=plugins,cn=config", "sub",
						   "(&(objectclass=nsBackendInstance)(|(nsslapd-suffix=$suffix)(nsslapd-suffix=$nsuffix)))");
  }

  while ($beent) {
	push @beents, $beent;
	$beent = $self->nextEntry();
  }

  return @beents;
}

# given a backend name, return the mapping tree entry for it
sub getSuffixForBackend {
  my ($self, $bename, @attrs) = @_;
  my $beent = $self->search("cn=plugins,cn=config", "sub",
							"(&(objectclass=nsBackendInstance)(cn=$_))",
							0, qw(nsslapd-suffix));
  if ($beent) {
	my $suffix = $beent->getValues('nsslapd-suffix');
	return $self->getMTEntry($suffix, @attrs);
  }

  return 0;
}

sub addSuffix {
  my ($self, $suffix, $binddn, $bindpw, @urls) = @_;
  my @beents = $self->getBackendsForSuffix($suffix, qw(cn));
  my $bename;
  my @benames;
  # no backends for this suffix yet - create one
  if (!@beents) {
	if (!($bename = $self->setupBackend($suffix, $binddn, $bindpw, \@urls))) {
	  print "Couldn't create backend for $suffix " . $self->getErrorString(), "\n";
	  return $self->getErrorCode();
	}
  } else { # use existing backend(s)
	for (@beents) {
	  push @benames, $_->getValues('cn');
	}
	$bename = shift @benames;
  }

  my $parent = $self->findParentSuffix($suffix);
  if (my $rc = $self->setupSuffix($suffix, $bename, $parent)) {
	print "Couldn't create suffix for $bename $suffix " . $self->getErrorString(), "\n";
  }

  return $rc;
}

# specify the suffix (should contain 1 local database backend),
# the name of the attribute to index, and the types of indexes
# to create e.g. "pres", "eq", "sub"
sub addIndex {
  my ($self, $suffix, $attr, @indexTypes, $rc) = @_;
  my @beents = $self->getBackendsForSuffix($suffix, qw(cn));
  # assume 1 local backend
  my $dn = "cn=$attr,cn=index," . $beents[0]->getDN();
  my $entry = new Mozilla::LDAP::Entry();
  $entry->dn($dn);
  $entry->add('objectclass', 'top', 'nsIndex');
  $entry->add('cn', $attr);
  $entry->add('nsSystemIndex', "false");
  $entry->add('nsIndexType', @indexTypes);
  $self->add($entry);
  if (($rc = $self->getErrorCode()) && ($rc != 68)) {
    print "Couldn't add index entry $dn: " . $self->getErrorString() . "\n";
  } elsif ($rc == 68) {
    print "Index entry $dn already exists\n";
  }
}

sub startTaskAndWait {
  my ($self, $entry, $verbose) = @_;

  my $dn = $entry->getDN();
  # start the task
  $self->add($entry);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't add entry $dn: " . $self->getErrorString() if ($verbose);
	return -1;
  } else {
	$entry = $self->search($dn, "base", "(objectclass=*)");
	if (! $entry) {
	  print "Entry $dn was added successfully, but I cannot search it: " .
		$self->getErrorString() if ($verbose);
	  return -1;
	} elsif ($verbose) {
	  printEntry($entry);
	}
  }

  # wait for task completion - task is complete when the nsTaskExitCode attr is set
  my @attrlist = qw(nsTaskLog nsTaskStatus nsTaskExitCode nsTaskCurrentItem nsTaskTotalItems);
  my $done = 0;
  my $exitCode = 0;
  while (! $done) {
	sleep 1;
	$entry = $self->search($dn, "base", "(objectclass=*)", 0, @attrlist);
	printEntry($entry) if ($verbose);
	if ($entry->exists('nsTaskExitCode')) {
	  $exitCode = $entry->getValues('nsTaskExitCode');
	  $done = 1;
	}
  }

  return $exitCode;
}

sub importLDIF {
  my ($self, $file, $suffix, $be, $verbose, $rc) = @_;
  my $cn = "import" . time;
  my $dn = "cn=$cn, cn=import, cn=tasks, cn=config";
  my $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', 'top', 'extensibleObject');
  $entry->setValues('cn', $cn);
  $entry->setValues('nsFilename', $file);
  if ($be) {
	$entry->setValues('nsInstance', $be);
  } else {
	$entry->setValues('nsIncludeSuffix', $suffix);
  }

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: import task $cn exited with $rc\n" if ($verbose);
  } else {
	print "Import task $cn completed successfully\n" if ($verbose);
  }

  return $rc;
}

sub exportLDIF {
  my ($self, $file, $suffix, $forrepl, $verbose, $rc) = @_;
  my $cn = "export" . time;
  my $dn = "cn=$cn, cn=export, cn=tasks, cn=config";
  my $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', 'top', 'extensibleObject');
  $entry->setValues('cn', $cn);
  $entry->setValues('nsFilename', $file);
  $entry->setValues('nsIncludeSuffix', $suffix);
  $entry->setValues('nsExportReplica', "true") if ($forrepl); # create replica init file

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: export task $cn exited with $rc\n" if ($verbose);
  } else {
	print "Export task $cn completed successfully\n" if ($verbose);
  }

  return $rc;
}

# use two ways: give conn and full path to archiveDir
# OR
# give conn, server root, and instance dir - a timestamp based archive name will be
# generated and returned
sub backupDB {
  my ($self, $archiveDir, $verbose, $rc) = @_;
  my $curtime = time;
  my $cn = "backup" . $curtime;
  my $dn = "cn=$cn, cn=backup, cn=tasks, cn=config";
  if (! $archiveDir) { # $archiveDir should not exist yet, so this must be the server root
	$archiveDir = "$self->{sroot}/slapd-$self->{inst}/bak/$curtime";
  } # also, this only works on the localhost
  my $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', 'top', 'extensibleObject');
  $entry->setValues('cn', $cn);
  $entry->setValues('nsArchiveDir', $archiveDir);

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: backup task $cn exited with $rc\n" if ($verbose);
	return 0;
  } else {
	print "Backup task $cn completed successfully\n" if ($verbose);
  }

  return $archiveDir;
}

sub restoreDB {
  my ($self, $archiveDir, $verbose, $rc) = @_;
  my $curtime = time;
  my $cn = "restore" . $curtime;
  my $dn = "cn=$cn, cn=restore, cn=tasks, cn=config";
  my $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', 'top', 'extensibleObject');
  $entry->setValues('cn', $cn);
  $entry->setValues('nsArchiveDir', $archiveDir);

  $rc = $self->startTaskAndWait($entry, $verbose);

  if ($rc) {
	print "Error: restore task $cn exited with $rc\n" if ($verbose);
  } else {
	print "Restore task $cn completed successfully\n" if ($verbose);
  }

  return $rc;
}

sub serverCmd {
  my ($self, $cmd, $verbose, $timeout) = @_;
  my ($sroot, $inst) = ($self->{sroot}, $self->{inst});
  my $instanceDir = $sroot . "/slapd-" . $inst;
  my $errLog = $instanceDir . "/" . 'logs' . "/" . 'errors';
  if ($self->{errlog}) {
	$errLog = $self->{errlog};
  }
  # emulate tail -f
  # if the last line we see does not contain "slapd started", try again
  my $done = 0;
  my $started = 1;
  my $code = 0;
  my $lastLine = "";
  $cmd = lc($cmd);
  my $fullCmd = $instanceDir . "/$cmd-slapd";
  my $cmdPat = (($cmd eq 'start') ? 'slapd started\.' : 'slapd stopped\.');

  $timeout = $timeout?$timeout:120; # default is 120 seconds
  $timeout = time + $timeout;	# 20 minutes
  if ($cmd eq 'stop') {
	$self->close();
  }

  open(IN, $errLog) or print "Could not open error log $errLog: $!\n", return -1;
  seek IN, 0, 2; # go to eof
  my $pos = tell(IN);
  # . . . reset the EOF status of the file desc
  seek(IN, $pos, 0);
  $code = system($fullCmd);
  while (($done == 0) && (time < $timeout)) {
    for (; ($done == 0) && ($_ = <IN>); $pos = tell(IN)) {
      $lastLine = $_;
	  print if ($verbose);
      # the server has already been started and shutdown once . . .
      if (/$cmdPat/) {
		$started++;
		if ($started == 2) {
		  $done = 1;
		}
		# sometimes the server will fail to come up; in that case, restart it
      } elsif (/Initialization Failed/) {
		#				print "Server failed to start: $_";
		$code = system($fullCmd);
		# sometimes the server will fail to come up; in that case, restart it
      } elsif (/exiting\./) {
		#				print "Server failed to start: $_";
		#$code = &mySystem($fullCmd);

		$code = system($fullCmd);
      }
    }
    if ($lastLine =~ /PR_Bind/) {
      # server port conflicts with another one, just report and punt
      print $lastLine;
      print "This server cannot be started until the other server on this\n";
      print "port is shutdown.\n";
      $done = 1;
    }
    if ($done == 0) {
      # rest a bit, then . . .
      sleep(2);
      # . . . reset the EOF status of the file desc
      seek(IN, $pos, 0);
    }
  }
  close(IN);

  if ($started < 2) {
    $! = $code;
    $now = time;
    if ($now > $timeout) {
    	print "Possible timeout: timeout=$timeout now=$now\n";
    }
    print "Error: could not $cmd server $sroot $inst: $!" if ($verbose);
	return 1;
  } else {
	print "$cmd was successful for $sroot $inst\n" if ($verbose);
	if ($cmd eq 'start') {
	  $self->init();
	}
  }

  return 0;
}

sub start {
  my ($self, $verbose, $timeout) = @_;
  if (!$self->{isLocal} && $self->{asport}) {
	my %cgiargs = ( 'dummy' => 'dummy' );
	print "starting remote server ", $self->toString(), "\n" if ($verbose);
	my $rc = &cgiPost($self->{host}, $self->{asport}, $self->{cfgdsuser},
					  $self->{cfgdspwd},
					  "/slapd-$self->{inst}/Tasks/Operation/start",
					  $verbose, \%cgiargs);
	print "connecting remote server ", $self->toString(), "\n" if ($verbose);
	$self->init() if (!$rc);
	print "started remote server ", $self->toString(), " rc = $rc\n" if ($verbose);
	return $rc;
  } else {
	return $self->serverCmd('start', $verbose, $timeout);
  }
}

sub stop {
  my ($self, $verbose, $timeout) = @_;
  if (!$self->{isLocal} && $self->{asport}) {
	print "stopping remote server ", $self->toString(), "\n" if ($verbose);
	$self->close();
	print "closed remote server ", $self->toString(), "\n" if ($verbose);
	my %cgiargs = ( 'dummy' => 'dummy' );
	my $rc = &cgiPost($self->{host}, $self->{asport}, $self->{cfgdsuser},
					  $self->{cfgdspwd},
					  "/slapd-$self->{inst}/Tasks/Operation/stop",
					  $verbose, \%cgiargs);
	print "stopped remote server ", $self->toString(), " rc = $rc\n" if ($verbose);
	return $rc;
  } else {
	return $self->serverCmd('stop', $verbose, $timeout);
  }
}

sub addSchema {
  my ($self, $attr, $val) = @_;
  my $dn = "cn=schema";
  my %mod = (
	$attr => { 'a' => [ $val ] }
  );
  ldap_modify_s($self->{ld}, $dn, \%mod);
  my $rc = $self->getErrorCode();
  if ($rc) {
	print "Couldn't add schema $attr $val: $rc: " . $self->getErrorString(), "\n";
  }

  return $rc;
}

sub addAttr {
  my $self = shift;
  return $self->addSchema('attributeTypes', @_);
}

sub addObjClass {
  my $self = shift;
  return $self->addSchema('objectClasses', @_);
}

sub waitForEntry {
  my ($self, $dn, $timeout, $attr, $quiet, $rc) = @_;
  my $scope = "base";
  my $filter = "(objectclass=*)";
  if ($attr) {
	$filter = "($attr=*)";
  }
  my @attrlist = ();
  if ($attr) {
	@attrlist = ($attr);
  }
  $timeout = ($timeout ? $timeout : 7200);
  $timeout = time + $timeout;

  if (ref($dn) eq 'Mozilla::LDAP::Entry') {
	$dn = $dn->getDN();
  }
  # wait for entry and/or attr to show up
  my $entry = $self->search($dn, $scope, $filter, 0, @attrlist);
  $rc = $self->getErrorCode();
  $attr = "" if (!$attr); # to avoid uninit. variable
  $| = 1; #keep that output coming...
  print "Waiting for $dn:$attr ", $self->toString() if (!$quiet);
  while (!$entry && (time < $timeout)) {
	print "$rc:" if (!$quiet);
	sleep 1;
	$entry = $self->search($dn, $scope, $filter, 0, @attrlist);
	$rc = $self->getErrorCode();
  }
  if (!$entry && (time > $timeout)) {
	print "\nwaitForEntry timeout for $dn for ", $self->toString(), "\n";
  } elsif ($entry && !$quiet) {
	print "\nThe waited for entry is:\n";
	printEntry($entry);
	print "\n";
  } elsif (!$entry) {
	print "\nwaitForEntry error $rc reading $dn for ", $self->toString(), "\n";
  }
  return $entry;
}

# if $parentOrEntry is a string DN, add a random entry using that DN as the parent
# if $parentOrEntry is an Entry, add the entry
# returns the entry added or undef
sub addEntry {
  my ($self, $parentOrEntry, $check) = @_;
  my $rc;
  my $dn;
  my $entry;
  if (ref($parentOrEntry) ne 'Mozilla::LDAP::Entry') {
	my $cn = "repl" . rand(100);
	$dn = "cn=$cn, " . $parentOrEntry;
	$entry = $self->search($dn, "base", "(objectclass=*)");
	if (!$entry) {
	  $entry = new Mozilla::LDAP::Entry();
	  $entry->setDN($dn);
	  $entry->setValues('objectclass', "top", "extensibleobject");
	  $entry->setValues('cn', $cn);
	  $self->add($entry);
	}
  } else {
	$entry = $parentOrEntry;
	$dn = $entry->getDN();
	$self->add($entry);
  }
  if ($rc = $self->getErrorCode()) {
	print "Couldn't add entry " . $entry->getDN() . ": " . $self->getErrorString(), "\n";
	$entry = undef;
  } elsif ($check) {
	$entry = $self->search($dn, "base", "(objectclass=*)");
	if (! $entry) {
	  print "Entry $dn was added successfully, but I cannot search it: " .
		$self->getErrorString(), "\n";
	} else {
	  printEntry($entry);
	}
  }
  return $entry;
}

sub enableReplLogging {
  my $self = shift;
  return $self->setLogLevel(8192);
}

sub disableReplLogging {
  my $self = shift;
  return $self->setLogLevel(0);
}

sub setLogLevel {
  my ($self, @vals) = @_;
  my ($rc, %mod, $val);
  for (@vals) {
	$val += $_;
  }
  $mod{'nsslapd-errorlog-level'} = { 'r' => [ $val ] };
  ldap_modify_s($self->{ld}, 'cn=config', \%mod);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't set log level to $val: $rc: " . $self->getErrorString(), "\n";
  }

  return $rc;
}

sub setAccessLogLevel {
  my ($self, @vals) = @_;
  my ($rc, %mod, $val);
  for (@vals) {
	$val += $_;
  }
  $mod{'nsslapd-accesslog-level'} = { 'r' => [ $val ] };
  ldap_modify_s($self->{ld}, 'cn=config', \%mod);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't set access log level to $val: $rc: " . $self->getErrorString(), "\n";
  }

  return $rc;
}

sub setDBReadOnly {
  my ($self, $val, $bename) = @_;
  $bename = ($bename ? $bename : "userRoot");
  my $dn = "cn=$bename, cn=ldbm database, cn=plugins, cn=config";
  my %mod = (
	'nsslapd-readonly' => { 'r' => [ $val ] }
  );
  ldap_modify_s($self->{ld}, $dn, \%mod);
  my $rc = $self->getErrorCode();
  if ($rc) {
	print "Couldn't set db $bename readonly to $val: $rc: " . $self->getErrorString(), "\n";
  }

  return $rc;
}

# argument is a hashref - key is password policy attr, value is off or on
# attrs are: 
#	passwordchecksyntax    - check password syntax when adding/changing password
#	passwordexp            - check for password expiration
#	passwordhistory        - keep and check password history
#	passwordlockout        - lockout accounts after unsuccessful bind attempts
#	passwordisglobalpolicy - allow replication of operational password policy attrs in user entries
sub setupPasswordPolicy {
  my ($self, $href) = @_;
  my %mod;
  while (my ($key, $val) = each %{$href}) {
	$mod{$key} = { 'r' => [ $val ] };
	print "setupPasswordPolicy: $key is $val\n";
  }
  ldap_modify_s($self->getLD(), "cn=config", \%mod);
  my $rc = $self->getErrorCode();
  if ($rc) {
	print "Error: could not setup password policy for ", keys %{$href}, ": $rc\n";
  }
  return $rc;
}

sub setupChainingIntermediate {
  my $self = shift;

  my $confdn = "cn=config,cn=chaining database,cn=plugins,cn=config";
  %mod = ( 'nsTransmittedControl' =>
		   { 'a' => [ '2.16.840.1.113730.3.4.12', '1.3.6.1.4.1.1466.29539.12' ] } );
  ldap_modify_s($self->getLD(), $confdn, \%mod);
  $rc = $self->getErrorCode();
  if ($rc != 0 && $rc != 20) {
	print "Couldn't add transmitted controls to $confdn $rc: " . $self->getErrorString(), "\n";
  } else {
	$rc = 0;
  }

  return $rc;
}

sub setupChainingMux {
  my ($self, $suffix, $isIntermediate, $binddn, $bindpw, @urls) = @_;
  my $rc = $self->addSuffix($suffix, $binddn, $bindpw, @urls);
  if (!$rc && $isIntermediate) {
	$rc = $self->setupChainingIntermediate();
  }
  return $rc;
}

sub setupChainingFarm {
  my ($self, $suffix, $binddn, $bindcn, $bindpw) = @_;
  my $rc;
  # step 1 - create the bind dn to use as the proxy
  if ($rc = $self->setupBindDN($binddn, $bindcn, $bindpw)) {
	print "Couldn't setup chaining bind dn $binddn $rc: " . $self->getErrorString(), "\n";
  } elsif ($rc = $self->addSuffix($suffix)) { # step 2 - create the suffix
	print "Couldn't add chaining suffix $bename $suffix $rc: " . $self->getErrorString(), "\n";
  } else {
	# step 3 - add the proxy ACI to the suffix
	my %mod = ( 'aci' => { 'a' => [ "(targetattr = \"*\")(version 3.0; acl \"Proxied authorization for database links\"; allow (proxy) userdn = \"ldap:///$binddn\";)" ] } );
	ldap_modify_s($self->getLD(), $suffix, \%mod);
	$rc = $self->getErrorCode();
	if ($rc != 0 && $rc != 20) { # ignore if aci already exists
	  print "Couldn't add proxy aci to $suffix $rc: " . $self->getErrorString(), "\n";
	} else {
	  $rc = 0;
	}
  }

  return $rc;
}

# setup chaining from self to $to - self is the mux, to is the farm
# if isIntermediate is set, this server will chain requests from another server to $to
sub setupChaining {
  my ($self, $to, $suffix, $isIntermediate) = @_;
  my $bindcn = "chaining user";
  my $binddn = "cn=$bindcn,cn=config";
  my $bindpw = "chaining";

  $to->setupChainingFarm($suffix, $binddn, $bindcn, $bindpw);
  $self->setupChainingMux($suffix, $isIntermediate, $binddn, $bindpw, $to->toLDAPURL());
}

sub setupChangelog {
  my ($self, $dir, $rc) = @_;
  my $dn = "cn=changelog5, cn=config";
  my $entry = $self->search($dn, "base", "(objectclass=*)");
  return $rc if ($entry);
  $dir = $dir ? $dir : "$self->{sroot}/slapd-$self->{inst}/../slapd-$self->{inst}/cldb";
  $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', "top", "extensibleobject");
  $entry->setValues('cn', "changelog5");
  $entry->setValues('nsslapd-changelogdir', $dir);
  $self->add($entry);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't add entry " . $entry->getDN() . ": " . $self->getErrorString(), "\n";
	return $rc;
  } else {
	$entry = $self->search($dn, "base", "(objectclass=*)");
	if (! $entry) {
	  print "Entry $dn was added successfully, but I cannot search it: " . $self->getErrorString(),
		"\n";
	  return -1;
	} else {
	  printEntry($entry);
	}
  }
  return $rc;
}

sub enableChainOnUpdate {
  my ($self, $suffix, $bename) = @_;
  # first, get the mapping tree entry to modify
  my $mtent = $self->getMTEntry($suffix, qw(cn));
  my $dn = $mtent->getDN();

  # next, get the path of the replication plugin
  my $plgent = $self->search("cn=Multimaster Replication Plugin,cn=plugins,cn=config",
							 "base", "(objectclass=*)", 0, qw(nsslapd-pluginPath));
  my $path = $plgent->getValues('nsslapd-pluginPath');

  my %mod = ( 'nsslapd-state' => { 'r' => [ 'backend' ] },
			  'nsslapd-backend' => { 'a' => [ $bename ] },
			  'nsslapd-distribution-plugin' => { 'a' => [ $path ] },
			  'nsslapd-distribution-funct' => { 'a' => [ 'repl_chain_on_update' ] } );

  ldap_modify_s($self->getLD(), $dn, \%mod);
  my $rc = $self->getErrorCode();
  if ($rc != 0 && $rc != 20) {
	print "Error: could not enable chain on update: $rc\n";
  } else {
	return 0;
  }

  return $rc;
}

sub enableReferralMode {
  my ($self, $suffix) = @_;
  # first, get the mapping tree entry to modify
  my $mtent = $self->getMTEntry($suffix, qw(cn));
  my $dn = $mtent->getDN();

  # next, get the path of the replication plugin

  my %mod = ( 'nsslapd-state' => { 'r' => [ 'referral' ] } );

  ldap_modify_s($self->getLD(), $dn, \%mod);
  my $rc = $self->getErrorCode();
  if ($rc != 0 && $rc != 20) {
	print "Error: could not enable referral mode: $rc\n";
  } else {
	return 0;
  }

  return $rc;
}

sub setupConsumerChainOnUpdate {
  my ($self, $suffix, $isIntermediate, $binddn, $bindpw, @urls) = @_;
  # suffix should already exist
  # we need to create a chaining backend
  my $chainbe = $self->setupBackend($suffix, $binddn, $bindpw, \@urls,
								   { 'nsCheckLocalACI'            => 'on' }); # enable local db aci eval.
  # do the stuff for intermediate chains
  $self->setupChainingIntermediate() if ($isIntermediate);
  # enable the chain on update
  return $self->enableChainOnUpdate($suffix, $chainbe);
}

my $REPLICAID = 0;
my $MASTER_TYPE = 0;
# N = 1 - a hub (read only supplier)
my $HUB_TYPE = 1;
# N = 2 - a "leaf" consumer
my $LEAF_TYPE = 2;

# arguments to set up a replica:
# suffix - dn of suffix
# type - master, hub, leaf (see above for values) - if type is omitted, default is master
# legacy - true or false for legacy consumer
# id - replica id
# binddn - the replication bind dn for this replica
# if replica ID is not given, an internal sequence number will be assigned
# call like this:
# $thing->setupReplica({
#		suffix => "dc=mcom, dc=com",
#		type => $MASTER_TYPE,
#		binddn => "cn=replication manager, cn=config",
#		id => 3
#  });
# binddn can also be an array ref:
#	binddn => [ "cn=repl1, cn=config", "cn=repl2, cn=config" ],
sub setupReplica {
  my ($self, $args) = @_;
  my $rc;
  my $suffix = $args->{suffix};
  my $type = $args->{type} || $MASTER_TYPE;
  my $legacy = $args->{legacy};
  my $binddn = $args->{binddn};
  my $id = $args->{id};
  my $tpi = $args->{tombstone_purge_interval};
  my $pd = $args->{purge_delay};
  my $referrals = $args->{referrals};
  my $nsuffix = normalizeDN($suffix);
  my $dn = "cn=replica, cn=\"" . $nsuffix . "\", cn=mapping tree, cn=config";

  if (my $entry = $self->search($dn, "base", "(objectclass=*)")) {
	$self->{$nsuffix}{dn} = $dn;
	return $rc;
  }

  my @binddnlist;
  if ($binddn && ref($binddn)) {
	@binddnlist = @{$binddn};
  } elsif ($binddn) {
	push @binddnlist, $binddn;
  } else {
	push @binddnlist, $REPLBINDDN;
  }

  if (!$id && !$type) {
	$id = ++$REPLICAID;
  } elsif (!$id) {
	$id = 0;
  } else {
	# replica id was given, so use that for our internal counter
	$REPLICAID = $id;
	die;
  }

  $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', "top", "nsds5replica", "extensibleobject");
  $entry->setValues('cn', "replica");
  $entry->setValues('nsds5replicaroot', $nsuffix);
  $entry->setValues('nsds5replicaid', $id);
  $entry->setValues('nsds5replicatype', ($type ? "2" : "3"));
  $entry->setValues('nsds5flags', "1") if ($type != $LEAF_TYPE);
  $entry->setValues('nsds5replicabinddn', @binddnlist);
  $entry->setValues('nsds5replicalegacyconsumer', ($legacy ? "on" : "off"));
  $entry->setValues('nsds5replicatombstonepurgeinterval', $tpi) if ($tpi);
  $entry->setValues('nsds5ReplicaPurgeDelay', $pd) if ($pd);
  $entry->setValues('nsds5ReplicaReferral', $referrals) if ($referrals);
  $entry->setValues('nsDS5ReplicatedAttributeList', $args->{fractional}) if ($args->{fractional});
  $self->add($entry);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't add entry " . $entry->getDN() . ": " . $self->getErrorString(), "\n";
	return $rc;
  } else {
	$entry = $self->search($dn, "base", "(objectclass=*)");
	if (! $entry) {
	  print "Entry $dn was added successfully, but I cannot search it: " . $self->getErrorString(),
		"\n";
	  return -1;
	} else {
      # remove this binary attr because it messes up the console
	  # when printed - this does not remove it from the real entry
	  $entry->remove("nsState");
	  $entry->remove("nsstate");
	  printEntry($entry);
	}
  }
  $self->{$nsuffix}{dn} = $dn;
  $self->{$nsuffix}{type} = $type;
  return $rc;
}

sub setupLegacyConsumer {
  my ($self, $binddn, $bindpw, $rc) = @_;
  my $legacydn = "cn=legacy consumer, cn=replication, cn=config";
  my $entry = $self->search($legacydn, "base", "(objectclass=*)");
  if (! $entry) {
#  $self->delete($entry) if ($entry);
	$entry = new Mozilla::LDAP::Entry();
	$entry->setDN($legacydn);
	$entry->setValues('objectclass', "top", "extensibleObject");
	$entry->setValues('nsslapd-legacy-updatedn', $binddn ? $binddn : $REPLBINDDN);
	$entry->setValues('nsslapd-legacy-updatepw', $bindpw ? $bindpw : $REPLBINDPW);
	$self->add($entry);
	if ($rc = $self->getErrorCode()) {
	  print "Couldn't add entry " . $entry->getDN() . ": " . $self->getErrorString(), "\n";
	  return $rc;
	} else {
	  $entry = $self->search($legacydn, "base", "(objectclass=*)");
	  if (! $entry) {
		print "Entry $legacydn was added successfully, but I cannot search it: " . $self->getErrorString(),
		  "\n";
		return -1;
	  } else {
		printEntry($entry);
	  }
	}
  }
  return $rc;
}

# $dn can be an entry
sub setupBindDN {
  my ($self, $dn, $cn, $pwd, $rc) = @_;
  my $ent;
  if ($dn && (ref($dn) eq 'Mozilla::LDAP::Entry')) {
	$ent = $dn;
	$dn = $ent->getDN();
  } elsif (!$dn) {
	$dn = $REPLBINDDN;
  }
  my $entry = $self->search($dn, "base", "(objectclass=*)");
  return $rc if ($entry);
  if (!$ent) {
	$ent = new Mozilla::LDAP::Entry();
	$ent->setDN($dn);
	$ent->setValues('objectclass', "top", "person");
	$ent->setValues('cn', $cn ? $cn : $REPLBINDCN);
	$ent->setValues('userpassword', $pwd ? $pwd : $REPLBINDPW);
	$ent->setValues('sn', "bind dn pseudo user");
  }
  $self->add($ent);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't add entry " . $ent->getDN() . ": " . $self->getErrorString(), "\n";
	return $rc;
  } else {
	$ent = $self->search($dn, "base", "(objectclass=*)");
	if (! $ent) {
	  print "Entry $dn was added successfully, but I cannot search it: " . $self->getErrorString(),
		"\n";
	  return -1;
	} else {
	  printEntry($ent);
	}
  }

  return $rc;
}

sub setupReplBindDN {
  my ($self, $dn, $cn, $pwd, $rc) = @_;
  return $self->setupBindDN($dn, $cn, $pwd);
}

# args - NDSAdmin consumer, suffix, binddn, bindpw, timeout
sub setupAgreement {
  my ($self, $repoth, $suffix, $binddn, $bindpw, $chain, $timeout, $fractional, $rc) = @_;
  my $nsuffix = normalizeDN($suffix);
  my ($othhost, $othport, $othsslport) =
	($repoth->{host}, $repoth->{port}, $repoth->{sslport});
  $othport = ($othsslport ? $othsslport : $othport);
  my $dn = "cn=meTo${othhost}$othport, " . $self->{$nsuffix}{dn};
  my $entry = $self->search($dn, "base", "(objectclass=*)");
  if ($entry) {
	print "Agreement exists:\n";
	printEntry($entry);
	$self->{$nsuffix}{$repoth->toString()} = $dn;
	return $dn;
  }
#	$conn->delete($dn);
#	sleep 1;
#	$entry = $conn->search($dn, "base", "(objectclass=*)");
#	if ($entry || (($rc = $conn->getErrorCode()) != 32)) {
#	  print "Error: could not delete $dn: $rc\n";
#	}
#  }

  $entry = new Mozilla::LDAP::Entry();
  $entry->setDN($dn);
  $entry->setValues('objectclass', "top", "nsds5replicationagreement");
  $entry->setValues('cn', "meTo${othhost}$othport");
  $entry->setValues('nsds5replicahost', $othhost);
  $entry->setValues('nsds5replicaport', $othport);
  $entry->setValues('nsds5replicatimeout', $timeout ? $timeout : '120');
  $entry->setValues('nsds5replicabinddn', $binddn ? $binddn : $REPLBINDDN);
  $entry->setValues('nsds5replicacredentials', $bindpw ? $bindpw : $REPLBINDPW);
  $entry->setValues('nsds5replicabindmethod', 'simple');
  $entry->setValues('nsds5replicaroot', $nsuffix);
  $entry->setValues('nsds5replicaupdateschedule', '0000-2359 0123456');
  $entry->setValues('description', "me to ${othhost}$othport");
  $entry->setValues('nsds5replicatransportinfo', 'SSL') if ($othsslport);
  $entry->setValues('nsDS5ReplicatedAttributeList', $fractional) if ($fractional);
  $self->add($entry);
  $entry = $self->waitForEntry($dn);
  $rc = $self->getErrorCode();
  if (!$rc && $entry) {
	$self->{$nsuffix}{$repoth->toString()} = $dn;
	if (!$self->{$nsuffix}{type} && $chain) { # a master
	  $self->setupChainingFarm($suffix, $binddn, 0, $bindpw);
	}
	if ($repoth->{$nsuffix}{type} == $LEAF_TYPE && $chain) {
	  $repoth->setupConsumerChainOnUpdate($suffix, 0, $binddn, $bindpw, $self->toLDAPURL());
	} elsif ($repoth->{$nsuffix}{type} == $HUB_TYPE && $chain) {
	  $repoth->setupConsumerChainOnUpdate($suffix, 1, $binddn, $bindpw, $self->toLDAPURL());
	}
  }

  return $dn;
}

sub stopReplication {
  my ($self, $agmtdn, $rc) = @_;
  my %mod = ( nsds5replicaupdateschedule => { r => [ '2358-2359 0' ] });
  ldap_modify_s($self->{ld}, $agmtdn, \%mod);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't stop replication to " . $agmtdn . ": $rc: " . $self->getErrorString(), "\n";
  }
  return $rc;
}

sub findAgreementDNs {
  my ($self, $filt, @attrs, $rc) = @_;
  my $realfilt;
  if ($filt) {
	$realfilt = "(&(objectclass=nsds5ReplicationAgreement)$filt)";
  } else {
	$realfilt = "(objectclass=nsds5ReplicationAgreement)";
  }
  @attrs = qw(cn) if (! @attrs);
  my @retdns;
  my $ent = $self->search("cn=mapping tree,cn=config", "sub", $realfilt, 0, @attrs);
  while ($ent) {
	push @retdns, $ent->getDN();
	$ent = $self->nextEntry();
  }
  return @retdns;
}

sub getReplStatus {
  my ($self, $agmtdn, $rc) = @_;
  my @attrlist = qw(cn nsds5BeginReplicaRefresh nsds5replicaUpdateInProgress
					nsds5ReplicaLastInitStatus nsds5ReplicaLastInitStart
				    nsds5ReplicaLastInitEnd nsds5replicaReapActive
				    nsds5replicaLastUpdateStart nsds5replicaLastUpdateEnd
				    nsds5replicaChangesSentSinceStartup nsds5replicaLastUpdateStatus
				    nsds5replicaChangesSkippedSinceStartup nsds5ReplicaHost
				    nsds5ReplicaPort);
  my $entry = $self->search($agmtdn, "base", "(objectclass=*)", 0, @attrlist);
  $rc = $self->getErrorCode();
  if (! $entry || $rc) {
	print "Error reading status from agreement $agmtdn: $rc\n";
	print "Server down\n" if ($rc == 81);
  } else {
	my $cn = $entry->getValues("cn");
	my $rh = $entry->getValues("nsds5ReplicaHost");
	my $rp = $entry->getValues("nsds5ReplicaPort");
	my $retstr = "Status for " . $self->toString() . " agmt $cn:$rh:$rp\n";
	$retstr .= "\tUpdate In Progress  : " . $entry->getValues("nsds5replicaUpdateInProgress") . "\n";
	$retstr .= "\tLast Update Start   : " . $entry->getValues("nsds5replicaLastUpdateStart") . "\n";
	$retstr .= "\tLast Update End     : " . $entry->getValues("nsds5replicaLastUpdateEnd") . "\n";
	$retstr .= "\tNum. Changes Sent   : " . $entry->getValues("nsds5replicaChangesSentSinceStartup") . "\n";
	$retstr .= "\tNum. Changes Skipped: " . $entry->getValues("nsds5replicaChangesSkippedSinceStartup") . "\n";
	$retstr .= "\tLast Update Status  : " . $entry->getValues("nsds5replicaLastUpdateStatus") . "\n";
	$retstr .= "\tInit in Progress    : " . $entry->getValues("nsds5BeginReplicaRefresh") . "\n";
	$retstr .= "\tLast Init Start     : " . $entry->getValues("nsds5ReplicaLastInitStart") . "\n";
	$retstr .= "\tLast Init End       : " . $entry->getValues("nsds5ReplicaLastInitEnd") . "\n";
	$retstr .= "\tLast Init Status    : " . $entry->getValues("nsds5ReplicaLastInitStatus") . "\n";
	$retstr .= "\tReap In Progress    : " . $entry->getValues("nsds5replicaReapActive") . "\n";
	return $retstr;
  }

  return "";
}

sub restartReplication {
  my ($self, $agmtdn, $rc) = @_;
  my %mod = ( nsds5replicaupdateschedule => { r => [ '0000-2359 0123456' ] });
  ldap_modify_s($self->{ld}, $agmtdn, \%mod);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't restart replication to " . $agmtdn . ": $rc: " . $self->getErrorString(), "\n";
  }
  return $rc;
}

sub startReplication_async {
  my ($self, $agmtdn, $rc) = @_;
  my %mod = ( nsds5BeginReplicaRefresh => { a => [ 'start' ] });
  ldap_modify_s($self->{ld}, $agmtdn, \%mod);
  if ($rc = $self->getErrorCode()) {
	print "Couldn't add value to " . $agmtdn . ": $rc: " . $self->getErrorString(), "\n";
  }
  return $rc;
}

# returns an array - first element is done/not done, 2nd is no error/has error
sub checkReplInit {
  my ($self, $agmtdn, $rc) = @_;
  my $done = 0;
  my $haserror = 0;
  my @attrlist = qw(nsds5BeginReplicaRefresh nsds5replicaUpdateInProgress
					nsds5ReplicaLastInitStatus nsds5ReplicaLastInitStart
				    nsds5ReplicaLastInitEnd);
  my $entry = $self->search($agmtdn, "base", "(objectclass=*)", 0, @attrlist);
  $rc = $self->getErrorCode();
  if (! $entry || $rc) {
	print "Error reading status from agreement $agmtdn: $rc\n";
	print "Server down\n" if ($rc == 81);
	$haserror = $rc;
  } else {
	my $refresh = $entry->getValues("nsds5BeginReplicaRefresh");
	my $inprogress = $entry->getValues("nsds5replicaUpdateInProgress");
	my $status = $entry->getValues("nsds5ReplicaLastInitStatus");
	my $start = $entry->getValues("nsds5ReplicaLastInitStart");
	my $end = $entry->getValues("nsds5ReplicaLastInitEnd");
	if (! $refresh) { # done with operation, check status
	  if ($status =~ /replica busy/) {
		print "Update failed - replica busy - status $status\n";
		$done = 1;
		$haserror = 2;
	  } elsif ($status =~ /Total update succeeded/) {
		print "Update succeeded: status $status\n";
		$done = 1;
	  } elsif (lc($inprogress) eq 'true') {
		print "Update in progress yet not in progress: status $status\n";
	  } else {
		print "Update failed: status $status\n";
		$haserror = 1 ;
	  }
	} else {
	  print "Update in progress: status $status\n";
	}
  }

  return ($done, $haserror);
}

sub waitForReplInit {
  my ($self, $agmtdn) = @_;
  my $done = 0;
  my $haserror = 0;
  while (! $done && ! $haserror) {
	sleep 1;  # give it a few seconds to get going
	($done, $haserror) = $self->checkReplInit($agmtdn);
  }

  return $haserror;
}

sub startReplication {
  my ($self, $agmtdn) = @_;
  my $rc = $self->startReplication_async($agmtdn);
  if (!$rc) {
	$rc = $self->waitForReplInit($agmtdn);
	if ($rc == 2) { # replica busy - retry
	  $rc = $self->startReplication($agmtdn);
	}
  }

  return $rc;
}

# returns a hash ref
# ruv->{gen} is the generation
# ruv->{1} through ruv->{N} are hash refs - the number (1-N) is the replica ID
#   ->{url} is the purl
#   ->{min} is the min csn
#   ->{max} is the max csn
#   ->{lastmod} is the last modified timestamp
# example ruv attr:
# nsds50ruv: {replicageneration} 3b0ebc7f000000010000
# nsds50ruv: {replica 1 ldap://myhost:51010} 3b0ebc9f000000010000 3b0ebef700000
#  0010000
# nsruvReplicaLastModified: {replica 1 ldap://myhost:51010} 292398402093
# if the tryrepl flag is true, if getting the ruv from the suffix fails, try getting
# the ruv from the cn=replica entry
sub getRUV {
  my ($self, $suffix, $tryrepl, $verbose, $rc) = @_;
  my $uuid = "ffffffff-ffffffff-ffffffff-ffffffff";
  my $entry = $self->search("$suffix", "one", "(&(nsuniqueid=$uuid)(objectclass=nsTombstone))",
						   0, qw(nsds50ruv nsruvReplicaLastModified));
  if (!$entry || !$entry->getValues("nsds50ruv")) {
	print "Error: could not get ruv from $self->{host}:$self->{port} for $suffix: ",
			$self->getErrorCode(), "\n" if ($verbose);
	if ($tryrepl) {
	  $entry = $self->search("cn=replica,cn=\"$suffix\",cn=mapping tree,cn=config", "base",
							 "(objectclass=*)", 0, qw(nsds50ruv));
	  if (!$entry || !$entry->getValues("nsds50ruv")) {
		print "Error: could not get cn=replica ruv from $self->{host}:$self->{port} for $suffix: ",
				$self->getErrorCode(), "\n" if ($verbose);
		return 0;
	  }
	} else {
	  return 0;
	}
  }
  my $ruv = {};
  for ($entry->getValues("nsds50ruv")) {
	if (/\{replicageneration\}\s+(\w+)/) {
	  $ruv->{gen} = $1;
	} elsif (/\{replica\s+(\d+)\s+(.+?)\}\s*(\w*)\s*(\w*)/) {
	  $ruv->{$1}->{url} = $2;
	  $ruv->{$1}->{min} = $3;
	  $ruv->{$1}->{max} = $4;
	} else {
	  print "unknown ruv element: $_\n";
	}
  }
  for ($entry->getValues("nsruvReplicaLastModified")) {
	if (/\{replica\s+(\d+)\s+(.+?)\}\s*(\w*)/) {
	  $ruv->{$1}->{lastmod} = hex($3); # convert to integer
	} else {
	  print "unknown ruv lastmod element: $_\n";
	}
  }
  return $ruv;
}

sub printRUV {
  my $ruv = shift;
  if (!$ruv) {
	print "ruv is NULL\n";
	return;
  }
  print "gen ", $ruv->{gen}, "\n";
  foreach my $ii ( keys %$ruv ) {
	next if ( $ii eq "gen" );
	print "  $ii ", $ruv->{$ii}->{url}, " ",
	  $ruv->{$ii}->{min}, " ", $ruv->{$ii}->{max}, " ",
	  $ruv->{$ii}->{lastmod}, "\n";
  }
}

# takes a CSN string and returns an array of ts, seq, rid, subseq
sub parseCSN {
  my $str = shift;
  my @csn;
  if ($str =~ /(.{8})(.{4})(.{4})(.{4})/) {
	@csn = (hex($1), hex($2), hex($3), hex($4));
  }

  return @csn;
}

# takes an array of hexadecimal string and returns an array of refs to arrays of 4 integers
sub parseCSNs {
  my @ret;
  for (@_) {
	# if someone knows how to do this with unpack, please do!
	my @csn = parseCSN($_);
	push @ret, \@csn;
  }

  return @ret;
}

sub getTSDiff {
 my ($ts1, $ts2) = @_;
 my $diff = $ts1 - $ts2;
 my $diffstr = "plus ";
 if ($diff < 0) {
   $diff = 0 - $diff;
   $diffstr = "minus ";
 }
 if (!$diff) {
   return "no difference ";
 }

 # diff is in seconds - lets format as weeks, days, etc.
 my $oneminute = 60;
 my $onehour = $oneminute * 60;
 my $oneday = $onehour * 24;
 my $oneweek = $oneday * 7;

 my $n = int($diff / $oneweek);
 $diffstr .= "$n wk " if ($n);
 $diff -= $n*$oneweek;

 $n = int($diff / $oneday);
 $diffstr .= "$n dy " if ($n);
 $diff -= $n*$oneday;

 $n = int($diff / $onehour);
 $diffstr .= "$n hr " if ($n);
 $diff -= $n*$onehour;

 $n = int($diff / $oneminute);
 $diffstr .= "$n min " if ($n);
 $diff -= $n*$oneminute;

 $diffstr .= "$diff sec " if ($diff);

 return $diffstr;
}

sub printTSDiff {
  print &getTSDiff(@_), "\n";
} 

sub printTS {
  for (@_) {
	print scalar(localtime($_)), "\n";
  }
}

sub compareCSNs {
  my ($csn1, $csn2) = @_;
  return 1 if (!$csn1 && !$csn2); # both null, so equal
  if (!$csn1) { print "csn1 is NULL\n"; return 0; }
  if (!$csn2) { print "csn2 is NULL\n"; return 0; }

  my @ary = &parseCSNs(@_);
  my $equal = 1;

  my $tsdiff = $ary[0]->[0] - $ary[1]->[0];
  printTSDiff($ary[0]->[0], $ary[1]->[0]) if ($tsdiff);
  $equal = 0 if ($tsdiff);

  my $seqdiff = $ary[0]->[1] - $ary[1]->[1];
  print "seq diff $seqdiff\n" if ($seqdiff);
  $equal = 0 if ($seqdiff);

  my $riddiff = $ary[0]->[2] - $ary[1]->[2];
  print "rid diff $riddiff\n" if ($riddiff);
  $equal = 0 if ($riddiff);

  my $subseqdiff = $ary[0]->[3] - $ary[1]->[3];
  print "subseq diff $subseqdiff\n" if ($subseqdiff);
  $equal = 0 if ($subseqdiff);

  return $equal;
}

# returns
# 1 if ruvs are equal
# 0 otherwise
sub compareRUVs {
  my ($ruv1, $ruv2) = @_;
  return 1 if ($ruv1 == $ruv2);
  return 0 if (!$ruv1 || !$ruv2);
  my $ret = &compareCSNs($ruv1->{gen}, $ruv2->{gen});
  print "replica generation differs\n" unless($ret);
  for (my $ii = 1; $ruv1->{$ii}; ++$ii) {
	my $el1 = $ruv1->{$ii};
	my $el2 = $ruv2->{$ii};
	print "mincsns differ\n" unless ($ret = &compareCSNs($el1->{min}, $el2->{min}));
	print "maxcsns differ\n" unless ($ret = &compareCSNs($el1->{max}, $el2->{max}));
  }

  return $ret;
}

sub getCgiContentAndLength {
  my $args = shift;
  my $escapechars = "^a-zA-Z0-9"; # escape all non alphanum chars
  my $content = "";
  my $firsttime = 1;
  while (my ($kk, $vv) = each %{$args}) {
	if ($firsttime) {
	  $firsttime = 0;
	} else {
	  $content = $content . "&";
	}
	$content = $content . $kk . "=" . uri_escape($vv, $escapechars);
  }
  my $length = length($content);

  return ($content, $length);
}

# fakes out the ds_create program into thinking it is getting cgi input
sub cgiFake {
  my ($sroot, $verbose, $prog, $args) = @_;
  # construct content string
  my ($content, $length) = &getCgiContentAndLength($args);

  # setup CGI environment
  $ENV{REQUEST_METHOD} = "POST";
  $ENV{NETSITE_ROOT} = $sroot;
  $ENV{CONTENT_LENGTH} = $length;

#  print "content = $content\n";

  # open the program
  my $curdir = getcwd();
  my $dir = dirname($prog);
  my $exe = basename($prog);
  chdir $dir;
  my $input = gensym();
  my $output = gensym();
  my $pid = open2($input, $output, "./$exe");
  sleep(1); # allow prog to init stdin read buffers
  print $output $content, "\n";
  CORE::close $output;

  if ($?) {
	print "Warning: $prog returned code $? and $!\n";
  }

  my $exitCode = 1;
  my @lines;
  while (<$input>) {
	print $_ if ($verbose);
	push @lines, $_;
	if (/^NMC_Status:\s*(\d+)/) {
	  $exitCode = $1;
	  last;
	}
  }
  CORE::close $input;
  chdir $curdir;

  if ($exitCode) {
	print "CGI $prog failed with $exitCode: here is the output:\n";
	map { print $_ } @lines;
  }

  if ($exitCode != 0) {
	print "Error: could not run $prog: $exitCode\n";
	return $exitCode;
  }

  return 0;
}

sub cgiPost {
  my ($host, $port, $user, $pwd, $url, $verbose, $args) = @_;
  # construct auth string
  my $auth = encode_base64($user . ":" . $pwd);
  $auth =~ s/\n//g;
  # construct content string
  my ($content, $length) = &getCgiContentAndLength($args);

  # construct header
  my $header =
"POST $url HTTP/1.0\n" .
"Host: $host:$port\n" .
"Connection: Keep-Alive\n" .
"User-Agent: Netscape-Console/5.01\n" .
"Accept-Language: en\n" .
"Authorization: Basic $auth\n" .
"Content-Length: $length\n" .
"Content-Type: application/x-www-form-urlencoded\n" .
"Content-Transfer-Encoding: 7bit\n";

  print "header = $header\n" if ($verbose);
  print "content = $content\n" if ($verbose);

  # open the connection
  my ($iaddr, $paddr, $proto, $line);

  my $ii = 0;

  $iaddr = inet_aton($host) or die "could not find host $host for http connection: $!";
#  print "iaddr = $iaddr\n";
  $paddr = sockaddr_in($port, $iaddr);
#  print "paddr = $paddr\n";

  $proto = getprotobyname('tcp');
#  print "proto = $proto\n";
  socket(SOCK, PF_INET, SOCK_STREAM, $proto) or die "could not open socket for $host:$port: $!";
#  print "proto = $proto\n";
  CORE::connect(SOCK, $paddr) or die "could not connect to http server $host:$port: $!";

  select SOCK ; $| = 1; select STDOUT; $| = 1;
  #print SOCK "GET / HTTP/1.0\n\n";
  #print SOCK <<EOF;
  #GET / HTTP/1.0
  #
  #EOF
  #print "after sending, now receiving...\n";
  #read(SOCK, $line, 12);
  #print $line, "\n";
  #while (<SOCK>) {
  #  print $_;
  #}

  print SOCK $header, "\n", $content, "\n\n";
  print "after sending, now receiving...\n" if ($verbose);

  my $exitCode = 1;
  my @lines;
  while (<SOCK>) {
	print $_ if ($verbose);
	push @lines, $_;
	if (/^NMC_Status:\s*(\d+)/) {
	  $exitCode = $1;
	  last;
	}
  }
  CORE::close(SOCK);
  if ($exitCode) {
	print "CGI failed with $exitCode: here is the output:\n";
	map { print $_ } @lines;
  }

  return $exitCode;
}

# The general idea here is to use the .inf file method if the server is local, and use
# the CGI method if the server is remote
# pass in a ref to a hash table e.g. like this:
# createInstance({ sroot => "/path", newhost => 'hostname', ....});
# If the sroot is given, it is assumed it is local
#
# required parameters are:
#	newrootpw - new directory manager password
#	newsuffix - the default suffix for the new server
#	newinst - the new instance name (server id)
#	sroot OR cfgdshost, cfgdsport, cfgdsuser, cfgdspwd
#	sroot AND cfgdsuser, cfgdspwd - for remote, cfgdshost and port can be looked up
#	cfgdspwd - this is required for creating a remote directory server
#
# optional parameters are:
#	newhost - default is the localhost
#	newport - default is 389 (must be root or creating remote)
#	newrootdn - default is cn=directory manager
#	newuserid (unix) - default is calculated or looked up
#
# You cannot create a local directory server if the server root is not given or if the
# server root cannot be looked up from the configds.
#
# Returns a new NDSAdmin object if successful or null if not
sub createInstance {
  my $arg = shift;
  my $status = shift; # ref to a scalar

  ${$status} = 0;

  my %aliases;
  my $myhost = getFQDN(0, \%aliases);
  # if newhost is not set, it will get set to FQDN
  # if newhost is set, but not FQDN, it will get set to FQDN
  # if newhost is already FQDN, it will be returned unchanged
  $arg->{newhost} = getFQDN($arg->{newhost});
  my $isLocal;
  my $verbose = $arg->{verbose};

  if (!$arg->{newhost}) { # no host given, default to local
	$arg->{newhost} = $myhost;
	$isLocal = 1;
  } elsif ($arg->{newhost} eq 'localhost') { # force localhost
	$isLocal = 1;
  } elsif ($arg->{newhost} eq $myhost) { # newhost is localhost
	$isLocal = 1;
  } elsif ($arg->{newhost} =~ /^$myhost\./) { # they match
	$isLocal = 1;
  } elsif ($aliases{$arg->{newhost}}) { # newhost is one of the aliases of localhost
	$isLocal = 1;
  } else {
	$isLocal = 0;
  }

  my $cfgdn = "o=NetscapeRoot";
  if (!$arg->{cfgdshost} || !$arg->{cfgdsport}) {
	if (-f "$arg->{sroot}/shared/config/dbswitch.conf") {
	  open(DBSWITCH, "$arg->{sroot}/shared/config/dbswitch.conf");
	  while (<DBSWITCH>) {
		chop;
		if (/^directory\s+default\s+/) {
		  my $h = ldap_url_parse($'); # ' fix font lock
		  $arg->{cfgdshost} = $h->{host};
		  $arg->{cfgdsport} = $h->{port};
		  $cfgdn = $h->{dn};
		}
	  }
	  close DBSWITCH;
	}
  }

  my $asport;
  # first, see if $cfguser is a full DN or not - if not, look up the DN
  my $cfgconn = new NDSAdmin($arg->{cfgdshost}, $arg->{cfgdsport});
  print "Error: could not open ldap connection to $arg->{cfgdshost}:$arg->{cfgdsport}\n"
	if (!$cfgconn);
  if ($arg->{cfgdspwd} && (!$arg->{cfgdsuser} || ($arg->{cfgdsuser} !~ /\=/))) {
#	my $ent = $cfgconn->search("o=NetscapeRoot", "sub", "(uid=$cfgdsuser)", 0, qw(dn));
#	if (!$ent || (my $rc = $cfgconn->getErrorCode())) {
#	  die "Error: could not find $cfgdsuser in $cfgdshost:$cfgdsport: error $rc";
#	}
	if ($cfgconn && $arg->{cfgdsuser}) {
	  my $ent = $cfgconn->search("o=NetscapeRoot", "sub", "(uid=$arg->{cfgdsuser})",
								 0, qw(dn));
	  $arg->{cfgdsuser} = $ent->getDN();
	} elsif ($arg->{sroot} && -f "$arg->{sroot}/shared/config/ldap.conf") {
	  open(LDAPCONF, "$arg->{sroot}/shared/config/ldap.conf");
	  while (<LDAPCONF>) {
		chop;
		if (/^admnm\s+/) {
		  $arg->{cfgdsuser} = $'; # ' fix font lock
		}
	  }
	  close LDAPCONF;
	} elsif ($arg->{cfgdsuser}) {
	  $arg->{cfgdsuser} =
		"uid=$arg->{cfgdsuser}, ou=Administrators, ou=TopologyManagement, o=NetscapeRoot";
	}

	# next, bind to the cfg ds as the cfg user
	if ($cfgconn && $arg->{cfgdsuser} && $arg->{cfgdspwd}) {
	  $cfgconn->simpleAuth($arg->{cfgdsuser}, $arg->{cfgdspwd}) or
		print "Error: could not bind to $arg->{cfgdshost}:$arg->{cfgdsport} as " .
		  "$arg->{cfgdsuser}:$arg->{cfgdspwd}: " . $cfgconn->getErrorCode(), "\n";
	}
  }

  # look up the server root - if we are installing on the local machine, and
  # the server root was not given, look up the server root for the config ds
  # and use it's server root as our server root
  if ($cfgconn && !$arg->{sroot} && $isLocal) {
	my $dn = "cn=config";
	my $ent = $cfgconn->search($dn, "base", "(objectclass=*)",
							   0, qw(nsslapd-instancedir));
	if ($ent) {
	  ($arg->{sroot} = $ent->getValues('nsslapd-instancedir')) =~ s|/[^/]+$||;
	}
  }

  if ($isLocal && !$arg->{admin_domain}) {
	if ($arg->{sroot} && -f "$arg->{sroot}/shared/config/ds.conf") {
	  open(DSCONF, "$arg->{sroot}/shared/config/ds.conf");
	  while (<DSCONF>) {
		chop;
		if (/^AdminDomain:\s*/) {
		  $arg->{admin_domain} = $'; # ' fix font lock
		}
	  }
	  close DSCONF;
	}
  }

  if ($cfgconn) {
	# look up the admin server port on the newhost
	my $dn = $cfgdn;
	if ($arg->{admin_domain}) {
	  $dn = "ou=$arg->{admin_domain}, $dn";
	  if ($arg->{newhost}) {
		$dn = "cn=$arg->{newhost}, $dn";
	  }
	}
	my $filter = "(&(objectclass=nsAdminServer)(serverHostName=$arg->{newhost})";
	$filter = $filter . "(serverRoot=$arg->{sroot})" if ($arg->{sroot});
	$filter = $filter . ")";
	my $asent = $cfgconn->search($dn, "sub", $filter,
								 0, qw(serverRoot));
	if ($asent) {
	  if (!$arg->{sroot}) {
		$arg->{sroot} = $asent->getValues('serverRoot');
	  }

	  if (!$arg->{admin_domain}) {
		@rdns = ldap_explode_dn($asent->getDN(), 1);
		$arg->{admin_domain} = $rdns[-2];
	  }

	  $dn = "cn=configuration, " . $asent->getDN();
	  $asent = $cfgconn->search($dn, "base", "(objectclass=*)",
								0, qw(nsServerPort nsSuiteSpotUser));
	  if ($asent) {
		$asport = $asent->getValues("nsServerPort");
		if (! $arg->{newuserid}) {
		  $arg->{newuserid} = $asent->getValues("nsSuiteSpotUser");
		}
	  }
	}
	$cfgconn->close();
  }

  if (!$arg->{newuserid} && $arg->{sroot} && -f "$arg->{sroot}/shared/config/ssusers.conf") {
	open(SSUSERS, "$arg->{sroot}/shared/config/ssusers.conf");
	while (<SSUSERS>) {
	  chop;
	  if (/^SuiteSpotUser\s+/) {
		$arg->{newuserid} = $'; # ' fix font lock
	  }
	}
	close SSUSERS;
  } elsif (!$arg->{newuserid}) {
	# assume running locally
	if (! $isNT) {
	  $arg->{newuserid} = getpwuid($>);
	} else {
	  $arg->{newuserid} = "nobody";
	}
	if ($arg->{newuserid} eq "root") {
	  $arg->{newuserid} = "nobody";
	}
  }

  $arg->{newport} = 389 if (!$arg->{newport});
  $arg->{newrootdn} = "cn=directory manager" if (!$arg->{newrootdn});
  $arg->{cfgdspwd} = "dummy" if ($isLocal && !$arg->{cfgdspwd});
  $arg->{cfgdshost} = $arg->{newhost} if ($isLocal && !$arg->{cfgdshost});
  $arg->{cfgdsport} = 55555 if ($isLocal && !$arg->{cfgdsport});
  $arg->{newsuffix} = defaultsuffix($arg->{newhost}) if (!$arg->{newsuffix});
  $arg->{admin_domain} = defaultadmindomain($arg->{newhost}) if (!$arg->{admin_domain});

  # check for missing required arguments
  my $missing = 0;
  for (qw(cfgdshost cfgdsport cfgdsuser cfgdspwd newhost newport
		  newrootdn newrootpw newinst newsuffix admin_domain)) {
	if (!$arg->{$_}) {
	  print "Error: missing required argument $_\n";
	  $missing = 1;
	}
  }

  if (!$isLocal && !$asport) {
	print "Error: missing required argument admin server port\n";
	$missing = 1;
  }

  if ($isLocal && !$arg->{sroot}) {
	print "Error: missing required argument sroot\n";
  }

  if ($missing) {
	print "Error: cannot create new instance\n";
	return 0;
  }

  # see if server already exists
  my $newconn = new NDSAdmin($arg->{newhost}, $arg->{newport},
							$arg->{newrootdn}, $arg->{newrootpw});
  if ($newconn) {
	$newconn->{isLocal} = $isLocal;
	$newconn->{asport} = $asport;
	$newconn->{cfgdsuser} = $arg->{cfgdsuser};
	$newconn->{cfgdspwd} = $arg->{cfgdspwd};
	print "Warning: server already exists: ", $newconn->toString(),
		" could not create new instance\n";
	${$status} = 1;
	return $newconn;
  }

  # next, construct a hash table with our arguments
  my %cgiargs = (
	cfg_sspt_uid => $arg->{cfgdsuser},
	cfg_sspt_uid_pw => $arg->{cfgdspwd},
	servname => $arg->{newhost},
	servport => $arg->{newport},
	rootdn => $arg->{newrootdn},
	rootpw => $arg->{newrootpw},
	servid => $arg->{newinst},
	suffix => $arg->{newsuffix},
	servuser => $arg->{newuserid},
	ldap_url => "ldap://$arg->{cfgdshost}:$arg->{cfgdsport}/$cfgdn",
	admin_domain => $arg->{admin_domain},
	start_server => 1
  );
  my $rc;
  if (!$isLocal) {
	$rc = &cgiPost($arg->{newhost}, $asport, $arg->{cfgdsuser},
				   $arg->{cfgdspwd}, "/slapd/Tasks/Operation/Create", $verbose,
				   \%cgiargs);
  } else {
	$rc = &cgiFake($arg->{sroot}, $verbose,
				   $arg->{sroot} . "/bin/slapd/admin/bin/ds_create",
				   \%cgiargs);
  }

  if (!$rc) { # success - try to create a new NDSAdmin
	$newconn = new NDSAdmin($arg->{newhost}, $arg->{newport}, $arg->{newrootdn},
						   $arg->{newrootpw});
	if ($newconn) {
	  $newconn->{isLocal} = $isLocal;
	  $newconn->{asport} = $asport;
	  $newconn->{cfgdsuser} = $arg->{cfgdsuser};
	  $newconn->{cfgdspwd} = $arg->{cfgdspwd};
	}
  }

  return $newconn;
}

# removes an instance of directory server
# - removes the instance directory and all sub directories in the file system
# - cleans up the information in the config DS under o=NetscapeRoot
# - removes the registry entries (on Windows)
# - closes the connection to the server
sub removeInstance {
  my ($self, $verbose) = @_;
  # construct a hash table with our arguments
  my %cgiargs = (
	InstanceName => "slapd-" . $self->{inst}
  );
  print "closing server ", $self->toString(), "\n" if ($verbose);
  $self->close();
  if (!$self->{isLocal} && $self->{asport}) {
	print "removing remote server ", $self->toString(), "\n" if ($verbose);
	my $rc = &cgiPost($self->{host}, $self->{asport}, $self->{cfgdsuser},
					  $self->{cfgdspwd},
					  "/slapd-$self->{inst}/Tasks/Operation/Remove",
					  $verbose, \%cgiargs);
	print "removed remote server ", $self->toString(), " rc = $rc\n" if ($verbose);
  } else {
	print "removing local server ", $self->toString(), "\n" if ($verbose);
	$ENV{SERVER_NAMES} = "slapd-" . $self->{inst};
	my $rc = &cgiFake($self->{sroot}, $verbose,
					  $self->{sroot} . "/bin/slapd/admin/bin/ds_remove",
					  \%cgiargs);
	print "removed local server ", $self->toString(), " rc = $rc\n" if ($verbose);
  }

  return $rc;
}

# removes an instance of directory server
# - removes the instance directory and all sub directories in the file system
# - cleans up the information in the config DS under o=NetscapeRoot
# - removes the registry entries (on Windows)
# - closes the connection to the server
sub removeOtherInstance {
  my ($cfgdsconn, $inst, $verbose) = @_;
  # construct a hash table with our arguments
  my %cgiargs = (
	InstanceName => "slapd-" . $inst
  );
  my $id;
  if (ref($cfgdsconn) eq 'NDSAdmin') {
	$id = $cfgdsconn->toString();
  } else {
	$id = $cfgdsconn->{sroot};
  }
  if (!$cfgdsconn->{isLocal} && $cfgdsconn->{asport}) {
	print "removing remote server $inst on $id\n" if ($verbose);
	my $rc = &cgiPost($cfgdsconn->{host}, $cfgdsconn->{asport}, $cfgdsconn->{cfgdsuser},
					  $cfgdsconn->{cfgdspwd},
					  "/slapd-$inst/Tasks/Operation/Remove",
					  $verbose, \%cgiargs);
	print "removed remote server $inst on $id rc = $rc\n" if ($verbose);
  } else {
	print "removing local server $inst on $id\n" if ($verbose);
	$ENV{SERVER_NAMES} = "slapd-" . $inst;
	my $rc = &cgiFake($cfgdsconn->{sroot}, $verbose,
					  $cfgdsconn->{sroot} . "/bin/slapd/admin/bin/ds_remove",
					  \%cgiargs);
	print "removed local server $inst on $id rc = $rc\n" if ($verbose);
  }

  return $rc;
}

# setup everything needed to enable replication for a given suffix
# argument - a hashref with the following fields
#	suffix - suffix to set up for replication
# optional fields and their default values
#	bename - name of backend corresponding to suffix
#	parent - parent suffix if suffix is a sub-suffix - default is undef
#	ro - put database in read only mode - default is read write
#	type - replica type ($MASTER_TYPE, $HUB_TYPE, $LEAF_TYPE) - default is master
#	legacy - make this replica a legacy consumer - default is no
#	binddn - bind DN of the replication manager user - default is $REPLBINDDN
#	bindcn - bind CN of the replication manager user - default is $REPLBINDCN
#	bindpw - bind password of the repl manager - default is $REPLBINDPW
#	log - if true, replication logging is turned on - default false
#	id - the replica ID - default is an auto incremented number
sub replicaSetupAll {
  my $self = shift;
  my $repArgs = shift;
  $repArgs->{type} = $MASTER_TYPE if (!$repArgs->{type});
  $self->addSuffix($repArgs->{suffix});
  if (!$repArgs->{bename}) {
	  @beents = getBackendsForSuffix($repArgs->{suffix}, qw(cn));
	  # just use first one
	  $repArgs->{bename} = $beents[0]->getValues("cn");
  }
  $self->setDBReadOnly("on", $repArgs->{bename}) if ($repArgs->{ro});
  $self->enableReplLogging() if ($repArgs->{log});
  $self->setupChangelog() if ($repArgs->{type} != $LEAF_TYPE);
  $self->setupReplBindDN($repArgs->{binddn}, $repArgs->{bindcn}, $repArgs->{bindpw});
  $self->setDBReadOnly("off", $repArgs->{bename}) if ($repArgs->{ro});
  $self->setupReplica($repArgs);
  $self->setDBReadOnly("on", $repArgs->{bename}) if ($repArgs->{ro});
  $self->setupLegacyConsumer($repArgs->{binddn}, $repArgs->{bindpw}) if ($repArgs->{legacy});
}

# pass this sub two hashrefs - the first one is a hashref suitable to create
# a new instance - see createInstance for more details
# the second is a hashref suitable for replicaSetupAll - see replicaSetupAll
sub createAndSetupReplica {
  my ($createArgs, $repArgs) = @_;

  my $conn = createInstance($createArgs);
  if (!$conn) {
	print "Error: could not create server %{$createArgs}\n";
	return 0;
  }

  $conn->replicaSetupAll($repArgs);

  return $conn;
}

sub findSuffixForEntry {
  my ($self, $entrydn) = @_;
  my $entrydnN = normalizeDN($entrydn);
  my @suffixN = ldap_explode_dn($entrydnN, 0);

  # search for the suffix of the entry
  my $done = 0;
  my $suffixdn;
  while (!$suffixdn) {
	my $trysuffix = join(',', @suffixN);
	my $mapent = $self->search('cn=mapping tree, cn=config', 'sub',
							   "(|(cn=$trysuffix)(cn=\"$trysuffix\"))",
							   0, qw(cn));
	my $rc = $self->getErrorCode();
	if ($mapent && !$rc) {
	  $suffixdn = $trysuffix;
	} else {
	  shift @suffixN; # remove 1 rdn and try again
	}
  }

  print "Error: could not find suffix for $entrydn\n" if (!$suffixdn);

  return $suffixdn;
}

# see if the given suffix has a parent suffix
sub findParentSuffix {
  my ($self, $suffix) = @_;
  my @rdns = ldap_explode_dn($suffix, 0);
  my $nsuffix = normalizeDN($suffix);
  my @nrdns = ldap_explode_dn($nsuffix, 0);
  shift @rdns;
  shift @nrdns;
  return 0 if (!@rdns);

  do {
	$suffix = join(',', @rdns);
	$nsuffix = join(',', @nrdns);
	my $mapent = $self->search('cn=mapping tree, cn=config', 'sub',
							   "(|(cn=\"$suffix\")(cn=\"$nsuffix\"))",
							   0, qw(cn));
	my $rc = $self->getErrorCode();
	if ($mapent && !$rc) {
	  return $suffix;
	} else {
	  shift @rdns;
	  shift @nrdns;
	}
  } while (@rdns);

  return 0;
}

sub findAndPrintTombstones {
  my ($self, $suffix) = @_;
  my $ent = $self->search($suffix, "sub", "(&(objectclass=nsTombstone)(nscpentrydn=*))");
  if (!$ent) {
	print "No tombstones under $suffix\n";
	return;
  }
  while ($ent) {
	printEntry($ent);
	$ent = $self->nextEntry();
  }
}


1; # obligatory true return from module
