Value Required DESTINATION (\S+)
Value PROTOCOL (\S+)
Value PREFERENCE (\d+)
Value COST (\d+)
Value NEXT_HOP (\S+)
Value INTERFACE (\S+)
Value STATE (\S+.*)
Value AGE (\S+)
Value PROCESS_ID (\d+)
Value TAG (\S+)

Start
  ^Destination:\s+${DESTINATION}
  ^\s*Protocol:\s+${PROTOCOL}
  ^\s*Preference:\s+${PREFERENCE}
  ^\s*Cost:\s+${COST}
  ^\s*NextHop:\s+${NEXT_HOP}
  ^\s*Interface:\s+${INTERFACE}
  ^\s*State:\s+${STATE}
  ^\s*Age:\s+${AGE}
  ^\s*Tag:\s+${TAG} -> Record
