# -*- coding: utf-8 -*-
"""
Phase 1: Data Fetcher
yfinance를 사용하여 주가, 환율, 지수 데이터 수집
"""

import yfinance as yf
from datetime import datetime, timedelta
import json
import os
from typing import Dict, Optional, Tuple, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DataFetcher:
    """
    주가, 환율, 지수 데이터 수집기
    """

    CURRENCY_TO_TICKER = {
        "USD": "USDKRW=X",
        "HKD": "HKDKRW=X",
        "CNY": "CNYKRW=X",
        "JPY": "JPYKRW=X",
        "EUR": "EURKRW=X",
        "CHF": "CHFKRW=X",
    }

    INDEX_TICKERS = {
        "KOSPI": "^KS11",
        "S&P": "^GSPC",
    }

    TICKER_MAP = {
        "035900.KQ": "JYP",  # 한국 코스닥
        "067160.KQ": "SOOP",  # 한국 코스닥
        "0700.HK": "0700.HK",  # 텐센트 (홍콩)
        "3690.HK": "3690.HK",  # 메이투안 (홍콩)
        "000858.SZ": "000858.SZ",  # 오량액 (중국)
        "2801 JT": "2801.T",  # 깃코만 (일본)
        "RMS.PA": "RMS.PA",  # 에르메스 (프랑스)
        "CFR.SW": "CFR.SW",  # 리슈몽 (스위스)
    }

    def __init__(self, cache_dir: str = "data/prices", cache_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_hours = cache_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.korean_fetcher = KoreanMarketFetcher()

    def _get_cache_path(self, key: str) -> Path:
        """캐시 파일 경로 반환"""
        safe_key = key.replace("/", "_").replace(":", "_")
        return self.cache_dir / f"{safe_key}.json"

    def _get_cache(self, key: str) -> Optional[Dict]:
        """캐시 조회"""
        cache_path = self._get_cache_path(key)
        if not cache_path.exists():
            return None

        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        cache_time = datetime.fromisoformat(cache_data["timestamp"])
        if datetime.now() - cache_time > timedelta(hours=self.cache_hours):
            return None

        return cache_data.get("data")

    def _save_cache(self, key: str, data: Dict):
        """캐시 저장"""
        cache_path = self._get_cache_path(key)
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

    def fetch_stock_price(
        self,
        ticker: str,
        date: str,
    ) -> Optional[float]:
        """
        특정 날짜의 주가 조회

        Args:
            ticker: 종목 코드 (e.g., 'AAPL', '0700.HK', '035900.KQ')
            date: 조회 날짜 (YYYY-MM-DD)

        Returns:
            해당 날짜의 종가 또는 None
        """
        cache_key = f"stock_{ticker}_{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("price")

        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")

            ticker_mapped = self.TICKER_MAP.get(ticker, ticker)

            stock = yf.Ticker(ticker_mapped)

            start_date = target_date.strftime("%Y-%m-%d")
            end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"No price data for {ticker} on {date}")
                return None

            price = hist["Close"].iloc[-1]

            result = {"price": price, "date": date, "ticker": ticker}
            self._save_cache(cache_key, result)

            logger.info(f"Fetched price for {ticker}: {price} on {date}")
            return price

        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return None

    def fetch_exchange_rate(
        self,
        from_currency: str,
        to_currency: str = "KRW",
        date: Optional[str] = None,
    ) -> Optional[float]:
        """
        환율 조회

        Args:
            from_currency: 원래 통화 (USD, HKD, CNY, JPY, EUR, CHF)
            to_currency: 목표 통화 (기본 KRW)
            date: 조회 날짜 (None이면 최신)

        Returns:
            환율 또는 None
        """
        if from_currency == to_currency:
            return 1.0

        if from_currency not in self.CURRENCY_TO_TICKER:
            logger.error(f"Unsupported currency: {from_currency}")
            return None

        cache_key = f"fx_{from_currency}_{to_currency}_{date or 'latest'}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("rate")

        try:
            ticker = self.CURRENCY_TO_TICKER[from_currency]
            fx = yf.Ticker(ticker)

            if date:
                target_date = datetime.strptime(date, "%Y-%m-%d")
                start_date = target_date.strftime("%Y-%m-%d")
                end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
                hist = fx.history(start=start_date, end=end_date)
            else:
                hist = fx.history(period="1d")

            if hist.empty:
                logger.warning(f"No exchange rate for {from_currency}")
                return None

            rate = hist["Close"].iloc[-1]

            result = {"rate": rate, "from": from_currency, "to": to_currency, "date": date}
            self._save_cache(cache_key, result)

            logger.info(f"Fetched FX rate: 1 {from_currency} = {rate} {to_currency}")
            return rate

        except Exception as e:
            logger.error(f"Error fetching FX rate for {from_currency}: {e}")
            return None

    def fetch_index_value(
        self,
        index_name: str,
        date: str,
    ) -> Optional[float]:
        """
        지수 값 조회 (KOSPI, S&P)

        Args:
            index_name: 지수명 ('KOSPI', 'S&P')
            date: 조회 날짜

        Returns:
            지수 값 또는 None
        """
        if index_name not in self.INDEX_TICKERS:
            logger.error(f"Unknown index: {index_name}")
            return None

        cache_key = f"index_{index_name}_{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("value")

        try:
            ticker = self.INDEX_TICKERS[index_name]
            target_date = datetime.strptime(date, "%Y-%m-%d")

            start_date = target_date.strftime("%Y-%m-%d")
            end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

            index = yf.Ticker(ticker)
            hist = index.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"No data for {index_name} on {date}")
                return None

            value = hist["Close"].iloc[-1]

            result = {"value": value, "index": index_name, "date": date}
            self._save_cache(cache_key, result)

            logger.info(f"Fetched {index_name}: {value} on {date}")
            return value

        except Exception as e:
            logger.error(f"Error fetching {index_name}: {e}")
            return None

    def fetch_multiple(
        self,
        tickers: List[str],
        date: str,
        currencies: List[str],
        indices: List[str],
    ) -> Dict:
        """
        여러 데이터 一括 조회 (API 호출 최소화)

        Args:
            tickers: 종목 코드 목록
            date: 조회 날짜
            currencies: 통화 목록
            indices: 지수 목록

        Returns:
            {'stocks': {ticker: price}, 'currencies': {currency: rate}, 'indices': {index: value}}
        """
        result = {
            "stocks": {},
            "currencies": {},
            "indices": {},
            "date": date,
        }

        for ticker in tickers:
            price = self.fetch_stock_price(ticker, date)
            if price is not None:
                result["stocks"][ticker] = price

        for currency in currencies:
            rate = self.fetch_exchange_rate(currency, "KRW", date)
            if rate is not None:
                result["currencies"][currency] = rate

        for index in indices:
            value = self.fetch_index_value(index, date)
            if value is not None:
                result["indices"][index] = value

        return result

    def clear_cache(self, older_than_hours = None):
        """
        캐시 클리어

        Args:
            older_than_hours: 이 시간보다 오래된 캐시만 삭제 (None이면 전체)
        """
        if not self.cache_dir.exists():
            return

        for cache_file in self.cache_dir.glob("*.json"):
            if older_than_hours is None:
                cache_file.unlink()
            else:
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)
                cache_time = datetime.fromisoformat(cache_data["timestamp"])
                if datetime.now() - cache_time > timedelta(hours=older_than_hours):
                    cache_file.unlink()

        logger.info(f"Cache cleared (older_than_hours={older_than_hours})")

    def get_cache_stats(self) -> Dict:
        """캐시 상태 조회"""
        if not self.cache_dir.exists():
            return {"count": 0, "size_mb": 0}

        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "count": len(cache_files),
            "size_mb": round(total_size / (1024 * 1024), 2),
        }

    def is_korean_stock(self, ticker: str) -> bool:
        """한국주(K/KQ) 확인"""
        return (
            ticker.endswith(".KQ") or
            ticker.endswith(".KS") or
            (ticker.isdigit() and len(ticker) == 6)
        )

    def fetch_stock_price(self, ticker: str, date: str) -> Optional[float]:
        """특정 날짜의 주가 조회 (한국주 특별 처리)"""

        if self.is_korean_stock(ticker):
            return self.korean_fetcher.fetch_korean_stock_price(ticker, date)

        return self._fetch_via_yfinance(ticker, date)

    def _fetch_via_yfinance(self, ticker: str, date: str) -> Optional[float]:
        """yfinance로 해외주 가격 조회"""
        cache_key = f"stock_{ticker}_{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("price")

        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
            ticker_mapped = self.TICKER_MAP.get(ticker, ticker)
            stock = yf.Ticker(ticker_mapped)

            start_date = target_date.strftime("%Y-%m-%d")
            end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

            hist = stock.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"No price data for {ticker} on {date}")
                return None

            price = hist["Close"].iloc[-1]

            result = {"price": price, "date": date, "ticker": ticker}
            self._save_cache(cache_key, result)

            logger.info(f"Fetched price for {ticker}: {price} on {date}")
            return price

        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {e}")
            return None

    def fetch_index_value(self, index_name: str, date: str) -> Optional[float]:
        """지수 값 조회 (KOSPI는 pykrx, S&P는 yfinance)"""
        if index_name == "KOSPI":
            return self.korean_fetcher.fetch_kospi_index(date)

        return self._fetch_index_via_yfinance(index_name, date)

    def _fetch_index_via_yfinance(self, index_name: str, date: str) -> Optional[float]:
        """yfinance로 지수 조회 (S&P 등)"""
        if index_name not in self.INDEX_TICKERS:
            logger.error(f"Unknown index: {index_name}")
            return None

        cache_key = f"index_{index_name}_{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("value")

        try:
            ticker = self.INDEX_TICKERS[index_name]
            target_date = datetime.strptime(date, "%Y-%m-%d")

            start_date = target_date.strftime("%Y-%m-%d")
            end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

            index = yf.Ticker(ticker)
            hist = index.history(start=start_date, end=end_date)

            if hist.empty:
                logger.warning(f"No data for {index_name} on {date}")
                return None

            value = hist["Close"].iloc[-1]

            result = {"value": value, "index": index_name, "date": date}
            self._save_cache(cache_key, result)

            logger.info(f"Fetched {index_name}: {value} on {date}")
            return value

        except Exception as e:
            logger.error(f"Error fetching {index_name}: {e}")
            return None


class KoreanMarketFetcher:
    """pykrx + Naver Finance 기반 한국 시장 데이터 수집"""

    KOSPI_INDEX_CODE = "1001"

    def __init__(self):
        self.cache_dir = Path("data/prices")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache(self, key: str) -> Optional[Dict]:
        """캐시 조회"""
        from pathlib import Path
        import json
        from datetime import datetime, timedelta

        safe_key = key.replace("/", "_").replace(":", "_")
        cache_path = self.cache_dir / f"{safe_key}.json"

        if not cache_path.exists():
            return None

        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        cache_time = datetime.fromisoformat(cache_data["timestamp"])
        if datetime.now() - cache_time > timedelta(hours=24):
            return None

        return cache_data.get("data")

    def _save_cache(self, key: str, data: Dict):
        """캐시 저장"""
        from pathlib import Path
        import json
        from datetime import datetime

        safe_key = key.replace("/", "_").replace(":", "_")
        cache_path = self.cache_dir / f"{safe_key}.json"

        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": data,
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

    def fetch_kospi_index(self, date: str) -> Optional[float]:
        """KOSPI 지수 조회 (investing.com 스크래핑)"""
        cache_key = f"kospi_{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("value")

        try:
            value = self._fetch_kospi_via_investing(date)
            if value is not None:
                result = {"value": value, "date": date}
                self._save_cache(cache_key, result)
                logger.info(f"Fetched KOSPI via investing.com: {value} on {date}")
                return value

            logger.warning(f"No KOSPI data for {date}")
            return None

        except Exception as e:
            logger.error(f"Error fetching KOSPI: {e}")
            return None

    def _fetch_kospi_via_investing(self, date: str) -> Optional[float]:
        """investing.com에서 KOSPI 지수 스크래핑"""
        import requests
        from bs4 import BeautifulSoup

        url = f"https://www.investing.com/indices/south-korea-kospi-historical-data"
        params = {
            "st_date": date,
            "end_date": date,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        response = requests.get(url, params=params, headers=headers, timeout=15)

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "lxml")

        try:
            data_row = soup.select_one("table tbody tr")
            if data_row:
                cells = data_row.select("td")
                if len(cells) >= 2:
                    price_text = cells[1].get_text().strip().replace(",", "")
                    return float(price_text)
        except Exception as e:
            logger.debug(f"investing.com parsing failed: {e}")

        return None

    def fetch_korean_stock_price(self, ticker: str, date: str) -> Optional[float]:
        """한국주 가격 조회 (pykrx 우선, Naver 백업)"""
        code = ticker.split(".")[0] if "." in ticker else ticker

        cache_key = f"kr_stock_{code}_{date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {cache_key}")
            return cached.get("price")

        price = self._fetch_via_pykrx(code, date)
        if price is not None:
            return price

        price = self._fetch_via_naver(code, date)
        if price is not None:
            return price

        logger.warning(f"No price data for {ticker} on {date}")
        return None

    def _fetch_via_pykrx(self, code: str, date: str) -> Optional[float]:
        """pykrx로 한국주 가격 조회"""
        try:
            from pykrx import stock

            date_krx = date.replace("-", "")

            if len(code) == 6:
                if code.startswith('0') or code.startswith('3'):
                    market = "kosdaq"
                else:
                    market = "kospi"
            else:
                market = "kospi"

            df = stock.get_ohlc_by_date(date_krx, date_krx, code)

            if df.empty:
                return None

            price = float(df.iloc[0]["종가"])

            result = {"price": price, "date": date, "ticker": code}
            self._save_cache(f"kr_stock_{code}_{date}", result)

            logger.info(f"Fetched price for {code} via pykrx: {price}")
            return price

        except Exception as e:
            logger.debug(f"pykrx failed for {code}: {e}")
            return None

    def _fetch_via_naver(self, code: str, date: str) -> Optional[float]:
        """Naver Finance 웹페이지에서 가격 스크래핑 (백업)"""
        try:
            import requests
            from bs4 import BeautifulSoup

            url = f"https://finance.naver.com/item/main.nhn?code={code}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "lxml")

            price_element = soup.select_one(".no_today .blind")
            if price_element is None:
                price_element = soup.select_one("#_nowVal")

            if price_element:
                price_text = price_element.get_text().strip().replace(",", "")
                if price_text:
                    price = float(price_text)

                    result = {"price": price, "date": date, "ticker": code}
                    self._save_cache(f"kr_stock_{code}_{date}", result)

                    logger.info(f"Fetched price for {code} via Naver: {price}")
                    return price

        except Exception as e:
            logger.debug(f"Naver fallback failed for {code}: {e}")

        return None


def test_data_fetcher():
    """DataFetcher 테스트"""
    fetcher = DataFetcher()

    print("=" * 50)
    print("DataFetcher Test")
    print("=" * 50)

    test_date = "2025-12-31"

    print(f"\n[Test] Stock prices for {test_date}")
    test_stocks = ["AAPL", "BABA", "0700.HK", "035900.KQ"]
    for stock in test_stocks:
        price = fetcher.fetch_stock_price(stock, test_date)
        print(f"  {stock}: {price}")

    print(f"\n[Test] Exchange rates for {test_date}")
    test_currencies = ["USD", "HKD", "CNY", "JPY", "EUR", "CHF"]
    for currency in test_currencies:
        rate = fetcher.fetch_exchange_rate(currency, "KRW", test_date)
        print(f"  {currency}: {rate}")

    print(f"\n[Test] Index values for {test_date}")
    for index in ["KOSPI", "S&P"]:
        value = fetcher.fetch_index_value(index, test_date)
        print(f"  {index}: {value}")

    print(f"\n[Test] Cache stats: {fetcher.get_cache_stats()}")


if __name__ == "__main__":
    test_data_fetcher()
