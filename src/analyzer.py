"""
Phase 4: Analyzer
수익률, 섹터/국가별 분배 분석
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np
from math import sqrt
import logging

logger = logging.getLogger(__name__)


@dataclass
class Allocation:
    """자산 배분"""
    name: str
    weight: float
    value: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TopHolding:
    """Top 구성종목"""
    rank: int
    ticker: str
    name: str
    weight: float
    sector: str
    country: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PerformanceSummary:
    """성과 요약"""
    ytd_return: float
    mtd_return: float
    one_year_return: float
    three_year_annualized: float
    since_inception_annualized: float
    monthly_returns: List[Dict]

    def to_dict(self) -> Dict:
        return asdict(self)


class PortfolioAnalyzer:
    """
    포트폴리오 분석기
    """

    def __init__(self, processor):
        self.processor = processor

    def calculate_allocation(
        self,
        date: str,
    ) -> List[Allocation]:
        """
        섹터/국가별 비중 계산 (섹터 + 국가 조합)

        Args:
            date: 조회 월

        Returns:
            [{'name': 'Information Technology - 미국', 'weight': 45.2, 'value': 154234000}, ...]
        """
        entries = self.processor.get_entries_by_date(date)
        total_value = self.processor.calculate_portfolio_value(date)

        if total_value == 0:
            return []

        allocation_dict = {}

        for entry in entries:
            if entry.ticker in ["KOSPI", "S&P"]:
                continue
            if entry.quantity is None or entry.price is None:
                continue

            if entry.currency == "KRW":
                rate = 1.0
            elif entry.exchange_rate:
                rate = entry.exchange_rate
            else:
                continue

            value = entry.quantity * entry.price * rate
            key = f"{entry.sector} - {entry.country}"

            if key in allocation_dict:
                allocation_dict[key] += value
            else:
                allocation_dict[key] = value

        allocations = [
            Allocation(name=key, weight=(value / total_value) * 100, value=value)
            for key, value in allocation_dict.items()
        ]

        return sorted(allocations, key=lambda x: x.weight, reverse=True)

    def calculate_country_allocation(
        self,
        date: str,
    ) -> Dict[str, float]:
        """
        국가별 비중

        Args:
            date: 조회 월

        Returns:
            {'미국': 68.5, '한국': 8.2, '홍콩': 7.8, ...}
        """
        entries = self.processor.get_entries_by_date(date)
        total_value = self.processor.calculate_portfolio_value(date)

        if total_value == 0:
            return {}

        country_dict = {}

        for entry in entries:
            if entry.ticker in ["KOSPI", "S&P"]:
                continue
            if entry.quantity is None or entry.price is None:
                continue

            if entry.currency == "KRW":
                rate = 1.0
            elif entry.exchange_rate:
                rate = entry.exchange_rate
            else:
                continue

            value = entry.quantity * entry.price * rate

            if entry.country in country_dict:
                country_dict[entry.country] += value
            else:
                country_dict[entry.country] = value

        return {k: (v / total_value) * 100 for k, v in country_dict.items()}

    def calculate_sector_allocation(
        self,
        date: str,
    ) -> Dict[str, float]:
        """
        섹터별 비중

        Args:
            date: 조회 월

        Returns:
            {'Information Technology': 45.2, 'Consumer Staples': 20.5, ...}
        """
        entries = self.processor.get_entries_by_date(date)
        total_value = self.processor.calculate_portfolio_value(date)

        if total_value == 0:
            return {}

        sector_dict = {}

        for entry in entries:
            if entry.ticker in ["KOSPI", "S&P"]:
                continue
            if entry.quantity is None or entry.price is None:
                continue

            if entry.currency == "KRW":
                rate = 1.0
            elif entry.exchange_rate:
                rate = entry.exchange_rate
            else:
                continue

            value = entry.quantity * entry.price * rate

            if entry.sector in sector_dict:
                sector_dict[entry.sector] += value
            else:
                sector_dict[entry.sector] = value

        return {k: (v / total_value) * 100 for k, v in sector_dict.items()}

    def get_top_holdings(
        self,
        date: str,
        n: int = 10,
    ) -> List[TopHolding]:
        """
        Top N 구성종목

        Args:
            date: 조회 월
            n: 상위 N개

        Returns:
            [{'rank': 1, 'ticker': 'BABA', 'name': '알리바바', 'weight': 9.5, 'sector': 'IT'}, ...]
        """
        entries = self.processor.get_entries_by_date(date)
        total_value = self.processor.calculate_portfolio_value(date)

        if total_value == 0:
            return []

        holdings = []

        for entry in entries:
            if entry.ticker in ["KOSPI", "S&P"]:
                continue
            if entry.quantity is None or entry.price is None:
                continue

            if entry.currency == "KRW":
                rate = 1.0
            elif entry.exchange_rate:
                rate = entry.exchange_rate
            else:
                continue

            value = entry.quantity * entry.price * rate
            weight = (value / total_value) * 100

            holdings.append(
                TopHolding(
                    rank=0,
                    ticker=entry.ticker,
                    name=entry.name,
                    weight=weight,
                    sector=entry.sector,
                    country=entry.country,
                )
            )

        holdings.sort(key=lambda x: x.weight, reverse=True)

        for i, h in enumerate(holdings[:n]):
            h.rank = i + 1

        return holdings[:n]

    def calculate_performance_summary(
        self,
        period_returns: List,
        benchmark_returns: Optional[Dict] = None,
    ) -> PerformanceSummary:
        """
        성과 요약

        Args:
            period_returns: 월별 수익률 목록 (TWRCalculator.PeriodReturn)
            benchmark_returns: 벤치마크 수익률 {'2025-05': 1.2, ...}

        Returns:
            PerformanceSummary
        """
        if not period_returns:
            return PerformanceSummary(
                ytd_return=0,
                mtd_return=0,
                one_year_return=0,
                three_year_annualized=0,
                since_inception_annualized=0,
                monthly_returns=[],
            )

        mtd_return = period_returns[-1].twr_estimate * 100 if period_returns else 0

        now = pd.Timestamp.now()
        current_month = now.strftime("%Y-%m")

        ytd_returns = [pr for pr in period_returns if pr.date.startswith(now.strftime("%Y-"))]
        ytd_return = 0
        if ytd_returns:
            cumulative = 1.0
            for pr in ytd_returns:
                cumulative *= (1 + pr.twr_estimate)
            ytd_return = (cumulative - 1) * 100

        if len(period_returns) >= 12:
            yearly_returns = period_returns[-12:]
            cumulative = 1.0
            for pr in yearly_returns:
                cumulative *= (1 + pr.twr_estimate)
            one_year_return = (cumulative - 1) * 100
        else:
            cumulative = 1.0
            for pr in period_returns:
                cumulative *= (1 + pr.twr_estimate)
            one_year_return = (cumulative - 1) * 100

        if len(period_returns) >= 36:
            three_year_cumulative = 1.0
            for pr in period_returns[-36:]:
                three_year_cumulative *= (1 + pr.twr_estimate)
            three_year_annualized = ((three_year_cumulative ** (12 / 36)) - 1) * 100
        else:
            three_year_annualized = 0

        cumulative = 1.0
        for pr in period_returns:
            cumulative *= (1 + pr.twr_estimate)
        since_inception = ((cumulative ** (12 / len(period_returns))) - 1) * 100

        monthly_returns = [
            {
                "month": pr.date,
                "return": round(pr.twr_estimate * 100, 2),
                "mwR": round(pr.mwr * 100, 2),
            }
            for pr in period_returns
        ]

        return PerformanceSummary(
            ytd_return=round(ytd_return, 2),
            mtd_return=round(mtd_return, 2),
            one_year_return=round(one_year_return, 2),
            three_year_annualized=round(three_year_annualized, 2),
            since_inception_annualized=round(since_inception, 2),
            monthly_returns=monthly_returns,
        )

    def calculate_risk_metrics(
        self,
        period_returns: List,
    ) -> Dict:
        """
        리스크 지표 계산

        Args:
            period_returns: 월별 수익률 목록

        Returns:
            {
                'volatility': 12.5,    # 연간 변동성
                'sharpe_ratio': 1.2,   # 샤프 비율
                'max_drawdown': -8.5,  # 최대 손실
                'beta': 0.95           # 베타
            }
        """
        if not period_returns or len(period_returns) < 2:
            return {
                "volatility": 0,
                "sharpe_ratio": 0,
                "max_drawdown": 0,
                "beta": 0,
            }

        returns = [pr.twr_estimate for pr in period_returns]
        monthly_returns_series = pd.Series(returns)

        volatility = monthly_returns_series.std() * sqrt(12) * 100

        risk_free_rate = 0.03
        excess_returns = monthly_returns_series.mean() * 12 - risk_free_rate
        sharpe_ratio = excess_returns / (volatility / 100) if volatility > 0 else 0

        cumulative = (1 + pd.Series(returns)).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() * 100

        beta = 1.0

        return {
            "volatility": round(volatility, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown": round(max_drawdown, 2),
            "beta": round(beta, 2),
        }

    def calculate_top_10_weight(self, date: str) -> float:
        """
        Top 10 비중 계산

        Args:
            date: 조회 월

        Returns:
            Top 10 비중 (%)
        """
        top_10 = self.get_top_holdings(date, n=10)
        return sum(h.weight for h in top_10)

    def get_fund_size(self, date: str) -> float:
        """
        Fund Size 조회

        Args:
            date: 조회 월

        Returns:
            Fund Size (KRW)
        """
        return self.processor.calculate_portfolio_value(date)


def test_analyzer():
    """PortfolioAnalyzer 테스트"""
    from src.data_processor import DataProcessor
    from src.twr_calculator import TWRCalculator

    processor = DataProcessor("data/portfolio.csv")
    calculator = TWRCalculator()
    analyzer = PortfolioAnalyzer(processor)

    print("=" * 50)
    print("PortfolioAnalyzer Test")
    print("=" * 50)

    dates = processor.get_all_dates()
    values = processor.calculate_all_values()

    quantity_changes = {}
    for i in range(1, len(dates)):
        curr_date = dates[i]
        changes = processor.detect_quantity_changes(dates[i - 1], curr_date)
        if changes:
            quantity_changes[curr_date] = changes

    period_returns = calculator.calculate_portfolio_twr(
        dates, values, quantity_changes, processor
    )

    latest = dates[-1]
    print(f"\n[Test] Analysis for {latest}")

    print(f"\n  Country Allocation:")
    country_alloc = analyzer.calculate_country_allocation(latest)
    for country, weight in sorted(country_alloc.items(), key=lambda x: -x[1])[:5]:
        print(f"    {country}: {weight:.1f}%")

    print(f"\n  Sector Allocation:")
    sector_alloc = analyzer.calculate_sector_allocation(latest)
    for sector, weight in sorted(sector_alloc.items(), key=lambda x: -x[1])[:5]:
        print(f"    {sector}: {weight:.1f}%")

    print(f"\n  Top 10 Holdings:")
    top_10 = analyzer.get_top_holdings(latest, n=10)
    for h in top_10[:5]:
        print(f"    {h.rank}. {h.name}: {h.weight:.1f}%")

    print(f"\n  Performance Summary:")
    perf = analyzer.calculate_performance_summary(period_returns)
    print(f"    YTD: {perf.ytd_return}%")
    print(f"    1Y: {perf.one_year_return}%")
    print(f"    Since Inception (Ann.): {perf.since_inception_annualized}%")

    print(f"\n  Risk Metrics:")
    risk = analyzer.calculate_risk_metrics(period_returns)
    print(f"    Volatility: {risk['volatility']}%")
    print(f"    Sharpe Ratio: {risk['sharpe_ratio']}")
    print(f"    Max Drawdown: {risk['max_drawdown']}%")

    print(f"\n  Fund Size: {analyzer.get_fund_size(latest):,.0f} KRW")
    print(f"  Top 10 Weight: {analyzer.calculate_top_10_weight(latest):.1f}%")


if __name__ == "__main__":
    test_analyzer()
