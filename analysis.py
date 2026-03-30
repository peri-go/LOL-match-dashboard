import pandas as pd
import requests

_DDRAGON_VERSION = None

def get_ddragon_version():
    global _DDRAGON_VERSION
    if _DDRAGON_VERSION:
        return _DDRAGON_VERSION
    try:
        r = requests.get('https://ddragon.leagueoflegends.com/api/versions.json', timeout=5)
        _DDRAGON_VERSION = r.json()[0]
    except:
        _DDRAGON_VERSION = '16.6.1'
    return _DDRAGON_VERSION

def champion_map():
    c = requests.get(f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/data/en_US/champion.json', timeout= 5)
    m = c.json()
    map={}
    for i in m['data']:
        map[m['data'][i]['key']] = m['data'][i]['id']
    
    return map

def item_url(item_id):
    if not item_id or int(item_id) == 0:
        return None
    return f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/img/item/{int(item_id)}.png'

def champ_id_icon(id, map):
    if id == -1:
        return None
    else:
        champ = map[str(id)]
        url = champ_icon_url(champ)
        return url

def champ_icon_url(champ_name):
    name = (champ_name or 'Ahri').replace(' ', '').replace("'", '').replace('.', '')
    return f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/img/champion/{name}.png'

def spell_url(spell):
    return f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/img/spell/{spell}.png'

def get_rune_paths():
    try: 
        r = requests.get(f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/data/en_US/runesReforged.json', timeout=5)
        runes = r.json()
        base = "https://ddragon.leagueoflegends.com/cdn/img/"
        rune_icons = {}
        for tree in runes:
            rune_icons[tree['id']] = base + tree['icon']
            for slot in tree["slots"]:
                for rune in slot["runes"]:
                    rune_icons[rune['id']] = base + rune['icon']
        return rune_icons
    except:
        return None
    
def load_csvs(all_players_path, timeline_path):
    df_players  = pd.read_csv(all_players_path)
    df_timeline = pd.read_csv(timeline_path)
    return df_players, df_timeline

def get_scoreboard(df_players):
    max_damage = int(df_players['dmg_to_champions'].max())
    def enrich(rows):
        for r in rows:
            r['max_damage'] = max_damage
        return rows
    blue = enrich(df_players[df_players['team_id'] == 100].to_dict(orient='records'))
    red  = enrich(df_players[df_players['team_id'] == 200].to_dict(orient='records'))
    return {'blue': blue, 'red': red}

def build_pid_map(df_players):
    pid_map = {}
    for _, row in df_players.iterrows():
        pid = int(row['participant_id'])
        pid_map[pid] = {
            'champion_name':      row.get('champion_name', '?'),
            'summoner_name': row.get('summoner_name', '?'),
            'team_id':       int(row.get('team_id', 100)),
        }
    return pid_map

def get_chart(df_players, col):
    data = df_players.sort_values(col, ascending=False)
    return {
        'labels':    data['summoner_name'].tolist(),
        'champions': data['champion_name'].tolist(),
        'values':    data[col].tolist(),
        'teams':     data['team_id'].tolist(),
    }

def get_timeline_events(df_timeline, pid_map):
    minutes = sorted(df_timeline['timestamp_min'].unique().tolist())
    events_by_minute = {}

    for minute in minutes:
        rows = df_timeline[df_timeline['timestamp_min'] == minute]
        events = []
        for _, e in rows.iterrows():
            etype     = str(e.get('type', ''))
            killer_id = int(e['killer_id']) if str(e.get('killer_id', '')).replace('.0','').isdigit() else 0
            victim_id = int(e['victim_id']) if str(e.get('victim_id', '')).replace('.0','').isdigit() else 0
            item_id   = int(e['item_id'])   if str(e.get('item_id',   '')).replace('.0','').isdigit() else 0

            killer_info = pid_map.get(killer_id, {})
            victim_info = pid_map.get(victim_id, {})

            events.append({
                'type':          etype,
                'killer_champ':  killer_info.get('champion', f'P{killer_id}'),
                'killer_team':   killer_info.get('team_id', 100),
                'victim_champ':  victim_info.get('champion', f'P{victim_id}'),
                'victim_team':   victim_info.get('team_id', 200),
                'item_id':       item_id,
                'item_url':      item_url(item_id) if item_id else None,
                'building_type': str(e.get('building_type', '') or ''),
                'monster_type':  str(e.get('monster_type',  '') or ''),
            })

        events_by_minute[int(minute)] = events

    return {
        'minutes': [int(m) for m in minutes],
        'events':  events_by_minute,
    }
 
def build_analysis(all_players_path, timeline_path, summoner_name=None):
    df_players, df_timeline = load_csvs(all_players_path, timeline_path)
    pid_map = build_pid_map(df_players)
    return {
        'scoreboard':   get_scoreboard(df_players),
        'player_stats': None,
        'charts': {
            'damage': get_chart(df_players, 'dmg_to_champions'),
            'gold':   get_chart(df_players, 'gold_earned'),
            'cs':     get_chart(df_players, 'cs'),
            'kda':    get_chart(df_players, 'kda'),
            'vision': get_chart(df_players, 'vision_score'),
        },
        'timeline': get_timeline_events(df_timeline, pid_map),
    }
