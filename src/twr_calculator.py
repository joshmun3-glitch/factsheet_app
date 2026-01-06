"""
Phase 3: TWR Calculator
수량변화 기반 TWR(추정) 계산 엔진
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CashFlow:
    """현금 흐름"""
    ticker: str
    name: str
    date: str
    quantity_change: int
    price: float
    exchange_rate: float
    cash_flow_krw: float

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PeriodReturn:
    """기간별 수익률"""
    date: str
    prev_date: str
    begin_value: float
    end_value: float
    cash_flow: float
    mwr: float
    twr_estimate: float

    def to_dict(self) -> Dict:
        return asdict(self)


class TWRCalculator:
    """
    TWR(시간가중수익률) 계산 엔진
    """

    def calculate_cash_flow(
        self,
        ticker: str,
        name: str,
        date: str,
        quantity_change: int,
        price: float,
        exchange_rate: float = 1.0,
    ) -> Optional[CashFlow]:
        """
        현금 흐름 계산

        수량 증가 = 매수 = 현금 유입 (+)
        수량 감소 = 매도 = 현금 인출 (-)

        Args:
            ticker: 종목 코드
            name: 종목명
            date: 날짜
            quantity_change: 수량 변화 (양수=매수, 음수=매도)
            price: 당월 초 가격 (전월 말 가격)
            exchange_rate: 환율

        Returns:
            CashFlow 인스턴스 또는 None (price가 None이면)
        """
        if price is None:
            logger.warning(f"Cannot calculate cash flow for {ticker}: price is None")
            return None

        cash_flow_krw = quantity_change * price * exchange_rate

        return CashFlow(
            ticker=ticker,
            name=name,
            date=date,
            quantity_change=quantity_change,
            price=price,
            exchange_rate=exchange_rate,
            cash_flow_krw=cash_flow_krw,
        )

    def calculate_period_return(
        self,
        prev_date: str,
        curr_date: str,
        prev_value: float,
        curr_value: float,
        cash_flows: List[CashFlow],
    ) -> PeriodReturn:
        """
        월별 수익률 계산

        TWR(추정) = (당월 총액 - 수량변화환산액) / 전월 총액
        MWR = (당월 총액 - 전월 총액) / 전월 총액

        Args:
            prev_date: 전월 날짜
            curr_date: 당월 날짜
            prev_value: 전월 말 평가액
            curr_value: 당월 말 평가액
            cash_flows: 현금 흐름 목록

        Returns:
            PeriodReturn 인스턴스
        """
        total_cash_flow = sum(cf.cash_flow_krw for cf in cash_flows)

        if prev_value == 0:
            mwr = 0.0
            twr_estimate = 0.0
            logger.warning(f"Previous value is 0 for {prev_date} → {curr_date}")
        else:
            mwr = (curr_value - prev_value) / prev_value
            twr_estimate = (curr_value - total_cash_flow) / prev_value - 1

        return PeriodReturn(
            date=curr_date,
            prev_date=prev_date,
            begin_value=prev_value,
            end_value=curr_value,
            cash_flow=total_cash_flow,
            mwr=mwr,
            twr_estimate=twr_estimate,
        )

    def calculate_portfolio_twr(
        self,
        dates: List[str],
        portfolio_values: Dict[str, float],
        quantity_changes: Dict[str, List[Dict]],
        processor,
    ) -> List[PeriodReturn]:
        """
        전체 포트폴리오 TWR 계산

        Args:
            dates: 날짜 목록 (정렬됨)
            portfolio_values: {날짜: 평가액}
            quantity_changes: {날짜: [{ticker, prev_qty, curr_qty, change, type}]}
            processor: DataProcessor 인스턴스 (가격 조회를 위해)

        Returns:
            월별 수익률 목록
        """
        period_returns = []

        for i in range(1, len(dates)):
            prev_date = dates[i - 1]
            curr_date = dates[i]

            prev_value = portfolio_values.get(prev_date, 0)
            curr_value = portfolio_values.get(curr_date, 0)

            if prev_value == 0:
                logger.warning(f"Skipping {prev_date} → {curr_date}: previous value is 0")
                continue

            changes = quantity_changes.get(curr_date, [])
            cash_flows = []

            for change in changes:
                ticker = change["ticker"]
                name = change["name"]
                qty_change = change["change"]
                currency = change.get("currency", "KRW")

                beginning_price = processor.get_beginning_price(ticker, curr_date)
                if beginning_price is None:
                    logger.warning(f"No beginning price for {ticker} on {curr_date}")
                    continue

                entry = next(
                    (e for e in processor.get_entries_by_date(curr_date) if e.ticker == ticker),
                    None,
                )
                exchange_rate = entry.exchange_rate if entry else 1.0

                cf = self.calculate_cash_flow(
                    ticker=ticker,
                    name=name,
                    date=curr_date,
                    quantity_change=qty_change,
                    price=beginning_price,
                    exchange_rate=exchange_rate if exchange_rate else 1.0,
                )
                if cf:
                    cash_flows.append(cf)

            period_return = self.calculate_period_return(
                prev_date=prev_date,
                curr_date=curr_date,
                prev_value=prev_value,
                curr_value=curr_value,
                cash_flows=cash_flows,
            )

            period_returns.append(period_return)
            logger.info(
                f"TWR {period_return.date}: {period_return.twr_estimate*100:.2f}% "
                f"(MWR: {period_return.mwr*100:.2f}%, CF: {period_return.cash_flow:,.0f})"
            )

        return period_returns

    def calculate_cumulative_return(
        self,
        period_returns: List,
        target_months = None,
    ) -> Dict[str, float]:
        """
        누적 수익률 계산

        Args:
            period_returns: 월별 수익률 목록
            target_months: 특정 기간만 계산 (None이면 전체)

        Returns:
            {'YTD': 12.5, '1M': 1.2, '3M': 3.5, '6M': 8.2, '1Y': 15.3}
        """
        if not period_returns:
            return {}

        returns_dict = {pr.date: pr.twr_estimate for pr in period_returns}
        dates = list(returns_dict.keys())

        cumulative_returns = {}

        now = datetime.now()
        current_month = now.strftime("%Y-%m")

        def calc_cumulative(start_idx: int) -> float:
            cumulative = 1.0
            for i in range(start_idx, len(period_returns)):
                cumulative *= (1 + period_returns[i].twr_estimate)
            return (cumulative - 1) * 100

        if len(dates) >= 1:
            cumulative_returns["1M"] = period_returns[-1].twr_estimate * 100

        if len(dates) >= 3:
            cumulative_returns["3M"] = calc_cumulative(len(period_returns) - 3)

        if len(dates) >= 6:
            cumulative_returns["6M"] = calc_cumulative(len(period_returns) - 6)

        if len(dates) >= 12:
            cumulative_returns["1Y"] = calc_cumulative(len(period_returns) - 12)

        ytd_start = [d for d in dates if d.startswith(now.strftime("%Y-"))]
        if ytd_start:
            ytd_idx = dates.index(ytd_start[0])
            cumulative_returns["YTD"] = calc_cumulative(ytd_idx)

        return cumulative_returns

    def calculate_annualized_return(
        self,
        period_returns: List[PeriodReturn],
    ) -> float:
        """
        연환산 수익률 (CAGR) 계산

        Args:
            period_returns: 월별 수익률 목록

        Returns:
            CAGR (percentage)
        """
        if not period_returns:
            return 0.0

        total_months = len(period_returns)
        if total_months == 0:
            return 0.0

        cumulative = 1.0
        for pr in period_returns:
            cumulative *= (1 + pr.twr_estimate)

        years = total_months / 12
        if years == 0:
            return 0.0

        cagr = (cumulative ** (1 / years) - 1) * 100
        return cagr

    def calculate_monthly_returns_series(
        self,
        period_returns: List[PeriodReturn],
    ) -> List[Dict]:
        """
        월별 수익률 시리즈 반환

        Returns:
            [{'month': '2025-04', 'return': 1.25}, ...]
        """
        return [
            {"month": pr.date, "return": round(pr.twr_estimate * 100, 2)}
            for pr in period_returns
        ]


def test_twr_calculator():
    """TWRCalculator 테스트"""
    from src.data_processor import DataProcessor

    processor = DataProcessor("data/portfolio.csv")
    calculator = TWRCalculator()

    print("=" * 50)
    print("TWR Calculator Test")
    print("=" * 50)

    dates = processor.get_all_dates()
    values = processor.calculate_all_values()

    print(f"\n[Test] Portfolio values:")
    for date in dates:
        print(f"  {date}: {values[date]:,.0f} KRW")

    quantity_changes = {}
    for i in range(1, len(dates)):
        curr_date = dates[i]
        changes = processor.detect_quantity_changes(dates[i - 1], curr_date)
        if changes:
            quantity_changes[curr_date] = changes

    print(f"\n[Test] Quantity changes:")
    for date, changes in list(quantity_changes.items())[:3]:
        print(f"  {date}: {len(changes)} changes")
        for c in changes[:2]:
            print(f"    {c['ticker']}: {c['prev_qty']} → {c['curr_qty']} ({c['type']})")

    print(f"\n[Test] TWR Calculation:")
    period_returns = calculator.calculate_portfolio_twr(
        dates, values, quantity_changes, processor
    )

    for pr in period_returns:
        print(
            f"  {pr.date}: TWR={pr.twr_estimate*100:.2f}%, MWR={pr.mwr*100:.2f}%, "
            f"Value={pr.begin_value:,.0f} → {pr.end_value:,.0f}"
        )

    cumulative = calculator.calculate_cumulative_return(period_returns)
    print(f"\n[Test] Cumulative returns:")
    for period, ret in cumulative.items():
        print(f"  {period}: {ret:.2f}%")

    annualized = calculator.calculate_annualized_return(period_returns)
    print(f"\n[Test] Annualized return (CAGR): {annualized:.2f}%")


if __name__ == "__main__":
    test_twr_calculator()
