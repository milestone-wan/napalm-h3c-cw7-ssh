Value OS_VERSION (.*)
Value VENDOR (\S+)
Value MODEL (\S+)
Value UPTIME (.*)

Start
  ^.*Comware\s+Software.*Version\s+[0-9\.]+,\s+${OS_VERSION}
  ^${VENDOR}\s+${MODEL}\s+uptime\s+is\s+${UPTIME} -> Record
