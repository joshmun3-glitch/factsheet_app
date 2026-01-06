# Paths
PORTFOLIO_CSV = "data/portfolio.csv"
PRICE_CACHE_DIR = "data/prices"
OUTPUT_DIR = "output/factsheets"
TEMPLATE_DIR = "templates"

# Data Fetching
YFINANCE_NO_JSON_LOAD = 1
CACHE_EXPIRE_HOURS = 24

# Currency to ticker mapping
CURRENCY_TICKERS = {
    "USD": "USDKRW=X",
    "HKD": "HKDKRW=X",
    "CNY": "CNYKRW=X",
    "JPY": "JPYKRW=X",
    "EUR": "EURKRW=X",
    "CHF": "CHFKRW=X",
}

# Index tickers
INDEX_TICKERS = {
    "KOSPI": "^KS11",
    "S&P": "^GSPC",
}

# Stock ticker prefixes by country
TICKER_PREFIXES = {
    "KR": "",
    "US": "",
    "HK": "",
    "CN": "",
    "JP": ".",
    "FR": ".",
    "CH": ".",
}
