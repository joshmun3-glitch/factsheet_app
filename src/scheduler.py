"""
Phase 6: Scheduler
월별 자동화 스케줄링
"""

import schedule
import time
from datetime import datetime, timedelta
from pathlib import Path
import logging
import sys
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class PortfolioScheduler:
    """
    월별 자동화 스케줄러
    """

    def __init__(self, config_path: str = "config/settings.py"):
        self.config_path = Path(config_path)
        self.logger = self._setup_logging()
        self.pipeline_func: Optional[Callable] = None

    def _setup_logging(self) -> logging.Logger:
        """로깅 설정"""
        logger = logging.getLogger("scheduler")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    def set_pipeline_function(self, func: Callable):
        """
        실행할 파이프라인 함수 설정

        Args:
            func: () -> None 형태의 함수
        """
        self.pipeline_func = func

    def update_prices(self):
        """주가/환율 업데이트"""
        try:
            from src.data_fetcher import DataFetcher
            from src.data_processor import DataProcessor

            fetcher = DataFetcher()
            processor = DataProcessor("data/portfolio.csv")

            latest_date = processor.get_latest_date()
            if latest_date:
                missing = processor.detect_missing_data(latest_date)
                if missing["missing_stocks"].get(latest_date) or missing["missing_rates"]:
                    processor.fill_missing_prices(fetcher, latest_date)
                    processor.fill_index_data(fetcher, [latest_date])
                    processor.save()
                    self.logger.info(f"Prices updated for {latest_date}")
                else:
                    self.logger.info(f"No missing data for {latest_date}")

        except Exception as e:
            self.logger.error(f"Error updating prices: {e}")
            raise

    def run_pipeline(self):
        """전체 파이프라인 실행"""
        if self.pipeline_func:
            try:
                self.logger.info("Starting pipeline...")
                self.pipeline_func()
                self.logger.info("Pipeline completed successfully")
            except Exception as e:
                self.logger.error(f"Pipeline failed: {e}")
                self.send_alert(f"Pipeline failed: {str(e)}")
        else:
            self.logger.warning("No pipeline function set")

    def send_alert(self, message: str):
        """실패 알림"""
        self.logger.info(f"Alert: {message}")

    def schedule_monthly(
        self,
        day: int = 1,
        hour: int = 2,
        minute: int = 0,
    ):
        """
        월별 스케줄 설정

        Args:
            day: 실행일 (기본 1일)
            hour: 실행시 (기본 새벽 2시)
            minute: 실행분
        """
        schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(self._monthly_job)

        self.logger.info(f"Scheduled monthly job: day {day} at {hour:02d}:{minute:02d}")

    def _monthly_job(self):
        """월별 실행 작업"""
        now = datetime.now()

        if now.day == 1:
            self.logger.info(f"Running monthly job for {now.strftime('%Y-%m')}")
            self.run_pipeline()

    def schedule_weekly(
        self,
        weekday: int = 0,
        hour: int = 2,
        minute: int = 0,
    ):
        """
        주별 스케줄 설정

        Args:
            weekday: 요일 (0=월, 6=일)
            hour: 실행시
            minute: 실행분
        """
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        schedule.every().weekday.at(f"{hour:02d}:{minute:02d}").do(
            lambda: self.logger.info(f"Weekly job triggered")
        )

        self.logger.info(
            f"Scheduled weekly job: {day_names[weekday]} at {hour:02d}:{minute:02d}"
        )

    def start_blocking(self):
        """
        블로킹 모드로 스케줄러 시작
        (Ctrl+C로 종료)
        """
        self.logger.info("Scheduler started (blocking mode)")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)

        except KeyboardInterrupt:
            self.logger.info("Scheduler stopped by user")

    def start_background(self) -> threading.Thread:
        """
        백그라운드 모드로 스케줄러 시작

        Returns:
            Thread 인스턴스
        """
        thread = threading.Thread(target=self.start_blocking, daemon=True)
        thread.start()
        self.logger.info("Scheduler started (background mode)")
        return thread

    @staticmethod
    def run_manually(target_date: str = None):
        """
        수동 실행

        Args:
            target_date: 특정 월만 처리 (YYYY-MM-DD)
        """
        from src.main import generate_monthly_factsheet

        if target_date:
            generate_monthly_factsheet(target_date=target_date)
        else:
            generate_monthly_factsheet()


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


def test_scheduler():
    """Scheduler 테스트"""
    print("=" * 50)
    print("Scheduler Test")
    print("=" * 50)

    scheduler = PortfolioScheduler()
    scheduler.set_pipeline_function(lambda: print("Pipeline executed!"))

    print("\n[Test] Scheduling jobs...")
    scheduler.schedule_monthly(day=1, hour=2, minute=0)

    print("\n[Test] Running pipeline manually...")
    scheduler.run_pipeline()

    print("\n[Test] Scheduler configured successfully")


if __name__ == "__main__":
    setup_logging()
    test_scheduler()
