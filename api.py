import os
import json
import time
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import API_KEY
CACHE_DIR  = os.path.join(os.path.dirname(__file__), 'cache')
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')

CONTINENTAL = {
    'NA': 'americas', 'BR': 'americas', 'LAN': 'americas', 'LAS': 'americas',
    'EUW': 'europe',  'EUNE': 'europe',  'TR': 'europe',   'RU': 'europe',
    'KR': 'asia',     'JP': 'asia',      'OCE': 'sea',
}
LOL_REGIONAL = {
    'NA': 'na1', 'BR': 'br1', 'LAN': 'la1', 'LAS': 'la2',
    'EUW': 'euw1', 'EUNE': 'eun1', 'TR': 'tr1', 'RU': 'ru',
    'KR': 'kr',  'JP': 'jp1', 'OCE': 'oc1',
}
QUEUE_NAMES = {
    420: 'Ranked Solo', 440: 'Ranked Flex', 450: 'ARAM',
    400: 'Normal Draft', 430: 'Normal Blind', 900: 'URF',
}

SUMMONER_SPELLS = {
    1:  'SummonerBoost',
    3:  'SummonerExhaust',
    4:  'SummonerFlash',
    6:  'SummonerHaste',
    7:  'SummonerHeal',
    11: 'SummonerSmite',
    12: 'SummonerTeleport',
    13: 'SummonerMana',
    14: 'SummonerDot',
    21: 'SummonerBarrier',
    32: 'SummonerSnowball',
}

_DDRAGON_VERSION = None

def get_ddragon_version():
    global _DDRAGON_VERSION
    if _DDRAGON_VERSION:
        return _DDRAGON_VERSION
    try:
        r = requests.get('https://ddragon.leagueoflegends.com/api/versions.json', timeout=5)
        _DDRAGON_VERSION = r.json()[0]
    except:
        _DDRAGON_VERSION = '16.7.1'
    return _DDRAGON_VERSION

# ── cache helpers ─────────────────────────────────────────────────────────────

def cache_path(key):
    return os.path.join(CACHE_DIR, f'{key}.json')

def is_cached(key):
    return os.path.exists(cache_path(key))

def load_cache(key):
    with open(cache_path(key), 'r') as f:
        return json.load(f)

def save_cache(key, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path(key), 'w') as f:
        json.dump(data, f, indent=2)

# ── http ──────────────────────────────────────────────────────────────────────

def riot_get(url):
    print(f'  GET ...{url.split("riotgames.com")[-1][:70]}')
    try:
        resp = requests.get(url, headers={'X-Riot-Token': API_KEY}, timeout=15)
        print(f'  -> {resp.status_code}')
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 401:
            raise ValueError('Invalid API key — regenerate at developer.riotgames.com')
        if resp.status_code == 403:
            raise ValueError('Forbidden — check your API key or endpoint access')
        if resp.status_code == 429:
            wait = int(resp.headers.get('Retry-After', 10))
            print(f'  Rate limited — waiting {wait}s')
            time.sleep(wait)
            r2 = requests.get(url, headers={'X-Riot-Token': API_KEY}, timeout=15)
            return r2.json() if r2.status_code == 200 else None
        return None
    except ValueError:
        raise
    except Exception as e:
        print(f'  Error: {e}')
        return None

# ── account ───────────────────────────────────────────────────────────────────

def get_puuid(name, tagline=''):
    """
    Accepts 'Name#TAG' as a single string, or name + tagline separately.
    Returns (puuid, display_name).
    """
    if '#' in name and not tagline:
        name, tagline = name.split('#', 1)

    tagline = tagline

    for routing in ['americas', 'europe', 'asia', 'sea']:
        d = riot_get(
            f'https://{routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{name}/{tagline}'
        )
        if d and d.get('puuid'):
            display = f'{d["gameName"]}#{d["tagLine"]}'
            return d['puuid'], display

    raise ValueError(f'Could not find account: {name}#{tagline}')

# ── match list ────────────────────────────────────────────────────────────────

def get_match_history(puuid, runes, region=None,start= 0,count= 20):
    region    = (region).upper()
    continent = CONTINENTAL.get(region, 'americas')

    ids = riot_get(
        f'https://{continent}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start={start}&count={count}'
    ) or []

    def fetch_one(mid):
        if is_cached(mid):
            m = load_cache(mid)
        else:
            m = riot_get(f'https://{continent}.api.riotgames.com/lol/match/v5/matches/{mid}')
            if m:
                save_cache(mid, m)
        if not m:
            return None

        info = m['info']
        me   = next((p for p in info['participants'] if p['puuid'] == puuid), None)
        if not me or info.get('queueId') not in QUEUE_NAMES:
            return None

        perks     = me.get('perks', {})
        styles    = perks.get('styles', [])
        pri       = styles[0] if styles else {}
        sub       = styles[1] if len(styles) > 1 else {}
        pri_sel   = pri.get('selections', [{}])
        dur       = max(info.get('gameDuration', 1), 1)
        kda       = (me['kills'] + me['assists']) / max(me['deaths'], 1)
        keystone  = pri_sel[0].get('perk') if pri_sel else None
        secondary = sub.get('style')
        row = {
            'match_id':     mid,
            'champion':     me.get('championName', '?'),
            'champion_icon': champ_icon_url(me.get('championName')),
            'position':     me.get('teamPosition') or me.get('individualPosition', ''),
            'queue':        QUEUE_NAMES.get(info.get('queueId'), 'Other'),
            'win':          me.get('win', False),
            'kills':        me.get('kills', 0),
            'deaths':       me.get('deaths', 0),
            'assists':      me.get('assists', 0),
            'kda':          round(kda, 2),
            'damage':       me.get('totalDamageDealtToChampions', 0),
            'cs':           me.get('totalMinionsKilled', 0),
            'duration_m':   dur // 60,
            'duration_s':   dur % 60,
            'patch':        info.get('gameVersion', '').rsplit('.', 1)[0],
            'level':        me.get('champLevel', 0),
            'spell_1':      spell_url(me.get('summoner1Id', 0)),
            'spell_2':      spell_url(me.get('summoner2Id', 0)),
            'keystone':     runes.get(keystone),
            'secondary':    runes.get(secondary),
            'item':         [me.get(f'item{i}') for i in range(6)],
        }
        row['item'].insert(3, me.get('item6'))
        row['item'].append(me.get('roleBoundItem'))
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_one, mid): mid for mid in ids}
        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)

    id_order = {mid: i for i, mid in enumerate(ids)}
    rows.sort(key=lambda r: id_order.get(r['match_id'], 0))
    return rows

# ── full match fetch + CSV build ──────────────────────────────────────────────

def get_match(match_id, region=None):
    region    = (region).upper()
    continent = CONTINENTAL.get(region, 'americas')

    if is_cached(match_id):
        match = load_cache(match_id)
    else:
        match = riot_get(f'https://{continent}.api.riotgames.com/lol/match/v5/matches/{match_id}')
        if match:
            save_cache(match_id, match)
    return match

def get_timeline(match_id, region=None):
    region    = (region).upper()
    continent = CONTINENTAL.get(region, 'americas')

    tl_key = f'{match_id}_timeline'
    if is_cached(tl_key):
        tl = load_cache(tl_key)
    else:
        tl = riot_get(f'https://{continent}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline')
        if tl:
            save_cache(tl_key, tl)

    return tl

def build_all_players_csv(match_id, region=None):
    match = get_match(match_id, region)
    if not match:
        raise ValueError(f'Could not fetch match {match_id}')

    info  = match.get("info", {})
    teams = {t["teamId"]: t for t in info.get("teams", [])}
    blue_bans = [b["championId"] for b in teams.get(100,{}).get("bans",[])]
    red_bans  = [b["championId"] for b in teams.get(200,{}).get("bans",[])]
    dur   = max(info.get("gameDuration", 1), 1)
    blue_horde = teams.get(100, {}).get('objectives', {}).get('horde', {})
    red_horde  = teams.get(200, {}).get('objectives', {}).get('horde', {})
    blue_horde_kills = blue_horde.get('kills', 0)
    red_horde_kills  = red_horde.get('kills', 0)

    meta = {
        "match_id":     match.get("metadata",{}).get("matchId","?"),
        "patch":        info.get("gameVersion","?").rsplit(".",1)[0],
        "queue":        info.get("gameMode","?"),
        "duration_min": round(dur/60,1),
        "duration_str": f"{dur//60}:{dur%60:02d}",
        "game_start":   info.get("gameStartTimestamp",""),
        "source":       "api",
    }

    participants = match['info']['participants']
    rows = []
    for p in participants:
        perks      = p.get("perks", {})
        styles     = perks.get("styles", [])
        pri        = styles[0] if styles else {}
        sub        = styles[1] if len(styles) > 1 else {}
        pri_sel    = pri.get("selections", [{}])
        rows.append({
            # identity
            "match_id":                  match_id,
            "puuid":                     p.get("puuid"),
            "summoner_name":             p.get("riotIdGameName"),
            "tagline":                   p.get("riotIdTagline"),
            "summoner_id":               p.get("summonerId"),
            "participant_id":            p.get("participantId"),
            "team_id":                   p.get("teamId"),
            "team":                      "blue" if p.get("teamId") == 100 else "red",
            "win":                       p.get("win"),
            # champion
            "champion_id":               p.get("championId"),
            "champion_name":             p.get("championName"),
            "champion_level":            p.get("champLevel"),
            "champion_xp":               p.get("champExperience"),
            "champion_transform":        p.get("championTransform"),
            # position
            "position":                  p.get("teamPosition"),
            "individual_position":       p.get("individualPosition"),
            "lane":                      p.get("lane"),
            "role":                      p.get("role"),
            # KDA
            "kills":                     p.get("kills"),
            "deaths":                    p.get("deaths"),
            "assists":                   p.get("assists"),
            'kda':            round((p['kills'] + p['assists']) / max(p['deaths'], 1), 2),
            "largest_killing_spree":     p.get("largestKillingSpree"),
            "largest_multikill":         p.get("largestMultiKill"),
            "killing_sprees":            p.get("killingSprees"),
            "double_kills":              p.get("doubleKills"),
            "triple_kills":              p.get("tripleKills"),
            "quadra_kills":              p.get("quadraKills"),
            "penta_kills":               p.get("pentaKills"),
            "unrealKills":               p.get("unrealKills"),
            "first_blood":               p.get("firstBloodKill"),
            "first_blood_assist":        p.get("firstBloodAssist"),
            "first_tower_kill":          p.get("firstTowerKill"),
            "first_tower_assist":        p.get("firstTowerAssist"),
            # runes
            "rune_primary_style":        pri.get("style"),
            "rune_sub_style":            sub.get("style"),
            "rune_keystone":             pri_sel[0].get("perk") if pri_sel else None,
            "rune_primary_slot1":        pri_sel[1].get("perk") if len(pri_sel) > 1 else None,
            "rune_primary_slot2":        pri_sel[2].get("perk") if len(pri_sel) > 2 else None,
            "rune_primary_slot3":        pri_sel[3].get("perk") if len(pri_sel) > 3 else None,
            "rune_stat_defense":         perks.get("statPerks", {}).get("defense"),
            "rune_stat_flex":            perks.get("statPerks", {}).get("flex"),
            "rune_stat_offense":         perks.get("statPerks", {}).get("offense"),
            # damage dealt
            "dmg_to_champions":          p.get("totalDamageDealtToChampions"),
            "dmg_physical_champ":        p.get("physicalDamageDealtToChampions"),
            "dmg_magic_champ":           p.get("magicDamageDealtToChampions"),
            "dmg_true_champ":            p.get("trueDamageDealtToChampions"),
            "dmg_total":                 p.get("totalDamageDealt"),
            "dmg_physical_total":        p.get("physicalDamageDealt"),
            "dmg_magic_total":           p.get("magicDamageDealt"),
            "dmg_true_total":            p.get("trueDamageDealt"),
            "largest_crit":              p.get("largestCriticalStrike"),
            "dmg_to_buildings":          p.get("damageDealtToBuildings"),
            "dmg_to_objectives":         p.get("damageDealtToObjectives"),
            "dmg_to_turrets":            p.get("damageDealtToTurrets"),
            # damage taken / mitigated
            "dmg_taken":                 p.get("totalDamageTaken"),
            "dmg_physical_taken":        p.get("physicalDamageTaken"),
            "dmg_magic_taken":           p.get("magicDamageTaken"),
            "dmg_true_taken":            p.get("trueDamageTaken"),
            "dmg_mitigated":             p.get("damageSelfMitigated"),
            "dmg_shielded_on_team":      p.get("totalDamageShieldedOnTeammates"),
            # healing
            "total_heal":                p.get("totalHeal"),
            "heals_on_teammates":        p.get("totalHealsOnTeammates"),
            "total_units_healed":        p.get("totalUnitsHealed"),
            # CS / economy
            "cs":                        p.get("totalMinionsKilled") + p.get("neutralMinionsKilled"),
            "cs_jungle":                 p.get("neutralMinionsKilled"),
            "cs_ally_jungle":            p.get("totalAllyJungleMinionsKilled"),
            "cs_enemy_jungle":           p.get("totalEnemyJungleMinionsKilled"),
            "gold_earned":               p.get("goldEarned"),
            "gold_spent":                p.get("goldSpent"),
            # vision
            "vision_score":              p.get("visionScore"),
            "wards_placed":              p.get("wardsPlaced"),
            "wards_killed":              p.get("wardsKilled"),
            "vision_wards_bought":       p.get("visionWardsBoughtInGame"),
            "sight_wards_bought":        p.get("sightWardsBoughtInGame"),
            "detector_wards_placed":     p.get("detectorWardsPlaced"),
            # objectives
            "turret_kills":              p.get("turretKills"),
            "turret_takedowns":          p.get("turretTakedowns"),
            "turrets_lost":              p.get("turretsLost"),
            "inhibitor_kills":           p.get("inhibitorKills"),
            "inhibitor_takedowns":       p.get("inhibitorTakedowns"),
            "inhibitors_lost":           p.get("inhibitorsLost"),
            "nexus_kills":               p.get("nexusKills"),
            "nexus_takedowns":           p.get("nexusTakedowns"),
            "nexus_lost":                p.get("nexusLost"),
            "baron_kills":               p.get("baronKills"),
            "dragon_kills":              p.get("dragonKills"),
            "objective_stolen":          p.get("objectivesStolen"),
            "objective_stolen_assists":  p.get("objectivesStolenAssists"),
            # CC
            "cc_score":                  p.get("totalTimeCCDealt"),
            "time_ccing_others":         p.get("timeCCingOthers"),
            # spells
            "spell1_casts":              p.get("spell1Casts"),
            "spell2_casts":              p.get("spell2Casts"),
            "spell3_casts":              p.get("spell3Casts"),
            "spell4_casts":              p.get("spell4Casts"),
            "summoner1_id":              p.get("summoner1Id"),
            "summoner1_casts":           p.get("summoner1Casts"),
            "summoner2_id":              p.get("summoner2Id"),
            "summoner2_casts":           p.get("summoner2Casts"),
            # items
            "item0": p.get("item0"), "item1": p.get("item1"),
            "item2": p.get("item2"), "item3": p.get("item3"),
            "item4": p.get("item4"), "item5": p.get("item5"),
            "item6": p.get("item6"),
            "mission": p.get("roleBoundItem"),
            # time stats
            "time_spent_dead":           p.get("totalTimeSpentDead"),
            "longest_time_alive":        p.get("longestTimeSpentLiving"),
            "earliest_dragon_percent":   p.get("earliestDragonTakedown"),
            # pings
            "all_in_pings":              p.get("allInPings"),
            "assist_me_pings":           p.get("assistMePings"),
            "bait_pings":                p.get("baitPings"),
            "command_pings":             p.get("commandPings"),
            "danger_pings":              p.get("dangerPings"),
            "enemy_missing_pings":       p.get("enemyMissingPings"),
            "get_back_pings":            p.get("getBackPings"),
            "hold_pings":                p.get("holdPings"),
            "need_vision_pings":         p.get("needVisionPings"),
            "on_my_way_pings":           p.get("onMyWayPings"),
            "push_pings":                p.get("pushPings"),
            "retreat_pings":             p.get("retreatPings"),
            "vision_cleared_pings":      p.get("visionClearedPings"),
            # performance flags
            "champ_solo_kills":          p.get("challenges", {}).get("soloKills"),
            "kill_participation":        p.get("challenges", {}).get("killParticipation"),
            "kda_challenge":             p.get("challenges", {}).get("kda"),
            "damage_per_death":          p.get("challenges", {}).get("damagePerDeath"),
            "gold_per_damage":           p.get("challenges", {}).get("goldPerDamage"),
            "rift_herald_takedowns":     p.get("challenges", {}).get("riftHeraldTakedowns"),
            "void_monster_kill":         p.get("challenges", {}).get("voidMonsterKill"),
            "max_cs_advantage_lane":     p.get("challenges", {}).get("maxCsAdvantageOnLaneOpponent"),
            "max_level_lead_lane":       p.get("challenges", {}).get("maxLevelLeadLaneOpponent"),
            "turret_plates_taken":       p.get("challenges", {}).get("turretPlatesTaken"),
            "saving_ally":               p.get("challenges", {}).get("saveAllyFromDeath"),
        })
        team_stats = {}
    for tid, tlabel in [(100,"blue"),(200,"red")]:
        tp  = [p for p in rows if p["team"]==tlabel]
        bans= blue_bans if tlabel=="blue" else red_bans
        map = champion_map()
        result = [champ_id_icon(i,map) for i in bans]
        icon,ban = zip(*result)
        team_stats[tlabel] = {
            "win":         bool(teams.get(tid,{}).get("win",False)),
            "kills":       sum(p["kills"]        for p in tp),
            "deaths":      sum(p["deaths"]       for p in tp),
            "assists":     sum(p["assists"]      for p in tp),
            "gold":        sum(p["gold_earned"]  for p in tp),
            "damage":      sum(p["dmg_to_champions"]    for p in tp),
            "barons":      sum(p['baron_kills'] for p in tp),
            "dragons":     sum(p['dragon_kills'] for p in tp),
            "towers":      sum(p['turret_kills'] for p in tp),
            "inhibitors":  sum(p['inhibitor_kills'] for p in tp),
            "voidgrubs":   blue_horde_kills if tlabel == "blue" else red_horde_kills,
            "icons" :      icon,
            "bans"  :      ban,
        }
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = os.path.join(UPLOAD_DIR, f'{match_id}_all_players.csv')
    pd.DataFrame(rows).to_csv(path, index=False)
    return path,{'meta': meta, 'team_stats' : team_stats}

def build_timeline(match_id, region=None):
    tl = get_timeline(match_id, region)
    if not tl:
        raise ValueError(f'Could not fetch timeline for {match_id}')

    events = []
    for frame in tl['info']['frames']:
        timestamp_min = frame['timestamp'] // 60000
        for event in frame['events']:
            e_type = event.get('type', '')
            item_id = str(event.get('itemId'))
            if e_type not in ('CHAMPION_KILL', 'BUILDING_KILL', 'ELITE_MONSTER_KILL', 'ITEM_PURCHASED','ITEM_SOLD') or item_id not in items:
                continue
            events.append({
                'timestamp_min': timestamp_min,
                'timestamp_ms':  event.get('timestamp'),
                'type':          e_type,
                'killer_id':     str(event.get('killerId') or event.get('creatorId') or event.get('participantId')),
                'victim_id':     str(event.get('victimId')),
                'assisting_ids': str(event.get('assistingParticipantIds', [])),
                'item_id':       item_id,
                'item_url':      item_url(item_id),
                'item_name':     items[item_id],
                'building_type': event.get('buildingType'),
                'monster_type':  event.get('monsterType'),
                'position_x':    event.get('position', {}).get('x'),
                'position_y':    event.get('position', {}).get('y'),
            })
    print(events)
    return events

def champion_map():
    c = requests.get(f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/data/en_US/champion.json', timeout= 5)
    m = c.json()
    map={}
    for i in m['data']:
        map[m['data'][i]['key']] = m['data'][i]['id']
    return map

def filter_item(item):
    tags = item.get("tags", [])

    if "Consumable" in tags:
        return False
    if "Trinket" in tags:
        return False

    if not item.get("gold", {}).get("purchasable", True):
        return False

    return True

def item_map():
    data = requests.get(
        f"https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/data/en_US/item.json"
    ).json()

    return {
        item_id: item["name"]
        for item_id, item in data["data"].items()
        if filter_item(item)
    }

def item_url(item_id):
    if not item_id or int(item_id) == 0:
        return None
    return f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/img/item/{int(item_id)}.png'

def champ_id_icon(id, map):
    if id == -1:
        return f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/img/profileicon/29.png','None'
    else:
        champ = map[str(id)]
        url = champ_icon_url(champ)
        return url,champ

def champ_icon_url(champ_name):
    name = (champ_name or 'Ahri').replace(' ', '').replace("'", '').replace('.', '')
    return f'https://ddragon.leagueoflegends.com/cdn/{get_ddragon_version()}/img/champion/{name}.png'

def spell_url(id):
    spell = SUMMONER_SPELLS.get(id)
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
    
runes = get_rune_paths()  
items = item_map()

def load_csvs(all_players_path):
    df_players  = pd.read_csv(all_players_path)
    return df_players

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

def build_analysis(all_players_path, summoner_name=None):
    df_players = load_csvs(all_players_path)
    new_cols = pd.DataFrame({
    'key_icon': df_players['rune_keystone'].map(runes),
    'sub_icon': df_players['rune_sub_style'].map(runes),
    'spell_1': df_players['summoner1_id'].apply(spell_url),
    'spell_2': df_players['summoner2_id'].apply(spell_url),
    'champion_icon': df_players['champion_name'].apply(champ_icon_url)
    })
    df_players = pd.concat([df_players, new_cols], axis=1)
    return {
        'scoreboard':   get_scoreboard(df_players),
        'player_stats': None,
        'charts': {
            'damage': get_chart(df_players, 'dmg_to_champions'),
            'gold':   get_chart(df_players, 'gold_earned'),
            'cs':     get_chart(df_players, 'cs'),
            'kda':    get_chart(df_players, 'kda'),
            'vision': get_chart(df_players, 'vision_score'),
        }
    }
