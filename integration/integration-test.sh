#!/usr/bin/env bash
#
# Integration test for fakturoid-cli, run against a real Fakturoid account.
#
# The script is safe to run repeatedly. It reads freely and writes only on
# generators, which are invoice templates and carry no document number.
#
# IT NEVER CREATES, UPDATES OR DELETES AN INVOICE. Creating an invoice consumes
# a document number permanently: Fakturoid hands out the next number from the
# account's number format and never gives it back, so a deleted test invoice
# still leaves a gap in the numbering that a tax audit can see. Invoice writes
# stay a manual step the author performs on purpose.
#
# Usage:
#   integration/integration-test.sh
#   FAKTUROID="uv run fakturoid" integration/integration-test.sh
#   FAKTUROID_PROFILE=other integration/integration-test.sh
#
# Exit code 0 means every step passed. Any other code means at least one step
# produced an unexpected result. Every command's stdout and stderr is kept in a
# temporary directory whose path is printed at the end.

set -euo pipefail

FAKTUROID=${FAKTUROID:-fakturoid}
OUT_DIR=$(mktemp -d "/tmp/fakturoid-integration-$(date +%Y%m%d-%H%M%S)-XXXXXX")

STEP=0
FAILURES=0
GENERATOR_ID=""
TEST_NAME="fakturoid-cli integration test $(date +%Y%m%dT%H%M%S)"

for tool in jq; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: %s is required\n' "$tool" >&2
        exit 1
    }
done

# ------------------------------------------------------------------ helpers

step() {
    STEP=$((STEP + 1))
    printf '\n[%02d] %s\n' "$STEP" "$1"
}

pass() {
    printf '     ok: %s\n' "$1"
}

record_fail() {
    FAILURES=$((FAILURES + 1))
    printf '     FAIL: %s\n' "$1" >&2
}

# run_json <label> <jq-assertion> -- <command...>
#
# Runs the command, keeps stdout and stderr, and requires exit code 0, parseable
# JSON on stdout, and a true jq assertion. Sets OUT to the stdout file so a
# caller can read a value out of it.
run_json() {
    local label="$1" assertion="$2"
    shift 2
    [[ "$1" == "--" ]] && shift

    OUT="$OUT_DIR/$(printf '%02d' "$STEP")-${label}.json"
    local err="${OUT%.json}.stderr"
    local status=0

    "$@" >"$OUT" 2>"$err" </dev/null || status=$?
    if [[ $status -ne 0 ]]; then
        record_fail "${label}: exit ${status}, see ${err}"
        return 1
    fi

    if ! jq -e "$assertion" "$OUT" >/dev/null 2>&1; then
        record_fail "${label}: assertion '${assertion}' failed, see ${OUT}"
        return 1
    fi

    pass "$label"
    return 0
}

# expect_exit <label> <expected-code> -- <command...>
expect_exit() {
    local label="$1" expected="$2"
    shift 2
    [[ "$1" == "--" ]] && shift

    local out="$OUT_DIR/$(printf '%02d' "$STEP")-${label}.json"
    local status=0

    "$@" >"$out" 2>"${out%.json}.stderr" </dev/null || status=$?
    if [[ $status -ne $expected ]]; then
        record_fail "${label}: expected exit ${expected}, got ${status}, see ${out%.json}.stderr"
        return 1
    fi

    pass "${label} (exit ${expected})"
    return 0
}

# Deletes the test generator even when a step above failed, so a broken run does
# not leave a template behind in the account.
cleanup() {
    local exit_code=$?
    if [[ -n "$GENERATOR_ID" ]]; then
        printf '\ncleanup: deleting leftover test generator %s\n' "$GENERATOR_ID"
        if $FAKTUROID api DELETE "generators/${GENERATOR_ID}.json" \
            >"$OUT_DIR/cleanup.json" 2>"$OUT_DIR/cleanup.stderr"; then
            printf 'cleanup: deleted\n'
        else
            printf 'cleanup: FAILED to delete generator %s, delete it by hand\n' "$GENERATOR_ID" >&2
            exit_code=1
        fi
    fi
    printf '\noutput kept in %s\n' "$OUT_DIR"
    exit "$exit_code"
}
trap cleanup EXIT

printf 'fakturoid-cli integration test\n'
printf 'command: %s\n' "$FAKTUROID"
printf 'output:  %s\n' "$OUT_DIR"

# ------------------------------------------------------------- read-only

step 'users me - credentials resolve and list the reachable accounts'
run_json users-me '.accounts | type == "array"' -- $FAKTUROID users me || true

step 'account show - the slug resolves to an account'
run_json account-show '.subdomain != null or .name != null' -- $FAKTUROID account show || true

step 'subjects list - the customer list is an array'
SUBJECT_ID=""
if run_json subjects-list 'type == "array"' -- $FAKTUROID subjects list; then
    SUBJECT_ID=$(jq -r '.[0].id // empty' "$OUT")
    printf '     first subject id: %s\n' "${SUBJECT_ID:-none}"
fi

if [[ -n "$SUBJECT_ID" ]]; then
    step "subjects show ${SUBJECT_ID} - one customer reads back"
    run_json subjects-show ".id == ${SUBJECT_ID}" -- $FAKTUROID subjects show "$SUBJECT_ID" || true
fi

step 'generators list - the template list is an array'
run_json generators-list 'type == "array"' -- $FAKTUROID generators list || true

step 'invoices list --page 1 - one page of invoices'
INVOICE_ID=""
if run_json invoices-list 'type == "array"' -- $FAKTUROID invoices list --page 1; then
    INVOICE_ID=$(jq -r '.[0].id // empty' "$OUT")
    printf '     first invoice id: %s\n' "${INVOICE_ID:-none}"
fi

if [[ -n "$INVOICE_ID" ]]; then
    step "invoices show ${INVOICE_ID} - one invoice reads back (READ ONLY)"
    run_json invoices-show ".id == ${INVOICE_ID}" -- $FAKTUROID invoices show "$INVOICE_ID" || true
fi

step 'invoices create --dry-run - describes the request and sends nothing'
run_json invoices-dry-run '.method == "POST" and (.url | endswith("/invoices.json")) and .headers.Authorization == "Bearer <redacted>"' \
    -- $FAKTUROID invoices create --dry-run --payload '{"subject_id":1}' || true

# ---------------------------------------------------------------- writes

if [[ -z "$SUBJECT_ID" ]]; then
    printf '\nskipping the write steps: the account has no subject to bill\n' >&2
    FAILURES=$((FAILURES + 1))
else
    step 'generators create - the only resource this script writes to'
    CREATE_PAYLOAD=$(
        jq -n --arg name "$TEST_NAME" --argjson subject "$SUBJECT_ID" '{
            name: $name,
            subject_id: $subject,
            due: 14,
            currency: "CZK",
            language: "cz",
            payment_method: "bank",
            lines: [{
                name: "fakturoid-cli integration test line",
                quantity: "1.0",
                unit_name: "ks",
                unit_price: "1.0",
                vat_rate: 21
            }]
        }'
    )
    if run_json generators-create ".name == \"${TEST_NAME}\"" \
        -- $FAKTUROID generators create --payload "$CREATE_PAYLOAD"; then
        GENERATOR_ID=$(jq -r '.id' "$OUT")
        printf '     test generator id: %s\n' "$GENERATOR_ID"
    fi

    if [[ -n "$GENERATOR_ID" ]]; then
        step "generators update ${GENERATOR_ID} - body read from stdin"
        UPDATE_NOTE="updated by the integration test at $(date +%H:%M:%S)"
        OUT="$OUT_DIR/$(printf '%02d' "$STEP")-generators-update.json"
        UPDATE_STATUS=0
        jq -n --arg note "$UPDATE_NOTE" '{note: $note}' |
            $FAKTUROID generators update "$GENERATOR_ID" \
                >"$OUT" 2>"${OUT%.json}.stderr" || UPDATE_STATUS=$?
        if [[ $UPDATE_STATUS -ne 0 ]]; then
            record_fail "generators-update: exit ${UPDATE_STATUS}, see ${OUT%.json}.stderr"
        elif ! jq -e ".note == \"${UPDATE_NOTE}\"" "$OUT" >/dev/null 2>&1; then
            record_fail "generators-update: the note did not come back, see ${OUT}"
        else
            pass 'generators-update'
        fi

        step "generators payload ${GENERATOR_ID} - pure transform, writes nothing"
        run_json generators-payload \
            '.subject_id != null and (.lines | length) > 0 and (.lines[0] | has("id") | not)' \
            -- $FAKTUROID generators payload "$GENERATOR_ID" || true

        DELETED_ID="$GENERATOR_ID"
        step "api DELETE generators/${DELETED_ID}.json - the passthrough removes it"
        DELETE_STATUS=0
        $FAKTUROID api DELETE "generators/${DELETED_ID}.json" \
            >"$OUT_DIR/$(printf '%02d' "$STEP")-generators-delete.json" \
            2>"$OUT_DIR/$(printf '%02d' "$STEP")-generators-delete.stderr" </dev/null || DELETE_STATUS=$?
        if [[ $DELETE_STATUS -ne 0 ]]; then
            record_fail "generators-delete: exit ${DELETE_STATUS}, the cleanup trap will try again"
        else
            # Nothing is left in the account, so the cleanup trap has no work.
            GENERATOR_ID=""
            pass 'generators-delete'

            step "generators show ${DELETED_ID} - confirms it is gone (exit 5)"
            expect_exit generators-show-gone 5 -- $FAKTUROID generators show "$DELETED_ID" || true
        fi
    fi
fi

# --------------------------------------------------------------- summary

printf '\n%d step(s) run, %d failure(s)\n' "$STEP" "$FAILURES"
if [[ $FAILURES -ne 0 ]]; then
    exit 1
fi
