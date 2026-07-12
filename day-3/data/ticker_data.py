"""
Mock enrichment data for the Ticker Triaging Agent. Not meant to be run -
data only. See ticker-triage-agent/README.md for example events to try -
ZVXQ and BABA are deliberately absent here, to exercise the "we don't
recognize this ticker, escalate regardless of how dramatic it looks"
guardrail.
"""

TICKER_LOOKUP = {
    "AAPL": {"company_name": "Apple Inc.", "sector": "Technology"},
    "TSLA": {"company_name": "Tesla Inc.", "sector": "Automotive"},
    "MSFT": {"company_name": "Microsoft Corp.", "sector": "Technology"},
    "KO": {"company_name": "Coca-Cola Co.", "sector": "Consumer Staples"},
    "GME": {"company_name": "GameStop Corp.", "sector": "Retail"},
    "NFLX": {"company_name": "Netflix Inc.", "sector": "Media & Entertainment"},
    "JPM": {"company_name": "JPMorgan Chase & Co.", "sector": "Financials"},
    "XOM": {"company_name": "Exxon Mobil Corp.", "sector": "Energy"},
}
