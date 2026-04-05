import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename
import api

app = Flask(__name__)
app.secret_key = 'lol-analyzer-secret'
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
REGIONS = ["BR","EUW","EUNE","KR","NA","LAN","LAS","OCE","RU","TR","JP"]
runes = api.get_rune_paths()

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None

    if request.method == 'POST':
        summoner_name = request.form.get('summoner_name', '').strip()
        tagline = request.form.get('tagline', '').strip()
        region = request.form.get('region', 'BR')
        if summoner_name:
            try:
                puuid, display_name = api.get_puuid(summoner_name, tagline)
                session['puuid'] = puuid
                session['summoner_name'] = display_name
                session['region'] = region
                return redirect(url_for('match_history'))
            except Exception as e:
                error = f'Could not find summoner: {e}'

    return render_template('index.html', error=error,regions = REGIONS)

@app.route('/history')
def match_history():
    puuid = session.get('puuid')
    summoner_name = session.get('summoner_name')
    if not puuid:
        return redirect(url_for('index'))

    region = session.get('region', 'BR')
    try:
        history = api.get_match_history(puuid, runes, region)
    except Exception as e:
        return render_template('history.html', error=str(e), history=[], summoner=summoner_name)

    return render_template('history.html', history=history, summoner=summoner_name, error=None)

@app.route('/history/load')
def history_load():
    puuid  = session.get('puuid')
    runes  = session.get('runes')
    region = session.get('region', 'BR')
    page   = int(request.args.get('page', 0))
    per_page = 10

    ids     = api.riot_get(puuid, region, start=page * per_page, count=per_page)
    matches = api.build_match_history(puuid, runes, ids, region)
    return jsonify({'matches': matches, 'done': len(matches) < per_page})

@app.route('/select_match/<match_id>')
def select_match(match_id):
    try:
        all_players_path,match = api.build_all_players_csv(match_id,session['region'])
        timeline_path = api.build_timeline_csv(match_id,session['region'])
        session['all_players_path'] = all_players_path
        session['match'] = match
        session['timeline_path'] = timeline_path
        session['match_id'] = match_id
        return redirect(url_for('analysis_page'))
    except Exception as e:
        return f'Error fetching match data: {e}', 500

@app.route('/analysis')
def analysis_page():
    all_players_path = session.get('all_players_path')
    timeline_path = session.get('timeline_path')
    summoner_name = session.get('summoner_name')
    match = session.get('match')
    if not all_players_path or not timeline_path:
        return redirect(url_for('index'))

    try:
        data = api.build_analysis(all_players_path, timeline_path, summoner_name)
    except Exception as e:
        return f'Error building analysis: {e}', 500
    return render_template('analysis.html',
        scoreboard=data['scoreboard'],
        player_stats=data['player_stats'],
        charts=json.dumps(data['charts']),
        timeline=json.dumps(data['timeline']),
        summoner=summoner_name,
        match= match)

@app.route('/search/<summoner_name>/<tagline>')
def search_summoner(summoner_name, tagline):
    try:
        puuid, display_name = api.get_puuid(summoner_name, tagline)
        session['puuid'] = puuid
        session['summoner_name'] = display_name
        session['region'] = session.get('region', 'BR')
        return redirect(url_for('match_history'))
    except Exception as e:
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
