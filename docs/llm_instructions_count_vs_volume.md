# LLM Instruction: Understanding COUNT vs VOLUME in Historical Orderbook Data

## Project Context
I'm working on goldZenith, a TSETMC (Tehran Stock Exchange) historical data analysis system that fetches, 
persists, and analyzes per-second orderbook snapshots and trade history.

## Data Architecture

### Persistence
- Historical orderbook snapshots are fetched from TSETMC CDN and persisted as Parquet files
- Location: `data/orderbooks/{isin}_{jalali_date}.parquet`
- Fetching code: `scripts/fetch_range.py` → `src/historical/client.py` (TSETMCClient)
- Storage code: `src/historical/storage.py` (StorageClient)

### Orderbook Columns
```
time, 
buy_count_1, buy_volume_1, buy_price_1, sell_price_1, sell_volume_1, sell_count_1,
buy_count_2, buy_volume_2, buy_price_2, sell_price_2, sell_volume_2, sell_count_2,
buy_count_3, buy_volume_3, buy_price_3, sell_price_3, sell_volume_3, sell_count_3,
buy_count_4, buy_volume_4, buy_price_4, sell_price_4, sell_volume_4, sell_count_4,
buy_count_5, buy_volume_5, buy_price_5, sell_price_5, sell_volume_5, sell_count_5
```

### Data Mapping from TSETMC CDN API
The raw TSETMC API response contains:
- `zOrdMeDem` → mapped to `buy_count` (number of orders at depth level on buy side)
- `qTitMeDem` → mapped to `buy_volume` (total quantity at depth level on buy side)
- `zOrdMeOf` → mapped to `sell_count` (number of orders at depth level on sell side)
- `qTitMeOf` → mapped to `sell_volume` (total quantity at depth level on sell side)

Source code mapping: `src/historical/client.py`, lines 86-91

## Question

**What is the difference between COUNT and VOLUME in each depth level?**

I see columns like `buy_count_1` and `buy_volume_1` at the same depth level. 
- What does each represent specifically?
- How are they related?
- Why do we need both metrics?
- How can I use them together for market microstructure analysis?

## Context for Analysis
I'm building a Jupyter notebook (`scripts/historical_analysis.ipynb`) to perform historical analysis on:
1. Market depth & microstructure (spread, imbalance, level changes)
2. Price movement & volatility analysis
3. Trade flow analysis

## Please Explain
- Clear definition of each metric
- A real-world example at a specific depth level
- Why both metrics matter for market structure analysis
- Example code showing how to analyze the relationship between count and volume
- Use cases for each metric in market microstructure research
