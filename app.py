import datetime
import itertools
import sqlite3
import numpy as np
import pandas as pd
import requests
import streamlit as st

# -------------------------------------------------------------------
# 頁面基本設定
# -------------------------------------------------------------------
st.set_page_config(
    page_title="⚡ ODD-HUNTER ｜ 全平台響應式 AI 體育決策中心",
    layout="wide",
    initial_sidebar_state="expanded"
)

TEAM_NAME_MAP = {
    "Arsenal": "阿仙奴", "Leeds United": "列斯聯", "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫", "Manchester United": "曼聯", "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦", "Manchester City": "曼城", "Aston Villa": "阿士東維拉",
    "Newcastle United": "紐卡素", "West Ham United": "韋斯咸", "Fulham": "富咸",
    "Hull City": "侯城", "Ipswich Town": "葉士域治", "Brighton": "白禮頓",
    "Crystal Palace": "水晶宮", "Brentford": "賓福特", "Everton": "愛華頓",
    "Coventry City": "高雲地利", "Detroit Pistons": "底特律活塞", "Boston Celtics": "波士頓塞爾特人",
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆拿", "Atletico Madrid": "馬德里體育會",
    "Los Angeles Lakers": "洛杉磯湖人", "Golden State Warriors": "金州勇士",
    "Miami Heat": "邁阿密熱火", "Brooklyn Nets": "布魯克林網", "Phoenix Suns": "菲尼克斯太陽",
    "Los Angeles Dodgers": "洛杉磯道奇", "New York Yankees": "紐約洋基",
    "Atlanta Braves": "亞特蘭大勇士", "Houston Astros": "休士頓太空人",
}

SPORT_CATEGORIES = {
    "⚽ 足球 (Soccer)": {
        "英格蘭超級聯賽 (EPL)": "soccer_epl",
        "西班牙甲組聯賽 (La Liga)": "soccer_spain_la_liga",
        "義大利甲組聯賽 (Serie A)": "soccer_italy_serie_a",
        "德國甲組聯賽 (Bundesliga)": "soccer_germany_bundesliga",
        "歐洲冠軍聯賽 (UCL)": "soccer_uefa_champs_league",
    },
    "🏀 籃球 (Basketball)": {
        "美國職業籃球 (NBA)": "basketball_nba",
        "歐洲籃球聯賽 (EuroLeague)": "basketball_euroleague",
    },
    "⚾ 棒球 (Baseball)": {
        "美國職棒大聯盟 (MLB)": "baseball_mlb",
    },
    "🏒 冰球 (Ice Hockey)": {
        "北美冰球聯賽 (NHL)": "icehockey_nhl",
    },
    "🏈 美式足球 (NFL)": {
        "美國職業橄欖球聯賽 (NFL)": "americanfootball_nfl",
    },
}

DEFAULT_MARKETS = ["不讓分 (獨贏)", "讓分盤", "大小分"]

SOCCER_MARKETS = [
    "全場三合一 (獨贏/讓分/大小)", "不讓分 (獨贏)", "讓分盤", "大小分",
    "波膽 (正確比數)", "波膽組合", "全場入球總數", "入球單/雙數",
    "半場/全場賽果", "球隊入球數", "最先入球球隊", "角球數賠率"
]

BASKETBALL_MARKETS = [
    "全場三合一 (獨贏/讓分/大小)", "不讓分 (獨贏)", "讓分盤", "大小分",
    "球隊取勝分差", "總得分單/雙數", "球隊得分上下盤 (大小)", "半全場賽果"
]


def check_password(target_password="900812"):
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 系統存取權限驗證")
        st.write("本系統為內部 AI 體育預測模型，請輸入授權密碼以繼續：")
        password_input = st.text_input("請輸入訪問密碼", type="password")

        if st.button("確認登入", use_container_width=True):
            if str(password_input) == str(target_password):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤！請重新輸入。")
    return False


@st.cache_data(ttl=600)
def fetch_all_markets(api_key, sport_key):
    if not api_key:
        return None, "請設定 API Key！"

    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None, f"API 連線失敗 (代碼 {response.status_code}): {response.text}"
        data = response.json()
    except Exception as e:
        return None, f"連線異常: {str(e)}"

    if not data:
        return None, "目前該聯賽暫無即時開盤數據。"

    all_options = []

    for match in data:
        commence_utc = match.get("commence_time", "")
        if commence_utc:
            dt_utc = datetime.datetime.fromisoformat(commence_utc.replace("Z", "+00:00"))
            dt_local = dt_utc + datetime.timedelta(hours=8)
            time_str = dt_local.strftime("%Y-%m-%d %H:%M")
        else:
            time_str = "時間未定"

        home_en = match.get("home_team", "")
        away_en = match.get("away_team", "")
        
        home_cn = TEAM_NAME_MAP.get(home_en, "")
        away_cn = TEAM_NAME_MAP.get(away_en, "")
        
        home_disp = f"{home_cn} {home_en}".strip()
        away_disp = f"{away_cn} {away_en}".strip()

        match_title = f"{home_disp} (主) vs {away_disp} (客)"

        if match.get("bookmakers"):
            bookmaker = match["bookmakers"][0]

            for market in bookmaker.get("markets", []):
                m_key = market["key"]

                if m_key == "h2h":
                    for outcome in market["outcomes"]:
                        team_en = outcome["name"]
                        team_cn = TEAM_NAME_MAP.get(team_en, team_en)
                        odds = outcome["price"]
                        p_win = round(1 / odds, 4) if odds > 0 else 0.5
                        
                        if team_en == "Draw":
                            pick_name = "全場和局 (Draw)"
                        else:
                            is_home = team_en == home_en
                            pick_name = f"{team_cn} {team_en} 不讓分勝 ({'主' if is_home else '客'})"

                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "match_time": time_str,
                            "type": "不讓分 (獨贏)",
                            "pick": pick_name,
                            "detail": f"賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                elif m_key == "spreads":
                    for outcome in market["outcomes"]:
                        team_en = outcome["name"]
                        team_cn = TEAM_NAME_MAP.get(team_en, team_en)
                        point = outcome.get("point", 0)
                        point_str = f"+{point}" if point > 0 else str(point)
                        pick_name = f"{team_cn} {team_en} 讓分 ({point_str})"
                        odds = outcome["price"]
                        p_win = round(1 / odds, 4) if odds > 0 else 0.5
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "match_time": time_str,
                            "type": "讓分盤",
                            "pick": pick_name,
                            "detail": f"盤口 ({point_
