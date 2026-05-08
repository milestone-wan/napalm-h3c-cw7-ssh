Value Required PEER (\d+\.\d+\.\d+\.\d+)
Value TYPE (\S+)
Value STATE (\S+)
Value LOCAL_AS (\d+)
Value REMOTE_AS (\d+)
Value LOCAL_ADDRESS (\d+\.\d+\.\d+\.\d+)
Value LOCAL_PORT (\d+)
Value REMOTE_ADDRESS (\d+\.\d+\.\d+\.\d+)
Value REMOTE_PORT (\d+)
Value HOLD_TIME (\d+)
Value KEEPALIVE_INTERVAL (\d+)
Value CONFIGURED_HOLD_TIME (\d+)
Value CONFIGURED_KEEPALIVE (\d+)
Value MESSAGES_SENT (\d+)
Value MESSAGES_RECEIVED (\d+)
Value UPDATE_MESSAGES_SENT (\d+)
Value UPDATE_MESSAGES_RECEIVED (\d+)
Value IMPORT_ROUTE_POLICY (\S+)
Value EXPORT_ROUTE_POLICY (\S+)
Value UP_DOWN_TIME (\S+)

Start
  ^\s*Peer:\s+${PEER}
  ^\s*Type:\s+${TYPE}
  ^\s*BGP\s+current\s+state:\s+${STATE}
  ^\s*Local\s+AS:\s+${LOCAL_AS}
  ^\s*Peer\s+AS:\s+${REMOTE_AS}
  ^\s*Local\s+address:\s+${LOCAL_ADDRESS}\s+Local\s+port:\s+${LOCAL_PORT}
  ^\s*Remote\s+address:\s+${REMOTE_ADDRESS}\s+Remote\s+port:\s+${REMOTE_PORT}
  ^\s*Hold\s+time:\s+${HOLD_TIME}
  ^\s*Keepalive\s+interval:\s+${KEEPALIVE_INTERVAL}
  ^\s*Configured\s+hold\s+time:\s+${CONFIGURED_HOLD_TIME}
  ^\s*Configured\s+keepalive\s+interval:\s+${CONFIGURED_KEEPALIVE}
  ^\s*Messages\s+sent:\s+${MESSAGES_SENT}
  ^\s*Messages\s+received:\s+${MESSAGES_RECEIVED}
  ^\s*Update\s+messages\s+sent:\s+${UPDATE_MESSAGES_SENT}
  ^\s*Update\s+messages\s+received:\s+${UPDATE_MESSAGES_RECEIVED}
  ^\s*Import\s+route\s+policy:\s+${IMPORT_ROUTE_POLICY}
  ^\s*Export\s+route\s+policy:\s+${EXPORT_ROUTE_POLICY}
  ^\s*Up/Down\s+time:\s+${UP_DOWN_TIME} -> Record
