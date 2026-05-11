Value CHASSIS_ID (\S+)
Value CONTACT (.*)
Value LOCATION (.*)

Start
  ^SNMP\s+entity\s+engine\s+ID:\s+${CHASSIS_ID}
  ^Contact:\s+${CONTACT}
  ^Location:\s+${LOCATION} -> Record
