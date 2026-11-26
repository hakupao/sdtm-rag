"""Rule 5 mutation run for the P2.9 fix round. Each mutant: break one new check, run the named
tests, expect FAIL; restore. Self-proof (docs/RULES.md rule 5 + supplement):
  - every target file's sha256 is frozen at start; a mutant refuses to run if the disk differs;
  - the old snippet must occur exactly once; after writing, the file is re-read and must contain the
    new snippet and have a sha different from the original;
  - restore writes the frozen original BYTES (never `git checkout --`) in `finally`, then re-checks
    the sha; a final pass verifies every file is byte-identical to the frozen snapshot.
Run from the repo root on a clean tree: .venv/bin/python <this file>"""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
F, E = "tests/test_p2_9_fixes.py", "tests/test_p2_9_public_e2e.py"
Q, I = "tests/test_p2_l2_quota.py", "tests/test_p2_l2_integration.py"  # noqa: E741
NODE = "node:webchat/tests/markdown.test.mjs"

M = [
    ("#1a streamed tokens priced", "server/quota.py",
     "out = math.ceil(1.5 * n)", "out = 0",
     [E + "::test_usage_less_normal_end_charges_streamed_heuristic",
      Q + "::test_streamed_reasoning_and_tool_args_count"]),
    ("#1b usage-less stream not charged full", "server/quota.py",
     "elif streamed_text is not None and purpose != \"web\":", "elif False:",
     [Q + "::test_aborted_stream_is_charged_prompt_plus_streamed_not_the_reservation",
      E + "::test_usage_less_normal_end_charges_streamed_heuristic"]),
    ("#1c reasoning counted", "server/outbound.py",
     "for attr in (\"content\", \"reasoning_content\"):", "for attr in (\"content\",):",
     [Q + "::test_streamed_reasoning_and_tool_args_count"]),
    ("#1d narrow-retry refund (clear only)", "server/outbound.py",
     "        if clear and refund_open_error:\n", "        if refund_open_error:\n",
     [Q + "::test_stream_open_failure_charge_follows_how_clear_the_rejection_is"]),
    ("#1e clear open failure prompt-only", "server/outbound.py", "        elif clear:\n",
     "        elif False:\n", [Q + "::test_stream_open_failure_charge_follows_how_clear_the_rejection_is"]),
    ("#1f router passes refund flag", "server/router.py",
     "                                              refund_open_error=True)",
     "                                              refund_open_error=False)",
     [F + "::test_narrow_retry_spends_one_round"]),
    ("#1g abort buffer on early close", "server/quota.py",
     "            out = max(out, n + int(cfg(s, \"quota_abort_buffer_tokens\")))\n",
     "            pass\n", [Q + "::test_aborted_stream_is_charged_prompt_plus_streamed_not_the_reservation"]),
    ("#1h early close detected", "server/outbound.py", "        end = \"closed\"\n",
     "        end = \"done\"\n", [Q + "::test_aborted_stream_is_charged_prompt_plus_streamed_not_the_reservation"]),
    ("#1g' abort buffer (e2e real disconnect)", "server/quota.py",
     "            out = max(out, n + int(cfg(s, \"quota_abort_buffer_tokens\")))\n",
     "            pass\n", [E + "::test_client_closing_the_stream_early_settles_partial"]),
    ("N2 validate non-finite / negative", "server/quota.py",
     "                and (not math.isfinite(v) or v < 0):", "                and False:",
     [F + "::test_validate_rejects_non_finite_and_negative"]),
    ("N3 APIConnectionError clear only if never connected", "server/outbound.py",
     "        return _caused_by(e, httpx.ConnectError)", "        return True",
     [F + "::test_api_connection_error_clear_only_when_never_connected"]),
    ("N3b cause chain walked", "server/outbound.py",
     "        if isinstance(cur, cls):\n            return True", "        if False:\n            return True",
     [F + "::test_api_connection_error_clear_only_when_never_connected"]),
    ("#1i mid-stream exception keeps full", "server/outbound.py",
     "        if end == \"error\":\n", "        if False:\n",
     [E + "::test_upstream_exception_mid_stream_keeps_the_full_reservation",
      I + "::test_aborted_stream_is_still_charged"]),
    ("#1j timeouts statuses ambiguous", "server/outbound.py",
     "        return status not in (408, 504)", "        return True",
     [Q + "::test_stream_open_failure_charge_follows_how_clear_the_rejection_is"]),
    ("#1k unknown open errors ambiguous", "server/outbound.py",
     "    return isinstance(e, httpx.ConnectError)", "    return True",
     [Q + "::test_stream_open_failure_charge_follows_how_clear_the_rejection_is",
      Q + "::test_cancelled_open_keeps_the_full_reservation"]),
    ("#2a public never unmetered", "server/auth.py",
     "        if public:\n            raise RuntimeError(\"public tier refuses to start unmetered",
     "        if False:\n            raise RuntimeError(\"public tier refuses to start unmetered",
     [F + "::test_public_refuses_to_start_unmetered", E + "::test_quota_off_refuses_to_start"]),
    ("#2b strict bool", "server/quota.py", "        if v in _FALSE:\n            return False\n",
     "        if True:\n            return False\n",
     [F + "::test_quota_bool_typo_raises_not_false", E + "::test_quota_off_refuses_to_start"]),
    ("#3 unknown quota env", "server/quota.py", "        if unknown:\n", "        if False:\n",
     [F + "::test_validate_refuses_misspelt_key_when_enabled_and_masks_secret"]),
    ("#3b validate called at startup", "server/auth.py",
     "    eff = quota.validate(settings)", "    eff = {}",
     [E + "::test_quota_off_refuses_to_start"]),
    ("#4a explicit SELECTABLE_MODELS", "server/instance.py",
     "if \"selectable_models\" not in s.model_fields_set:", "if False:",
     [F + "::test_public_requires_explicit_selectable_models"]),
    ("#4b explicit max_output_tokens", "server/instance.py",
     "if \"max_output_tokens\" not in m.model_fields_set:", "if False:",
     [F + "::test_public_model_needs_explicit_max_output_and_a_bounded_round"]),
    ("#4c round <= free pool / 10", "server/instance.py", "        if est > budget:",
     "        if False:", [F + "::test_public_model_needs_explicit_max_output_and_a_bounded_round"]),
    ("#4d security headers", "server/instance.py", "    if not s.security_headers_enabled:",
     "    if False:", [F + "::test_public_requires_security_headers"]),
    ("#5 site_busy vs cap", "server/quota.py",
     "if store.settled(day, pool) + est <= cap + 1e-9:", "if False:",
     [F + "::test_reserve_refusal_busy_vs_cap"]),
    ("#6 trusted proxies narrow", "server/auth.py",
     "if n.prefixlen < _MIN_TRUSTED_PREFIX[n.version]]", "if False]",
     [F + "::test_public_trusted_proxies_must_be_narrow"]),
    ("#7a global RL keyed on visitor", "server/auth.py", "        if self.trusted is not None:\n",
     "        if False:\n", [F + "::test_public_global_rate_limit_keys_on_cf_connecting_ip"]),
    ("#7b trust_forwarded refused", "server/auth.py",
     "    if public and settings.rate_limit_trust_forwarded:", "    if False:",
     [F + "::test_public_refuses_rate_limit_trust_forwarded"]),
    ("#10a in-flight cap", "server/quota.py", "        if len(slots) >= cap:\n",
     "        if False:\n", [F + "::test_inflight_cap_per_ip_released_by_finalize"]),
    ("#10b in-flight release", "server/quota.py", "            slots.pop(tok, None)     # idempotent\n",
     "            pass\n", [F + "::test_inflight_cap_per_ip_released_by_finalize",
                          F + "::test_refused_admit_releases_its_slot"]),
    ("#10c in-flight TTL", "server/quota.py", "if now - t0 < ttl}", "if True}",
     [F + "::test_inflight_slot_expires_if_finalize_never_runs"]),
    ("#11a flag file cap", "server/quota.py",
     "    if size + nbytes > int(cfg(s, \"flag_file_max_bytes\")):", "    if False:",
     [F + "::test_flag_per_ip_daily_bytes_and_file_cap"]),
    ("#11b flag per-IP bytes", "server/quota.py",
     "    if not _store(s).take([(f\"fb:{ip}\", int(cfg(s, \"flag_bytes_per_ip_day\")))], _day(), nbytes):",
     "    if False:", [F + "::test_flag_per_ip_daily_bytes_and_file_cap"]),
    ("#11c flag endpoint calls admit_flag", "server/router.py",
     "    quota.admit_flag(request, len(entry.encode(\"utf-8\")))", "    pass",
     [F + "::test_flag_per_ip_daily_bytes_and_file_cap"]),
    ("#12a stdlib message redaction", "server/providers.py",
     "record.msg, record.args = redact_text(msg, secrets), None", "record.msg, record.args = msg, None",
     [F + "::test_stdlib_child_logger_record_is_redacted_on_root_handler"]),
    ("#12b stdlib exc_text redaction", "server/providers.py",
     "                record.exc_text = redact_text(record.exc_text, secrets)\n",
     "                pass\n", [F + "::test_stdlib_child_logger_record_is_redacted_on_root_handler"]),
    ("#12c public loggers at WARNING", "server/providers.py",
     "        if public and lg.getEffectiveLevel() < logging.WARNING:", "        if False:",
     [F + "::test_public_holds_third_party_loggers_at_warning"]),
    ("#13 continue refusal keeps parts", "server/router.py",
     "                    if purpose != \"continue\":\n                        raise",
     "                    if True:\n                        raise",
     [I + "::test_cap_hit_mid_request_keeps_the_partial_answer"]),
    ("#14a free web single owner", "server/providers.py",
     "if default and ctx.credentials is None and not quota.free_web_allowed(ctx):", "if False:",
     [E + "::test_free_web_is_downgraded_once_and_reported_off", I + "::test_free_stream_gets_no_web"]),
    ("#14b key actually enables web", "server/quota.py",
     "    return bool(cfg(s, \"quota_free_web_enabled\"))", "    return False",
     [E + "::test_free_web_key_actually_enables_web",
      Q + "::test_byok_not_counted_free_web_policy_owned_by_l1"]),
    ("#14c web_status off on downgrade", "server/router.py",
     "if not body.web or (s.web_search_enabled and not use_web):", "if not body.web:",
     [E + "::test_free_web_is_downgraded_once_and_reported_off"]),
    ("#15a bad-key probing gate", "server/quota.py", "    if store.count(key, day) >= limit:",
     "    if False:", [F + "::test_bad_byok_keys_per_ip_are_capped",
                       F + "::test_upstream_401_counts_as_bad_key"]),
    ("#15b upstream 401 counted", "server/providers.py",
     "            from server import quota\n\n            quota.note_bad_key(ctx)\n",
     "            pass\n", [F + "::test_upstream_401_counts_as_bad_key"]),
    ("#15c format-invalid key counted", "server/providers.py",
     "        quota.note_bad_key(ctx)\n        raise ServiceRefusal(401",
     "        raise ServiceRefusal(401", [F + "::test_bad_byok_keys_per_ip_are_capped"]),
    ("#15d BYOK side budget per IP", "server/quota.py",
     "if not store.take([(key, int(float(cfg(s, \"quota_byok_side_per_ip_usd\")) * 1e6))], day, micros):",
     "if False:", [F + "::test_byok_side_budget_is_shared_per_ip"]),
    ("#15e side counter settled to actual", "server/quota.py",
     "if store.settle(handle, actual) and entry.sub:",
     "if store.settle(handle, actual) and False:", [F + "::test_byok_side_budget_is_shared_per_ip"]),
    ("#16 prune", "server/quota_store.py",
     "                self._db.execute(f\"DELETE FROM {table} WHERE day < ?\", (before_day,))\n",
     "                pass\n", [F + "::test_store_prunes_old_days_once_per_day"]),
    ("#17 trust_env=False", "server/provider_registry_net.py",
     "                        timeout=timeout, trust_env=False)", "                        timeout=timeout)",
     [F + "::test_pinned_client_does_not_trust_env"]),
    ("#18 info no-store", "server/instance.py", "headers={\"Cache-Control\": \"no-store\"}", "headers={}",
     [E + "::test_public_info_is_not_cacheable"]),
    ("#19 FORBID_TAGS passed", "webchat/js/markdown.js",
     "return DOMPurify.sanitize(marked.parse(md || \"\"), SANITIZE_CONFIG);",
     "return DOMPurify.sanitize(marked.parse(md || \"\"));", [NODE]),
    ("#20 compare cancels siblings", "server/compare.py", "            t.cancel()\n", "            pass\n",
     [F + "::test_compare_cancels_siblings_on_refusal"]),
    ("#21 web counter untaken", "server/quota.py",
     "        if web_taken:\n            store.untake(*web_taken)\n        if sub:",
     "        if sub:", [F + "::test_byok_web_counter_untaken_when_cap_refuses"]),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
frozen = {rel: (ROOT / rel).read_bytes() for rel in {m[1] for m in M}}
frozen_sha = {rel: hashlib.sha256(b).hexdigest() for rel, b in frozen.items()}
rows = []
for name, rel, old, new, tests in M:
    p = ROOT / rel
    if sha(p) != frozen_sha[rel]:
        sys.exit(f"REFUSE {name}: {rel} differs from the frozen snapshot before mutating")
    src = frozen[rel].decode("utf-8")
    assert src.count(old) == 1, (name, src.count(old))
    try:
        p.write_text(src.replace(old, new), encoding="utf-8")
        back = p.read_text(encoding="utf-8")
        assert new in back and sha(p) != frozen_sha[rel], f"{name}: mutation did not land"
        for d in ROOT.rglob("__pycache__"):
            if ".venv" not in d.parts and "vendor" not in d.parts:
                shutil.rmtree(d, ignore_errors=True)
        if tests == [NODE]:
            cmd = ["node", "--test", NODE.split(":", 1)[1]]
        else:
            cmd = [str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "-o", "addopts=", *tests]
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        out = r.stdout.strip().splitlines()
        tail = next((ln for ln in reversed(out) if "passed" in ln or "failed" in ln or ln.startswith("ℹ fail")),
                    (out[-1] if out else r.stderr[-200:]))
        rows.append((name, rel, r.returncode != 0, tail.strip()))
    finally:
        p.write_bytes(frozen[rel])
        assert sha(p) == frozen_sha[rel], f"{name}: restore failed"
for rel, h in frozen_sha.items():
    assert sha(ROOT / rel) == h, f"final check: {rel} not restored"
for name, rel, killed, tail in rows:
    print(f"| {name} | {rel} | {'KILLED' if killed else 'SURVIVED'} | {tail} |")
print(f"{sum(k for _, _, k, _ in rows)}/{len(rows)} killed; all files restored byte-identical")
sys.exit(0 if all(k for _, _, k, _ in rows) else 1)
