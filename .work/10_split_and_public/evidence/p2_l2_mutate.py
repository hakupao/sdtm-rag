"""Rule 5 mutation run for P2 L2: break each check, expect the named tests to fail, restore."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # repo root
U, I = "tests/test_p2_l2_quota.py", "tests/test_p2_l2_integration.py"  # noqa: E741
M = [
    ("M1 free-count limit", "server/quota_store.py", "if (row[0] if row else 0) + n > limit:",
     "if (row[0] if row else 0) + n > limit + 1:", [U + "::test_take_is_atomic_across_threads",
                                           I + "::test_n_plus_1_question_is_429_with_quota_fields"]),
    ("M2 cap in reserve SQL", "server/quota_store.py", "(? IS NULL OR usd + ? <= ? + 1e-9)",
     "(? IS NULL OR ? > -1 OR ? > -1)", [U + "::test_reserve_never_exceeds_cap_across_threads",
                                        I + "::test_cap_hit_mid_request_refuses_continuation"]),
    ("M3 settle idempotency (store)", "server/quota_store.py",
     "\"SELECT day, usd FROM reservations WHERE id=? AND status='open'\",\n                                       (rid,)).fetchone()\n                cur = self._db.execute(\n                    \"UPDATE reservations SET status='settled' WHERE id=? AND status='open'\"",
     "\"SELECT day, usd FROM reservations WHERE id=?\",\n                                       (rid,)).fetchone()\n                cur = self._db.execute(\n                    \"UPDATE reservations SET status='settled' WHERE id=?\"",
     [U + "::test_settle_close_expire_are_idempotent"]),
    ("M4 cookie signature", "server/auth.py", "return self.signer.unsign(raw).decode(\"ascii\")",
     "return raw.rsplit('.', 1)[0]", [I + "::test_tampered_cookie_is_a_new_visitor"]),
    ("M5 proxy trust", "server/auth.py",
     "if not nets or not any(ipaddress.ip_address(peer) in n for n in nets):",
     "if not nets:", [I + "::test_cf_connecting_ip_only_trusted_from_tunnel_peer"]),
    ("M6 body limit (content-length)", "server/auth.py", "if declared > self.limit:", "if False:",
     [I + "::test_declared_oversized_body_is_refused_without_reading_it"]),
    ("M7 body limit (chunked)", "server/auth.py", "if total > self.limit:", "if False:",
     [I + "::test_body_too_large_is_413"]),
    ("M8 flag rate limit", "server/auth.py",
     "ok, retry = self.limiter.allow(resolve_client_ip(scope, self.trusted, self.v6_prefix))\n        if ok:",
     "ok, retry = self.limiter.allow(resolve_client_ip(scope, self.trusted, self.v6_prefix))\n        if True:",
     [I + "::test_flag_rate_limited"]),
    ("M9 visitor secret required", "server/auth.py", "    if not secret:\n", "    if False:\n",
     [I + "::test_enabled_without_secret_fails_at_startup"]),
    ("M10 history trim", "server/quota.py",
     "if len(kept) >= max_messages or total + n > max_chars:", "if False:",
     [U + "::test_trim_keeps_last_8", I + "::test_oversized_history_is_trimmed"]),
    ("M11 kill switch", "server/quota.py", "if cfg(s, \"free_tier_disabled\"):", "if False:",
     [I + "::test_kill_switch_disables_free_not_byok"]),
    ("M12 admit cap", "server/quota.py",
     "if store.spent(st.day) >= float(cfg(s, \"quota_site_cap_usd\")):", "if False:",
     [U + "::test_admit_refuses_at_cap_before_counting"]),
    ("M13 rate limit", "server/quota.py", "            if not ok:\n", "            if False:\n",
     [U + "::test_rate_limit_applies_to_byok"]),
    ("M14 free count", "server/quota.py", "if not store.take(limits, st.day, _weight(ctx, body, s)):", "if False:",
     [I + "::test_n_plus_1_question_is_429_with_quota_fields"]),
    ("M15 IP key counted", "server/quota.py",
     "limits = [(f\"ip:{st.ip}\", int(cfg(s, \"quota_free_per_ip_day\")))]", "limits = []",
     [I + "::test_cookieless_client_is_bounded_by_ip"]),
    ("M16 BYOK cap exemption", "server/quota.py",
     "cap = float(cfg(s, \"quota_byok_side_cap_usd\") if (st.byok and purpose != \"web\")\n                else cfg(s, \"quota_site_cap_usd\"))",
     "cap = float(cfg(s, \"quota_site_cap_usd\"))",
     [I + "::test_cap_reached_free_off_byok_still_works"]),
    ("M17 BYOK answer user-paid", "server/quota.py",
     "return purpose in _ANSWER_PURPOSES or kw.get(\"api_key\") == creds.api_key", "return False",
     [U + "::test_reserve_rejects_over_remaining_budget_free_only"]),
    ("M18 BYOK web daily quota", "server/quota.py", "if not store.take(limits, _day()):", "if False:",
     [U + "::test_byok_web_daily_quota"]),
    ("M19 aborted stream charged", "server/quota.py", "actual = est if tokens is None else",
     "actual = 0.0 if tokens is None else", [U + "::test_aborted_stream_is_charged_the_reservation",
                                            I + "::test_aborted_stream_is_still_charged"]),
    ("M20 finalize closes", "server/quota.py", "        store.close(rid)\n", "        pass\n",
     [U + "::test_finalize_charges_unsettled_and_late_settle_is_noop"]),
    ("M21 expiry sweep", "server/quota.py",
     "    store.expire(now - float(cfg(s, \"quota_reservation_ttl_s\")))\n", "",
     [U + "::test_reservation_never_finalized_expires_charged"]),
    ("M22 free no web", "server/quota.py", "        body.web = False\n", "        pass\n",
     [I + "::test_free_stream_gets_no_web"]),
    ("M23 unknown model never $0", "server/quota.py", "if r_in is None and r_out is None:",
     "if False:", [U + "::test_estimate_uses_deployment_max_tokens_and_never_zero"]),
    ("M24 BYOK side-call ceiling", "server/quota.py", "cap = float(cfg(s, \"quota_byok_side_cap_usd\") if (st.byok and purpose != \"web\")\n                else cfg(s, \"quota_site_cap_usd\"))",
     "cap = None if (st.byok and purpose != \"web\") else float(cfg(s, \"quota_site_cap_usd\"))",
     [U + "::test_byok_side_calls_have_a_hard_ceiling"]),
    ("M25 deny-by-default endpoints", "server/quota.py", "_EXEMPT_ENDPOINTS: frozenset = frozenset()",
     "_EXEMPT_ENDPOINTS: frozenset = frozenset({\"ask_compare\", \"validate\"})",
     [U + "::test_every_metered_endpoint_counts_compare_weighted",
      U + "::test_rate_limit_covers_non_ask_endpoints"]),
    ("M26 compare weight", "server/quota.py", "return max(1, len(models)) + (1 if judge else 0)",
     "return 1", [U + "::test_every_metered_endpoint_counts_compare_weighted"]),
    ("M27 IPv6 /64 key", "server/auth.py",
     "return str(ipaddress.ip_network(f\"{addr}/{v6_prefix}\", strict=False))", "return str(addr)",
     [U + "::test_client_key_normalizes_ipv6", I + "::test_ipv6_clients_keyed_by_64"]),
    ("M28 IPv4-mapped -> IPv4", "server/auth.py", "return str(addr.ipv4_mapped)", "return str(addr)",
     [U + "::test_client_key_normalizes_ipv6"]),
]

env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
rows = []
for name, rel, old, new, tests in M:
    p = ROOT / rel
    src = p.read_text(encoding="utf-8")
    assert src.count(old) == 1, (name, src.count(old))
    p.write_text(src.replace(old, new), encoding="utf-8")
    try:
        for d in ROOT.rglob("__pycache__"):
            if ".venv" not in d.parts and "vendor" not in d.parts:
                shutil.rmtree(d, ignore_errors=True)
        r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "pytest", "-q", "-o", "addopts=",
                            *tests], cwd=ROOT, env=env, capture_output=True, text=True)
        tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
        rows.append((name, rel, r.returncode != 0, tail))
    finally:
        p.write_text(src, encoding="utf-8")
for name, rel, killed, tail in rows:
    print(f"| {name} | {rel} | {'KILLED' if killed else 'SURVIVED'} | {tail} |")
sys.exit(0 if all(k for _, _, k, _ in rows) else 1)
