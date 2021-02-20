import pythondcspro as pythondcs
from datetime import datetime, timedelta
import configparser, textwrap, argparse
import smtplib
from email.mime.text import MIMEText

def get_dt(dt):
    """Converts ISO timestamp into a datetime object
    Appends zeros to the end if the microseconds part is
    shorter than expected"""
    l = len(dt)
    if '.' in dt and l < 26:
        dt += '0' * (26-l)
    return dcs._fromisoformat(dt)

def test_users(AllUsers, dt, days):
    """Returns a list of user IDs where the last activity timestamp
    is older than days before dt and where the user expiration date
    is after dt"""
    return set( [ u['id'] for u in AllUsers.values() if u['lastActivityTimestamp'] is not None and dt - u['lastActivityTimestamp'] >= timedelta(days=days) and u['expirationDate'] is not None and u['expirationDate'] > dt ] ) if days is not None else set()

def makeemail(emailto, emailcc, emailbcc, emailfrom, subject, body):
    msg = MIMEText('\r\n'.join(textwrap.wrap(body, width=998, break_on_hyphens=False)), 'html')
    msg['From']=emailfrom
    msg['To']=emailto
    msg['Cc']=emailcc
    msg['Bcc']=emailbcc
    msg['Subject']=subject
    return msg

def connectSMTP(cfg):
    if cfg.getboolean('SMTP', 'SSL'):
        server = smtplib.SMTP_SSL(cfg.get('SMTP', 'server'), cfg.getint('SMTP', 'port'))
    else:
        server = smtplib.SMTP(cfg.get('SMTP', 'server'), cfg.getint('SMTP', 'port'))
    try:
        if cfg.getboolean('SMTP', 'auth'):
            server.login(cfg.get('SMTP', 'username'), cfg.get('SMTP', 'password'))
        return server
    except Exception as fail:
        print('Failed to connect to SMTP server:', fail)
        return None

def emailUsers(server, users, emailcc, emailbcc, emailfrom, subject, template):
    for id in users:
        user = AllUsers[id]
        emailto = user['email']
        try: 
            lastlogin=user['lastActivityTimestamp'].strftime("%d-%b-%y")
            days=round( (now - user['lastActivityTimestamp']).total_seconds() / 86400 )
        except TypeError:
            lastlogin = "(Unknown!)"
            days= "(Unknown!)"
        output = template.format(
            name=user["name"],
            lastlogin=lastlogin,
            days=days,
            url=DCSurl,
        )
        print(f"{user['name']}, {emailto}, {lastlogin}, {days}, {subject}")
        msg = makeemail(emailto, emailcc, emailbcc, emailfrom, subject, output)
        server.send_message(msg)

def expireUser(id,dtstr):
    """Sets the expirationDate to a iso datetime string (dtstr) of the user with id via a read-modify-write transaction"""
    user = dcs.get_users(id)
    user['expirationDate'] = dtstr
    _ = dcs.update_user(user)

# Command Line Arguement Parser
parser = argparse.ArgumentParser(description="Checks DCS Server for inactive users")
parser.add_argument("cfg", action='store', metavar='UserChecker.cfg', nargs="?", default='UserChecker.cfg', type=argparse.FileType('r+t'), help="Path to configuration file")
args = parser.parse_args()

# Config File Loader
cfg=configparser.RawConfigParser()
cfgfile=args.cfg
cfg.read_file(cfgfile)

# Timestamp
now = datetime.now()
nowstr = now.isoformat()
print("Time of execution is: ", now)
cfg.set('DATA', 'lastrun', now.strftime('%Y-%m-%d %H:%M:%S.%f'))

# Get Timeouts
try:
    firstLoginDays = cfg.getint('DATA', 'firstlogindays', fallback = 7)
    if firstLoginDays <= 0:
        cfg.set('DATA', 'firstlogindays', 0)
        firstLoginDays = None
except ValueError:
    firstLoginDays = None

try:
    warningDays = cfg.getint('DATA', 'warningdays', fallback = 30)
    if warningDays <= 0:
        cfg.set('DATA', 'warningdays', 0)
        warningDays = None
except ValueError:
    warningDays = None

try:
    expireDays = cfg.getint('DATA', 'expiredays', fallback = 60)
    if expireDays <= 0:
        cfg.set('DATA', 'expiredays', 0)
        expireDays = None
except ValueError:
    expireDays = None

try:
    graceDays = cfg.getint('DATA', 'gracedays', fallback = 7)
    if graceDays <= 0:
        cfg.set('DATA', 'gracedays', 0)
        graceDays = None
except ValueError:
    graceDays = None

# Get Immune user lists from config
immuneUserscfg = cfg.get('DATA', 'immuneUsers')
immuneUsers = set([ username for username in immuneUserscfg.split(',') ] if immuneUserscfg != '' else [])
immuneUsers.discard(None)
cfg.set('DATA', 'immuneUsers', ','.join(sorted(immuneUsers)))
immuneUsers.add(cfg.get('DCS', 'username')) # Make sure the script doesn't lock itself out

# Get email templates and addresses
warnsubject = cfg.get('Email', 'warnsubject', fallback ='DCS account inactivity warning')
try:
    with open(cfg.get('Email', 'warntemplate', fallback = None),"r") as f:
        warnemail = f.read()
except Exception as fail:
    print("Failed to load Warning template:", fail)
    warnemail = None

expiresubject = cfg.get('Email', 'expiresubject', fallback ='DCS account expiry due to inactivity')
try:
    with open(cfg.get('Email', 'expiretemplate', fallback = None),"r") as f:
        expireemail = f.read()
except Exception as fail:
    print("Failed to load Expire template:", fail)
    expireemail = None

emailcc = ','.join( [ppl.strip() for ppl in cfg.get('Email', 'cc', fallback ='').split(',')] )
cfg.set('Email', 'cc', emailcc)

emailbcc = ','.join( [ppl.strip() for ppl in cfg.get('Email', 'bcc', fallback ='').split(',')] )
cfg.set('Email', 'bcc', emailbcc)

emailfrom = cfg.get('Email', 'from')
cfg.set('Email', 'from', emailfrom)


# Get Data from DCS
DCSurl = cfg.get('DCS', 'url')
dcs = pythondcs.DCSSession(DCSurl, cfg.get('DCS', 'username'), cfg.get('DCS', 'password'))
AllUsers = { u["id"].lower() : u for u in dcs.get_users()}

# Convert timestamps to datetime objects and consistent ids
for id in AllUsers:
    user = AllUsers[id]
    user['id'] = id
    lastActivityTimestamp = user['lastActivityTimestamp']
    if lastActivityTimestamp is not None:
        user['lastActivityTimestamp'] = get_dt(lastActivityTimestamp)
    expirationDate = user['expirationDate']
    if expirationDate is not None:
        user['expirationDate'] = get_dt(expirationDate)

for section in ['NeverLoggedIn','Warned','Expired']:
    if not cfg.has_section(section): cfg.add_section(section)

# Find out who needs to be warned and who needs to be expired, and who has never logged in
usersToExpire = test_users(AllUsers,now,expireDays)
usersInGrace = set( [u for u in cfg.options('Warned') if (now - get_dt(cfg.get('Warned',u))) <= timedelta(days=graceDays) ])
usersToWarn = test_users(AllUsers,now,warningDays) - usersToExpire - usersInGrace
usersToWatch = set( [ u['id'] for u in AllUsers.values() if u['lastActivityTimestamp'] is None and ( u['expirationDate'] is None or u['expirationDate'] > now ) ] )

# Remove ids who have since logged in or will be expired (Those we knew about excluding those we want to watching now)
for id in (set( cfg.options('NeverLoggedIn') ) - usersToWatch):
    _ = cfg.remove_option('NeverLoggedIn',id)

# Add new inactive ids that havent been seen yet (Users identified now but ignoring the ones we already knew about)
for id in (usersToWatch - set(cfg.options('NeverLoggedIn'))):
    cfg.set('NeverLoggedIn', id, nowstr)

# Add newly warned ids (Those to warn excluding thse we have already warned recently)
for id in (usersToWarn - usersInGrace):
    cfg.set('Warned', id, nowstr)

# Remove ids who have since logged in (Those we have warned before, excluding those we are watching, those we are warning now, and those still in grace period, but including those we are expiring)
for id in (set(cfg.options('Warned')) - usersToWatch - usersToWarn - usersInGrace) | usersToExpire:
    _ = cfg.remove_option('Warned',id)

### Send Emails

if cfg.getboolean('Email', 'enabled') and len(usersToWarn)+len(usersToExpire) > 0:
    server = connectSMTP(cfg)
    print("Connected to Mail Server")
    if warnemail is not None: emailUsers(server, usersToWarn, emailcc, emailbcc, emailfrom, warnsubject, warnemail)
    if expireemail is not None: emailUsers(server, usersToExpire, emailcc, emailbcc, emailfrom, expiresubject, expireemail)
    server.quit()
    print("Disconnected from Mail Server")

# Users who havent logged in after long enough should also be expired ad removed from the list, irrespective of previous expiry date
if firstLoginDays is not None:
    expireNew = set( [ id for id in cfg.options('NeverLoggedIn') if (now - get_dt(cfg.get('NeverLoggedIn', id))) >= timedelta(days=firstLoginDays) ] )
    for id in expireNew:
        _ = cfg.remove_option('NeverLoggedIn',id)
    usersToExpire |= expireNew

## Expire IDs

print("\nExpire the following:")
for id in usersToExpire:
    user = AllUsers[id]
    user['expirationDate'] = nowstr
    print(f"Expiring: {user['name']}")
    expireUser(id, nowstr)
    cfg.set('Expired', id, nowstr)

dcs.logout()

# Store config details
cfgfile.seek(0)
cfg.write(cfgfile)
cfgfile.truncate()
cfgfile.close()



