import datetime
import itertools
import sqlite3
import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson
import streamlit as st

# -------------------------------------------------------------------
# 頁面基本設定
# -------------------------------------------------------------------
st.set_page_config(
    page_title="⚡ ODD-HUNTER ｜ 全球體育全玩法賠率獵人 AI x 實體串關決策中心",
    layout="wide",
)

# 隊伍名稱中譯字典 (全球熱門聯賽擴充)
TEAM_NAME_MAP = {
    # 足球 - 英超 (EPL)
    "Arsenal": "阿仙奴", "Leeds United": "列斯聯", "Chelsea": "車路士",
    "Bournemouth": "般尼茅夫", "Manchester United": "曼聯", "Tottenham Hotspur": "熱刺",
    "Liverpool": "利物浦", "Manchester City": "曼城", "Aston Villa": "阿士東維拉",
    # 足球 - 西甲 (La Liga)
    "Real Madrid": "皇家馬德里", "Barcelona": "巴塞隆拿", "Atletico Madrid": "馬德里體育會",
    # 足球 - 義甲 (Serie A)
    "Inter": "國際米蘭", "AC Milan": "AC米蘭", "Juventus": "祖雲達斯", "Napoli": "拿玻里",
    # 足球 - 德甲 (Bundesliga)
    "Bayern Munich": "拜仁慕尼黑", "Borussia Dortmund": "多蒙特", "Bayer Leverkusen": "利華古遜",
    # 籃球 - NBA
    "Los Angeles Lakers": "洛杉磯湖人", "Golden State Warriors": "金州勇士",
    "Boston Celtics": "波士頓塞爾特人", "Miami Heat": "邁阿密熱火",
    "Brooklyn Nets": "布魯克林網", "Phoenix Suns": "菲尼克斯太陽",
    "Milwaukee Bucks": "密爾沃基公鹿", "Denver Nuggets": "丹佛金塊",
    # 棒球 - MLB
    "Los Angeles Dodgers": "洛杉磯道奇", "New York Yankees": "紐約洋基",
    "Atlanta Braves": "亞特蘭大勇士", "Houston Astros": "休士頓太空人",
    "San Diego Padres": "聖地牙哥教士", "Boston Red Sox": "波士頓紅襪",
}

# 全球體育項目與所有主流聯賽字典
SPORT_CATEGORIES = {
    "⚽ 足球 (Soccer)": {
        "英格蘭超級聯賽 (EPL)": "soccer_epl",
        "西班牙甲組聯賽 (La Liga)": "soccer_spain_la_liga",
        "義大利甲組聯賽 (Serie A)": "soccer_italy_serie_a",
        "德國甲組聯賽 (Bundesliga)": "soccer_germany_bundesliga",
        "法國甲組聯賽 (Ligue 1)": "soccer_france_ligue_one",
        "歐洲冠軍聯賽 (UEFA Champions League)": "soccer_uefa_champs_league",
        "歐洲聯賽 (UEFA Europa League)": "soccer_uefa_europa_league",
        "美國職業足球大聯盟 (MLS)": "soccer_usa_mls",
    },
    "🏀 籃球 (Basketball)": {
        "美國職業籃球 (NBA)": "basketball_nba",
        "美國女子職業籃球 (WNBA)": "basketball_wnba",
        "歐洲籃球聯賽 (EuroLeague)": "basketball_euroleague",
        "澳洲職業籃球 (NBL)": "basketball_nbl",
    },
    "⚾ 棒球 (Baseball)": {
        "美國職棒大聯盟 (MLB)": "baseball_mlb",
        "日本職棒 (NPB)": "baseball_npb",
        "韓國職棒 (KBO)": "baseball_kbo",
    },
    "🏒 冰球 (Ice Hockey)": {
        "北美冰球聯賽 (NHL)": "icehockey_nhl",
        "瑞典冰球超級聯賽 (SHL)": "icehockey_sweden_shl",
    },
    "🏈 美式足球 (American Football)": {
        "美國職業橄欖球聯賽 (NFL)": "americanfootball_nfl",
        "美國大學橄欖球 (NCAAF)": "americanfootball_ncaaf",
    },
    "🎾 網球 (Tennis)": {
        "ATP 男子網球巡迴賽": "tennis_atp_aus_open",
        "WTA 女子網球巡迴賽": "tennis_wta_aus_open",
    },
    "🥊 綜合格鬥 (MMA)": {
        "終極格鬥冠軍賽 (UFC)": "mma_mixed_martial_arts",
    }
}


# -------------------------------------------------------------------
# 🔒 密碼驗證模組
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# 📡 數據解析：全體育多玩法與白話說明
# -------------------------------------------------------------------
@st.cache_data(ttl=600)
def fetch_all_markets(api_key, sport_key):
    if not api_key:
        return None, "請設定 API Key！"

    # 請求包含 h2h (不讓分/獨贏), spreads (讓分), totals (大小分), h2h_h1 (上半場獨贏), spreads_h1 (上半場讓分), totals_h1 (上半場大小)
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=eu&markets=h2h,spreads,totals,h2h_h1,spreads_h1,totals_h1&oddsFormat=decimal"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return (
                None,
                f"API 連線失敗 (代碼 {response.status_code}): {response.text}",
            )
        data = response.json()
    except Exception as e:
        return None, f"連線異常: {str(e)}"

    if not data:
        return None, "目前該聯賽暫無即時開盤數據（可能是休賽期或今日無賽事）。"

    all_options = []

    for match in data:
        home_en = match.get("home_team", "")
        away_en = match.get("away_team", "")
        home_cn = TEAM_NAME_MAP.get(home_en, home_en)
        away_cn = TEAM_NAME_MAP.get(away_en, away_en)
        match_title = f"{home_cn} (主) vs {away_cn} (客)"

        if match.get("bookmakers"):
            bookmaker = match["bookmakers"][0]

            for market in bookmaker.get("markets", []):
                m_key = market["key"]

                # 1. 全場獨贏盤 (H2H)
                if m_key == "h2h":
                    for outcome in market["outcomes"]:
                        team_cn = TEAM_NAME_MAP.get(outcome["name"], outcome["name"])
                        if outcome["name"] == "Draw":
                            pick_name = "全場和局"
                            p_win = 0.25
                        else:
                            is_home = outcome["name"] == home_en
                            pick_name = f"{team_cn} 全場不讓分勝 ({'主場' if is_home else '客場'})"
                            p_win = 0.48 if is_home else 0.35

                        odds = outcome["price"]
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "type": "不讓分 (獨贏)",
                            "pick": pick_name,
                            "detail": f"賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                # 2. 全場讓分盤 (Spreads)
                elif m_key == "spreads":
                    for outcome in market["outcomes"]:
                        team_cn = TEAM_NAME_MAP.get(outcome["name"], outcome["name"])
                        point = outcome.get("point", 0)
                        point_str = f"+{point}" if point > 0 else str(point)
                        is_home = outcome["name"] == home_en
                        pick_name = f"{team_cn} 全場讓分 ({point_str}) ({'主場' if is_home else '客場'})"

                        odds = outcome["price"]
                        p_win = 0.50
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "type": "讓分盤",
                            "pick": pick_name,
                            "detail": f"盤口 ({point_str}) @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                # 3. 全場大小分 (Totals)
                elif m_key == "totals":
                    for outcome in market["outcomes"]:
                        name_cn = "大分" if outcome["name"].lower() == "over" else "小分"
                        point = outcome.get("point", 0)
                        pick_name = f"全場大小分：{name_cn} ({point} 球/分)"

                        odds = outcome["price"]
                        p_win = 0.50
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "type": "大小分",
                            "pick": pick_name,
                            "detail": f"{point} {name_cn} @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                # 4. 上半場不讓分 (H2H H1)
                elif m_key == "h2h_h1":
                    for outcome in market["outcomes"]:
                        team_cn = TEAM_NAME_MAP.get(outcome["name"], outcome["name"])
                        if outcome["name"] == "Draw":
                            pick_name = "上半場和局"
                            p_win = 0.30
                        else:
                            is_home = outcome["name"] == home_en
                            pick_name = f"{team_cn} 上半場不讓分勝 ({'主場' if is_home else '客場'})"
                            p_win = 0.45 if is_home else 0.35

                        odds = outcome["price"]
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "type": "上半場不讓分",
                            "pick": pick_name,
                            "detail": f"賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                # 5. 上半場讓分 (Spreads H1)
                elif m_key == "spreads_h1":
                    for outcome in market["outcomes"]:
                        team_cn = TEAM_NAME_MAP.get(outcome["name"], outcome["name"])
                        point = outcome.get("point", 0)
                        point_str = f"+{point}" if point > 0 else str(point)
                        is_home = outcome["name"] == home_en
                        pick_name = f"{team_cn} 上半場讓分 ({point_str}) ({'主場' if is_home else '客場'})"

                        odds = outcome["price"]
                        p_win = 0.50
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "type": "上半場讓分",
                            "pick": pick_name,
                            "detail": f"盤口 ({point_str}) @ 賠率 {odds}",
                            "odds": odds,
                            "win_prob": p_win,
                            "ev": ev,
                        })

                # 6. 上半場大小分 (Totals H1)
                elif m_key == "totals_h1":
                    for outcome in market["outcomes"]:
                        name_cn = "大分" if outcome["name"].lower() == "over" else "小分"
                        point = outcome.get("point", 0)
                        pick_name = f"上半場大小分：{name_cn} ({point} 球/分)"

                        odds = outcome["price"]
                        p_win = 0.50
                        ev = round((p_win * odds) - 1, 3)

                        all_options.append({
                            "match": match_title,
                            "type": "上半場大小分",
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

    st.title("⚡ ODD-HUNTER ｜ 全球體育全玩法賠率獵人 AI x 實體串關決策中心")
    st.caption(
        "全體育聯賽與全玩法選擇 ｜ 直白盤口細節標示 ｜ 擬真運彩串關投注單試算"
    )

    api_key = "c0d0209bb272cde2bb4464ce0a93ea56"

    # 1. 側邊欄：多層選單（先選運動，再選聯賽，最後勾選玩法）
    st.sidebar.header("⚙️ 賽事與玩法選擇")
    
    selected_category = st.sidebar.selectbox(
        "1. 選擇體育運動項目",
        list(SPORT_CATEGORIES.keys())
    )

    available_leagues = SPORT_CATEGORIES[selected_category]
    selected_league_name = st.sidebar.selectbox(
        "2. 選擇特定職業聯賽",
        list(available_leagues.keys())
    )
    selected_sport_key = available_leagues[selected_league_name]

    ALL_MARKET_OPTIONS = [
        "不讓分 (獨贏)", "讓分盤", "大小分",
        "上半場不讓分", "上半場讓分", "上半場大小分"
    ]

    market_types_selected = st.sidebar.multiselect(
        "3. 選擇顯示下注玩法",
        ALL_MARKET_OPTIONS,
        default=["不讓分 (獨贏)", "讓分盤", "大小分"],
    )

    budget = st.sidebar.number_input(
        "預計單張投注預算 ($)", min_value=10, value=100, step=10
    )

    if st.sidebar.button("🔄 手動刷新盤口數據"):
        st.cache_data.clear()
        st.rerun()

    # 2. 載入盤口資料
    with st.spinner(f"📡 正在抓取 【{selected_league_name}】 全盤口與玩法數據中..."):
        df_all, error_msg = fetch_all_markets(api_key, selected_sport_key)

    if error_msg:
        st.error(f"❌ 數據載入失敗：{error_msg}")
    else:
        tab1, tab2 = st.tabs(
            ["📋 自由勾選盤口 (全玩法總覽)", "🎯 AI 智能精選推薦單"]
        )

        # ---------------------------------------------------------------
        # TAB 1: 自由勾選全盤口
        # ---------------------------------------------------------------
        with tab1:
            st.subheader(f"🌐 【{selected_league_name}】 即時盤口與全玩法清單")
            st.info(
                "💡 **說明**：請在下方列表中勾選你想串關的選項（可跨場次、跨全場/半場玩法），下方會自動為你產出彩券試算！"
            )

            if not market_types_selected:
                st.warning("⚠️ 請在左側選單勾選至少一種玩法！")
            elif df_all is None or df_all.empty:
                st.warning(f"目前【{selected_league_name}】暫無即時開盤賽事，請切換其他聯賽試試看。")
            else:
                matches = df_all["match"].unique()
                selected_items = []

                for m in matches:
                    with st.expander(f"🏆 賽事：{m}", expanded=True):
                        sub_df = df_all[df_all["match"] == m]

                        num_cols = min(len(market_types_selected), 3)
                        cols = st.columns(num_cols)

                        for idx_m, m_type in enumerate(market_types_selected):
                            col_target = cols[idx_m % num_cols]
                            with col_target:
                                st.markdown(f"**【{m_type}】**")
                                type_df = sub_df[sub_df["type"] == m_type]

                                if type_df.empty:
                                    st.caption("無可提供盤口")
                                else:
                                    for idx, row in type_df.iterrows():
                                        ev_color = "🟢" if row["ev"] > 0 else "⚪"
                                        label = (
                                            f"{row['pick']} | 賠率"
                                            f" {row['odds']} ({ev_color} EV:"
                                            f" {row['ev']})"
                                        )
                                        if st.checkbox(label, key=f"chk_{idx}"):
                                            selected_items.append(row)

                # 擬真彩券試算
                st.markdown("---")
                st.subheader("🧾 你的自選串關投注單")

                if len(selected_items) >= 1:
                    total_odds = 1.0
                    total_prob = 1.0

                    st.write(f"已勾選 **{len(selected_items)}** 個投注選項：")

                    for item in selected_items:
                        total_odds *= item["odds"]
                        total_prob *= item["win_prob"]
                        st.success(
                            f"📌 **{item['match']}** ➔ **{item['pick']}**"
                            f" （{item['detail']}）"
                        )

                    total_odds = round(total_odds, 2)
                    payout = round(budget * total_odds, 2)
                    combo_ev = round((total_prob * total_odds) - 1, 3)

                    st.markdown(
                        f"""
                    <div style="background-color:#1e293b; padding:20px; border-radius:10px; border:2px solid #3b82f6;">
                        <h3 style="color:#60a5fa; margin-top:0;">🎟️ 串關彩券試算結果 ({len(selected_items)} 串 1)</h3>
                        <p style="font-size:18px;">💵 <b>投注預算</b>：$ {budget} 元</p>
                        <p style="font-size:18px;">⚡ <b>組合總賠率</b>：<span style="color:#f59e0b; font-size:22px; font-weight:bold;">{total_odds} 倍</span></p>
                        <p style="font-size:18px;">🎯 <b>預估全過過關率</b>：{total_prob:.1%}</p>
                        <p style="font-size:18px;">📈 <b>整體期望值 (EV)</b>：{combo_ev}</p>
                        <hr>
                        <h2 style="color:#10b981; margin-bottom:0;">💰 預計最高派彩金額：$ {payout} 元</h2>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning(
                        "💡 目前尚未勾選任何選項，請在上方賽事列表中勾選 1 個以上的投注項目！"
                    )

        # ---------------------------------------------------------------
        # TAB 2: AI 智能精選推薦單
        # ---------------------------------------------------------------
        with tab2:
            st.subheader("🔥 AI 自動篩選高 EV 最佳買法推薦")

            if df_all is None or df_all.empty:
                st.warning("目前無數據可供推薦。")
            else:
                positive_ev_df = df_all[df_all["ev"] > 0]

                if not positive_ev_df.empty:
                    st.write("系統自動為你篩選出**期望值 > 0** 的最優質投注組合：")

                    for match_name in positive_ev_df["match"].unique():
                        match_df = positive_ev_df[
                            positive_ev_df["match"] == match_name
                        ]

                        with st.container():
                            st.markdown(f"#### 🏆 {match_name}")
                            for _, r in match_df.iterrows():
                                st.info(
                                    f"👉 **建議買法**：【**{r['pick']}**】\n"
                                    f"* **盤口玩法**：{r['type']} |"
                                    f" **細節**：`{r['detail']}`\n"
                                    f"* **模型 EV (期望值)**：`+{r['ev']}` （具備長期投注價值）\n"
                                    f"* **實戰下注指引**：開啟運彩投注 App ➔ 找到"
                                    f" `{match_name}` ➔ 選擇"
                                    f" `{r['type']}` ➔ 勾選"
                                    f" **`{r['pick']}`**"
                                )
                            st.markdown("---")
                else:
                    st.warning("目前實時盤口中暫無符合正期望值 (EV > 0) 的選項。")
