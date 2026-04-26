# Regular investing replay summary

- Replay dates: 76
- Candidates: 664
- False-positive rate: 0.5221
- Invalidation hit rate: 0.4729
- Point-in-time limitation: Replay truncates OHLCV at each replay date and strips non-point-in-time fundamentals/news/social/short-interest/options. Results are historical evidence, not proof or guaranteed prediction accuracy.
- Fundamental limitation: Historical replay strips non-point-in-time fundamentals unless the provider supplies point-in-time snapshots. Current real-provider fundamentals are active snapshots and are not used in OHLCV-only replay scoring.

## Forward Returns
- 20d: avg 3.0393, median 2.0425, win rate 0.5557, sample 655
- 60d: avg 8.9058, median 5.9888, win rate 0.6185, sample 637
- 120d: avg 20.0146, median 14.8337, win rate 0.6934, sample 610
- 252d: avg 43.0575, median 30.4651, win rate 0.7796, sample 558

## Baseline Comparisons
- Excess vs SPY/QQQ: {'SPY_20d': {'sample_size': 655, 'average': 1.8773, 'median': 0.7503}, 'QQQ_20d': {'sample_size': 655, 'average': 1.5225, 'median': 0.2985}, 'SPY_60d': {'sample_size': 637, 'average': 5.2747, 'median': 1.6375}, 'QQQ_60d': {'sample_size': 637, 'average': 4.4812, 'median': 0.833}, 'SPY_120d': {'sample_size': 610, 'average': 12.0517, 'median': 5.3466}, 'QQQ_120d': {'sample_size': 610, 'average': 10.3436, 'median': 4.5483}, 'SPY_252d': {'sample_size': 558, 'average': 25.8748, 'median': 11.1201}, 'QQQ_252d': {'sample_size': 558, 'average': 22.798, 'median': 8.1557}}
- Excess vs random: {'20d': -0.0794, '60d': -0.1724, '120d': -0.9032, '252d': -0.8091}
- Excess vs equal-weight universe: {'20d': -0.157, '60d': -0.5067, '120d': -1.3035, '252d': -1.8078}

## Styles And Labels
- Investing styles: [{'investing_style': 'Value + Improving Trend', 'sample_size': 254, 'average': 3.3686, 'median': 2.9909, 'win_rate': 0.5906, 'false_positive_rate': 0.4921}, {'investing_style': 'Watchlist Only', 'sample_size': 208, 'average': 3.1838, 'median': 1.0025, 'win_rate': 0.5385, 'false_positive_rate': 0.5385}, {'investing_style': 'Exit / Broken Thesis', 'sample_size': 91, 'average': 2.4777, 'median': -0.0625, 'win_rate': 0.4945, 'false_positive_rate': 0.5385}, {'investing_style': 'Data Insufficient', 'sample_size': 89, 'average': 2.3261, 'median': 2.7159, 'win_rate': 0.5618, 'false_positive_rate': 0.5506}, {'investing_style': 'Turnaround Candidate', 'sample_size': 13, 'average': 3.1044, 'median': 2.4763, 'win_rate': 0.5385, 'false_positive_rate': 0.5385}]
- Action labels: [{'investing_action_label': 'Watchlist Only', 'sample_size': 283, 'average': 3.2586, 'median': 1.3689, 'win_rate': 0.5477, 'false_positive_rate': 0.5406}, {'investing_action_label': 'Hold', 'sample_size': 281, 'average': 3.0002, 'median': 2.6852, 'win_rate': 0.5836, 'false_positive_rate': 0.4982}, {'investing_action_label': 'Exit / Sell Candidate', 'sample_size': 91, 'average': 2.4777, 'median': -0.0625, 'win_rate': 0.4945, 'false_positive_rate': 0.5385}]