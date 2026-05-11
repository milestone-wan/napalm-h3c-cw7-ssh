Value Required ASSOCIATION_TYPE (unicast-server|unicast-peer)
Value Required ADDRESS (\d+\.\d+\.\d+\.\d+|[0-9A-Fa-f:]+)
Value VERSION (\d+)
Value SOURCE_INTERFACE (\S+)
Value VPN_INSTANCE (\S+)

Start
  ^ntp-service\s+${ASSOCIATION_TYPE}\s+${ADDRESS}(?:\s+version\s+${VERSION})?(?:\s+source-interface\s+${SOURCE_INTERFACE})?(?:\s+vpn-instance\s+${VPN_INSTANCE})? -> Record
