"""
Phase 2: Data Processor
CSV 파싱, 누락 데이터 감지/채우기, 수량변화 계산
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class PortfolioEntry:
    """포트폴리오 한 행"""
    date: str
    ticker: str
    name: str
    quantity: Optional[int]
    price: Optional[float]
    weight: Optional[float]
    sector: str
    country: str
    currency: str
    exchange_rate: Optional[float]

    def to_dict(self) -> Dict:
        return asdict(self)


class DataProcessor:
    """
    포트폴리오 데이터 처리기
    """

    INDEX_TICKERS = ["KOSPI", "S&P"]

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        self.df = self._load_csv()
        self.entries = self._parse_entries()

    def _load_csv(self) -> pd.DataFrame:
        """CSV 로드"""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        df = pd.read_csv(self.csv_path)

        if df.empty:
            raise ValueError("CSV file is empty")

        return df

    def _parse_entries(self) -> List[PortfolioEntry]:
        """CSV 파싱"""
        entries = []
        for _, row in self.df.iterrows():
            quantity_val = row["수량"]
            price_val = row["현재가"]
            weight_val = row["비중(%)"]
            exchange_val = row["환율"]

            def is_valid_number(val):
                """값이 유효한 숫자인지 확인 (None, NaN, 빈 문자열 제외)"""
                if val is None:
                    return False
                if pd.isna(val):
                    return False
                if isinstance(val, str) and val.strip() == "":
                    return False
                try:
                    float(val)
                    return True
                except (ValueError, TypeError):
                    return False

            def to_int(val):
                """숫자를 int로 변환"""
                if is_valid_number(val):
                    return int(float(val))
                return None

            def to_float(val):
                """숫자를 float으로 변환"""
                if is_valid_number(val):
                    return float(val)
                return None

            quantity = to_int(quantity_val)
            price = to_float(price_val)
            weight = to_float(weight_val)
            exchange_rate = to_float(exchange_val)

            entry = PortfolioEntry(
                date=str(row["기준일"]),
                ticker=str(row["종목코드"]),
                name=str(row["종목명"]),
                quantity=quantity,
                price=price,
                weight=weight,
                sector=str(row["섹터"]),
                country=str(row["국가"]),
                currency=str(row["통화"]),
                exchange_rate=exchange_rate,
            )
            entries.append(entry)
        return entries

    def get_all_dates(self) -> List[str]:
        """모든 날짜 목록 반환"""
        return sorted(list(set(str(d) for d in self.df["기준일"].unique())))

    def get_latest_date(self) -> Optional[str]:
        """최신 날짜 반환"""
        dates = self.get_all_dates()
        return dates[-1] if dates else None

    def get_entries_by_date(self, date: str) -> List[PortfolioEntry]:
        """특정 날짜의 모든 항목 반환"""
        return [e for e in self.entries if e.date == date]

    def get_tickers_by_date(self, date: str) -> List[str]:
        """특정 날짜의 모든 종목 코드 반환"""
        entries = self.get_entries_by_date(date)
        return [e.ticker for e in entries if e.ticker not in self.INDEX_TICKERS]

    def get_unique_tickers(self) -> List[str]:
        """모든 고유 종목 코드 반환"""
        return sorted(
            list(set(e.ticker for e in self.entries if e.ticker not in self.INDEX_TICKERS))
        )

    def get_unique_currencies(self) -> List[str]:
        """모든 고유 통화 반환"""
        return sorted(list(set(e.currency for e in self.entries)))

    def detect_missing_data(self, date: Optional[str] = None) -> Dict:
        """
        누락 데이터 감지

        Args:
            date: 특정 날짜만 검증 (None이면 전체)

        Returns:
            {
                'date': 날짜,
                'missing_stocks': [종목코드],
                'missing_rates': [통화],
                'missing_indices': [지수명]
            }
        """
        if date:
            dates = [date]
        else:
            dates = self.get_all_dates()

        all_missing_stocks = {}
        all_missing_rates = set()
        all_missing_indices = set()

        for d in dates:
            entries = self.get_entries_by_date(d)
            missing_stocks = []
            currencies_in_date = set()

            for entry in entries:
                if entry.ticker in self.INDEX_TICKERS:
                    if self._get_value_by_entry(entry, "price") is None:
                        all_missing_indices.add(entry.ticker)
                else:
                    if entry.price is None:
                        missing_stocks.append(entry.ticker)
                    currencies_in_date.add(entry.currency)

            if missing_stocks:
                all_missing_stocks[d] = missing_stocks

            for currency in currencies_in_date:
                if currency != "KRW":
                    entry = next(
                        (e for e in entries if e.currency == currency), None
                    )
                    if entry and entry.exchange_rate is None:
                        all_missing_rates.add(currency)

        return {
            "date": date,
            "missing_stocks": all_missing_stocks,
            "missing_rates": list(all_missing_rates),
            "missing_indices": list(all_missing_indices),
        }

    def _get_value_by_entry(self, entry: PortfolioEntry, field: str):
        """항목에서 특정 필드 값 반환"""
        return getattr(entry, field, None)

    def fill_missing_prices(self, fetcher, date: str) -> int:
        """
        특정 월의 누락 주가/환율 자동 채우기

        Args:
            fetcher: DataFetcher 인스턴스
            date: 대상 월 (YYYY-MM-DD)

        Returns:
            업데이트된 행 수
        """
        entries = self.get_entries_by_date(date)
        updated_count = 0

        tickers_to_fetch = set()
        currencies_to_fetch = set()

        for entry in entries:
            if entry.ticker in self.INDEX_TICKERS:
                continue
            if entry.price is None:
                tickers_to_fetch.add(entry.ticker)
            if entry.currency != "KRW" and entry.exchange_rate is None:
                currencies_to_fetch.add(entry.currency)

        logger.info(
            f"Filling data for {date}: {len(tickers_to_fetch)} stocks, {len(currencies_to_fetch)} currencies"
        )

        for ticker in tickers_to_fetch:
            price = fetcher.fetch_stock_price(ticker, date)
            if price is not None:
                self._update_price(date, ticker, price)
                updated_count += 1
                logger.info(f"  Updated price for {ticker}: {price}")

        for currency in currencies_to_fetch:
            rate = fetcher.fetch_exchange_rate(currency, "KRW", date)
            if rate is not None:
                self._update_exchange_rate(date, currency, rate)
                updated_count += 1
                logger.info(f"  Updated exchange rate for {currency}: {rate}")

        return updated_count

    def _update_price(self, date: str, ticker: str, price: float):
        """가격 업데이트"""
        mask = (self.df["기준일"] == date) & (self.df["종목코드"] == ticker)
        self.df.loc[mask, "현재가"] = price

    def _update_exchange_rate(self, date: str, currency: str, rate: float):
        """환율 업데이트"""
        mask = (self.df["기준일"] == date) & (self.df["통화"] == currency)
        self.df.loc[mask, "환율"] = rate

    def fill_index_data(self, fetcher, dates: List[str]) -> int:
        """
        KOSPI/S&P 지수 데이터 채우기

        Args:
            fetcher: DataFetcher 인스턴스
            dates: 대상 날짜 목록

        Returns:
            업데이트된 행 수
        """
        updated_count = 0

        for date in dates:
            for index in self.INDEX_TICKERS:
                value = fetcher.fetch_index_value(index, date)
                if value is not None:
                    self._update_price(date, index, value)
                    updated_count += 1
                    logger.info(f"  Updated {index}: {value}")

        return updated_count

    def calculate_portfolio_value(
        self,
        date: str,
        use_exchange_rate: bool = True,
        korean_rate: float = 1.0,
    ) -> float:
        """
        특정 월의 포트폴리오 총액 계산 (KRW)

        Args:
            date: 조회 월
            use_exchange_rate: KRW로 환산 여부
            korean_rate: 한국주 환율 (기본 1.0)

        Returns:
            포트폴리오 총액 (KRW)
        """
        entries = self.get_entries_by_date(date)
        total = 0.0

        for entry in entries:
            if entry.ticker in self.INDEX_TICKERS:
                continue
            if entry.quantity is None or entry.price is None:
                continue

            value = entry.quantity * entry.price

            if use_exchange_rate:
                if entry.currency == "KRW":
                    rate = korean_rate
                elif entry.exchange_rate:
                    rate = entry.exchange_rate
                else:
                    logger.warning(f"No exchange rate for {entry.ticker} on {date}")
                    continue
                value = value * rate

            total += value

        return total

    def calculate_all_values(
        self, use_exchange_rate: bool = True
    ) -> Dict[str, float]:
        """모든 날짜의 포트폴리오 총액 계산"""
        values = {}
        for date in self.get_all_dates():
            values[date] = self.calculate_portfolio_value(date, use_exchange_rate)
        return values

    def detect_quantity_changes(
        self, prev_date: str, curr_date: str
    ) -> List[Dict]:
        """
        수량 변화 감지 (매도매수 추정)

        Returns:
            [
                {'ticker': '2801.JT', 'prev_qty': 500, 'curr_qty': 600,
                 'change': 100, 'type': 'BUY'},
                {'ticker': 'GRAB', 'prev_qty': 2352, 'curr_qty': 2354,
                 'change': 2, 'type': 'BUY'},
            ]
        """
        prev_entries = {e.ticker: e for e in self.get_entries_by_date(prev_date)}
        curr_entries = {e.ticker: e for e in self.get_entries_by_date(curr_date)}

        changes = []
        all_tickers = set(prev_entries.keys()) | set(curr_entries.keys())

        for ticker in all_tickers:
            if ticker in self.INDEX_TICKERS:
                continue

            prev = prev_entries.get(ticker)
            curr = curr_entries.get(ticker)

            if prev is None:
                continue
            if curr is None:
                continue

            if prev.quantity is None or curr.quantity is None:
                continue

            change = curr.quantity - prev.quantity

            if change != 0:
                change_type = "BUY" if change > 0 else "SELL"
                changes.append(
                    {
                        "ticker": ticker,
                        "name": curr.name if curr else prev.name,
                        "prev_qty": prev.quantity,
                        "curr_qty": curr.quantity,
                        "change": change,
                        "type": change_type,
                        "currency": curr.currency if curr else prev.currency,
                    }
                )

        return sorted(changes, key=lambda x: abs(x["change"]), reverse=True)

    def get_beginning_price(
        self, ticker: str, date: str
    ) -> Optional[float]:
        """
        당월 초 가격 조회 (전월 말 가격)

        Args:
            ticker: 종목 코드
            date: 당월 날짜

        Returns:
            당월 초 가격 또는 None
        """
        dates = self.get_all_dates()
        current_idx = dates.index(date)

        if current_idx == 0:
            return None

        prev_date = dates[current_idx - 1]
        entries = self.get_entries_by_date(prev_date)

        for entry in entries:
            if entry.ticker == ticker:
                return entry.price

        return None

    def save(self, path: Optional[str] = None):
        """CSV 저장"""
        save_path = path or str(self.csv_path)
        self.df.to_csv(save_path, index=False, encoding="utf-8-sig")
        logger.info(f"Saved portfolio data to {save_path}")

    def recalculate_weights(self, date: str):
        """
        특정 월의 비중 재계산

        Args:
            date: 대상 월
        """
        total_value = self.calculate_portfolio_value(date)

        if total_value == 0:
            logger.warning(f"Portfolio value is 0 for {date}")
            return

        mask = self.df["기준일"] == date
        for idx, row in self.df[mask].iterrows():
            if row["종목코드"] in self.INDEX_TICKERS:
                continue
            qty = row["수량"]
            price = row["현재가"]
            rate = row["환율"]

            if qty is not None and price is not None:
                if rate is not None:
                    value = float(qty) * float(price) * float(rate)
                else:
                    value = float(qty) * float(price)
                weight = (value / total_value) * 100
                self.df.loc[idx, "비중(%)"] = round(float(weight), 2)

        logger.info(f"Recalculated weights for {date}")


def test_data_processor():
    """DataProcessor 테스트"""
    processor = DataProcessor("data/portfolio.csv")

    print("=" * 50)
    print("DataProcessor Test")
    print("=" * 50)

    dates = processor.get_all_dates()
    print(f"\n[Test] All dates: {len(dates)} entries")
    print(f"  First: {dates[0]}")
    print(f"  Latest: {dates[-1]}")

    latest = dates[-1]
    print(f"\n[Test] Missing data for {latest}:")
    missing = processor.detect_missing_data(latest)
    print(f"  Missing stocks: {missing['missing_stocks'].get(latest, [])}")
    print(f"  Missing rates: {missing['missing_rates']}")
    print(f"  Missing indices: {missing['missing_indices']}")

    if len(dates) >= 2:
        prev, curr = dates[-2], dates[-1]
        print(f"\n[Test] Quantity changes: {prev} → {curr}")
        changes = processor.detect_quantity_changes(prev, curr)
        for c in changes[:5]:
            print(f"  {c['ticker']}: {c['prev_qty']} → {c['curr_qty']} ({c['type']} {abs(c['change'])})")

    print(f"\n[Test] Portfolio values:")
    for date in dates[-3:]:
        value = processor.calculate_portfolio_value(date)
        print(f"  {date}: {value:,.0f} KRW")


if __name__ == "__main__":
    import sys

    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/portfolio.csv"
    processor = DataProcessor(csv_path)
    test_data_processor()
