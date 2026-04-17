# VSTAR Universe (S12a) TCGPlayer Cart Optimizer

Automatically scrapes every seller listing across all 344 target cards
in the Japanese VSTAR Universe set and finds the **minimum number of
sellers** you need to buy from — then shows you the cheapest option
within that constraint.

---

## Prerequisites

| Requirement | Minimum version |
|---|---|
| Python | 3.11+ |
| pip | any recent version |

---

## One-Time Setup

### 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2 — Install the Playwright browser binary

```bash
playwright install chromium
```

This downloads a bundled Chromium (~150 MB).  You only need to do this once.

---

## Running the Script

```bash
python vstar_optimizer.py
```

The script runs in three phases:

| Phase | What it does | Output file |
|---|---|---|
| **1** | Paginates the TCGPlayer set search and collects every product URL + card number | `products.json` |
| **2** | Visits each product page and scrapes all seller listings | `listings.json` |
| **3** | Solves the set-cover optimisation and writes results | `optimized_cart.csv` + `summary.txt` |

### Progress is automatically saved

Phase 2 saves progress every 10 cards.  If the script is interrupted,
re-running it will skip all already-scraped cards and continue from
where it left off.  To **start completely fresh**, delete
`products.json` and `listings.json`.

---

## Expected Run Time

- **Phase 1**: 5–15 minutes (depends on how many pages TCGPlayer has for the set)
- **Phase 2**: 4–8 hours (344 cards × ~4 seconds each + loading time per page)

Run it overnight.  The browser window will be visible by default so
you can see it working.

---

## Output Files

### `optimized_cart.csv`

One row per card.  Columns:

| Column | Description |
|---|---|
| `card_number` | Printed card number (e.g. `107`) |
| `card_name` | Full TCGPlayer product name |
| `variant` | Normal, Holofoil, etc. |
| `seller` | TCGPlayer seller username |
| `price_usd` | Card price from that seller |
| `shipping_usd` | Shipping charge (FREE if $0) |
| `condition` | Near Mint / Lightly Played |
| `tcgplayer_url` | Direct link to the product page |

### `summary.txt`

Human-readable summary printed to your terminal and saved to disk:

```
===================================================================
  VSTAR UNIVERSE (S12a)  –  OPTIMISED CART SUMMARY
===================================================================
  Cards to purchase   : 344
  Unique sellers      : 12
  Total card cost     : $347.82
  Total shipping      : $48.00
  Estimated grand total: $395.82

  PER-SELLER BREAKDOWN  (sorted by cards held descending)
  ------------------------------------------------------------------
  Seller                            Cards  Card $    Ship   Subtotal
  ------------------------------------------------------------------
  BestDealsCards                       87  $82.43   $4.00    $86.43
  ...
```

---

## Configuration

Edit the block at the top of `vstar_optimizer.py`:

```python
# Card numbers to skip
EXCLUDED_CARD_NUMBERS = {"205", "212", "221", "259", "261", "262", "263"}

# Only consider Near Mint and Lightly Played copies
ACCEPTED_CONDITIONS = ("near mint", "lightly played")

# True = invisible browser, False = visible (default, less likely to be blocked)
HEADLESS = False

# Seconds between page loads (increase if you keep getting blocked)
MIN_DELAY = 2.5
MAX_DELAY = 5.0
```

---

## Troubleshooting

### "No products were discovered"
TCGPlayer's page structure may have changed, or you may be rate-limited.
Try increasing `MIN_DELAY` / `MAX_DELAY` and re-running.  If the set
search page looks different in the browser, inspect the page source and
update the selector logic in `discover_products()`.

### Script is running but finding 0 listings for many cards
TCGPlayer's DOM class names sometimes change between deploys.  The
script tries **both** network interception (capturing the JSON responses
the frontend fetches) and DOM scraping.  If both fail:
1. Open one of the card URLs in a regular browser.
2. Open DevTools → Network → filter for "listing" or "sellerlisting".
3. Find the JSON response that contains seller data.
4. Update `_parse_network_listings()` to match the new field names.

### Getting CAPTCHAs or blocked
- Increase `MIN_DELAY` and `MAX_DELAY` to 5–10 seconds.
- Keep `HEADLESS = False` (visible browser is less detectable).
- Try running it at a different time of day.
- If a CAPTCHA appears, solve it manually in the browser window —
  the script will wait for `networkidle` and then continue automatically.

### "playwright: command not found"
Make sure you installed into the right Python environment:
```bash
python -m playwright install chromium
```

---

## How the Optimisation Works

The problem of choosing which sellers to buy from is a variant of the
**weighted set cover** problem.  This is NP-hard in general, but the
greedy algorithm produces solutions within a logarithmic factor of
optimal and works well in practice for this size of problem.

**Step 1 — Inventory**  
For each seller, find the cheapest price they offer for each card.

**Step 2 — Greedy set cover**  
Repeatedly pick the seller who covers the most **still-uncovered**
cards.  Ties are broken by lowest total cost for those cards.

**Step 3 — Local search refinement**  
After the greedy pass, scan for sellers who are now redundant (all
their cards are also available from other already-chosen sellers) and
remove them.  Also try swapping single-card sellers for alternatives.

**Step 4 — Assignment**  
For each card, assign it to whichever chosen seller offers it cheapest.

---

## License

Do whatever you want with this script.  Scraping publicly visible prices
for personal use is generally fine, but be polite — don't remove the
delays or hammer TCGPlayer's servers.
