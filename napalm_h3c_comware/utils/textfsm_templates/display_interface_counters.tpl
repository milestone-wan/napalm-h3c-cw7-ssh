Value INTERFACE (\S+)
Value SECTION (Input|Output)
Value PACKETS (\d+)
Value BYTES (\d+)
Value UNICASTS (\d+)
Value MULTICASTS (\d+)
Value BROADCASTS (\d+)
Value ERRORS (\d+)
Value DISCARDS (\d+)

Start
  ^${INTERFACE}\s*$$ -> Record
  ^(${SECTION}):\s+${PACKETS}\s+packets?,\s*${BYTES}\s+bytes? -> Record
  ^\s+${UNICASTS}\s+unicasts?,\s*${MULTICASTS}\s+multicasts?,\s*${BROADCASTS}\s+broadcasts? -> Record
  ^\s+${ERRORS}\s+errors?,\s*${DISCARDS}\s+discards? -> Record
