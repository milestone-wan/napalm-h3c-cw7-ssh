Value Required DESTINATION (\S+)
Value PROTOCOL (\S+)
Value PREFERENCE (\d+)
Value COST (\d+)
Value NEXT_HOP (\d+\.\d+\.\d+\.\d+)
Value INTERFACE (\S+)

Start
  ^Destination/Mask\s+Proto\s+Pre\s+Cost\s+NextHop\s+Interface -> ROUTES

ROUTES
  ^${DESTINATION}\s+${PROTOCOL}\s+${PREFERENCE}\s+${COST}\s+${NEXT_HOP}\s+${INTERFACE} -> Record
