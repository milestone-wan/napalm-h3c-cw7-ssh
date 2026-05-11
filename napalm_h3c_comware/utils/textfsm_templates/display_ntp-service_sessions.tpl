Value Required CLOCK_SOURCE (\d+\.\d+\.\d+\.\d+|[0-9A-Fa-f:]+)
Value Filldown CLOCK_STRATUM (\d+)
Value Filldown CLOCK_STATUS (\S+.*)
Value Filldown REFERENCE_ID (\d+\.\d+\.\d+\.\d+|[0-9A-Fa-f:]+|\S+)
Value Filldown REACHABILITY (\d+)
Value Filldown POLL_INTERVAL (\d+)
Value Filldown LAST_UPDATE (\S+)
Value Filldown OFFSET ([\d\.\-]+)
Value Filldown DELAY ([\d\.\-]+)
Value Filldown JITTER ([\d\.\-]+)

Start
  ^\s*Clock\s+source:\s+${CLOCK_SOURCE}
  ^\s*Clock\s+stratum:\s+${CLOCK_STRATUM}
  ^\s*Clock\s+status:\s+${CLOCK_STATUS}
  ^\s*Reference\s+clock\s+ID:\s+${REFERENCE_ID}
  ^\s*Reachability:\s+${REACHABILITY}
  ^\s*Current\s+poll\s+interval:\s+${POLL_INTERVAL}
  ^\s*Last\s+update\s+time:\s+${LAST_UPDATE}
  ^\s*Offset:\s+${OFFSET}\s*ms
  ^\s*Delay:\s+${DELAY}\s*ms
  ^\s*Jitter:\s+${JITTER}\s*ms -> Record
