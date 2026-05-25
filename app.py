import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import api
from config import SECRET_KEY,SUMMONER,TAG

app = Flask(__name__)
app.secret_key = SECRET_KEY
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)
REGIONS = ["BR","EUW","EUNE","KR","NA","LAN","LAS","OCE","RU","TR","JP"]
dragon_version = api.get_ddragon_version()

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

    return render_template('index.html', error=error,regions = REGIONS,summoner = SUMMONER,tag=TAG)

@app.route('/history')
def match_history():
    puuid = session.get('puuid')
    summoner_name = session.get('summoner_name')
    if not puuid:
        return redirect(url_for('index'))

    region = session.get('region', 'BR')
    try:
        history = api.get_match_history(puuid, region)
    except Exception as e:
        return render_template('history.html', error=str(e), history=[], summoner=summoner_name)

    return render_template('history.html', history=history, summoner=summoner_name, error=None,version = dragon_version)

@app.route('/history/load')
def history_load():
    puuid  = session.get('puuid')
    region = session.get('region', 'BR')
    page   = int(request.args.get('page', 0))
    per_page = 10
    matches = api.get_match_history(puuid, region, page * per_page, per_page)
    return render_template("history_rows.html", history=matches, version = dragon_version)

@app.route('/select_match/<match_id>')
def select_match(match_id):
    try:
        all_players_path,match = api.build_all_players_csv(match_id,session['region'])
        session['all_players_path'] = all_players_path
        session['match'] = match
        session['match_id'] = match_id
        return redirect(url_for('analysis_page'))
    except Exception as e:
        return f'Error fetching match data: {e}', 500

@app.route('/analysis')
def analysis_page():
    all_players_path = session.get('all_players_path')
    summoner_name = session.get('summoner_name')
    match = session.get('match')
    match_id = session.get('match_id')
    region = session.get('region')
    if not all_players_path:
        return redirect(url_for('index'))

    try:
        timeline = api.build_timeline(match_id, region)
        skills = api.build_skill_timeline(match_id, region)
        data = api.build_analysis(all_players_path, skills,summoner_name)
    except Exception as e:
        return f'Error building analysis: {e}', 500
    return render_template('analysis.html',
        scoreboard=data['scoreboard'],
        player_stats=data['player_stats'],
        charts=json.dumps(data['charts']),
        summoner=summoner_name,
        match= match,
        timeline= timeline,
        version = dragon_version)

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
