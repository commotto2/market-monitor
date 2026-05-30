name: Daily Market Report

on:
  schedule:
    - cron: '30 7 * * 1-5'
  workflow_dispatch:

jobs:
  daily-report:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install yfinance pandas matplotlib requests numpy pykrx

      - name: Run Daily Report
        env:
          TELEGRAM_TOKEN_MARKET: ${{ secrets.TELEGRAM_TOKEN_MARKET }}
          TELEGRAM_CHAT_DAILY:   ${{ secrets.TELEGRAM_CHAT_DAILY }}
          ANTHROPIC_API_KEY:     ${{ secrets.ANTHROPIC_API_KEY }}
          KIS_APP_KEY:           ${{ secrets.KIS_APP_KEY }}
          KIS_APP_SECRET:        ${{ secrets.KIS_APP_SECRET }}
          KIS_ACCESS_TOKEN:      ${{ secrets.KIS_ACCESS_TOKEN }}
        run: python reports/daily_report.py
