# Scoped identity reference correction

Keep the existing identity preload, complete required reads, loading order,
role and direct-superior checks, scope, duties and actual host evidence.

The change is limited to replacing identity/capsule digest references with the
issued court number, prohibiting repeat integrity checks during normal use,
and adding `HHmm` plus 2–3 office letters only to the semantic capsule reference
(`LBH` for 吏部 and `LB` for 礼部). Office and child task naming stays unchanged.
Installation performs its integrity check once and removes installation-only
checkers afterwards. Do not redesign schemas, recall, classification, lifecycle
or historical-record storage as part of this correction.
