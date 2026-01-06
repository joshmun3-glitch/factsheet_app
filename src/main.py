"""
Portfolio Factsheet Automation Pipeline
월별 포트폴리오 TWR 계산 및 팩트시트 생성
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_fetcher import DataFetcher
from src.data_processor import DataProcessor
from src.twr_calculator import TWRCalculator
from src.analyzer import PortfolioAnalyzer
from src.factsheet_gen import FactsheetGenerator, FactsheetData
from src.scheduler import PortfolioScheduler
from datetime import datetime
import logging
import argparse


def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("portfolio.log", encoding="utf-8"),
        ],
    )


def generate_monthly_factsheet(
    csv_path: str = "data/portfolio.csv",
    output_dir: str = "output/factsheets",
    target_date = None,
):
    """
    월별 팩트시트 생성 통합 함수

    Args:
        csv_path: 포트폴리오 CSV 경로
        output_dir: 출력 디렉토리
        target_date: 대상 월 (YYYY-MM-DD, None이면 최신)
    """
    processor = DataProcessor(csv_path)
    fetcher = DataFetcher()

    if target_date is None:
        target_date = processor.get_latest_date()

    if target_date is None:
        raise ValueError("No date found in portfolio data")

    print(f"\n{'='*50}")
    print(f"Generating Factsheet for {target_date}")
    print(f"{'='*50}")

    print("\n[1/7] Checking for missing data...")
    missing = processor.detect_missing_data(target_date)

    idx_updated = 0
    if missing["missing_indices"]:
        print(f"  Found {len(missing['missing_indices'])} missing index values")
        idx_updated = processor.fill_index_data(fetcher, [target_date])
        print(f"  Updated {idx_updated} index values")

    stock_updated = 0
    if missing["missing_stocks"].get(target_date):
        print(f"  Found {len(missing['missing_stocks'][target_date])} missing stock prices")
        stock_updated = processor.fill_missing_prices(fetcher, target_date)
        print(f"  Updated {stock_updated} stock prices")

    if missing["missing_rates"]:
        print(f"  Found {len(missing['missing_rates'])} missing exchange rates")
        rate_updated = processor.fill_missing_prices(fetcher, target_date)
        print(f"  Updated {rate_updated} exchange rates")
        stock_updated += rate_updated

    # stocks 또는 indices 중 하나라도 업데이트되면 저장
    if stock_updated > 0 or idx_updated > 0:
        processor.save()
        print("  Portfolio data saved to CSV")

    print("\n[2/7] Calculating portfolio value...")
    portfolio_value = processor.calculate_portfolio_value(target_date)
    print(f"  Portfolio value: {portfolio_value:,.0f} KRW")

    print("\n[3/7] Calculating TWR...")
    dates = processor.get_all_dates()
    values = processor.calculate_all_values()

    quantity_changes = {}
    for i in range(1, len(dates)):
        curr_date = dates[i]
        changes = processor.detect_quantity_changes(dates[i - 1], curr_date)
        if changes:
            quantity_changes[curr_date] = changes

    calculator = TWRCalculator()
    period_returns = calculator.calculate_portfolio_twr(
        dates, values, quantity_changes, processor
    )

    print(f"  Calculated {len(period_returns)} periods of returns")

    print("\n[4/7] Analyzing portfolio...")
    analyzer = PortfolioAnalyzer(processor)
    sector_alloc = analyzer.calculate_sector_allocation(target_date)
    country_alloc = analyzer.calculate_country_allocation(target_date)
    top_10 = analyzer.get_top_holdings(target_date, n=10)
    top_10_dicts = [h.to_dict() for h in top_10]
    top_10_weight = analyzer.calculate_top_10_weight(target_date)
    num_holdings = len(analyzer.processor.get_tickers_by_date(target_date))

    print(f"  Sector allocation: {len(sector_alloc)} sectors")
    print(f"  Country allocation: {len(country_alloc)} countries")
    print(f"  Top 10 weight: {top_10_weight:.1f}%")

    print("\n[5/7] Calculating performance metrics...")
    perf_summary = analyzer.calculate_performance_summary(period_returns)
    risk_metrics = analyzer.calculate_risk_metrics(period_returns)

    print(f"  YTD Return: {perf_summary.ytd_return:.1f}%")
    print(f"  1Y Return: {perf_summary.one_year_return:.1f}%")
    print(f"  Volatility: {risk_metrics['volatility']:.1f}%")
    print(f"  Sharpe Ratio: {risk_metrics['sharpe_ratio']:.2f}")

    print("\n[6/7] Generating factsheet...")
    data = FactsheetData(
        report_date=target_date,
        fund_size=portfolio_value,
        num_holdings=num_holdings,
        top_10_weight=top_10_weight,
        ytd_return=perf_summary.ytd_return,
        mtd_return=perf_summary.mtd_return,
        one_year_return=perf_summary.one_year_return,
        three_year_annualized=perf_summary.three_year_annualized,
        since_inception_annualized=perf_summary.since_inception_annualized,
        sector_allocation=sector_alloc,
        country_allocation=country_alloc,
        top_10_holdings=top_10_dicts,
        monthly_returns=perf_summary.monthly_returns,
        volatility=risk_metrics["volatility"],
        sharpe_ratio=risk_metrics["sharpe_ratio"],
        max_drawdown=risk_metrics["max_drawdown"],
    )

    generator = FactsheetGenerator()
    result = generator.generate_factsheet(data, output_dir, output_format="html")

    print(f"  Generated: {result['html']}")

    print("\n[7/7] Complete!")
    print(f"{'='*50}")

    return result


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="Portfolio Factsheet Generator")
    parser.add_argument(
        "--date", "-d", type=str, help="Target date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--csv", type=str, default="data/portfolio.csv", help="Portfolio CSV path"
    )
    parser.add_argument(
        "--output", type=str, default="output/factsheets", help="Output directory"
    )
    parser.add_argument(
        "--schedule", action="store_true", help="Run scheduler"
    )
    parser.add_argument(
        "--schedule-monthly",
        action="store_true",
        help="Schedule monthly job",
    )

    args = parser.parse_args()

    setup_logging()

    if args.schedule or args.schedule_monthly:
        scheduler = PortfolioScheduler()
        if args.schedule_monthly:
            scheduler.schedule_monthly()
            scheduler.start_blocking()
        else:
            scheduler.run_manually()
    else:
        generate_monthly_factsheet(
            csv_path=args.csv,
            output_dir=args.output,
            target_date=args.date,
        )


if __name__ == "__main__":
    main()
