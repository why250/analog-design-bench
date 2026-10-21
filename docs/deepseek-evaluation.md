# DeepSeek through a Chat Completions relay

Use an authorized OpenAI-compatible relay with the canonical
`scripts/Invoke-NmosEvaluation.ps1` entrypoint. Follow the
[configured-model SOP](nmos-evaluation.md), [evaluation policy](model-evaluation.md)
and [capture requirements](trace-capture.md). This is operator documentation,
not solver input. The runner uses the Python standard library; the optional
SDK example below does not add an SDK dependency to it.

Choose and record the comparison protocol and requested attempt scope before
configuring access or making connection probes. A provider or relay choice does
not justify creating a new solving budget, attempt policy, or turn cap.

## Endpoint and credentials

Use the relay's HTTPS API base URL, including `/v1` when required. Do not append
`/chat/completions` to `base_url`; the SDK and runner append that resource path.
Keep real endpoints, account-specific choices and machine paths in ignored
`.local/` notes. Shared templates use placeholders.

Reuse the existing authorized `NEW_API_KEY`. Never put its value in source,
configuration JSON, command arguments, chat, or public evidence. If the Windows
user variable has not been configured, enter it without placing the literal key
in shell history:

```powershell
$relayKey = Read-Host 'Enter the relay API key' -AsSecureString
try {
    [Environment]::SetEnvironmentVariable('NEW_API_KEY', [System.Net.NetworkCredential]::new('', $relayKey).Password, 'User')
} finally {
    $relayKey.Dispose()
    Remove-Variable relayKey
}
```

The PowerShell evaluation launcher prefers an existing process value, otherwise
loads the Windows user value temporarily and restores the original process
value afterward. It passes the variable name to Python, keeps the key out of
retained configuration, and does not pass it to the solver container.

Existing shells do not automatically inherit a newly saved user variable. The
standalone SDK reads process variables; load the user value only when needed,
without printing it:

```powershell
if (-not $env:NEW_API_KEY) {
    $env:NEW_API_KEY = [Environment]::GetEnvironmentVariable('NEW_API_KEY', 'User')
}
$env:NEW_API_BASE_URL = 'https://api.example.com/v1'
```

Replace the example URL with the authorized endpoint. A present variable alone
does not prove provider access or request-field support.

## Minimal SDK request

With the optional `openai` Python package and the process variables configured:

```python
import os

from openai import OpenAI

client = OpenAI(
    base_url=os.environ["NEW_API_BASE_URL"],
    api_key=os.environ["NEW_API_KEY"],
)

completion = client.chat.completions.create(
    model="deepseek-flash",
    messages=[
        {"role": "user", "content": "Explain quantum entanglement in one paragraph."}
    ],
)

print(completion.choices[0].message.content)
```

Running this example makes a real model request and may incur a charge. It is
an optional connectivity example, not a scored attempt or the runner's tool
roundtrip probe. It does not request `max` effort or test streaming, tools and
complete usage reporting.

The SDK supports relay-specific fields through `extra_body`; for example,
`extra_body={"reasoning_effort": "max", "thinking": {"type": "enabled"}}`
expresses those additional requested fields. The relay must support them.
Transport success does not establish that the relay applied `max` or returned
the requested model. Retain requested settings and observed evidence separately.
See the [official Python SDK reference](https://developers.openai.com/api/reference/python)
and [SDK configuration documentation](https://github.com/openai/openai-python#configuring-the-http-client).

## Configure the canonical evaluation

Copy the [DeepSeek relay template](../evaluation/nmos-ldo/deepseek-relay.example.json)
to a fresh ignored local file, then replace its placeholder `baseUrl`:

```powershell
New-Item -ItemType Directory -Force .\.local | Out-Null
if (Test-Path .\.local\deepseek-relay.json) { throw 'Choose a new configuration filename instead of overwriting this one.' }
Copy-Item .\evaluation\nmos-ldo\deepseek-relay.example.json .\.local\deepseek-relay.json
```

The example URL is intentionally rejected by the runner until replaced. Review
these requested settings against the selected relay's actual interface:

| Configuration | Request meaning |
| --- | --- |
| `model: "deepseek-flash"` | Exact provider ID; a display label is not a different API model |
| `apiKeyEnvironmentVariable: "NEW_API_KEY"` | Variable name, never its value |
| `request.reasoningEffort: "max"` | Sends `reasoning_effort: "max"` |
| `request.thinking: {"type":"enabled"}` | Sends the relay-specific thinking object |
| `request.maxTokensField: "max_tokens"` | Selects the response token-limit field |
| `request.includeUsage: true` | Requests `stream_options.include_usage` |
| `limits.maxTurns: 0` | Adds no turn cap before the solving deadline |
| `limits.maxTokensPerResponse: 131072` | Requested per-response token limit |
| `pricing: null` | Keeps estimated cost unknown without compatible dated rates |

These are configuration choices, not verified capabilities of every relay.
Unsupported fields require an explicit configuration change and a fresh input
preview. Do not silently fall back while retaining the original configuration
identity. Preserve any limits actually imposed as observed evidence.

## Review, execute, and retain evidence

Prepare/check the images using the [image procedure](nmos-evaluation.md#prepare-the-images).
Then check configuration/images and generate a fresh not-sent input preview:

```powershell
powershell -NoProfile -File .\scripts\Invoke-NmosEvaluation.ps1 -Config .\.local\deepseek-relay.json -PreflightOnly
powershell -NoProfile -File .\scripts\Invoke-NmosEvaluation.ps1 -Config .\.local\deepseek-relay.json -PreviewInputOnly -OutputDirectory .\.local\deepseek-input-preview-1
```

Neither command reads the model key or calls the model. Review the complete
`initial-input.preview.json`: exact model/settings, public task and tools, without
operator documents, hidden scores, prior circuits, references or publishing
context. Its `NOT SENT` status cannot repair missing historical as-sent input.

If a real tool roundtrip probe is within the requested scope, use
`-ConnectionTestOnly` with the same configuration. It makes real model requests;
retain the probe as separate setup overhead, outside scored attempts.

The canonical default is three independent blind attempts per task, each with a
7200-second solving allowance. Execute only the requested scope. For an
explicitly requested first attempt, choose a fresh campaign/output identity:

```powershell
powershell -NoProfile -File .\scripts\Invoke-NmosEvaluation.ps1 -Config .\.local\deepseek-relay.json -CampaignId deepseek-ldo-attempt-1 -Attempts 1 -StartAttempt 1 -OutputDirectory .\.local\deepseek-ldo-attempt-1
```

This is partial coverage under `official-2h-3`, not a completed three-attempt
campaign. For an authorized full campaign, follow the
[attempt scope procedure](nmos-evaluation.md#run-the-requested-attempts).
The same allowance alone does not make this Chat Completions harness equivalent
to a native Codex harness; keep that distinction visible in comparisons.

Inspect actual initial input, requests/responses/tools, capture report, usage/cost,
frozen circuit hash and original independent verifier reports using the
[evidence procedure](nmos-evaluation.md#inspect-and-deliver-evidence).
Zero verifier exit status alone is not acceptance. Review the selected archive
before handoff to a consumer; evaluation is not website publication.

## Legacy compatibility helper

`scripts/Invoke-DeepSeekEvaluation.ps1` retains the separate `local-chat-capped`
workflow: 1800 seconds, one attempt, 128 turns, `deepseek-flash`, requested `max`
effort and enabled thinking, `max_tokens: 131072`, and key variable `NEW_API_KEY`.
Choose `-BaseUrl` or `NEW_API_BASE_URL`; it also loads a Windows user key when needed.

Use this helper only when that short protocol is explicitly intended. Changing
its time limit does not convert its capped one-attempt policy into the default
protocol. Historical records retain actual conditions, capture gaps, original
circuit and verifier evidence; never fabricate missing historical input.
Withdrawing a public result does not change its local historical evidence.
