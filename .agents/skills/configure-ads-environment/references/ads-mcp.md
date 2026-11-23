# ADS MCP configuration and session selection

Read this reference when the selected ADS environment uses MCP or MCP setup is
part of the requested work. Keep a working configured route, instance name and
approved launcher. This guide preserves the connection method while making its
machine-specific values replaceable. Writing a task does not configure a client,
start a server or ADS session, or authorize GUI work and simulation.

## Capture the existing binding first

Record the client, server label, transport, command/argument array, launcher,
environment settings, intended ADS version, execution host, native workspace,
path mapping and timeout choices. Keep actual bindings in local configuration;
portable task instructions refer to the selected profile and expected capabilities.
An approved wrapper can establish installation or filesystem requirements:
preserve it instead of bypassing it with a guessed direct executable.

When no binding exists, use the following as setup templates and retain pending
status until the destination supplies and verifies the values. The templates are
not changes to the client and do not require MCP for a task using another route.

## Codex stdio templates

For Codex, a trusted project's `.codex/config.toml` can contain a
`[mcp_servers.<label>]` entry. The examples use `ads_selected` only as a label;
reuse the actual existing label when one is configured. Resolve every `{{...}}`
marker before use. Select one transport pattern, not both entries under one label.
The timeout values are example choices, not ADS or Codex defaults.

Local installed server or approved local launcher:

```toml
[mcp_servers.ads_selected]
command = "{{local_ads_mcp_executable_or_launcher}}"
args = []
startup_timeout_sec = 90
tool_timeout_sec = 300
enabled = true

[mcp_servers.ads_selected.env]
PYTHONUTF8 = "1"
PYTHONIOENCODING = "utf-8"
```

Preserve any required launcher arguments. The environment table applies to the
local process and its descendants. Use `cwd` when the selected launcher requires
a particular working directory. Keep credentials out of shared examples.

Existing SSH alias carrying the remote MCP server's stdio:

```toml
[mcp_servers.ads_selected]
command = "{{local_ssh_executable}}"
args = [
  "-T",
  "-o", "BatchMode=yes",
  "-o", "ConnectTimeout=12",
  "{{existing_ssh_alias}}",
  "{{remote_launch_command}}"
]
startup_timeout_sec = 90
tool_timeout_sec = 300
enabled = true
```

For a verified Windows PowerShell remote shell, the launch-command pattern is:

```powershell
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; & '{{remote_ads_mcp_executable}}'
```

Use the selected server's actual shell and quoting rules. A local `env` setting
on `ssh` does not automatically set the remote process environment. The two
Python encoding variables above preserve a Windows ADS reference setup's raw
non-ASCII source/result handling; validate that round trip on a new installation.

Keep stdin open, disable pseudo-terminal allocation, and keep stderr separate
from protocol stdout. Do not add SSH `-n` or merge output with `2>&1`. Startup
banners or launcher logging must not contaminate the MCP stream. Reuse existing
SSH authentication; do not change keys, server policy or firewall configuration
as a side effect of authoring a task. Other MCP-capable clients need their own
supported config format; do not assume they read Codex TOML.

## Claude Code project `.mcp.json` template

Claude Code does not read Codex's `.codex/config.toml`; encode the same server
in the project `.mcp.json` (or the user's Claude Code MCP configuration). The
transport is stdio; the command and arguments may reuse the existing SSH alias
and remote launcher.

```json
{
  "mcpServers": {
    "ads2027": {
      "type": "stdio",
      "command": "{{local_ssh_executable}}",
      "args": [
        "-T",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=12",
        "{{existing_ssh_alias}}",
        "{{remote_launch_command}}"
      ]
    }
  }
}
```

After creating or changing the file, restart or reload the client session and
approve the project server. A registered config or a successful SSH exit does
not prove the tools are exposed; verify `list_sessions` and a read-only
`execute_python` call.

A sub-agent or sub-session inherits the parent client's tool catalog; it does
not read another client's config file. If the native tools are absent, a local
JSON-RPC client over the same SSH launch is a fallback. It adds PowerShell, SSH
and process layers, loses REPL state between calls, and requires self-contained
scripts or detached solvers. Do not present the bridge as equivalent to native
tool registration. Keep host aliases and executable paths in ignored local
configuration rather than in a committed project file.

## Registration, discovery and attachment are different checks

Record each level separately and perform only checks within current authorization:

1. Confirm which client configuration is loaded, whether the project is trusted,
   and which server label/launcher it selects. `codex mcp list` lists configured
   servers; it is not proof of an active ADS process or a refreshed tool catalog.
2. Initialize the MCP transport and retrieve the advertised tool schemas. A valid
   TOML file or successful SSH exit alone does not establish this step.
3. Use advertised documentation and session-discovery tools. ADS MCP releases
   may expose `get_docs`, `search_docs` and `list_sessions`; discover actual
   schemas instead of assuming these names and arguments across versions.
4. Select the intended existing session by host, ADS version and workspace, then
   attach through its advertised connection tool. Discover a fresh session ID
   after restart; do not hard-code a PID in a reusable profile.
5. Verify the connected process identity, active workspace and consumer-visible
   paths with documented read-only operations. Keep applicable GUI-consent rules.
   A discovery/attachment check does not authorize design changes.
6. Treat a headless-session start as a separate mode that may consume a license.
   GUI-only APIs are not interchangeable with headless APIs. Do not silently
   start another ADS process because an intended existing session is unavailable.
7. Run a model or simulation smoke check only when separately authorized, retaining
   actual inputs, model bindings, logs and dataset. Transport and session checks
   alone never establish electrical acceptance or model applicability.

If the client requires a restart or connection refresh after a config change,
follow its supported procedure. If setup or schemas remain unavailable, keep the
task ready for preflight with explicit binding fields and resolution steps.

## Documentation and version boundaries

Client config semantics are documented in the
[OpenAI MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
ADS executable discovery, tool names, execution modes and Python APIs must be
checked against the selected installed version's documentation/tool schemas.
The templates and workflow above are bundled authoring guidance; no source
project documentation or machine installation is needed to read and use them.
