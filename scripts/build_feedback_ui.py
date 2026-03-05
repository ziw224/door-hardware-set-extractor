from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a lightweight feedback UI for extraction JSON")
    parser.add_argument("--pred", required=True, help="Path to extraction JSON")
    parser.add_argument("--out", required=True, help="Path to output HTML")
    args = parser.parse_args()

    pred_path = Path(args.pred)
    out_path = Path(args.out)

    data = json.loads(pred_path.read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False)

    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
  <title>Hardware Extraction Feedback</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 16px; }}
    .toolbar {{ position: sticky; top: 0; background: #fff; padding: 8px 0; border-bottom: 1px solid #ddd; margin-bottom: 12px; }}
    button {{ margin-right: 8px; padding: 8px 12px; }}
    .set {{ border: 1px solid #ddd; border-radius: 8px; padding: 10px; margin: 12px 0; }}
    .set h3 {{ margin: 0 0 6px 0; font-size: 16px; }}
    .meta {{ color: #555; font-size: 12px; margin-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #eee; padding: 4px; vertical-align: top; }}
    th {{ background: #f7f7f7; position: sticky; top: 42px; }}
    input {{ width: 100%; box-sizing: border-box; border: 1px solid #ccc; padding: 4px; font-size: 12px; }}
    .conf {{ color: #666; font-size: 11px; }}
  </style>
</head>
<body>
  <div class=\"toolbar\">
    <button id=\"download\">Download Corrected JSON</button>
    <button id=\"expand\">Expand All</button>
    <button id=\"collapse\">Collapse All</button>
    <span id=\"stats\"></span>
  </div>
  <div id=\"root\"></div>

  <script>
    const data = {payload};

    function text(v) {{ return v == null ? '' : String(v); }}

    function render() {{
      const root = document.getElementById('root');
      root.innerHTML = '';
      let setCount = 0;
      let compCount = 0;

      (data.documents || []).forEach((doc, di) => {{
        (doc.hardware_sets || []).forEach((set, si) => {{
          setCount += 1;
          const details = document.createElement('details');
          details.className = 'set';
          details.open = false;

          const summary = document.createElement('summary');
          summary.innerHTML = `<h3 style=\"display:inline\">Set ${{text(set.set_number)}} - ${{text(set.description)}}</h3>`;
          details.appendChild(summary);

          const meta = document.createElement('div');
          const loc = set.location || {{}};
          meta.className = 'meta';
          meta.textContent = `${{text(doc.doc_path)}} | pages ${{text(loc.page_start)}}-${{text(loc.page_end)}} | lines ${{text((loc.line_range||[]).join('-'))}}`;
          details.appendChild(meta);

          const table = document.createElement('table');
          table.innerHTML = `
            <thead>
              <tr>
                <th>qty</th><th>description</th><th>catalog</th><th>mfr</th><th>finish</th><th>notes</th><th>resolved</th><th>confidence</th>
              </tr>
            </thead>
            <tbody></tbody>`;
          const tbody = table.querySelector('tbody');

          (set.components || []).forEach((c, ci) => {{
            compCount += 1;
            const tr = document.createElement('tr');

            const fields = ['qty','description','catalog_number','mfr','finish','notes','resolved_description'];
            fields.forEach((f) => {{
              const td = document.createElement('td');
              const input = document.createElement('input');
              input.value = text(c[f]);
              input.oninput = () => {{
                const v = input.value.trim();
                c[f] = v === '' ? null : v;
              }};
              td.appendChild(input);
              tr.appendChild(td);
            }});

            const tdConf = document.createElement('td');
            const conf = c.field_confidence || {{}};
            tdConf.className = 'conf';
            tdConf.textContent = Object.entries(conf).map(([k,v]) => `${{k}}:${{v}}`).join(' | ');
            tr.appendChild(tdConf);

            tbody.appendChild(tr);
          }});

          details.appendChild(table);
          root.appendChild(details);
        }});
      }});

      document.getElementById('stats').textContent = `Sets: ${{setCount}} | Components: ${{compCount}}`;
    }}

    function download() {{
      const blob = new Blob([JSON.stringify(data, null, 2)], {{type: 'application/json'}});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'corrected_extraction.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }}

    document.getElementById('download').onclick = download;
    document.getElementById('expand').onclick = () => document.querySelectorAll('details').forEach(d => d.open = true);
    document.getElementById('collapse').onclick = () => document.querySelectorAll('details').forEach(d => d.open = false);

    render();
  </script>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote feedback UI: {out_path}")


if __name__ == "__main__":
    main()
