Value Required MODE (read|write)
Value Required COMMUNITY_NAME (\S+)
Value ACL (\S+)

Start
  ^snmp-agent\s+community\s+${MODE}\s+${COMMUNITY_NAME}(?:\s+acl\s+${ACL})? -> Record
