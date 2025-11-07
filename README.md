# does-coin-leave-on-applause

This repository contains the research design, automation scripts, and visualization assets for testing whether coins listed on major centralized exchanges (CEXs) experience short-term price declines within 10 days of listing. The English version appears first, followed by the Korean original.

---

## English Overview

### 1. Research Topic
- Research question: Do coins listed on major exchanges meaningfully decline within 10 days of listing?

### 2. Hypothesis Setup
- Null hypothesis (H₀): Coins listed on major exchanges do not exhibit a statistically significant downtrend within 10 days.
- Alternative hypothesis (H₁): Coins listed on major exchanges do exhibit a statistically significant downtrend within 10 days.

### 3. Exchange Definition and Selection Criteria
- “Major exchanges” are leading CEXs evaluated by trading volume, security posture, user trust, and regulatory compliance.
- Data sources: CoinMarketCap and CoinGecko.
- Metrics (equal weights): trust score, market share, liquidity, security evaluation, and real trading activity.
- Exchanges analyzed: Binance, Coinbase, Bybit, Upbit, OKX, Bitget, Gate.io, Kraken.
- Detailed scoring is provided in Appendix A.

### 4. Sample Construction Principles
- Primary sample: coins listed on all eight exchanges (AND intersection).
- Auxiliary sample: coins listed on ≥5 of the eight exchanges (k-of-8 rule).
- Multiple listings of the same coin are stored as separate events; tests cluster standard errors at the coin level.
- Every event defines listing day as t = 0 with its own timeline.

### 5. Downtrend Classification
- Let P₀ be the close on listing day and P₁₀ the close on day 10; classify as a drop if P₁₀ < P₀.
- Cumulative log return: R₁₀ = Σₜ₌₁¹⁰ ln(Pₜ / Pₜ₋₁); classify as a downtrend if R₁₀ < 0.
- Secondary indicators: maximum drawdown, linear trend coefficient (β < 0 in ln Pₜ = α + βt), sign test, and Wilcoxon signed-rank test.
- Significance level 0.05 with Benjamini–Hochberg FDR adjustment.

### 6. Data Collection and Preprocessing
- Listings: exchange announcements or databases.
- Prices: daily OHLCV from t=0 to t=10 per exchange; all quoted in USDT and normalized to UTC.
- Exclude stablecoins and pegged assets.
- Remove the top/bottom 1% of returns to control outliers.
- Identify coins via CoinMarketCap or CoinGecko IDs to avoid ticker collisions.
- Listing universes are fetched with `scripts/fetch_listed_coins.py`, which outputs `data/listed_coins.json` (per exchange) and `data/common_coins.json` (intersection). Example: `python3 scripts/fetch_listed_coins.py --log-level INFO`.
- Daily histories for intersection coins are maintained with `scripts/fetch_daily_histories.py`. Each run loads existing `data/daily_histories/<COIN>.json`, appends missing days, and saves the merged result. Use `--full-refresh` to rebuild from scratch. Example cron job (UTC 03:00 daily):
  ```bash
  0 3 * * * cd /Users/bentley/Documents/codebase/does-coin-leave-on-applause && /usr/bin/python3 scripts/fetch_daily_histories.py --log-level INFO >> /tmp/coin-harvest.log 2>&1
  ```
- The Chart.js dashboard in `web/` consumes these JSON files. Serve the repo root (`python3 -m http.server`) and open `http://localhost:8000/web/` to compare per-exchange high/low lines.

### 7. Analysis Procedure
- Define t = 0 at listing and analyze t ∈ [0, 10].
- Compute R₁₀ per coin, then aggregate mean/median across the sample.
- After normality checks: run one-sample t-tests if normal; otherwise use sign and Wilcoxon tests.
- When coins have multiple listings, estimate confidence intervals with coin-clustered standard errors.
- Report effect size, 95% CI, p-value, BH-adjusted q-value, and visualize all price paths.

### 8. Visualization & Interpretation
- For each coin, draw 10-day high/low lines (two series per exchange).
- Mark listing times with vertical lines and shade the 10-day window.
- Distinguish multiple events for the same coin on shared charts.
- Plot the cumulative return distribution to observe median shifts.

### 9. Quality Control & Bias Mitigation
- Separate announcement vs. actual listing dates to compare effects.
- Normalize all daily bars to UTC for cross-exchange comparability.
- Document overlapping windows when listings occur close together.
- Treat missing, halted, or erroneous quotes as nulls—no interpolation.
- Log raw pulls with timestamps and time zones for reproducibility.

### 10. Result Interpretation
- Reject H₀ if the median R₁₀ is negative and statistically significant.
- A significant negative effect indicates a short-term post-listing decline tendency.
- If exchanges differ, discuss screening rigor, liquidity, and operational reliability.
- Always contextualize with market regime, Bitcoin volatility, and disclosure timing.

---

### Appendix A. Exchange Selection Details
- Combined metrics: CoinMarketCap/CoinGecko trust scores, volume, security, market share.
- Security factors: cold storage ratio, incident disclosures, bug-bounty coverage.
- Activity factors: “real volume,” pair diversity, API availability.
- Equal-weight averages using the latest (2025) public research.

### Appendix B. Statistical Approach
- Daily log return: Rₜ = ln(Pₜ / Pₜ₋₁).
- Cumulative return: R₁₀ = Σₜ₌₁¹⁰ Rₜ.
- Downtrend ratio: N(R₁₀ < 0) / N_total.
- One-sample t-test: t = mean(R₁₀) / (s / √n).
- Wilcoxon signed-rank: W = Σ rank(|R₁₀|) × sign(R₁₀).
- Sign test: z = (X − n/2) / √(n/4), where X counts negative samples.
- Event-study abnormal return: ARₜ = Rₜ − Rₜ^(m); CAR = Σ ARₜ.
- Market model: Rₜ = α + βRₜ^(m) + εₜ, analyze mean(εₜ).

### Appendix C. Reporting Standards
- Report mean, median, standard deviation, IQR, p-value, 95% CI, q-value.
- Interpret results per coin, per exchange, and per market regime.
- Flag a short-term downtrend if the decline ratio significantly exceeds 50%.
- Round all figures to three decimals.

### Appendix D. References
- CoinMarketCap: https://coinmarketcap.com
- CoinGecko: https://www.coingecko.com
- Binance API Docs: https://binance-docs.github.io/apidocs/
- Coinbase Advanced Trade API: https://docs.cloud.coinbase.com/advanced-trade-api/
- Bybit API Docs: https://bybit-exchange.github.io/docs/
- Upbit API Docs: https://docs.upbit.com/
- OKX API Docs (v5): https://www.okx.com/docs-v5/
- Bitget API Docs: https://bitgetlimited.github.io/apidoc/
- Gate.io API v4 Docs: https://www.gate.io/docs/developers/apiv4/en/
- Kraken REST API: https://docs.kraken.com/rest/

---

## 한국어 개요

상장 직후 단기 하락 여부를 정량적으로 검증하기 위한 연구 설계 문서입니다. 유명 중앙화 거래소(CEX)에서 새롭게 상장한 코인을 표본으로 삼아, 상장 후 10일 이내 가격 경로와 누적 수익률을 체계적으로 분석합니다.

### 1. 연구 주제
- 연구 질문: 유명 거래소에 상장된 코인은 상장 이후 10일 이내에 유의미한 가격 하락을 보이는가?

### 2. 가설 설정
- 귀무가설 (H₀): 모든 유명 거래소에 상장된 코인은 상장 후 10일 이내에 유의미한 하락세를 보이지 않는다.
- 대립가설 (H₁): 모든 유명 거래소에 상장된 코인은 상장 후 10일 이내에 유의미한 하락세를 보인다.

### 3. 거래소 정의 및 선정 근거
- 유명 거래소는 거래량, 보안성, 사용자 신뢰도, 규제 준수 여부를 종합적으로 고려한 주요 CEX로 정의한다.
- 데이터 출처: CoinMarketCap, CoinGecko.
- 선정 기준: Trust Score, 시장 점유율, 유동성, 보안 평가, 실제 거래 활성도 등을 동일 가중치로 반영한다.
- 분석 대상 8개 거래소: Binance, Coinbase, Bybit, Upbit, OKX, Bitget, Gate.io, Kraken.
- 세부 평가지표와 점수는 Appendix A 참고.

### 4. 표본 구성 원칙
- 기본 표본: 8개 거래소 모두에 상장된 코인(AND 교집합).
- 보조 표본: 8개 중 5개 이상(k-of-8) 상장된 코인.
- 동일 코인의 다중 상장 이벤트는 각각 독립적으로 기록하되, 검정 시 코인 단위로 군집화된 표준오차를 사용한다.
- 각 이벤트는 상장일을 t=0으로 설정하고 개별 타임라인을 구성한다.

### 5. 하락세 판정 기준
- 상장일 종가를 P₀, 상장 후 10일째 종가를 P₁₀이라 정의하고 P₁₀ < P₀이면 하락으로 분류한다.
- 누적 로그수익률 R₁₀ = Σₜ₌₁¹⁰ ln(Pₜ / Pₜ₋₁); R₁₀ < 0이면 하락세로 간주한다.
- 보조 지표: 최대낙폭(Max Drawdown), 선형 추세 계수(ln Pₜ = a + bt 에서 b < 0), 중앙값 기반 비정규 검정(부호검정, 윌콕슨 검정).
- 유의수준 0.05, 다중검정은 Benjamini–Hochberg FDR 보정.

### 6. 데이터 수집 및 전처리
- 상장 목록: 각 거래소 공식 공지 또는 데이터베이스 기반.
- 시세 데이터: 거래소별 상장일 이후 +10일까지의 일봉(OHLCV) 기준, 모든 시세는 USDT로 통일하고 타임스탬프는 UTC 정규화.
- 스테이블코인 및 페깅 자산 제외.
- 수익률 데이터는 상·하위 1% 극단값 제거.
- 각 코인은 CoinMarketCap 혹은 CoinGecko 고유 ID로 식별하여 심볼 중복이나 리브랜딩을 방지한다.
- 거래소별 상장 코인 목록은 `scripts/fetch_listed_coins.py`로 자동 수집하며, 실행 시 `data/listed_coins.json`과 `data/common_coins.json`을 동시에 생성한다. 사용 예: `python3 scripts/fetch_listed_coins.py --log-level INFO`.
- 공통 상장 코인의 일별 시세는 `scripts/fetch_daily_histories.py`로 관리한다. 기존 JSON을 읽고 새 캔들만 덧붙이는 증분 모드가 기본이며, `--full-refresh`로 전량 재수집할 수 있다. 예시 크론:
  ```bash
  0 3 * * * cd /Users/bentley/Documents/codebase/does-coin-leave-on-applause && /usr/bin/python3 scripts/fetch_daily_histories.py --log-level INFO >> /tmp/coin-harvest.log 2>&1
  ```
- `web/` 폴더에는 Chart.js 기반 대시보드가 포함되어 있으며, 루트에서 `python3 -m http.server`를 실행하고 `http://localhost:8000/web/`에 접속하면 거래소별 고·저가를 동시에 확인할 수 있다.

### 7. 분석 절차
- 상장일을 t=0, 분석 구간을 t ∈ [0, 10]으로 정의한다.
- 코인별 누적수익률 R₁₀을 계산하고 표본 전체 평균/중앙값을 산출한다.
- 정규성 검정 후 정규성을 만족하면 단일표본 t-검정, 그렇지 않으면 부호검정과 윌콕슨 검정을 수행한다.
- 동일 코인의 다중 이벤트가 있을 경우 코인 단위 군집 표준오차로 신뢰구간을 추정한다.
- 평균 효과크기, 95% 신뢰구간, p-value, BH 보정 q-value를 보고하고 모든 시계열을 시각화한다.

### 8. 시각화 및 해석 절차
- 코인 단위로 10일간의 고가·저가 라인을 표시한다(거래소별 2라인).
- 거래소별 상장 시점을 수직선으로, 상장 후 10일 구간을 음영으로 강조한다.
- 동일 코인의 다중 상장 이벤트는 동일 그래프 안에서 타임라인을 구분한다.
- 전체 이벤트의 누적수익률 분포를 시각화하여 중앙값 편차를 확인한다.

### 9. 품질 관리 및 편향 통제
- 상장 공지일과 실제 상장일을 분리해 효과를 비교한다.
- 거래소별 일봉 기준을 UTC로 통일한다.
- 이벤트 윈도우가 겹칠 경우 영향을 부록에 기록한다.
- 시세 누락·결측·거래 중단은 결측으로 처리하고 보간하지 않는다.
- 원본 로그, 수집 시각, 타임존 정보를 모두 기록해 재현성을 보장한다.

### 10. 결과 해석 원칙
- 상장 후 10일간 누적수익률 중앙값이 0보다 작고 통계적으로 유의하면 귀무가설을 기각한다.
- 하락 효과가 유의하면 단기 하락 경향이 존재한다고 해석한다.
- 거래소 간 효과 차이가 존재하면 신뢰도, 상장 심사, 거래 규모 등 구조적 요인을 논의한다.
- 전체 시장 국면, 비트코인 변동성, 공시 시차 등 외부 요인을 함께 고려한다.

---

### Appendix A. 거래소 선정 세부 설명
- CoinMarketCap·CoinGecko 신뢰 점수, 거래량, 보안 수준, 시장 점유율을 기반으로 평가한다.
- 보안성은 콜드월렛 비중, 사고 공시 이력, 버그바운티 운영 여부 등을 반영한다.
- 거래 활성도는 실거래 지수, 거래쌍 다양성, API 가용성 등을 포함한다.
- 각 지표는 동일 가중치로 평균하며, 데이터는 2025년 기준 최신 공개 리서치를 사용한다.

### Appendix B. 통계적 접근 개요
- 일별 로그수익률: Rₜ = ln(Pₜ / Pₜ₋₁).
- 누적수익률: R₁₀ = Σₜ₌₁¹⁰ Rₜ.
- 하락 비율: N(R₁₀ < 0) / N_total.
- 단일표본 t-검정: t = mean(R₁₀) / (s / √n).
- 윌콕슨 검정: W = Σ rank(|R₁₀|) × sign(R₁₀).
- 부호검정: z = (X − n/2) / √(n/4), X는 음수 표본 수.
- 비정상수익(Event Study): ARₜ = Rₜ − Rₜ^(m), CAR = Σ ARₜ.
- 시장모델: Rₜ = a + bRₜ^(m) + εₜ, 잔차 평균을 분석한다.

### Appendix C. 결과 보고 체계
- 평균, 중앙값, 표준편차, IQR, p-value, 95% 신뢰구간, q-value를 모두 보고한다.
- 결과는 코인 단위뿐 아니라 거래소별·시장별로 구분해 해석한다.
- 하락 비율이 50%보다 유의하게 높으면 단기 하락 경향으로 판단한다.
- 모든 수치는 소수점 셋째 자리까지 반올림한다.

### Appendix D. 참고 자료
- CoinMarketCap: https://coinmarketcap.com
- CoinGecko: https://www.coingecko.com
- Binance API Docs: https://binance-docs.github.io/apidocs/
- Coinbase Advanced Trade API: https://docs.cloud.coinbase.com/advanced-trade-api/
- Bybit API Docs: https://bybit-exchange.github.io/docs/
- Upbit API Docs: https://docs.upbit.com/
- OKX API Docs (v5): https://www.okx.com/docs-v5/
- Bitget API Docs: https://bitgetlimited.github.io/apidoc/
- Gate.io API v4 Docs: https://www.gate.io/docs/developers/apiv4/en/
- Kraken REST API: https://docs.kraken.com/rest/
