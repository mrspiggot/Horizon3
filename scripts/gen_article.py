"""Generate ONE article for a (decision-maker, jurisdiction, model-set) — the steering contract in action.

    gen_article.py <persona> <jurisdiction> [model1,model2,...]

The models run in the chosen currency (run_model(instance=)); an explicit model list pins the set (the
graph enumerator's pick) over Role-2 selection. This is how the same engine writes a US policy piece and a
euro-area rates piece from the same catalogue.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import psycopg2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render.writer import build_article_full  # noqa: E402


def main() -> None:
    persona = sys.argv[1]
    jur = sys.argv[2] if len(sys.argv) > 2 else "US"
    models = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else None
    conn = psycopg2.connect(host="localhost", port=5434, dbname="unified_market_data",
                            user="postgres", password="devpassword")
    out = Path(__file__).resolve().parents[1] / "output" / "steering" / f"{persona}_{jur}"
    out.mkdir(parents=True, exist_ok=True)
    r = build_article_full(persona, conn, out, jurisdiction=jur, model_ids=models)
    print(f"{persona} [{jur}]: grounded={r.get('grounded')} critic_ok={r['critic_ok']} "
          f"charts={r['n_charts']} models={models or 'selected'} → {out}")
    conn.close()


if __name__ == "__main__":
    main()
