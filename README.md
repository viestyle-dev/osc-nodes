# osc-nodes

A nonoha-engine plugin nodes for OSC (Open Sound Control) communication, providing bidirectional data streaming capabilities between nonoha-engine and OSC-compatible applications.

## Overview

This plugin provides specialized nodes for sending and receiving OSC messages within the nonoha-engine visual programming environment. It enables real-time communication with audio software (SuperCollider, Max/MSP, Pure Data), media applications, and custom OSC implementations.

## Features

### Nodes Provided

- **OscUdpSendBlob**: Sends array data as OSC blob messages over UDP
  - Configurable IP address, port, and OSC address path
  - Supports various data types (Uint8/16/32/64) with automatic big-endian conversion
  - Efficient blob encoding for large data transfers

- **OscUdpReceiveBlob**: Receives OSC blob messages and outputs as arrays
  - Listens on specified port and OSC address
  - Automatic blob-to-array conversion with configurable data types
  - Supports Int8/16/32/64, Uint8/16/32/64, Float32/64 data types

- **OscUdpSendValues**: Sends multiple scalar values as OSC messages
  - Supports mixed data types in a single message
  - Automatic type mapping (integers, floats, booleans)
  - Bundle support for synchronized message delivery

## Installation

### From the Repository

```sh
pip install git+https://github.com/viestyle-dev/osc-nodes.git
```

Requires Python 3.11+. `nonoha-core` is provided by the host runtime (the
nonoha engine), so it is not a runtime dependency of this package.

### As a Dependency in nonoha-engine Workspace

1. Add `osc-nodes` to your workspace's `pyproject.toml`:

```toml
[project]
dependencies = [
    "osc-nodes",
    # other dependencies...
]

[tool.uv.sources]
osc-nodes = { path = "./plugins/osc-nodes", editable = false }
```

2. Install dependencies using uv:

```bash
uv sync
```

### As a Built-in Plugin

To include osc-nodes as a built-in plugin in your nonoha-engine instance:

1. Import the plugin in your `src/main.py`:

```python
import osc_nodes
```

2. Add to RuntimeConfig:

```python
from nonoha_engine.runtime_config import RuntimeConfig

config = RuntimeConfig(
    builtin_plugins=[
        osc_nodes,
        # other built-in plugins...
    ]
)
```

## Usage

Once installed, the OSC nodes will appear in the nonoha-engine node palette. You can:

1. Drag and drop OSC nodes into your visual programming workspace
2. Configure node properties (IP address, port, OSC address, data types)
3. Connect data flows between OSC nodes and other processing nodes
4. Run the graph to enable real-time OSC communication

## Requirements

- Python >= 3.11
- nonoha-core (nonoha-engine core library)
- python-osc (OSC protocol implementation)
- numpy (array processing)

## Development

To contribute or modify the plugin:

```bash
uv sync        # also installs the dev dependency group (pytest, nonoha-core)
uv run pytest
```

## OpenSoundControl Specification 1.0

<https://opensoundcontrol.stanford.edu/spec-1_0.html>

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Pull requests require signing the [nonoha CLA](CLA.md) (a one-time
comment on your first PR, shared across the nonoha repositories).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
