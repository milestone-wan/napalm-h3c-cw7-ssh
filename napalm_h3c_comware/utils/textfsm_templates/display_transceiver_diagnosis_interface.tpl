Value Required INTERFACE (\S+)
Value TEMPERATURE ([\d\.\-]+)
Value VOLTAGE ([\d\.\-]+)
Value BIAS_CURRENT ([\d\.\-]+)
Value TX_POWER ([\d\.\-]+)
Value RX_POWER ([\d\.\-]+)

Start
  ^\s*Interface:\s+${INTERFACE}
  ^\s*Current diagnostic -> CURRENT

CURRENT
  ^\s*${TEMPERATURE}\s+${VOLTAGE}\s+${BIAS_CURRENT}\s+${TX_POWER}\s+${RX_POWER} -> Next.Record Start
