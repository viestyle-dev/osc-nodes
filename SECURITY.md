# Security Policy

## Reporting a Vulnerability

Please use GitHub's **Private Vulnerability Reporting**
(Security tab → "Report a vulnerability") on this repository.
Do not open public issues for security reports.

## Scope

osc-nodes sends and receives OSC packets over UDP. Receive nodes bind a
UDP server on **all interfaces** (`0.0.0.0`) at the port given in the
graph, without authentication: any host that can reach that port can
inject values into the graph. Send nodes transmit to whatever IP address
and port the graph specifies. The plugin does not execute code from
packets or graph definitions; malformed packets are logged and dropped.
Run the engine on a trusted network or restrict the ports with a firewall.

The host runtime it plugs into (the nonoha engine) may include script
nodes with their own threat model — see the security policy of the host
project for loading untrusted graphs.

## Supported versions

Security fixes target the latest minor release.
