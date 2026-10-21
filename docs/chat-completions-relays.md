# Connecting models through a Chat Completions relay

Use this operator guide for an authorized OpenAI-compatible relay, including
when changing from one provider model to another. The SDK connection pattern
is reusable; accepted parameters, backend versions and capabilities are specific
to each model and route. Keep this guide and account configuration outside blind
solver input.

For scored NMOS LDO evaluations, follow the [evaluation policy](model-evaluation.md),
[configured-model SOP](nmos-evaluation.md) and [capture requirements](trace-capture.md).
The canonical runner uses the Python standard library, not the optional SDK below.
Changing a relay or model does not select a different benchmark protocol.

## Endpoint and credentials

Keep the authorized HTTPS API base URL and account-specific selections in ignored
`.local/` notes. Shared examples use `https://api.example.com/v1`; replace it with
the actual base URL. Do not append `/chat/completions` to `base_url`: the client
appends the resource path. The evaluation runner rejects credentials, query
strings and fragments in the URL.

Reuse an existing authorized key variable such as `NEW_API_KEY`. Never put its
value in source, JSON, command arguments, chat or exported evidence. If it has
not been configured, enter a Windows user variable without a literal in history:

```powershell
$relayKey = Read-Host 'Enter the relay API key' -AsSecureString
try {
    [Environment]::SetEnvironmentVariable('NEW_API_KEY', [System.Net.NetworkCredential]::new('', $relayKey).Password, 'User')
} finally {
    $relayKey.Dispose()
    Remove-Variable relayKey
}
```

The PowerShell evaluation launcher prefers a process value, otherwise temporarily
loads the Windows user value and restores the process afterward. It passes only
the variable name to Python and does not pass the key to the solver container.
Standalone Python reads process variables, so an existing shell may need:

```powershell
if (-not $env:NEW_API_KEY) {
    $env:NEW_API_KEY = [Environment]::GetEnvironmentVariable('NEW_API_KEY', 'User')
}
$env:NEW_API_BASE_URL = 'https://api.example.com/v1'
$env:MODEL_ID = 'glm-5.3'
```

Replace the example endpoint. `MODEL_ID` is a requested provider ID, not proof
that the account or route serves that model. It is used by the SDK snippets;
the evaluation runner reads its model and endpoint from configuration JSON.

## Reusable SDK connection

With the optional `openai` Python package installed, construct a client without
making a request:

```python
import os

from openai import OpenAI

client = OpenAI(
    base_url=os.environ["NEW_API_BASE_URL"],
    api_key=os.environ["NEW_API_KEY"],
    max_retries=0,
)
model_id = os.environ["MODEL_ID"]
```

The snippets deliberately disable automatic retries so an optional generation
probe does not silently become several generation attempts. They are manual
examples, not the scored campaign harness. See the
[official Python SDK reference](https://developers.openai.com/api/reference/python)
for client configuration, additional request fields and response inspection.

### Discover declared metadata

Using the client above, optionally request the relay's model catalog:

```python
found = False
for entry in client.models.list():
    if entry.id == model_id:
        print(entry.model_dump_json(indent=2))
        found = True
        break
if not found:
    print("No matching model metadata was returned; availability is unconfirmed.")
```

This makes authenticated metadata requests, not a generation request. A relay
may omit the endpoint, omit a model or return only an alias. Preserve optional
name/version, supported effort levels and default effort when supplied; absence
means unknown. Catalog capabilities are service declarations, not evidence of
the backend or effort applied to a particular completion. Do not derive a model
release version from `created` or `system_fingerprint`.

### Optional generation probe

Only within an explicitly selected access/spending scope, run a minimal request:

```python
completion = client.chat.completions.create(
    model=model_id,
    messages=[
        {"role": "user", "content": "Explain quantum entanglement in one paragraph."}
    ],
)

print(completion.choices[0].message.content)
print("Reported model:", completion.model)
print(completion.model_dump_json(indent=2))
```

This makes a real generation request and may incur a charge. It does not select
an effort level, certify tools/streaming or create a scored attempt. Inspect the
full response locally to retain returned metadata and extra fields; apply the
[capture/export rules](trace-capture.md) before sharing it. A returned alias or
reasoning text does not independently establish an exact version or effort.

## Select parameters for each model

Use the existing [neutral model template](../evaluation/nmos-ldo/model.example.json)
for a new local configuration. Do not copy another model's options unchanged.

| Configuration | Decision required when changing models |
| --- | --- |
| `id` | Use a distinct configuration identity for a changed model, effort, harness or material option. Keep actual versions/hashes in provenance. |
| `model` | Exact requested provider ID, such as `glm-5.3`; record returned identifiers separately. |
| `baseUrl`, `apiKeyEnvironmentVariable` | Authorized endpoint and key variable name; no secret value. |
| `request.reasoningEffort` | Set only a supported, intended value. `null` omits the field; it does not disable reasoning. |
| `request.thinking` | Model-specific object or `null` to omit. Omission leaves provider behavior unspecified. |
| `request.maxTokensField` | Choose the supported `max_tokens` or `max_completion_tokens`; the template default is not universal. |
| `limits.maxTokensPerResponse` | Select an accepted response limit. The template's `131072` is a configured limit, not a discovered capability. |
| `request.includeUsage` | Requests stream usage when enabled. Missing counters remain unknown. |
| `request.extra` | Provider-specific fields; the runner rejects overrides of its structured options, model, messages, tools and stream. |
| `limits.maxTurns`, protocol and scope | Preserve the selected comparison contract. Under `official-2h-3`, use zero extra turn cap and a 7200-second allowance; execute only requested attempt numbers. |
| `pricing` | Exact compatible dated rates or `null`; changing model invalidates inherited rates. Unknown estimates are not zero charges. |

The SDK accepts additional provider fields through `extra_body`. The runner
instead maps its structured JSON fields and `request.extra` into the request.
Neither interface proves that a relay applies every accepted field. Preserve
requested values, service declarations and observed response evidence separately.
Do not silently fall back to different settings while keeping the original identity.

Model-specific examples, checked on 2026-10-21:

- [DeepSeek configuration](deepseek-evaluation.md) documents an explicit requested
  `max` profile and its separate legacy helper.
- The [GLM-5.3 provider documentation](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3)
  states that thinking is always enabled, `reasoning_effort` supports `low`,
  `high` and `max`, and its default is `max`; disabling thinking is unsupported.
  These are provider claims, not verification of a relay's GLM route. A minimal
  SDK call does not explicitly select an effort even when a provider defines one.

## Connect the selected configuration to an evaluation

Settle task revision, protocol, attempt scope and spending policy before real
requests. Use the [NMOS SOP](nmos-evaluation.md) for configuration copying,
image/source preflight and a fresh `NOT SENT` input preview. Preflight and preview
make no model requests or key reads. Review the actual planned messages and
tools; regenerate the preview whenever model options or limits change.

The current NMOS runner always requests SSE and function tools, plus one token
limit field. Text-only SDK success is insufficient. When authorized, use its
`-ConnectionTestOnly` mode with the exact planned configuration. A normal
successful probe makes two generation requests for a tool/result roundtrip;
it executes no model-supplied shell command. Save its stdout in a fresh local
file and account for the probe separately from scored attempts.

Probe success establishes that roundtrip, not backend identity, actual effort
or complete billing. The output reports the second response's model and two
usage entries. Inspect both: missing usage does not make the probe fail and must
remain unknown. The probe does not automatically retain campaign-style request
or stream files. A dollar spending cap also requires suitable billing/control
support; time and token limits alone do not enforce a dollar cap.

Then execute only the selected fresh blind attempts through the canonical
entrypoint. Retain actual capture and independently verify the frozen circuit
as specified in the [evidence procedure](nmos-evaluation.md#inspect-and-deliver-evidence).
The current backend supports this NMOS task, not arbitrary tasks or native
subscription sessions. Hand off a reviewed neutral evidence archive; consumer
adaptation and publication are separate. A relay change alone does not justify
a new comparison protocol, and equal time allowances do not make harnesses identical.
