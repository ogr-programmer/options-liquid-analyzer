#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Analyzer for QUIK option mispricing detector CSV exports.

Usage:
  python options_analyzer.py --input /path/to/archive_or_folder --output analysis
"""
import argparse, zipfile, tempfile, shutil
from pathlib import Path
import pandas as pd
import numpy as np


def find_file(root, name):
    p = root / name
    if p.exists():
        return p
    hits = list(root.rglob(name))
    return hits[0] if hits else None


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(',', '.', regex=False), errors='coerce')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='ZIP archive or folder with CSV files')
    ap.add_argument('--output', default='options_analysis', help='Output folder')
    args = ap.parse_args()
    src, temp = Path(args.input), None
    if src.is_file() and src.suffix.lower() == '.zip':
        temp = Path(tempfile.mkdtemp(prefix='opt_an_'))
        with zipfile.ZipFile(src) as zf:
            zf.extractall(temp)
        root = temp
    else:
        root = src
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    md = find_file(root, 'options_market_data.csv')
    sg = find_file(root, 'options_signals_v3.csv')
    if not md or not sg:
        raise SystemExit('Не найдены options_market_data.csv и/или options_signals_v3.csv')
    market = pd.read_csv(md, sep=None, engine='python', on_bad_lines='skip')
    signals = pd.read_csv(sg, sep=None, engine='python', on_bad_lines='skip')
    for df in (market, signals):
        for c in df.columns:
            df[c] = df[c].astype(str).str.strip()
    for df in (market, signals):
        for c in ['strike', 'theorprice', 'market_price', 'volume', 'edge_points',
                  'edge_percent', 'bid', 'offer', 'bid_volume', 'offer_volume',
                  'future_price']:
            if c in df:
                df[c] = num(df[c])
    for df in (market, signals):
        for c in ['timestamp', 'expdate']:
            if c in df:
                df[c] = pd.to_datetime(df[c], errors='coerce')
    if 'timestamp' in signals:
        signals = signals.sort_values('timestamp')
    if 'timestamp' in market:
        market = market.sort_values('timestamp')
    if 'future_price' not in signals.columns and {'sec_code', 'timestamp'}.issubset(signals.columns) and {'sec_code', 'timestamp', 'future_price'}.issubset(market.columns):
        m = market[['sec_code', 'timestamp', 'future_price']].dropna().sort_values('timestamp')
        signals = pd.merge_asof(signals.sort_values('timestamp'), m, on='timestamp', by='sec_code', direction='backward', tolerance=pd.Timedelta('10min'))
    if 'future_price' in signals:
        signals['strike_distance'] = signals['strike'] - signals['future_price']
        signals['strike_distance_abs'] = signals['strike_distance'].abs()
        signals['moneyness_pct'] = signals['strike_distance'] / signals['future_price'] * 100
        signals['distance_bucket'] = pd.cut(signals['moneyness_pct'].abs(), [-np.inf, 1, 3, 5, 10, np.inf], labels=['near ≤1%', '1–3%', '3–5%', '5–10%', 'far >10%'])
    signals['signal_date'] = signals['timestamp'].dt.date if 'timestamp' in signals else ''
    keycols = [c for c in ['sec_code', 'signal_type', 'session_id'] if c in signals.columns]
    events = []
    if keycols and 'status' in signals:
        for key, g in signals.groupby(keycols, dropna=False):
            g = g.sort_values('timestamp')
            opens, closes = g[g.status.eq('OPEN')], g[g.status.eq('CLOSED')]
            for _, op in opens.iterrows():
                later = closes[closes.timestamp >= op.timestamp]
                cl = later.iloc[0] if len(later) else None
                row = op.to_dict()
                row['close_timestamp'] = cl.timestamp if cl is not None else pd.NaT
                row['duration_seconds'] = (cl.timestamp - op.timestamp).total_seconds() if cl is not None else np.nan
                row['closed'] = cl is not None
                events.append(row)
    events = pd.DataFrame(events)
    reports = {
        'signal_frequency_by_strike': signals.groupby(['strike'], dropna=False).agg(signal_rows=('status', 'size'), opens=('status', lambda x: (x == 'OPEN').sum()), closes=('status', lambda x: (x == 'CLOSED').sum()), avg_edge_points=('edge_points', 'mean'), avg_volume=('volume', 'mean')).reset_index(),
        'calls_vs_puts': signals.groupby(['option_type'], dropna=False).agg(rows=('status', 'size'), opens=('status', lambda x: (x == 'OPEN').sum()), avg_edge_points=('edge_points', 'mean'), median_edge_points=('edge_points', 'median'), avg_volume=('volume', 'mean')).reset_index(),
        'signal_by_future': signals.groupby(['future_code'], dropna=False).agg(rows=('status', 'size'), opens=('status', lambda x: (x == 'OPEN').sum()), closes=('status', lambda x: (x == 'CLOSED').sum()), avg_edge_points=('edge_points', 'mean'), avg_volume=('volume', 'mean')).reset_index(),
        'signal_by_expiry': signals.groupby(['expdate'], dropna=False).agg(rows=('status', 'size'), opens=('status', lambda x: (x == 'OPEN').sum()), avg_edge_points=('edge_points', 'mean'), avg_volume=('volume', 'mean')).reset_index(),
        'edge_distribution': signals.groupby(['signal_type'], dropna=False).agg(count=('edge_points', 'size'), min=('edge_points', 'min'), p25=('edge_points', lambda x: x.quantile(.25)), median=('edge_points', 'median'), p75=('edge_points', lambda x: x.quantile(.75)), max=('edge_points', 'max')).reset_index(),
    }
    if 'distance_bucket' in signals:
        reports['near_far_otm'] = signals.groupby(['distance_bucket'], observed=False).agg(rows=('status', 'size'), opens=('status', lambda x: (x == 'OPEN').sum()), avg_edge_points=('edge_points', 'mean'), median_edge_points=('edge_points', 'median'), avg_volume=('volume', 'mean')).reset_index()
    if not events.empty:
        reports['signal_duration'] = events.groupby(['signal_type'], dropna=False).agg(events=('closed', 'size'), closed=('closed', 'sum'), avg_duration_min=('duration_seconds', lambda x: x.dropna().mean() / 60), median_duration_min=('duration_seconds', lambda x: x.dropna().median() / 60), max_duration_min=('duration_seconds', lambda x: x.dropna().max() / 60)).reset_index()
    with pd.ExcelWriter(out / 'options_analysis.xlsx', engine='openpyxl') as w:
        signals.to_excel(w, 'signals_enriched', index=False)
        market.to_excel(w, 'market_data', index=False)
        if not events.empty:
            events.to_excel(w, 'signal_events', index=False)
        for n, d in reports.items():
            d.to_excel(w, n[:31], index=False)
    import matplotlib.pyplot as plt
    plt.figure(); signals.groupby('strike').size().sort_index().plot(kind='bar'); plt.title('Частота сигналов по страйкам'); plt.tight_layout(); plt.savefig(out / '01_frequency_by_strike.png', dpi=150); plt.close()
    if 'option_type' in signals:
        plt.figure(); signals.groupby('option_type').size().plot(kind='bar'); plt.title('Calls против Puts'); plt.tight_layout(); plt.savefig(out / '02_calls_vs_puts.png', dpi=150); plt.close()
    plt.figure(); signals['edge_points'].dropna().plot(kind='hist', bins=40); plt.title('Распределение edge_points'); plt.tight_layout(); plt.savefig(out / '03_edge_distribution.png', dpi=150); plt.close()
    if 'distance_bucket' in signals:
        plt.figure(); signals.groupby('distance_bucket', observed=False).size().plot(kind='bar'); plt.title('Близкие и дальние OTM'); plt.tight_layout(); plt.savefig(out / '04_near_far_otm.png', dpi=150); plt.close()
    if 'timestamp' in signals:
        plt.figure(); signals.set_index('timestamp')['edge_points'].resample('5min').median().plot(); plt.title('Медианный edge во времени'); plt.tight_layout(); plt.savefig(out / '05_edge_over_time.png', dpi=150); plt.close()
    if temp:
        shutil.rmtree(temp, ignore_errors=True)
    print(f'Готово. Результаты: {out.resolve()}')


if __name__ == '__main__':
    main()
