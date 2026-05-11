Value Required USERNAME (\S+)
Value SERVICE (\S+)
Value STATE (\S+)

Start
  ^\s*Username\s+Service.*State\s* -> TABLE
  ^\s*Device management user\s+${USERNAME}: -> DETAIL

TABLE
  ^\s*${USERNAME}\s+${SERVICE}\s+${STATE} -> Record

DETAIL
  ^\s*State:\s+${STATE}
  ^\s*Service type:\s+${SERVICE} -> Record
