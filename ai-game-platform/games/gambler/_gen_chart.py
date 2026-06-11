"""Generate HTML asset curve chart from ui_state.json."""
import json, webbrowser, os
from pathlib import Path

HERE = Path(__file__).parent
data = json.load(open(HERE / 'ui_state.json', encoding='utf-8'))
traj = data['trajectories_with_start']
names = data['player_names']
max_r = data['game_config']['max_rounds']

colors = ['#FF6384','#36A2EB','#FFCE56','#4BC0C0','#9966FF','#FF9F40','#7BC8A4','#E8A87C']

datasets_js = []
for i, name in enumerate(names):
    pts = traj.get(name, [])
    pts_json = json.dumps([{'x': p['round'], 'y': round(p['assets'], 2)} for p in pts])
    c = colors[i % len(colors)]
    datasets_js.append(
        f"{{label:'{name}',data:{pts_json},borderColor:'{c}',"
        f"backgroundColor:'{c}22',borderWidth:2.5,pointRadius:3,tension:0.2,fill:false}}"
    )

# Build table rows
rows = []
ranked = sorted(data['players'], key=lambda x: x['current_assets'], reverse=True)
for i, p in enumerate(ranked):
    profit = p['current_assets'] - p['initial_assets']
    sign = '+' if profit >= 0 else ''
    pc = 'up' if profit >= 0 else 'down'
    rc = {0:'r1',1:'r2',2:'r3'}.get(i,'')
    wl = f"{p['gamble_wins']}W/{p['gamble_losses']}L" if p['gamble_count'] > 0 else '—'
    rows.append(
        f"<tr><td class='{rc}'>{i+1}</td>"
        f"<td><strong>{p['name']}</strong></td>"
        f"<td style='opacity:0.5'>{p['model_name']}</td>"
        f"<td>${p['current_assets']:,.2f}</td>"
        f"<td class='{pc}'>{sign}${profit:,.2f}</td>"
        f"<td>{p['work_count']}&times;</td>"
        f"<td>{p['gamble_count']}&times;</td>"
        f"<td>{wl}</td></tr>"
    )

html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Gambler Asset Curves</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ background: #0f0f1a; color: #c8c8d8; font-family: system-ui; margin: 20px; }}
  h1 {{ color: #e2b04a; font-size: 1.3rem; }}
  .chart-wrap {{ max-width: 1100px; height: 550px; margin: 0 auto; background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 20px; }}
  table {{ width: 100%; max-width: 1100px; margin: 20px auto; border-collapse: collapse; background: #1a1a2e; border-radius: 8px; overflow: hidden; }}
  th {{ font-size: 0.7rem; opacity: 0.5; text-transform: uppercase; text-align: left; padding: 10px 14px; border-bottom: 1px solid #2a2a4a; }}
  td {{ padding: 8px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.85rem; }}
  .r1 {{ color: #ffd700; font-weight: 700; }} .r2 {{ color: #c0c0c0; }} .r3 {{ color: #cd7f32; }}
  .up {{ color: #4caf84; }} .down {{ color: #e0556a; }}
</style></head><body>
<h1>Gambler Game — Asset Curves (Seed 42, 20 Rounds)</h1>
<div class="chart-wrap"><canvas id="chart"></canvas></div>
<table><thead><tr><th>#</th><th>Player</th><th>Model</th><th>Assets</th><th>Profit</th><th>Work</th><th>Gamble</th><th>W/L</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table>
<script>
new Chart(document.getElementById('chart').getContext('2d'), {{
  type: 'line',
  data: {{ datasets: [{','.join(datasets_js)}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    scales: {{
      x: {{ type:'linear', title:{{display:true,text:'Round',color:'#888'}}, min:0, max:{max_r}, ticks:{{stepSize:1,color:'#666'}}, grid:{{color:'#1a1a2e'}} }},
      y: {{ title:{{display:true,text:'Assets ($)',color:'#888'}}, ticks:{{color:'#666',callback:v=>'$'+v.toLocaleString()}}, grid:{{color:'#1a1a2e'}} }},
    }},
    plugins: {{ legend: {{ labels: {{color:'#c8c8d8',usePointStyle:true,padding:16}} }} }},
    interaction: {{ mode:'nearest',axis:'x',intersect:false }},
  }},
}});
</script></body></html>"""

out = HERE / '_chart.html'
out.write_text(html, encoding='utf-8')
webbrowser.open('file:///' + str(out.resolve()).replace('\\', '/'))
print('Chart opened:', out)
