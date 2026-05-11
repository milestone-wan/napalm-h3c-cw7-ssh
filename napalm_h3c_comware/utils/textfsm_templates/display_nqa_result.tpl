Value Filldown,Required ADMIN (\S+)
Value Filldown,Required TEST (\S+)
Value Filldown,Required PROBE_COUNT (\d+)
Value Filldown RECEIVED (\d+)
Value Filldown PACKET_LOSS ([\d\.]+)
Value Filldown RTT ([\d\/]+)
Value Filldown CURRENT_MIN_DELAY ([\d\.]+)
Value Filldown CURRENT_MAX_DELAY ([\d\.]+)
Value Filldown CURRENT_AVG_DELAY ([\d\.]+)
Value Filldown LAST_MIN_DELAY ([\d\.]+)
Value Filldown LAST_MAX_DELAY ([\d\.]+)
Value Filldown LAST_AVG_DELAY ([\d\.]+)
Value Filldown GLOBAL_MIN_DELAY ([\d\.]+)
Value Filldown GLOBAL_MAX_DELAY ([\d\.]+)
Value Filldown GLOBAL_AVG_DELAY ([\d\.]+)

Start
  ^NQA\s+entry\(${ADMIN},\s*${TEST}\)\s+test\s+results:
  ^\s*Send\s+operation\s+times:\s+${PROBE_COUNT}\s+Receive\s+response\s+times:\s+${RECEIVED}
  ^\s*Min/Max/Avg\s+round\s+trip\s+time:\s+${RTT}\s*ms
  ^\s*Packet\s+loss:\s*${PACKET_LOSS}%
  ^\s*Current\s+test\s+min\s+delay:\s+${CURRENT_MIN_DELAY}\s*ms
  ^\s*Current\s+test\s+max\s+delay:\s+${CURRENT_MAX_DELAY}\s*ms
  ^\s*Current\s+test\s+avg\s+delay:\s+${CURRENT_AVG_DELAY}\s*ms
  ^\s*Last\s+test\s+min\s+delay:\s+${LAST_MIN_DELAY}\s*ms
  ^\s*Last\s+test\s+max\s+delay:\s+${LAST_MAX_DELAY}\s*ms
  ^\s*Last\s+test\s+avg\s+delay:\s+${LAST_AVG_DELAY}\s*ms
  ^\s*Global\s+test\s+min\s+delay:\s+${GLOBAL_MIN_DELAY}\s*ms
  ^\s*Global\s+test\s+max\s+delay:\s+${GLOBAL_MAX_DELAY}\s*ms
  ^\s*Global\s+test\s+avg\s+delay:\s+${GLOBAL_AVG_DELAY}\s*ms -> Next.Record Start
