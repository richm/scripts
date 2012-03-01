#!/bin/sh

if [ "$1" -a -d "$1" ] ; then
    secdir="$1"
    echo "Using $1 as sec directory"
    assecdir=$secdir/../admin-serv
else
    secdir=/etc/dirsrv/slapd-localhost
    assecdir=/etc/dirsrv/admin-serv
fi

if [ "$2" ] ; then
    ldapport=$2
else
    ldapport=389
fi

if [ "$3" ] ; then
    ldapsport=$3
else
    ldapsport=636
fi

me=`whoami`
if [ "$me" = "root" ] ; then
    isroot=1
fi

# see if there are already certs and keys
if [ -f $secdir/cert8.db ] ; then
    # look for CA cert
    if certutil -L -d $secdir -n "CA certificate" 2> /dev/null ; then
        echo "Using existing CA certificate"
    else
        echo "No CA certificate found - will create new one"
        needCA=1
    fi

    # look for server cert
    if certutil -L -d $secdir -n "Server-Cert" 2> /dev/null ; then
        echo "Using existing directory Server-Cert"
    else
        echo "No Server Cert found - will create new one"
        needServerCert=1
    fi

    # look for admin server cert
    if certutil -L -d $assecdir -n "server-cert" 2> /dev/null ; then
        echo "Using existing admin server-cert"
    else
        echo "No Admin Server Cert found - will create new one"
        needASCert=1
    fi
    prefix="new-"
    prefixarg="-P $prefix"
else
    needCA=1
    needServerCert=1
    needASCert=1
fi

# get our user and group
if test -n "$isroot" ; then
    uid=`/bin/ls -ald $secdir | awk '{print $3}'`
    gid=`/bin/ls -ald $secdir | awk '{print $4}'`
fi

# 2. Create a password file for your security token password:
if [ -n "$needCA" -o -n "$needServerCert" -o -n "$needASCert" ] ; then
    if [ -f $secdir/pwdfile.txt ] ; then
        echo "Using existing $secdir/pwdfile.txt"
    else
        echo "Creating password file for security token"
        (ps -ef ; w ) | sha1sum | awk '{print $1}' > $secdir/pwdfile.txt
        if test -n "$isroot" ; then
            chown $uid:$gid $secdir/pwdfile.txt
        fi
        chmod 400 $secdir/pwdfile.txt
    fi

# 3. Create a "noise" file for your encryption mechanism: 
    if [ -f $secdir/noise.txt ] ; then
        echo "Using existing $secdir/noise.txt file"
    else
        echo "Creating noise file"
        (w ; ps -ef ; date ) | sha1sum | awk '{print $1}' > $secdir/noise.txt
        if test -n "$isroot" ; then
            chown $uid:$gid $secdir/noise.txt
        fi
        chmod 400 $secdir/noise.txt
    fi

# 4. Create the key3.db and cert8.db databases:
    if [ -z "$prefix" ] ; then
        echo "Creating initial key and cert db"
    else
        echo "Creating new key and cert db"
    fi
    certutil -N $prefixarg -d $secdir -f $secdir/pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid $secdir/${prefix}key3.db $secdir/${prefix}cert8.db
    fi
    chmod 600 $secdir/${prefix}key3.db $secdir/${prefix}cert8.db
fi

if test -n "$needCA" ; then
# 5. Generate the encryption key:
    echo "Creating encryption key for CA"
    certutil -G $prefixarg -d $secdir -z $secdir/noise.txt -f $secdir/pwdfile.txt
# 6. Generate the self-signed certificate: 
    echo "Creating self-signed CA certificate"
# note - the basic constraints flag (-2) is required to generate a real CA cert
# it asks 3 questions that cannot be supplied on the command line
    ( echo y ; echo ; echo y ) | certutil -S $prefixarg -n "CA certificate" -s "cn=CAcert" -x -t "CT,," -m 1000 -v 120 -d $secdir -z $secdir/noise.txt -f $secdir/pwdfile.txt -2
# export the CA cert for use with other apps
    echo Exporting the CA certificate to cacert.asc
    certutil -L $prefixarg -d $secdir -n "CA certificate" -a > $secdir/cacert.asc
fi

if test -n "$MYHOST" ; then
    myhost="$MYHOST"
else
    myhost=`hostname --fqdn`
fi
if test -n "$needServerCert" ; then
# 7. Generate the server certificate:
    echo "Generating server certificate for 389 Directory Server on host $myhost"
    echo Using fully qualified hostname $myhost for the server name in the server cert subject DN
    echo Note: If you do not want to use this hostname, edit this script to change myhost to the
    echo real hostname you want to use
    certutil -S $prefixarg -n "Server-Cert" -s "cn=$myhost,ou=389 Directory Server" -c "CA certificate" -t "u,u,u" -m 1001 -v 120 -d $secdir -z $secdir/noise.txt -f $secdir/pwdfile.txt
fi

if test -n "$needASCert" ; then
# Generate the admin server certificate
    echo Creating the admin server certificate
    certutil -S $prefixarg -n "server-cert" -s "cn=$myhost,ou=389 Administration Server" -c "CA certificate" -t "u,u,u" -m 1002 -v 120 -d $secdir -z $secdir/noise.txt -f $secdir/pwdfile.txt

# export the admin server certificate/private key for import into its key/cert db
    echo Exporting the admin server certificate pk12 file
    pk12util -d $secdir $prefixarg -o $secdir/adminserver.p12 -n server-cert -w $secdir/pwdfile.txt -k $secdir/pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid $secdir/adminserver.p12
    fi
    chmod 400 $secdir/adminserver.p12
fi

# create the pin file
if [ ! -f $secdir/pin.txt ] ; then
    echo Creating pin file for directory server
    pinfile=$secdir/pin.txt
    echo 'Internal (Software) Token:'`cat $secdir/pwdfile.txt` > $pinfile
    if test -n "$isroot" ; then
        chown $uid:$gid $pinfile
    fi
    chmod 400 $pinfile
else
    echo Using existing $secdir/pin.txt
fi

if [ -n "$needCA" -o -n "$needServerCert" -o -n "$needASCert" ] ; then
    if [ -n "$prefix" ] ; then
    # move the old files out of the way
        mv $secdir/cert8.db $secdir/orig-cert8.db
        mv $secdir/key3.db $secdir/orig-key3.db
    # move in the new files - will be used after server restart
        mv $secdir/${prefix}cert8.db $secdir/cert8.db
        mv $secdir/${prefix}key3.db $secdir/key3.db
    fi
fi

# create the admin server key/cert db
if [ ! -f $assecdir/cert8.db ] ; then
    echo Creating key and cert db for admin server
    certutil -N -d $assecdir -f $secdir/pwdfile.txt
    if test -n "$isroot" ; then
        chown $uid:$gid $assecdir/*.db
    fi
    chmod 600 $assecdir/*.db
fi

if test -n "$needASCert" ; then
# import the admin server key/cert
    echo "Importing the admin server key and cert (created above)"
    pk12util -d $assecdir -n server-cert -i $secdir/adminserver.p12 -w $secdir/pwdfile.txt -k $secdir/pwdfile.txt

# import the CA cert to the admin server cert db
    echo Importing the CA certificate from cacert.asc
    certutil -A -d $assecdir -n "CA certificate" -t "CT,," -a -i $secdir/cacert.asc
fi

if [ ! -f $assecdir/password.conf ] ; then
# create the admin server password file
    echo Creating the admin server password file
    echo 'internal:'`cat $secdir/pwdfile.txt` > $assecdir/password.conf
    if test -n "$isroot" ; then
        chown $uid:$gid $assecdir/password.conf
    fi
    chmod 400 $assecdir/password.conf
fi

# tell admin server to use the password file and turn on mod_nss
if [ -f $assecdir/nss.conf ] ; then
    cd $assecdir
    echo Enabling the use of a password file in admin server
    sed -e "s@^NSSPassPhraseDialog .*@NSSPassPhraseDialog file:`pwd`/password.conf@" nss.conf > /tmp/nss.conf && mv /tmp/nss.conf nss.conf
    if test -n "$isroot" ; then
        chown $uid:$gid nss.conf
    fi
    chmod 400 nss.conf
    echo Turning on NSSEngine
    sed -e "s@^NSSEngine off@NSSEngine on@" console.conf > /tmp/console.conf && mv /tmp/console.conf console.conf
    if test -n "$isroot" ; then
        chown $uid:$gid console.conf
    fi
    chmod 600 console.conf
    echo Use ldaps for config ds connections
    sed -e "s@^ldapurl: ldap://$myhost:$ldapport/o=NetscapeRoot@ldapurl: ldaps://$myhost:$ldapsport/o=NetscapeRoot@" adm.conf > /tmp/adm.conf && mv /tmp/adm.conf adm.conf
    if test -n "$isroot" ; then
        chown $uid:$gid adm.conf
    fi
    chmod 600 adm.conf
    cd $secdir
fi

# enable SSL in the directory server
echo "Enabling SSL in the directory server"
if [ -z "$DMPWD" ] ; then
    echo "when prompted, provide the directory manager password"
    echo -n "Password:"
    stty -echo
    read dmpwd
    stty echo
else
    dmpwd="$DMPWD"
fi

ldapmodify -x -h localhost -p $ldapport -D "cn=directory manager" -w "$dmpwd" <<EOF
dn: cn=encryption,cn=config
changetype: modify
replace: nsSSL3
nsSSL3: on
-
replace: nsSSLClientAuth
nsSSLClientAuth: allowed
-
add: nsSSL3Ciphers
nsSSL3Ciphers: -rsa_null_md5,+rsa_rc4_128_md5,+rsa_rc4_40_md5,+rsa_rc2_40_md5,
 +rsa_des_sha,+rsa_fips_des_sha,+rsa_3des_sha,+rsa_fips_3des_sha,+fortezza,
 +fortezza_rc4_128_sha,+fortezza_null,+tls_rsa_export1024_with_rc4_56_sha,
 +tls_rsa_export1024_with_des_cbc_sha

dn: cn=config
changetype: modify
add: nsslapd-security
nsslapd-security: on
-
replace: nsslapd-ssl-check-hostname
nsslapd-ssl-check-hostname: off
-
replace: nsslapd-secureport
nsslapd-secureport: $ldapsport

dn: cn=RSA,cn=encryption,cn=config
changetype: add
objectclass: top
objectclass: nsEncryptionModule
cn: RSA
nsSSLPersonalitySSL: Server-Cert
nsSSLToken: internal (software)
nsSSLActivation: on

EOF

ldapsearch_attrval()
{
    attrname="$1"
    shift
    ldapsearch "$@" $attrname | sed -n '/^'$attrname':/,/^$/ { /^'$attrname':/ { s/^'$attrname': *// ; h ; $ !d}; /^ / { H; $ !d}; /^ /! { x; s/\n //g; p; q}; $ { x; s/\n //g; p; q} }'
}

echo "Enabling SSL in the admin server"
# find the directory server config entry DN
dsdn=`ldapsearch_attrval dn -x -LLL -h localhost -p $ldapport -D "cn=directory manager" -w "$dmpwd" -b o=netscaperoot "(&(objectClass=nsDirectoryServer)(serverhostname=$myhost)(nsserverport=$ldapport))"`
ldapmodify -x -h localhost -p $ldapport -D "cn=directory manager" -w "$dmpwd" <<EOF
dn: $dsdn
changetype: modify
replace: nsServerSecurity
nsServerSecurity: on
-
replace: nsSecureServerPort
nsSecureServerPort: $ldapsport

EOF

# find the admin server config entry DN
asdn=`ldapsearch_attrval dn -x -LLL -h localhost -p $ldapport -D "cn=directory manager" -w "$dmpwd" -b o=netscaperoot "(&(objectClass=nsAdminServer)(serverhostname=$myhost))"`
ldapmodify -x -h localhost -p $ldapport -D "cn=directory manager" -w "$dmpwd" <<EOF
dn: cn=configuration,$asdn
changetype: modify
replace: nsServerSecurity
nsServerSecurity: on

EOF

echo "Done.  You must restart the directory server and the admin server for the changes to take effect."
