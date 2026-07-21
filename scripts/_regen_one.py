"""Regenerate ONE persona in place (output/<today>/articles/<pid>/) with the current code.

    _regen_one.py <persona> [jurisdiction]   # jurisdiction defaults to US only when typed on the CLI
"""
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import psycopg2  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.writer import build_article_full  # noqa: E402
from render.output_paths import article_dir  # noqa: E402

pid = sys.argv[1] if len(sys.argv) > 1 else "macro_rates_trader"
jur = sys.argv[2] if len(sys.argv) > 2 else "US"
conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                        user="postgres", password="devpassword")
out = article_dir(pid)
r = build_article_full(pid, conn, out, jurisdiction=jur)
print(f"\n{pid} [{jur}]: grounded={r.get('grounded')} critic_ok={r['critic_ok']} charts={r['n_charts']} → {out}")
