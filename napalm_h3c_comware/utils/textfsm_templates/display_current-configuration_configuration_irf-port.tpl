Value MEMBER_ID (\d+)
Value PORT_ID (\d+)
Value List PORT_MEMBER (\S+)

Start
  ^\s*# -> Continue.Record
  ^\s*irf-port\s+${MEMBER_ID}/${PORT_ID}
  ^\s*port\s+group\s+interface\s+${PORT_MEMBER} -> Continue