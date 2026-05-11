Value IPV6_ADDRESS ([0-9A-Fa-f:]+)
Value MAC_ADDRESS (\w+-\w+-\w+|\S+)
Value VLAN_VSI (\S+|\d+)
Value INTERFACE (\S+)
Value STATE (\S+)
Value AGING (\S+)

Start
  ^IPv6\s+Address\s+MAC\s+Address.* -> NEIGHBORS

NEIGHBORS
  ^${IPV6_ADDRESS}\s+${MAC_ADDRESS}\s+${VLAN_VSI}\s+${INTERFACE}\s+${STATE}\s+${AGING} -> Record
