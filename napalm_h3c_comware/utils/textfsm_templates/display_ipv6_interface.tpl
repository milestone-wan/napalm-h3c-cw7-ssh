Value INTERFACE (\S+)
Value LINK_LOCAL ([0-9A-Fa-f:]+)
Value List GLOBAL_ADDRESS ([0-9A-Fa-f:]+)
Value List GLOBAL_PREFIX_LENGTH (\d+)

Start
  ^\S+\s+current\s+state -> Continue.Record
  ^${INTERFACE}\s+current\s+state
  ^\s+link-local\s+address\s+is\s+${LINK_LOCAL} -> Continue
  ^\s+${GLOBAL_ADDRESS},\s+subnet\s+is\s+\S+/${GLOBAL_PREFIX_LENGTH} -> Continue
