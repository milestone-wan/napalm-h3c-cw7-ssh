Value Required ROUTER_ID (\d+\.\d+\.\d+\.\d+)
Value LOCAL_AS (\d+)

Start
  ^BGP\s+local\s+router\s+ID:\s+${ROUTER_ID}
  ^Local\s+AS\s+number:\s+${LOCAL_AS} -> Record
