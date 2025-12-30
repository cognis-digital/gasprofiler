# Demo 01 — Basic gas profile + unbounded-loop detection

This demo profiles a small `Airdrop.sol` contract that contains a classic
gas footgun: a loop over a dynamic array (`recipients.length`) with a storage
write inside it. As the recipient list grows, gas grows linearly and the
transaction can eventually exceed the block gas limit and revert.

## Run it

```bash
# Per-function gas table (human readable)
python -m gasprofiler profile demos/01-basic/Airdrop.sol

# Machine readable for CI / piping
python -m gasprofiler profile demos/01-basic/Airdrop.sol --format json
```

## What you should see

- A table listing each function with an estimated relative gas cost.
- `distribute` and `clearAll` flagged with `UNBOUNDED` because they loop over
  `recipients.length` / use an unbounded `while`.
- `setOwner` has no loops and the lowest gas.
- The command **exits with code 1** because there are `error`-severity
  unbounded-loop findings — so it can fail a PR on its own.

## Regression gate

```bash
# 1. Save a baseline
python -m gasprofiler profile demos/01-basic/Airdrop.sol --out /tmp/base.json --no-fail

# 2. Later, in CI, fail if any function got >5% more expensive
python -m gasprofiler check demos/01-basic/Airdrop.sol --baseline /tmp/base.json --tolerance 0.05
```

Against an unchanged file, `check` prints `OK: no gas regressions.` and exits 0.
