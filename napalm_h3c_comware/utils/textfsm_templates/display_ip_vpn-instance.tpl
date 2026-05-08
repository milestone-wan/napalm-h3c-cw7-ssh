Value Required VPN_INSTANCE_NAME (\S+)
Value RD (\S+)
Value CREATE_TIME (.*)

Start
  ^VPN-Instance\s+Name\s+RD\s+Create\s+Time -> INSTANCES

INSTANCES
  ^${VPN_INSTANCE_NAME}\s+${RD}\s+${CREATE_TIME} -> Record
