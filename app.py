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
    page_title="⚡ ODD-HUNTER ｜ 穩健過關率 AI x 組合防禦決策中心",
    layout="wide",
)

TEAM_NAME_MAP = {
    # 足球 - 英超 (EPL)
    "Arsenal": "阿仙奴", "Leeds United": "列斯聯", "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫", "Manchester United": "曼聯", "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦", "Manchester City": "曼城", "Aston Villa": "阿士東維拉",
    "Newcastle United": "紐卡素", "West Ham United": "韋斯咸", "Fulham": "富咸",
    "Hull City": "侯城", "Ipswich Town": "葉士域治", "Brighton": "白禮頓",
    "Crystal Palace": "水晶宮",
    # 足球 - 西甲 (La Liga)
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆拿", "Atletico Madrid": "馬德里體育會",
    # 籃球 - NBA
    "Los Angeles Lakers": "洛杉磯湖人", "Golden State Warriors": "金州勇士",
    "Boston Celtics": "波士頓塞爾特人", "Miami Heat": "邁阿密熱火",
    "Brooklyn Nets": "布魯克林網", "Phoenix Suns": "菲尼克斯太陽",
    # 棒球 - MLB
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

ALL_MARKET_OPTIONS = ["不讓分 (獨贏)", "讓分盤", "大小分"]


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
        home_cn = TEAM_NAME_MAP.get(home_en, home_en)
        away_cn = TEAM_NAME_MAP.get(away_en, away_en)

        match_title = f"{home_cn} {home_en} (主) vs {away_cn} {away_en} (客)"

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
                            "detail": f"盤口 ({point_str}) @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                elif m_key == "totals":
                    for outcome in market["outcomes"]:
                        name_en = outcome["name"]
                        name_cn = "大分 Over" if name_en.lower() == "over" else "小分 Under"
                        point = outcome.get("point", 0)
                        pick_name = f"全場大小分：{name_cn} ({point})"
                        odds = outcome["price"]
                        p_win = round(1 / odds, 4) if odds > 0 else 0.5
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "match_time": time_str,
                            "type": "大小分",
                            "pick": pick_name,
                            "detail": f"{point} {name_cn} @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

    return pd.DataFrame(all_options), None


# -------------------------------------------------------------------
# 🚀 主程式頁面
# -------------------------------------------------------------------
if check_password("900812"):
    st.sidebar.success("✅ 權限驗證通過")
    if st.sidebar.button("🔒 登出系統"):
        st.session_state["password_correct"] = False
        st.rerun()

    st.title("⚡ ODD-HUNTER ｜ 穩健過關率 AI x 組合防禦決策中心")
    st.caption("高勝率篩選 ｜ 中英文雙語隊名 ｜ 賽事時間標示 ｜ 2 串 1 容錯組合")

    api_key = "c0d0209bb272cde2bb4464ce0a93ea56"

    st.sidebar.header("⚙️ 賽事與策略設定")
    selected_category = st.sidebar.selectbox("1. 選擇體育項目", list(SPORT_CATEGORIES.keys()))
    available_leagues = SPORT_CATEGORIES[selected_category]
    selected_league_name = st.sidebar.selectbox("2. 選擇特定聯賽", list(available_leagues.keys()))
    selected_sport_key = available_leagues[selected_league_name]

    user_selected_markets = st.sidebar.multiselect(
        "3. 選擇顯示玩法 (未選則全部顯示)",
        ALL_MARKET_OPTIONS,
        default=[]
    )

    display_markets = user_selected_markets if user_selected_markets else ALL_MARKET_OPTIONS

    budget = st.sidebar.number_input("總投注資金 ($)", min_value=10, value=100, step=10)

    if st.sidebar.button("🔄 刷新盤口數據"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner(f"📡 抓取 【{selected_league_name}】 數據中..."):
        df_all, error_msg = fetch_all_markets(api_key, selected_sport_key)

    if error_msg:
        st.error(f"❌ 數據載入失敗：{error_msg}")
    else:
        tab1, tab2 = st.tabs(["🛡️ 容錯串關試算 (雙語 & 賽程時間)", "🔥 AI 精選高勝率最穩組合"])

        with tab1:
            st.subheader(f"🌐 【{selected_league_name}】 即時賽事與盤口清單")
            
            if not user_selected_markets:
                st.caption("ℹ️ 目前選單未勾選特定玩法，已自動顯示**所有玩法**（不讓分 / 讓分盤 / 大小分）。")
            else:
                st.caption(f"ℹ️ 已根據選擇動態過濾，僅顯示：**{', '.join(display_markets)}**")

            if df_all is None or df_all.empty:
                st.warning("目前無即時開盤賽事。")
            else:
                matches = df_all["match"].unique()
                selected_items = []

                for m in matches:
                    sub_df = df_all[df_all["match"] == m]
                    m_time = sub_df["match_time"].iloc[0]

                    with st.expander(f"🏆 賽事：{m} ｜ ⏰ 開賽時間：{m_time}", expanded=True):
                        num_cols = len(display_markets)
                        cols = st.columns(num_cols)

                        for col, m_type in zip(cols, display_markets):
                            with col:
