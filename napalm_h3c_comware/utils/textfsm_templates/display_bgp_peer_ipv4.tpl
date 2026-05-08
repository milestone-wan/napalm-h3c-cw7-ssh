Value Filldown ROUTER_ID (\d+\.\d+\.\d+\.\d+)
Value Filldown LOCAL_AS (\d+)
Value Required PEER (\d+\.\d+\.\d+\.\d+)
Value REMOTE_AS (\d+)
Value STATE (\S+)
Value PREF_RCV (\d+)
Value ACTIVE (\d+)
Value ACCEPTED (\d+)
Value UPSTREAM (\d+)

Start
  ^BGP\s+local\s+router\s+ID:\s+${ROUTER_ID} -> Continue
  ^Local\s+AS\s+number:\s+${LOCAL_AS} -> Continue
  ^Peer\s+AS\s+State\s+Pref -> PEERS

PEERS
  ^${PEER}\s+${REMOTE_AS}\s+${STATE}\s+${PREF_RCV}\s+${ACTIVE}\s+${ACCEPTED}\s+${UPSTREAM} -> Record
