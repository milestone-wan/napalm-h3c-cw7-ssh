Value Filldown VPN_INSTANCE_NAME (\S+)
Value Required RD (\S+)
Value List INTERFACES (\S+)

Start
  ^VPN-Instance\s+Name:\s+${VPN_INSTANCE_NAME}
  ^\s+Route\s+Distinguisher:\s+${RD}
  ^\s+Interfaces:
  ^\s{4,}${INTERFACES} -> Continue.Record
  ^$$ -> Record
