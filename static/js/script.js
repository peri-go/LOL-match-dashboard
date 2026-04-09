
const chartsData   = {{ charts|safe }};
const summoner     = "{{ summoner or '' }}";

function switchTab(name, btn) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'charts') Object.values(charts).forEach(c => c.resize());
}

function teamColors(teams, labels) {
const summonerBase = summoner.split('#')[0];
return teams.map((t, i) =>
  labels[i] === summonerBase
    ? 'rgba(200,155,60,0.85)'
    : t === 100 ? 'rgba(83,131,232,0.75)' : 'rgba(232,64,87,0.75)'
);
}

function makeBarChart(id, data) {
return new Chart(document.getElementById(id), {
  type: 'bar',
  data: {
    labels: data.labels,
    datasets: [{ data: data.values, backgroundColor: teamColors(data.teams, data.labels), borderRadius: 4, borderSkipped: false }]
    },
    options: {
      indexAxis: 'y', responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: '#1c1c2e', borderColor: '#2e2e48', borderWidth: 1, titleColor: '#e2e2f0', bodyColor: '#7878a8', padding: 10 }
      },
      scales: {
        x: { beginAtZero: true, grid: { color: 'rgba(46,46,72,0.6)' }, ticks: { color: '#7878a8', font: { family: "'Sora', sans-serif", size: 12 } } },
        y: { grid: { display: false }, ticks: { color: '#e2e2f0', font: { family: "'Sora', sans-serif", size: 12 } } }
      }
    }
  });
}

const charts = {
  damage: makeBarChart('damageChart', chartsData.damage),
  gold:   makeBarChart('goldChart',   chartsData.gold),
  cs:     makeBarChart('csChart',     chartsData.cs),
  kda:    makeBarChart('kdaChart',    chartsData.kda),
  vision: makeBarChart('visionChart', chartsData.vision),
};

document.getElementById('togglename').addEventListener('change', function() {
const useChamp = this.checked;
Object.keys(charts).forEach(key => {
  const raw = chartsData[key];
  charts[key].data.labels = useChamp ? raw.champions : raw.labels;
  charts[key].data.datasets[0].backgroundColor = teamColors(raw.teams, raw.labels);
  charts[key].update();
});
});

