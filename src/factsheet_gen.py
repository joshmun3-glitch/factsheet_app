"""
Phase 5: Factsheet Generator
Fundsmith 스타일 HTML/PDF 팩트시트 생성
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)

PLOTLY_AVAILABLE = False
WEASYPRINT_AVAILABLE = False
JINJA2_AVAILABLE = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    logger.warning("plotly not installed, chart generation will be skipped")

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    logger.warning(f"weasyprint not available (requires GTK): {e}")
    WEASYPRINT_AVAILABLE = False

try:
    from jinja2 import Template
    JINJA2_AVAILABLE = True
except ImportError:
    logger.warning("jinja2 not installed, using simple string formatting")


@dataclass
class FactsheetData:
    """팩트시트 데이터"""
    report_date: str
    fund_size: float
    num_holdings: int
    top_10_weight: float

    fund_name: str = "My Portfolio"
    fund_size_currency: str = "KRW"
    yield_pct: float = 0.0
    ptr_pct: float = 0.0

    ytd_return: float = 0
    mtd_return: float = 0
    one_year_return: float = 0
    three_year_annualized: float = 0
    since_inception_annualized: float = 0

    sector_allocation: Dict[str, float] = field(default_factory=dict)
    country_allocation: Dict[str, float] = field(default_factory=dict)
    top_10_holdings: List[Dict[str, Any]] = field(default_factory=list)
    monthly_returns: List[Dict[str, Any]] = field(default_factory=list)

    volatility: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0

    benchmark_return: Optional[float] = None
    alpha: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class FactsheetGenerator:
    """
    Fundsmith 스타일 팩트시트 생성기
    """

    def __init__(self, template_dir: str = "templates"):
        self.template_dir = Path(template_dir)

    def _format_number(self, value: float, decimals: int = 0) -> str:
        """숫자 포맷팅"""
        if value is None:
            return "N/A"
        if decimals == 0:
            return f"{value:,.0f}"
        return f"{value:,.{decimals}f}"

    def _format_pct(self, value: float) -> str:
        """퍼센트 포맷팅"""
        if value is None:
            return "N/A"
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.1f}%"

    def _create_pie_chart(
        self,
        labels: List[str],
        values: List[float],
        title: str,
        colors: List[str] = None,
    ) -> str:
        """파이 차트 생성 (HTML)"""
        if not PLOTLY_AVAILABLE:
            return f"<p style='color:gray;'>{title}: Chart not available (plotly not installed)</p>"

        if colors is None:
            colors = [
                "#1a3a5c", "#2e5984", "#4579ac", "#5c99d4",
                "#73b9fc", "#8ad1ff", "#a1e5ff", "#b8f9ff",
            ]

        fig = go.Figure(
            data=[
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.4,
                    marker=dict(colors=colors[: len(labels)]),
                    textinfo="label+percent",
                )
            ]
        )

        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            showlegend=True,
            legend=dict(orientation="h", y=-0.1),
            margin=dict(t=30, b=30, l=10, r=10),
            height=250,
        )

        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    def _create_bar_chart(
        self,
        x: List[str],
        y: List[float],
        title: str,
        colors: List[str] = None,
    ) -> str:
        """바 차트 생성 (HTML)"""
        if not PLOTLY_AVAILABLE:
            return f"<p style='color:gray;'>{title}: Chart not available (plotly not installed)</p>"

        bar_colors = ["#1a3a5c" if v >= 0 else "#c0392b" for v in y]

        fig = go.Figure(
            data=[
                go.Bar(
                    x=x,
                    y=y,
                    marker_color=bar_colors,
                    text=[f"{v:.1f}%" for v in y],
                    textposition="auto",
                )
            ]
        )

        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            xaxis=dict(title="", tickangle=-45),
            yaxis=dict(title="Return (%)"),
            margin=dict(t=30, b=60, l=50, r=20),
            height=250,
        )

        return fig.to_html(full_html=False, include_plotlyjs=False)

    def _create_performance_chart(
        self,
        monthly_returns: List[Dict[str, Any]],
        ytd_return: float,
        one_year_return: float,
    ) -> str:
        """성과 차트 생성 (HTML)"""
        if not PLOTLY_AVAILABLE:
            return "<p style='color:gray;'>Performance chart not available (plotly not installed)</p>"

        months = [r["month"][-2:] for r in monthly_returns]
        returns = [r["return"] for r in monthly_returns]

        cumulative = [100]
        for r in returns:
            cumulative.append(cumulative[-1] * (1 + r / 100))

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=("Monthly Returns (%)", "Cumulative Growth (%)"),
            specs=[[{"type": "bar"}, {"type": "scatter"}]],
        )

        fig.add_trace(
            go.Bar(
                x=months,
                y=returns,
                marker_color=["#27ae60" if v >= 0 else "#e74c3c" for v in returns],
                name="Monthly",
            ),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=list(range(len(months) + 1)),
                y=cumulative,
                mode="lines+markers",
                line=dict(color="#1a3a5c", width=2),
                name="Cumulative",
            ),
            row=1,
            col=2,
        )

        fig.update_layout(
            showlegend=False,
            margin=dict(t=30, b=30, l=50, r=20),
            height=250,
        )

        return fig.to_html(full_html=False, include_plotlyjs=False)

    def generate_charts(self, data: FactsheetData) -> Dict[str, str]:
        """팩트시트용 차트 생성"""
        charts: Dict[str, str] = {}

        if data.sector_allocation:
            charts["sector_chart"] = self._create_pie_chart(
                labels=list(data.sector_allocation.keys()),
                values=list(data.sector_allocation.values()),
                title="Sector Allocation",
            )

        if data.country_allocation:
            charts["country_chart"] = self._create_pie_chart(
                labels=list(data.country_allocation.keys()),
                values=list(data.country_allocation.values()),
                title="Geographic Allocation",
            )

        charts["performance_chart"] = self._create_performance_chart(
            monthly_returns=data.monthly_returns,
            ytd_return=data.ytd_return,
            one_year_return=data.one_year_return,
        )

        if data.monthly_returns:
            charts["monthly_bar_chart"] = self._create_bar_chart(
                x=[r["month"][-2:] for r in data.monthly_returns[-12:]],
                y=[r["return"] for r in data.monthly_returns[-12:]],
                title="Last 12 Months Returns (%)",
            )

        return charts

    def _generate_top_10_html(self, top_10: List[Dict[str, Any]]) -> str:
        """Top 10 구성종목 테이블 HTML"""
        if not top_10:
            return "<p>No holdings data available</p>"

        rows = ""
        for h in top_10:
            rows += f"""
            <tr>
                <td>{h.get('rank', '-')}</td>
                <td>{h.get('ticker', '')}</td>
                <td>{h.get('name', '')}</td>
                <td>{h.get('sector', '')}</td>
                <td>{h.get('country', '')}</td>
                <td class="text-right">{h.get('weight', 0):.1f}%</td>
            </tr>
            """

        return f"""
        <table class="factsheet-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Ticker</th>
                    <th>Name</th>
                    <th>Sector</th>
                    <th>Country</th>
                    <th class="text-right">Weight</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """

    def _generate_monthly_table_html(
        self, monthly_returns: List[Dict[str, Any]]
    ) -> str:
        """월별 성과 테이블 HTML"""
        if not monthly_returns:
            return "<p>No performance data available</p>"

        def format_month(date_str: str) -> str:
            """YYYY-MM-DD를 MM월 형식으로 변환"""
            try:
                parts = date_str.split("-")
                if len(parts) == 3:
                    month_num = int(parts[1])
                    month_names = ["1월", "2월", "3월", "4월", "5월", "6월",
                                   "7월", "8월", "9월", "10월", "11월", "12월"]
                    return month_names[month_num - 1]
            except:
                pass
            return date_str[-2:]

        html = '<div class="monthly-table-grid">'

        for i in range(0, len(monthly_returns), 4):
            chunk = monthly_returns[i : i + 4]
            html += '<div class="monthly-row">'

            for r in chunk:
                month = format_month(r.get("month", ""))
                ret = r.get("return", 0)
                color_class = "positive" if ret >= 0 else "negative"
                html += f"""
                <div class="monthly-cell">
                    <div class="month-name">{month}</div>
                    <div class="month-return {color_class}">{ret:+.1f}%</div>
                </div>
                """

            html += "</div>"

        html += "</div>"
        return html

    def generate_html(self, data: FactsheetData) -> str:
        """HTML 팩트시트 생성"""
        charts = self.generate_charts(data)
        top_10_html = self._generate_top_10_html(data.top_10_holdings)
        monthly_table_html = self._generate_monthly_table_html(data.monthly_returns)

        fund_size_str = f"{data.fund_size:,.0f} {data.fund_size_currency}"

        def format_pct(v):
            if v is None:
                return "N/A"
            sign = "+" if v >= 0 else ""
            return f"{sign}{v:.1f}%"

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Portfolio Factsheet - {data.report_date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 12px; color: #333; background: #fff; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #1a3a5c 0%, #2c5282 100%); color: white; padding: 20px 30px; border-radius: 8px 8px 0 0; display: flex; justify-content: space-between; align-items: center; }}
        .header h1 {{ font-size: 24px; font-weight: 600; }}
        .header .date {{ font-size: 14px; opacity: 0.9; }}
        .key-facts {{ background: #f8fafc; padding: 15px 30px; display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; border-bottom: 1px solid #e2e8f0; }}
        .key-fact {{ text-align: center; }}
        .key-fact .label {{ font-size: 11px; color: #64748b; text-transform: uppercase; margin-bottom: 4px; }}
        .key-fact .value {{ font-size: 18px; font-weight: 600; color: #1a3a5c; }}
        .section {{ padding: 20px 30px; border-bottom: 1px solid #e2e8f0; }}
        .section-title {{ font-size: 14px; font-weight: 600; color: #1a3a5c; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #1a3a5c; }}
        .two-column {{ display: grid; grid-template-columns: 1fr 1fr; gap: 30px; }}
        .factsheet-table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
        .factsheet-table th {{ background: #1a3a5c; color: white; padding: 8px 10px; text-align: left; font-weight: 500; }}
        .factsheet-table td {{ padding: 8px 10px; border-bottom: 1px solid #e2e8f0; }}
        .text-right {{ text-align: right; }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        .monthly-table-grid {{ display: flex; flex-direction: column; gap: 8px; }}
        .monthly-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
        .monthly-cell {{ background: #f8fafc; padding: 8px; border-radius: 4px; text-align: center; }}
        .month-name {{ font-size: 10px; color: #64748b; margin-bottom: 2px; }}
        .month-return {{ font-size: 14px; font-weight: 600; }}
        .performance-summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }}
        .perf-item {{ background: #f8fafc; padding: 12px; border-radius: 6px; text-align: center; }}
        .perf-item .label {{ font-size: 10px; color: #64748b; text-transform: uppercase; margin-bottom: 4px; }}
        .perf-item .value {{ font-size: 20px; font-weight: 600; color: #1a3a5c; }}
        .chart-container {{ margin: 15px 0; }}
        .footer {{ padding: 15px 30px; background: #f8fafc; font-size: 10px; color: #64748b; border-radius: 0 0 8px 8px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{data.fund_name}</h1>
        <div class="date">Factsheet as of {data.report_date}</div>
    </div>

    <div class="key-facts">
        <div class="key-fact">
            <div class="label">Fund Size</div>
            <div class="value">{fund_size_str}</div>
        </div>
        <div class="key-fact">
            <div class="label">Holdings</div>
            <div class="value">{data.num_holdings}</div>
        </div>
        <div class="key-fact">
            <div class="label">Top 10 Weight</div>
            <div class="value">{data.top_10_weight:.1f}%</div>
        </div>
        <div class="key-fact">
            <div class="label">Volatility</div>
            <div class="value">{data.volatility:.1f}%</div>
        </div>
        <div class="key-fact">
            <div class="label">Sharpe Ratio</div>
            <div class="value">{data.sharpe_ratio:.2f}</div>
        </div>
    </div>

    <div class="section">
        <h2 class="section-title">Performance Summary</h2>
        <div class="performance-summary">
            <div class="perf-item">
                <div class="label">YTD</div>
                <div class="value {'positive' if data.ytd_return >= 0 else 'negative'}">{format_pct(data.ytd_return)}</div>
            </div>
            <div class="perf-item">
                <div class="label">1 Year</div>
                <div class="value {'positive' if data.one_year_return >= 0 else 'negative'}">{format_pct(data.one_year_return)}</div>
            </div>
            <div class="perf-item">
                <div class="label">3 Year (Ann.)</div>
                <div class="value {'positive' if data.three_year_annualized >= 0 else 'negative'}">{format_pct(data.three_year_annualized)}</div>
            </div>
            <div class="perf-item">
                <div class="label">Since Inception (Ann.)</div>
                <div class="value {'positive' if data.since_inception_annualized >= 0 else 'negative'}">{format_pct(data.since_inception_annualized)}</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2 class="section-title">Top 10 Holdings</h2>
        {top_10_html}
    </div>

    <div class="section">
        <h2 class="section-title">Allocation</h2>
        <div class="two-column">
            <div class="chart-container">
                {charts.get('sector_chart', '')}
            </div>
            <div class="chart-container">
                {charts.get('country_chart', '')}
            </div>
        </div>
    </div>

    <div class="section">
        <h2 class="section-title">Monthly Performance</h2>
        {monthly_table_html}
    </div>

    <div class="section">
        <h2 class="section-title">Performance Chart</h2>
        {charts.get('performance_chart', '')}
    </div>

    <div class="footer">
        <p>Generated by Portfolio Factsheet Automation Pipeline</p>
        <p>Past performance is not indicative of future results.</p>
    </div>
</body>
</html>
        """

        return html

    def convert_to_pdf(
        self,
        html_path: str,
        output_path: str,
    ) -> str:
        """HTML → PDF 변환"""
        if not WEASYPRINT_AVAILABLE:
            logger.warning("weasyprint not installed, skipping PDF generation")
            return html_path

        try:
            HTML(filename=html_path).write_pdf(output_path)
            logger.info(f"PDF generated: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            return html_path

    def generate_factsheet(
        self,
        data: FactsheetData,
        output_dir: str,
        output_format: str = "both",
    ) -> Dict[str, str]:
        """팩트시트 생성 통합 함수"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        safe_date = data.report_date.replace("-", "")
        base_name = f"factsheet_{safe_date}"

        result: Dict[str, str] = {}

        html_content = self.generate_html(data)
        html_file_path = output_path / f"{base_name}.html"
        with open(html_file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        result["html"] = str(html_file_path)

        if output_format in ["pdf", "both"]:
            pdf_path = output_path / f"{base_name}.pdf"
            self.convert_to_pdf(str(html_file_path), str(pdf_path))
            if str(pdf_path).endswith(".pdf"):
                result["pdf"] = str(pdf_path)

        logger.info(f"Factsheet generated: {result}")
        return result


def test_factsheet_generator():
    """FactsheetGenerator 테스트"""
    from src.data_processor import DataProcessor
    from src.twr_calculator import TWRCalculator
    from src.analyzer import PortfolioAnalyzer

    processor = DataProcessor("data/portfolio.csv")
    calculator = TWRCalculator()
    analyzer = PortfolioAnalyzer(processor)

    print("=" * 50)
    print("FactsheetGenerator Test")
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

    perf_summary = analyzer.calculate_performance_summary(period_returns)
    risk_metrics = analyzer.calculate_risk_metrics(period_returns)

    latest = dates[-1]

    top_10 = analyzer.get_top_holdings(latest, n=10)
    top_10_dicts = [h.to_dict() for h in top_10]

    sector_alloc = analyzer.calculate_sector_allocation(latest)
    country_alloc = analyzer.calculate_country_allocation(latest)

    data = FactsheetData(
        report_date=latest,
        fund_size=analyzer.get_fund_size(latest),
        num_holdings=len(analyzer.processor.get_tickers_by_date(latest)),
        top_10_weight=analyzer.calculate_top_10_weight(latest),
        ytd_return=perf_summary.ytd_return,
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
    result = generator.generate_factsheet(data, "output/factsheets", output_format="html")

    print(f"\n[Test] Factsheet generated: {result['html']}")


if __name__ == "__main__":
    test_factsheet_generator()
