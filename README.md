# fakturoid-cli

A command-line interface for the [Fakturoid](https://www.fakturoid.cz/) REST API v3. One shell command becomes one HTTP request, and the response body is printed to stdout as raw JSON. The tool models the handful of endpoints that carry the monthly invoicing loop, and `fakturoid api` reaches everything else.

It is built for humans and for coding agents at the same time. An agent that drives it gets machine-readable output on every path, a distinct exit code for every failure class, and a payload check that fails loudly instead of quietly creating a broken financial document.

## The output contract

This is the promise the whole tool is built around, so read it first.

- **stdout carries JSON and nothing else.** The API response body is printed as it arrived, pretty-printed with two-space indent, with no `{success, data, meta}` envelope, no injected timestamp and no reordered keys.
- **Every human-facing line goes to stderr.** Warnings, error bodies, request logs and configuration notices. There are no spinners and no progress lines.
- **There is no `--json` flag,** because there is only one output mode.
- **Nothing reaches stdout on failure,** so a pipe never sees half an object.

The result is that `fakturoid <anything> | jq` always works, including inside a pipeline, inside a subshell, and with a narrow `COLUMNS`.

```bash
fakturoid invoices list --status open | jq -r '.[] | "\(.number)\t\(.total)\t\(.due_on)"'
```

## Quick start

```bash
uv tool install --editable .

fakturoid users me                       # which accounts do these credentials reach
fakturoid account show                   # does the slug resolve
fakturoid generators list                # the invoice templates
fakturoid generators payload 100001      # a template turned into an invoice payload
fakturoid invoices list --status open
```

## Install

The documented install is an editable uv tool. The author develops the tool and uses it from the same checkout, so `git pull` is the whole upgrade procedure.

```bash
git clone https://github.com/fprochazka/fakturoid-cli.git
cd fakturoid-cli
uv tool install --editable .
```

That puts `fakturoid` on `PATH`. To remove it, run `uv tool uninstall fakturoidcli`.

For development inside the checkout, skip the install and run the command through uv:

```bash
uv sync
uv run fakturoid --help
```

Python 3.11 or newer is required.

## Configuration

Credentials live in `~/.config/fakturoidcli/config.toml`, one TOML table per profile. The file holds plaintext secrets, so it must be mode `0600`. The CLI warns on stderr when it finds a looser mode.

```toml
[default]
client_id = "your-client-id"
client_secret = "your-client-secret"
default_slug = "your-account"
user_agent_contact = "you@example.com"
```

| Key | Meaning |
|---|---|
| `client_id` | OAuth2 client id for the `client_credentials` flow. |
| `client_secret` | The matching secret. |
| `default_slug` | The account slug used when `--slug` is absent. It is the subdomain part of your Fakturoid URL. |
| `user_agent_contact` | Contact address stamped into the `User-Agent` header. Fakturoid answers `400` to a request without a User-Agent, so this is mandatory. |

Create the file with the right mode from the start:

```bash
mkdir -p ~/.config/fakturoidcli
touch ~/.config/fakturoidcli/config.toml
chmod 600 ~/.config/fakturoidcli/config.toml
```

### Where the credentials come from

In Fakturoid, open **Settings -> User account** and find the API section. It hands you a `client_id` and a `client_secret` for the **client credentials flow**. Those are the two values this tool needs.

Do **not** use the OAuth application section aimed at developers who publish an integration. That section issues credentials for the authorization code flow, which needs a redirect URL and a browser round trip. This tool never opens a browser.

The slug is the account identifier in the Fakturoid URL, and `fakturoid users me` prints every slug the credentials can reach.

### The token cache

The client credentials are exchanged for an access token that lives 7200 seconds. The token is cached at `~/.config/fakturoidcli/cache.json`, mode `0600`, one entry per profile, with an absolute expiry and a fingerprint of the `client_id` it belongs to. A token is treated as expired a minute early to absorb clock skew.

The cache is disposable. Delete it at any time and the next command fetches a new token:

```bash
rm ~/.config/fakturoidcli/cache.json
```

Any read failure, a corrupt file or a `client_id` mismatch is a cache miss, never an error. A `401` on a live request also triggers exactly one refetch and one retry.

### Environment variables

Environment values beat file values, so a shell can drive the CLI with no config file at all.

| Variable | Overrides |
|---|---|
| `FAKTUROID_CONFIG` | The config file path. |
| `FAKTUROID_PROFILE` | The profile name, same as `--profile`. |
| `FAKTUROID_CLIENT_ID` | `client_id`. |
| `FAKTUROID_CLIENT_SECRET` | `client_secret`. |
| `FAKTUROID_SLUG` | `default_slug`. `--slug` still wins over it. |
| `FAKTUROID_USER_AGENT_CONTACT` | `user_agent_contact`. |

### Profile selection

1. `--profile NAME`, or `FAKTUROID_PROFILE`.
2. The table named `default`, when the file declares one.
3. The only table in the file, when exactly one exists.
4. `default`, so an environment-only setup needs no file.

## Global options

These are valid in any position. The CLI hoists them in front of the sub-command before dispatch, so `fakturoid invoices list --slug other` and `fakturoid --slug other invoices list` do the same thing. Put them after the full command path, which is what prefix-based permission matching needs.

| Option | Meaning |
|---|---|
| `--slug <slug>` | Account slug for this invocation. Overrides `default_slug`. `users me` carries no slug in its path and ignores it. |
| `-p`, `--profile <name>` | Credential profile from the config file. |
| `--dry-run` | Print the request that would be sent as JSON, and send nothing. No token is fetched, so a dry run reaches the network zero times. |
| `--output-dir <dir>` | Directory for downloaded files. Defaults to `/tmp/fakturoid`. |
| `--page <n>` | Fetch page `n` of a list endpoint. 40 records per page, fixed by the server. |
| `--all` | Walk every page and print one merged JSON array. |
| `-f`, `--field <key=value>` | Add a query parameter. Repeatable, and valid on every command including `api`. |
| `-v`, `--verbose` | Log request lines to stderr. |
| `-V`, `--version` | Print the version as JSON and exit. |

`--page` together with `--all` is a usage error and exits `2`.

A key repeated twice, or a key that ends in `[]`, becomes an array, which is the form the API expects for tags:

```bash
fakturoid invoices list -f 'tags[]=retainer' -f 'tags[]=2026'
# ...invoices.json?tags%5B%5D=retainer&tags%5B%5D=2026
```

`--dry-run` prints the method, the full URL, the headers with the token redacted, and the body:

```bash
fakturoid invoices list --dry-run --status open
```

```json
{
  "method": "GET",
  "url": "https://app.fakturoid.cz/api/v3/accounts/example-account/invoices.json?status=open",
  "headers": {
    "User-Agent": "fakturoid-cli (you@example.com)",
    "Accept": "application/json",
    "Authorization": "Bearer <redacted>"
  },
  "body": null
}
```

## Commands

Every command is also a passthrough. Request bodies are never filtered and never reshaped, extra fields included. `-f key=value` adds arbitrary query parameters next to the named options. `--help` documents the known shape as information, it does not constrain what the command accepts.

### users

**`fakturoid users me`** — `GET /user.json`. The one endpoint with no account slug in its path. This is where the slug for the config file comes from.

```bash
fakturoid users me
```

```json
{
  "id": 90001,
  "full_name": "Jan Novák",
  "email": "jan@example.com",
  "avatar_url": null,
  "default_account": null,
  "accounts": [
    {
      "slug": "example-account",
      "name": "Jan Novák",
      "registration_no": "12345678",
      "permission": "owner",
      "allowed_scope": ["invoices", "expenses", "reports"]
    }
  ]
}
```

### account

**`fakturoid account show`** — `GET /accounts/{slug}/account.json`. Fakturoid keeps the account read-only, so there is no update command. This is the cheapest check that both the credentials and the slug resolve. The response also carries `api_calls_limit` and `api_calls_used`, which is how you see where you stand against the rate limit.

```bash
fakturoid account show | jq '{subdomain, name, currency, api_calls_used, api_calls_limit}'
```

```json
{
  "subdomain": "example-account",
  "name": "Jan Novák",
  "currency": "CZK",
  "api_calls_used": 37,
  "api_calls_limit": 8000
}
```

### subjects

A subject is a customer or a supplier. Fakturoid calls them contacts in its own web interface.

**`fakturoid subjects list`** — `GET /accounts/{slug}/subjects.json`. Returns an array.

| Option | Meaning |
|---|---|
| `--since` | Created after this ISO 8601 date or datetime. |
| `--until` | Created before this ISO 8601 date or datetime. |
| `--updated-since` | Created or updated after this value. |
| `--updated-until` | Created or updated before this value. |
| `--custom-id` | Filter by your own identifier. |

Date values are passed through as typed, so a value the server rejects comes back as the server's own `400`.

**`fakturoid subjects search --query TEXT`** — `GET /accounts/{slug}/subjects/search.json`. The server looks at `name`, `full_name`, `email`, `email_copy`, `registration_no`, `vat_no` and `private_note`.

**`fakturoid subjects show ID`** — `GET /accounts/{slug}/subjects/{id}.json`. This is where the customer email address for a delivery mail comes from.

```bash
fakturoid subjects search --query acme | jq -r '.[] | "\(.id)\t\(.name)"'
fakturoid subjects show 55000123 | jq '{id, name, email, due}'
```

```json
{
  "id": 55000123,
  "name": "Acme s.r.o.",
  "email": "faktury@acme.example",
  "due": 14
}
```

### generators

A generator is an invoice template, not a schedule. Fakturoid calls a schedule a recurring generator, which is a different resource and is not modeled here.

**`fakturoid generators list`** — `GET /accounts/{slug}/generators.json`. Options: `--since`, `--updated-since`, `--subject-id`.

**`fakturoid generators show ID`** — `GET /accounts/{slug}/generators/{id}.json`.

**`fakturoid generators create`** — `POST /accounts/{slug}/generators.json`. The body comes from `--payload`, or from stdin. Requires `name` and `subject_id`.

**`fakturoid generators update ID`** — `PATCH /accounts/{slug}/generators/{id}.json`. A partial body is the point of the verb, so the schema requires no field at all.

**`fakturoid generators payload ID`** — reads the generator and prints an invoice-shaped payload. It performs no write of any kind, so it is a stdout filter. See [Working with generators](#working-with-generators).

```bash
fakturoid generators list | jq -r '.[] | "\(.id)\t\(.name)"'
```

```
100001	Acme monthly
100002	Acme support retainer
```

```bash
fakturoid generators create --payload '{
  "name": "Acme monthly",
  "subject_id": 55000123,
  "due": 14,
  "currency": "CZK",
  "language": "cz",
  "payment_method": "bank",
  "lines": [
    {"name": "Konzultace", "quantity": "10.0", "unit_name": "MD", "unit_price": "4500.0", "vat_rate": 21}
  ]
}'
```

The response is the created generator, including the assigned `id`, the computed `subtotal` and `total`, and a line `id` per line.

```bash
fakturoid generators update 100001 --payload '{"due": 21}'
echo '{"note": "Fakturujeme na základě smlouvy č. 2026/1."}' | fakturoid generators update 100001
```

There is no `generators delete`. Use the passthrough:

```bash
fakturoid api DELETE generators/100001.json
```

### invoices

**`fakturoid invoices list`** — `GET /accounts/{slug}/invoices.json`.

| Option | Meaning |
|---|---|
| `--since`, `--until` | Created within this ISO 8601 range. |
| `--updated-since`, `--updated-until` | Created or updated within this range. |
| `--subject-id` | Filter by customer id. |
| `--custom-id` | Filter by your own identifier. |
| `--number` | Filter by document number. |
| `--status` | `open`, `sent`, `overdue`, `paid`, `cancelled`, `uncollectible`. |
| `--document-type` | `regular`, `proforma`, `invoice`, `correction`, `tax_document`. |

The status and type values are sent as typed, so a value Fakturoid adds later works before this help text knows about it.

**`fakturoid invoices show ID`** — `GET /accounts/{slug}/invoices/{id}.json`. Yields `public_html_url`, the link you send to a customer.

**`fakturoid invoices create`** — `POST /accounts/{slug}/invoices.json`. **This consumes a document number permanently.** Fakturoid hands out the next number from the account's number format and never gives it back, so a deleted invoice still leaves a gap in the numbering. Requires `subject_id`. The invoice is created in `open` state, and nothing in this tool can move it out of that state or mail it.

**`fakturoid invoices update ID`** — `PATCH /accounts/{slug}/invoices/{id}.json`. Requires no field.

**`fakturoid invoices pdf ID`** — `GET /accounts/{slug}/invoices/{id}/download.pdf`. Writes the PDF to disk and prints a descriptor. Options `--pdf-wait` (default `15.0` seconds) and `--pdf-interval` (default `1.5` seconds) control the retry loop described in [File downloads](#file-downloads).

```bash
fakturoid invoices list --status open --subject-id 55000123 | jq -r '.[] | "\(.id)\t\(.number)\t\(.total)"'
```

```
61200042	2026-0042	55599.5
```

```bash
fakturoid invoices show 61200042 | jq -r '.public_html_url'
```

```
https://app.fakturoid.cz/example-account/p/aBcDeF0123456789/faktura-2026-0042
```

```bash
fakturoid invoices pdf 61200042
```

```json
{
  "path": "/tmp/fakturoid/invoice-61200042-20260831T184149.pdf",
  "content_type": "application/pdf",
  "bytes": 33517
}
```

Check the request before you spend a number:

```bash
fakturoid invoices create --dry-run --payload "$(cat /tmp/invoice.json)"
```

## The `fakturoid api` passthrough

`fakturoid api` is modeled on `glab api`. Use it for every endpoint that has no dedicated command, for every endpoint Fakturoid ships after this README was written, and whenever you need to send a body that the schema check would reject.

```
fakturoid api [METHOD] PATH [-X METHOD] [--payload JSON] [--input FILE|-] [-f key=value] [--paginate] [--include]
```

| Element | Behavior |
|---|---|
| `PATH` | Account-relative by default. `invoices.json` becomes `/accounts/{slug}/invoices.json`. |
| A path starting with `/` | Used verbatim under the API base, which is how `/user.json` is reached. A leading `/api/v3` is accepted and stripped. |
| A full `https://app.fakturoid.cz/api/v3/...` URL | Accepted as is, so a `url` field from a response can be pasted straight back in. Any other host is a usage error. |
| `:slug` and `{slug}` | Replaced with the effective slug, following the `glab` placeholder convention. |
| `METHOD` | Positional when given first, otherwise `-X`/`--method`. Giving it twice is a usage error. Defaults to `GET`, or to `POST` when a body is present. Allowed: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`. |
| `-f key=value` | Query parameter. Repeatable. This is the global option, so it works the same here as everywhere else. |
| `--payload JSON` | Request body as a JSON string. |
| `--input FILE` | Read the request body from a file. `--input -` reads stdin. |
| `--paginate` | Walk every page and print one merged array. `GET` only, and mutually exclusive with `--page`. |
| `--include` | Print the response status and headers to stderr as JSON. stdout still carries the body alone. |

Examples:

```bash
fakturoid api GET /user.json
fakturoid api GET invoices.json -f status=open -f subject_id=55000123
fakturoid api GET invoices.json --paginate
fakturoid api DELETE generators/100001.json
fakturoid api PATCH generators/100001.json --payload '{"note": "Platba na účet."}'
cat body.json | fakturoid api POST invoices.json --input -
fakturoid api GET invoices.json --include -f status=overdue
```

Non-JSON responses are written to disk here too, and the descriptor is printed instead of the bytes. The filename is built from the last two path segments, so `invoices/61200042/download.pdf` lands as `api-61200042-download-<timestamp>.pdf`.

The passthrough never lets a caller unset `User-Agent`, `Accept` or `Authorization`.

### A malformed id will not save you

Fakturoid parses the id segment of a path the way Rails does, so it reads the leading integer and ignores the rest. `DELETE generators/12345-oops.json` deletes generator `12345`. A typo after the number does not turn a destructive call into a harmless one, and neither does a trailing word you thought made the path invalid.

Check the id before sending a `DELETE`, and reach for `--dry-run` when you are unsure what a path resolves to.

## Request bodies

Four commands send a body: `invoices create`, `invoices update`, `generators create`, `generators update`. Plus `fakturoid api`, for any method that carries one.

**Precedence, on every one of them:**

1. `--payload` wins. stdin is not read at all, even when it is a pipe.
2. Otherwise, on `fakturoid api` only, `--input FILE` is read. `--input -` reads stdin.
3. Otherwise, if stdin is not a terminal, the whole of stdin is read.
4. Otherwise there is no body. For the four write commands that is a usage error, not an empty `POST`.

Invalid JSON from any source is a usage error, exit `2`, and nothing is sent.

The four write commands take `--payload` only. They have no `--input`, so a file goes in through the shell:

```bash
fakturoid invoices create --payload "$(cat /tmp/invoice.json)"
fakturoid invoices create < /tmp/invoice.json
```

For anything longer than one line, write the JSON to a file first and pipe it. It keeps the shell quoting out of the way and makes the payload editable.

## Payload validation

The four write endpoints check the request body against a JSON Schema before anything is sent. The point is narrow: an agent driving this CLI should fail loudly on a wrong value instead of quietly creating a broken financial document.

| Command | Endpoint | Required fields |
|---|---|---|
| `invoices create` | `POST /invoices.json` | `subject_id` |
| `invoices update` | `PATCH /invoices/{id}.json` | none |
| `generators create` | `POST /generators.json` | `name`, `subject_id` |
| `generators update` | `PATCH /generators/{id}.json` | none |

**The schemas are open-world.** Every one sets `additionalProperties: true`. An unknown field is never a validation failure, because Fakturoid ships fields before this tool models them.

**An unknown field warns on stderr and is sent anyway.** One line per field, nested paths included:

```bash
fakturoid invoices create --payload '{"subject_id": 55000123, "subject_di": 9, "lines": [{"name": "x", "quantyty": 1}]}'
```

```
warning: 'subject_di' is not a known field for POST /invoices.json - sending it anyway
warning: 'lines[0].quantyty' is not a known field for POST /invoices.json - sending it anyway
```

This is the load-bearing half of the design. An open-world schema cannot tell a genuinely new field from a misspelled known one, so `subject_di` would otherwise pass in silence. The warning makes the most likely mistake visible without closing the passthrough, and it goes to stderr, so a piped stdout stays clean.

**A wrong value on a known field stops the command with exit `2`.** Every offending field is named, with what was expected and what arrived. Nothing is sent.

```bash
fakturoid invoices create --payload '{"subject_id": 55000123, "due": "soon", "language": "klingon"}'
```

```
error: payload is not valid for POST /invoices.json
  due: 'soon' is not of type 'integer', 'null'
  language: 'klingon' is not one of ['cz', 'sk', 'en', 'de', 'fr', 'it', 'es', 'ru', 'pl', 'hu', 'ro']
Use 'fakturoid api' to send a body without validation.
```

**Requiredness stays minimal.** Types and enums are enforced freely, because they are known from the docs and from real responses. Requiredness is not: `PATCH` requires nothing, and `POST` requires only what the API plainly cannot default. A wrong `required` list blocks a request the server would have accepted, so the server stays the authority there.

### Why there is no `--no-validate` flag

`fakturoid api` is the escape hatch and the only one. It sends the body unvalidated, so a stale schema is never a hard blocker:

```bash
fakturoid api POST invoices.json --input /tmp/invoice.json
```

Keeping the bypass in a separate command makes it a deliberate act rather than a flag someone adds by reflex after the first false positive. It also keeps the dedicated commands honest: if you are on `invoices create`, the schema applies, with no exceptions to reason about. The cost is real and worth stating — when a schema is wrong, you must retype the command as an `api` call rather than add a flag.

## Pagination

Fakturoid serves 40 records per page through a `page` query parameter. There is no cursor and no `Link` header.

- **The default is one page.** A list command with no pagination option sends no `page` parameter and prints what the server returns.
- **`--page N`** fetches page `N` and prints that page alone.
- **`--all`** walks from page 1 and prints **one merged JSON array**, not a stream of arrays. It stops on the first short page.
- **`--page` with `--all`** is a usage error, exit `2`. On `fakturoid api`, `--paginate` is the same walk and clashes with `--page` the same way.

```bash
fakturoid invoices list --all | jq 'length'
fakturoid invoices list --page 3
```

Pages are requested serially, never in parallel. `--all` does not throttle itself. It runs flat out and surfaces exit code `8` when it hits the rate limit, which is 400 requests per 60 seconds. If any page fails, the whole command fails with that page's exit code and prints nothing to stdout, because a truncated array that looks complete is worse than an error.

## File downloads

A non-JSON response is written to disk and never to stdout.

- The default directory is `/tmp/fakturoid/`, created with mode `0700`. Files are written with mode `0600`. These are financial documents, and `/tmp` is world-readable on a shared machine.
- `--output-dir` overrides the directory.
- The filename is `<resource>-<identifier>-<timestamp>.<ext>`, for example `invoice-61200042-20260831T184149.pdf`. The extension comes from the response `Content-Type` and falls back to `.bin`.
- stdout gets the descriptor:

```json
{
  "path": "/tmp/fakturoid/invoice-61200042-20260831T184149.pdf",
  "content_type": "application/pdf",
  "bytes": 33517
}
```

**The 204 retry loop.** `GET /invoices/{id}/download.pdf` answers `200` with the PDF, or `204` with an empty body when the PDF is not generated yet. On a `204`, `invoices pdf` waits `--pdf-interval` seconds and asks again, until `--pdf-wait` seconds run out. It then exits `11`, the asset-not-ready code, rather than reporting success with no file.

```bash
fakturoid invoices pdf 61200042 --output-dir ~/Documents/invoices --pdf-wait 60
```

To pull the path straight out of the descriptor:

```bash
PDF=$(fakturoid invoices pdf 61200042 | jq -r '.path')
```

## Exit codes

| Code | Condition |
|---|---|
| 0 | Success. A `204` with an empty body counts as success. |
| 1 | Unexpected internal error. A stack trace goes to stderr. |
| 2 | Usage error. Unknown option, missing required option, missing or invalid JSON body, a payload the schema rejects, `--page` with `--all`. |
| 3 | Configuration error. Credentials missing, unreadable or malformed, or no account slug available. |
| 4 | Authentication or authorization failure. `401` that survives one token refetch, or `403`. |
| 5 | Not found. `404`. |
| 6 | Validation error from the server. `422`. The `{"errors": {...}}` body goes to stderr verbatim. |
| 7 | Other client error. `400`, `405`, `409`, `415`, and any other 4xx. |
| 8 | Rate limited. `429`. `X-RateLimit-Policy` and `X-RateLimit` are echoed to stderr when present. |
| 9 | Server error. 5xx, including the `503` the search endpoints answer when they are busy. |
| 10 | Network failure. DNS, connection refused, TLS, or timeout. Nothing reached the server. |
| 11 | Asset not ready. A download still answered `204` after `--pdf-wait` expired. |
| 12 | Payment required. `402`. The Fakturoid account itself is blocked for non-payment, which is a different problem from a bad request. |

Codes `2` and `6` both mean "the body was wrong". Code `2` means this CLI rejected it and sent nothing. Code `6` means the server rejected it.

For every non-2xx, the CLI prints Fakturoid's own JSON error body to stderr, unmodified and unwrapped. If the body is not JSON, the raw text goes out instead.

## Working with generators

This is the loop the tool exists for: turn a template into this month's invoice.

Fakturoid has **no server-side generate-from-template endpoint** in API v3. The web interface has a button, the API does not. So the mapping from a generator to an invoice payload happens here, in `fakturoid generators payload`, and it is a pure transform over a JSON document that reaches the network only to read the generator.

```bash
# 1. Find the template.
fakturoid generators list | jq -r '.[] | "\(.id)\t\(.name)"'

# 2. Turn it into an invoice payload.
fakturoid generators payload 100001 > /tmp/invoice.json

# 3. Edit /tmp/invoice.json for the month: the quantity, the note, the dates.
$EDITOR /tmp/invoice.json

# 4. Check the request without spending a document number.
fakturoid invoices create --dry-run < /tmp/invoice.json

# 5. Create it. This consumes a document number permanently.
fakturoid invoices create < /tmp/invoice.json > /tmp/created.json

# 6. Collect what a delivery mail needs.
ID=$(jq -r '.id' /tmp/created.json)
fakturoid invoices show "$ID" | jq -r '.public_html_url'
fakturoid invoices pdf "$ID" | jq -r '.path'
```

### What `generators payload` does, and why it exists

A generator response is not an invoice payload. Two things in it will break the new document, and nothing in the response marks them:

- **Line ids.** A generator line carries an `id` that points at a row of the template. Sent to `POST /invoices.json`, that id means "update the invoice line with this id", which is not a row that belongs to the new invoice.
- **Computed fields.** `unit_price_without_vat`, `unit_price_with_vat`, `total_price_without_vat`, `total_vat`, every `native_*` field, `subtotal`, `total` and `rounding_adjustment` are the server's own arithmetic. Sending them back fights it.

`generators payload` drops both, plus the `inventory` block on each line. A line keeps `name`, `quantity`, `unit_name`, `unit_price` and `vat_rate` and nothing else.

It carries over `subject_id`, `lines`, `due`, `payment_method`, `currency`, `language`, `note`, `footer_note`, `number_format_id`, `bank_account_id`, `tags` and `order_number`. A `null` value is **omitted entirely** rather than sent as an explicit `null`, because an explicit `null` overrides an account default the server would otherwise apply.

A generator says "this is a proforma" with a boolean `proforma`. An invoice says it with `document_type`. When the generator's `proforma` is true, the payload carries `"document_type": "proforma"` instead. When it is false, the field stays absent, because the server already defaults to a regular invoice.

```bash
fakturoid generators payload 100001
```

```json
{
  "subject_id": 55000123,
  "lines": [
    {
      "name": "Konzultace",
      "quantity": "10.0",
      "unit_name": "MD",
      "unit_price": "4500.0",
      "vat_rate": 21
    },
    {
      "name": "Cestovné",
      "quantity": "1.0",
      "unit_price": "950.0",
      "vat_rate": 21
    }
  ],
  "due": 14,
  "payment_method": "bank",
  "currency": "CZK",
  "language": "cz"
}
```

The transform writes nothing and touches no invoice. Run it as often as you like.

## Not implemented yet

Everything below is reachable through `fakturoid api` and has no dedicated command.

| Area | Reach it with |
|---|---|
| Delete an invoice | `fakturoid api DELETE invoices/61200042.json` |
| Fire an invoice action (`mark_as_sent`, `cancel`, `lock`, ...) | `fakturoid api POST 'invoices/61200042/fire.json?event=mark_as_sent'` — the event goes in the query string, not the body |
| Send an invoice by email | `fakturoid api POST invoices/61200042/message.json --payload '...'` |
| Invoice and expense payments | `fakturoid api POST invoices/61200042/payments.json --payload '...'` |
| Expenses | `fakturoid api GET expenses.json` |
| Recurring generators | `fakturoid api GET recurring_generators.json` |
| Delete a generator | `fakturoid api DELETE generators/100001.json` |
| Inbox files | `fakturoid api GET inbox_files.json` |
| Events | `fakturoid api GET events.json` |
| Bank accounts | `fakturoid api GET bank_accounts.json` |
| Number formats | `fakturoid api GET number_formats/invoices.json` |
| Inventory items and moves | `fakturoid api GET inventory_items.json` |
| Todos | `fakturoid api GET todos.json` |
| Webhooks | `fakturoid api GET webhooks.json` |
| Subject create, update and delete | `fakturoid api POST subjects.json --payload '...'` |
| Invoice and expense attachments | `fakturoid api GET invoices/61200042/attachments/700123/download` |

Two omissions are deliberate rather than pending. `invoices fire` and `invoices message` stay out of the dedicated surface, so no command in this tool can email a document to a customer or change its status by accident. Reaching them through `api` is an explicit act.

The bodies these endpoints take are not schema-checked, because `fakturoid api` never validates. Read the [Fakturoid API v3 documentation](https://www.fakturoid.cz/api/v3) for their shapes.

## Project structure

```
src/fakturoidcli/
  cli.py              entry point, global options, argv hoisting, exit-code mapping
  config.py           TOML profiles, env overrides, 0600 handling
  cache.py            OAuth access-token cache with an absolute expiry
  constants.py        base URL, timeouts, page size, file modes
  context.py          the global options of one invocation, lazy client
  errors.py           exception hierarchy and the exit code each failure maps to
  logging.py          Rich logging, stderr only
  output.py           json_out, stderr helpers, download descriptors
  payload.py          request-body precedence between --payload and stdin
  transforms.py       generator to invoice payload
  validation.py       open-world schema check with unknown-field warnings
  schemas/            one JSON Schema file per write resource
  client/
    base.py           httpx client, paths, pagination, downloads, dry run
    auth.py           OAuth2 client_credentials flow
  commands/
    common.py         shared get/list/write plumbing
    api.py            the raw passthrough
    users.py account.py subjects.py generators.py invoices.py
tests/                pytest, pure functions only, no HTTP mocking
integration/          bash script against a real account
```

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The unit tests cover pure functions only: the generator-to-invoice transform, query-parameter serialization, path building, filename construction, payload precedence, schema validation, and JSON output under a narrow `COLUMNS`. There is no HTTP mocking and no cassette framework, on purpose.

The HTTP layer is covered by a real end-to-end script:

```bash
integration/integration-test.sh
FAKTUROID="uv run fakturoid" integration/integration-test.sh
```

The script is safe to run repeatedly. It reads freely, and it writes only on generators, which carry no document number. **It never creates, updates or deletes an invoice**, because creating one consumes a document number permanently. It creates one clearly named test template, updates it, deletes it through `fakturoid api DELETE`, confirms it is gone, and removes it in a cleanup trap even when a step fails.

## License

MIT. See [LICENSE](LICENSE).
