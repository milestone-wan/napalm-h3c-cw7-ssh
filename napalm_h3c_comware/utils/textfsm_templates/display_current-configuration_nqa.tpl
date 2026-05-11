Value ADMIN (\S+)
Value TEST (\S+)
Value PROBE_TYPE (\S+)
Value TARGET (\d+\.\d+\.\d+\.\d+)
Value SOURCE (\d+\.\d+\.\d+\.\d+)
Value PROBE_COUNT (\d+)
Value TEST_INTERVAL (\d+)

Start
  ^nqa\s+entry\s+${ADMIN}\s+${TEST} -> Record
  ^\s*type\s+${PROBE_TYPE} -> Record
  ^\s*destination\s+ip\s+${TARGET} -> Record
  ^\s*source\s+ip\s+${SOURCE} -> Record
  ^\s*probe\s+count\s+${PROBE_COUNT} -> Record
  ^\s*frequency\s+${TEST_INTERVAL} -> Record
