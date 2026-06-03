# TCGScraper

> Documentation in progress.

---

## Debug

### Exporting listing data

To dump the raw seller/listing data fetched during a session to a JSON file, run the app with the `DEBUG_DUMP` environment variable set:

```bash
DEBUG_DUMP=1 node main.js
```

After listings are fetched, a `listings_debug.json` file will be written to the current directory. The UI will briefly confirm the path and card count.

### Replaying the optimizer

Once you have a dump file, you can re-run the optimizer against it without re-scraping:

```bash
python test_optimizer.py listings_debug.json
```

This prints a per-card breakdown (seller, price, shipping, total) and compares the optimized cart total against the naive baseline of buying each card individually at its cheapest listing.
